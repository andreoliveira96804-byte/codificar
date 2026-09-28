"""Backtest aproximado (dados EOD do DoltHub) da venda de volatilidade em resultados.

Uso:
    python -m backtest_earnings.executar --inicio 2022-01-01 --saida resultados
    python -m backtest_earnings.executar --simbolos AAPL,MSFT,AMZN   # teste rápido

Gera `<saida>/trades.csv` com uma linha por evento: filtros na entrada,
cotações de entrada/saída de cada perna e os retornos do straddle e do calendar.
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .dolthub import DoltHub, ErroConsulta, LimiteDeLinhas, lista_sql
from .estrategias import cotar, escolher_contratos, retorno_calendar, retorno_straddle
from .eventos import carregar_eventos, definir_datas, dias_com_dados
from .indicadores import calcular_filtros

JANELA = 30                  # pregões usados na RV30 e no volume médio
PREGOES_ANTES = JANELA + 5   # quantos pregões de preço baixar antes da entrada
FAIXA_DELTA = (0.2, 0.8)     # na entrada, só baixamos opções "perto do dinheiro"
COLUNAS_CADEIA = ["date", "act_symbol", "expiration", "strike", "call_put", "bid", "ask", "vol"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


DATAS = {"date", "expiration"}
TEXTOS = {"act_symbol", "call_put"}


def para_tabela(linhas, colunas):
    """Converte linhas da API (tudo em texto) numa tabela com datas e números."""
    df = pd.DataFrame(linhas, columns=colunas)
    for coluna in colunas:
        if coluna in DATAS:
            df[coluna] = pd.to_datetime(df[coluna])
        elif coluna not in TEXTOS:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    return df


def executar_tarefas(cliente, db, tarefas, montar_sql, colunas, descricao):
    """Roda (data, lote) em paralelo e junta tudo numa tabela.

    Se um lote passar de 1.000 linhas, divide ao meio. Cada resposta já vira
    tabela ao chegar, para não acumular milhões de dicionários na memória.
    """

    def ja_dividida(data, lote):
        """Consultas divididas antes do aviso de limite ser guardado: as metades estão no cache."""
        if len(lote) < 2 or cliente.em_cache(db, montar_sql(data, lote)):
            return False
        meio = len(lote) // 2
        return all(cliente.em_cache(db, montar_sql(data, metade)) or ja_dividida(data, metade)
                   for metade in (lote[:meio], lote[meio:]))

    def rodar(data, lote):
        if ja_dividida(data, lote):
            meio = len(lote) // 2
            return rodar(data, lote[:meio]) + rodar(data, lote[meio:])
        try:
            return cliente.consultar(db, montar_sql(data, lote))
        except LimiteDeLinhas:
            if len(lote) == 1:
                log(f"  aviso: {lote[0]} em {data:%Y-%m-%d} tem mais de 1.000 linhas; ignorado")
                return []
            meio = len(lote) // 2
            return rodar(data, lote[:meio]) + rodar(data, lote[meio:])
        except ErroConsulta as erro:
            log(f"  aviso: consulta de {data:%Y-%m-%d} ({len(lote)} itens) falhou e foi ignorada: {erro}")
            return []

    partes, feitas = [], 0
    with ThreadPoolExecutor(cliente.paralelismo) as executor:
        futuros = [executor.submit(rodar, data, lote) for data, lote in tarefas]
        for futuro in as_completed(futuros):
            linhas = futuro.result()
            if linhas:
                partes.append(para_tabela(linhas, colunas))
            feitas += 1
            if feitas % 500 == 0 or feitas == len(futuros):
                log(f"  {descricao}: {feitas}/{len(futuros)} consultas")
    if not partes:
        return para_tabela([], colunas)
    return pd.concat(partes, ignore_index=True)


def em_lotes(itens, tamanho):
    return [itens[i:i + tamanho] for i in range(0, len(itens), tamanho)]


def baixar_cadeias_entrada(cliente, eventos, tamanho=20):
    tarefas = [(data, lote) for data, grupo in eventos.groupby("data_entrada")
               for lote in em_lotes(sorted(grupo["simbolo"].unique()), tamanho)]

    def sql(data, lote):
        return ("SELECT date, act_symbol, expiration, strike, call_put, bid, ask, vol FROM option_chain "
                f"WHERE date='{data:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)}) "
                f"AND ABS(delta) BETWEEN {FAIXA_DELTA[0]} AND {FAIXA_DELTA[1]}")

    return executar_tarefas(cliente, "options", tarefas, sql, COLUNAS_CADEIA, "cadeias de entrada")


def baixar_cadeias_saida(cliente, operacoes, tamanho=6):
    """Na saída baixamos a cadeia inteira: se o strike da entrada sumiu, o sorriso
    de volatilidade do dia permite estimar o preço dele (ver estrategias.cotar)."""
    tarefas = [(data, lote) for data, grupo in operacoes.groupby("data_saida")
               for lote in em_lotes(sorted(grupo["simbolo"].unique()), tamanho)]

    def sql(data, lote):
        return ("SELECT date, act_symbol, expiration, strike, call_put, bid, ask, vol FROM option_chain "
                f"WHERE date='{data:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")

    return executar_tarefas(cliente, "options", tarefas, sql, COLUNAS_CADEIA, "cadeias de saída")


def baixar_precos(cliente, eventos, dias_pregao, tamanho=300):
    """OHLCV diário de cada ação: de PREGOES_ANTES pregões antes da entrada até a saída."""
    pregoes = pd.DatetimeIndex(sorted(dias_pregao))
    precisa = {}
    for ev in eventos.itertuples():
        i_ini = max(pregoes.searchsorted(ev.data_entrada) - PREGOES_ANTES, 0)
        i_fim = pregoes.searchsorted(ev.data_saida)
        for dia in pregoes[i_ini:i_fim + 1]:
            precisa.setdefault(dia, set()).add(ev.simbolo)
    tarefas = [(dia, lote) for dia, simbolos in sorted(precisa.items())
               for lote in em_lotes(sorted(simbolos), tamanho)]

    def sql(data, lote):
        return ("SELECT date, act_symbol, open, high, low, close, volume FROM ohlcv "
                f"WHERE date='{data:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")

    colunas = ["date", "act_symbol", "open", "high", "low", "close", "volume"]
    precos = executar_tarefas(cliente, "stocks", tarefas, sql, colunas, "preços das ações")
    return precos.sort_values(["act_symbol", "date"])


PERNAS = (("fc", "front", "Call"), ("fp", "front", "Put"), ("bc", "back", "Call"))


def cotar_pernas(op, cadeia, spot, data, momento):
    """Preenche bid/ask (reais ou estimados) das 3 pernas num momento ('ent' ou 'sai')."""
    for prefixo, vencimento, tipo in PERNAS:
        bid, ask, estimado = cotar(cadeia, op[vencimento], op["strike"], tipo, spot, data)
        op[f"{prefixo}_bid_{momento}"], op[f"{prefixo}_ask_{momento}"] = bid, ask
        op[f"{prefixo}_est_{momento}"] = estimado


def montar_operacoes(eventos, cadeias, precos):
    """Calcula filtros e escolhe os contratos de cada evento (tudo com dados da entrada)."""
    cadeias_por_chave = {chave: grupo for chave, grupo in cadeias.groupby(["date", "act_symbol"])}
    precos_por_simbolo = {s: g for s, g in precos.groupby("act_symbol")}
    datas_por_simbolo = {s: set(g["date"]) for s, g in precos_por_simbolo.items()}
    operacoes, motivos = [], {}

    def descartar(motivo):
        motivos[motivo] = motivos.get(motivo, 0) + 1

    for ev in eventos.itertuples():
        cadeia = cadeias_por_chave.get((ev.data_entrada, ev.simbolo))
        if cadeia is None:
            descartar("sem cadeia de opções na entrada")
            continue
        historico = precos_por_simbolo.get(ev.simbolo)
        datas = datas_por_simbolo.get(ev.simbolo, set())
        if ev.data_entrada not in datas or ev.data_saida not in datas:
            descartar("sem preço da ação na entrada ou na saída")
            continue
        ate_entrada = historico[historico["date"] <= ev.data_entrada]
        spot = float(ate_entrada["close"].iloc[-1])
        contratos = escolher_contratos(cadeia, spot, ev.data_saida)
        if contratos is None:
            descartar("não deu para montar strike/vencimentos")
            continue

        op = ev._asdict()
        op.pop("Index")
        op.update(calcular_filtros(cadeia, spot, ev.data_entrada, ate_entrada, JANELA))
        op.update(contratos)
        op["spot_ent"] = spot
        op["spot_sai"] = float(historico.loc[historico["date"] == ev.data_saida, "close"].iloc[0])
        op["dist_strike"] = contratos["strike"] / spot - 1
        cotar_pernas(op, cadeia, spot, ev.data_entrada, "ent")
        operacoes.append(op)
    return pd.DataFrame(operacoes), motivos


def preencher_saida(operacoes, cadeias_saida):
    cadeias_por_chave = {chave: grupo for chave, grupo in cadeias_saida.groupby(["date", "act_symbol"])}
    linhas = []
    for op in operacoes.to_dict("records"):
        cadeia = cadeias_por_chave.get((op["data_saida"], op["simbolo"]))
        if cadeia is None:
            cadeia = cadeias_saida.iloc[0:0]
        cotar_pernas(op, cadeia, op["spot_sai"], op["data_saida"], "sai")
        linhas.append(op)
    return pd.DataFrame(linhas)


def cotacoes_validas(df, pernas, momento):
    ok = pd.Series(True, index=df.index)
    for perna in pernas:
        bid, ask = df[f"{perna}_bid_{momento}"], df[f"{perna}_ask_{momento}"]
        ok &= bid.notna() & ask.notna() & (ask > 0) & (ask >= bid)
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inicio", default="2022-01-01")
    parser.add_argument("--fim", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--simbolos", help="lista separada por vírgula (opcional, para testes)")
    parser.add_argument("--folga", type=int, default=2, help="pregões de tolerância na entrada/saída")
    parser.add_argument("--saida", default="resultados")
    parser.add_argument("--cache", default="dados/cache")
    parser.add_argument("--paralelismo", type=int, default=8)
    parser.add_argument("--so-cache", action="store_true",
                        help="não baixa nada: usa só o que já está no cache (resultado parcial)")
    args = parser.parse_args(argv)

    cliente = DoltHub(args.cache, args.paralelismo, so_cache=args.so_cache)
    inicio, fim = pd.Timestamp(args.inicio), pd.Timestamp(args.fim)

    log("1/6 Mapeando dias com dados (pregões e opções)...")
    dias_pregao = dias_com_dados(cliente, "stocks", "ohlcv", inicio - pd.Timedelta(days=80), fim + pd.Timedelta(days=10))
    dias_opcoes = dias_com_dados(cliente, "options", "option_chain", inicio - pd.Timedelta(days=10), fim + pd.Timedelta(days=10))
    log(f"  {len(dias_pregao)} pregões, {len(dias_opcoes)} dias com opções")

    log("2/6 Carregando calendário de resultados...")
    eventos = carregar_eventos(cliente, inicio, fim)
    if args.simbolos:
        eventos = eventos[eventos["simbolo"].isin(args.simbolos.upper().split(","))]
    funil = {"eventos com horário (AMC/BMO)": len(eventos)}
    eventos = definir_datas(eventos, dias_pregao, dias_opcoes, args.folga).dropna(subset=["data_entrada", "data_saida"])
    funil["com dia de opções na entrada e na saída"] = len(eventos)

    log(f"3/6 Baixando cadeias de opções na entrada ({len(eventos)} eventos)...")
    cadeias = baixar_cadeias_entrada(cliente, eventos)
    chaves = set(zip(cadeias["date"], cadeias["act_symbol"]))
    eventos = eventos[[(d, s) in chaves for d, s in zip(eventos["data_entrada"], eventos["simbolo"])]]
    funil["com cadeia de opções na entrada"] = len(eventos)

    log(f"4/6 Baixando preços das ações ({eventos['simbolo'].nunique()} ações)...")
    precos = baixar_precos(cliente, eventos, dias_pregao)

    log("5/6 Calculando filtros e escolhendo contratos...")
    operacoes, motivos = montar_operacoes(eventos, cadeias, precos)
    for motivo, n in motivos.items():
        log(f"  descartados: {n} ({motivo})")
    funil["com preços e contratos montáveis"] = len(operacoes)

    log(f"6/6 Baixando cotações de saída ({len(operacoes)} operações)...")
    cadeias_saida = baixar_cadeias_saida(cliente, operacoes)
    com_saida = set(zip(cadeias_saida["date"], cadeias_saida["act_symbol"]))
    funil["com cadeia de opções na saída"] = sum((d, s) in com_saida for d, s in zip(operacoes["data_saida"], operacoes["simbolo"]))
    operacoes = preencher_saida(operacoes, cadeias_saida)

    ok_straddle = cotacoes_validas(operacoes, ["fc", "fp"], "ent") & cotacoes_validas(operacoes, ["fc", "fp"], "sai") & (operacoes["fc_bid_ent"] > 0) & (operacoes["fp_bid_ent"] > 0)
    ok_calendar = cotacoes_validas(operacoes, ["fc", "bc"], "ent") & cotacoes_validas(operacoes, ["fc", "bc"], "sai") & (operacoes["fc_bid_ent"] > 0)
    operacoes["ret_straddle"] = retorno_straddle(operacoes).where(ok_straddle)
    operacoes["ret_calendar"] = retorno_calendar(operacoes).where(ok_calendar)
    operacoes["movimento"] = operacoes["spot_sai"] / operacoes["spot_ent"] - 1
    mid = lambda p: (operacoes[f"{p}_bid_ent"] + operacoes[f"{p}_ask_ent"]) / 2
    operacoes["movimento_esperado"] = (mid("fc") + mid("fp")) / operacoes["spot_ent"]
    operacoes["exato"] = (operacoes["defasagem_entrada"] == 0) & (operacoes["defasagem_saida"] == 0)
    funil["straddle com cotações válidas"] = int(operacoes["ret_straddle"].notna().sum())
    funil["calendar com cotações válidas"] = int(operacoes["ret_calendar"].notna().sum())

    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    operacoes.to_csv(pasta / "trades.csv", index=False)
    pd.Series(funil, name="eventos").to_csv(pasta / "funil.csv", header=True)
    log("Funil de eventos:")
    for etapa, n in funil.items():
        log(f"  {n:>7}  {etapa}")
    log(f"Pronto: {pasta / 'trades.csv'}")


if __name__ == "__main__":
    main()
