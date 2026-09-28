"""Backtest da venda de puts em ações grandes (o "esqueleto" da estratégia da Annie).

Uso:
    python -m backtest_puts.executar --inicio 2022-01-01 --saida resultados_puts

Gera em <saida>/:
    universo.csv     as ações escolhidas
    trades.csv       uma linha por put vendida (entrada, saída, variantes A e B)
    trajetorias.csv  cotação diária de cada put enquanto ela aparece na base
    precos.csv       fechamentos diários do universo e do SPY (para a carteira)
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_earnings.dolthub import DoltHub, lista_sql
from backtest_earnings.estrategias import cotar
from backtest_earnings.eventos import consultar_paginado, dias_com_dados
from backtest_earnings.executar import em_lotes, executar_tarefas, log

N_UNIVERSO = 100
DELTA_ALVO, FAIXA_DELTA = -0.25, (-0.30, -0.20)
DTE_ALVO, FAIXA_DTE = 35, (21, 56)
ALVO_LUCRO = 0.50           # recompra quando 50% do prêmio já foi embolsado
MAX_PREGOES_ACOES = 126     # variante B: segura a ação exercida por no máximo ~6 meses
REFERENCIA = "SPY"

COLUNAS_PUTS = ["date", "act_symbol", "expiration", "strike", "call_put", "bid", "ask", "vol", "delta"]


def escolher_universo(cliente, dias_pregao, dias_opcoes, inicio, n=N_UNIVERSO):
    """As `n` ações mais negociadas (em US$) no trimestre anterior ao início que pagaram
    dividendo no ano anterior, não são ETF e têm opções na base no primeiro dia do teste.
    Só usa dados de ANTES do início: não há viés de sobrevivência."""
    ano = inicio.year - 1
    pagadoras = consultar_paginado(
        cliente, "stocks",
        f"SELECT DISTINCT act_symbol FROM dividend WHERE ex_date BETWEEN '{ano}-01-01' AND '{ano}-12-31'",
        "act_symbol")
    etfs = consultar_paginado(cliente, "stocks", "SELECT act_symbol FROM symbol WHERE is_etf = 1", "act_symbol")
    candidatos = sorted({l["act_symbol"] for l in pagadoras} - {l["act_symbol"] for l in etfs})
    log(f"  {len(candidatos)} ações pagaram dividendo em {ano} (sem ETFs)")

    amostra = [d for d in dias_pregao if d.year == ano and d.month >= 10][::5]
    tarefas = [(d, lote) for d in amostra for lote in em_lotes(candidatos, 300)]
    sql = lambda d, lote: ("SELECT date, act_symbol, close, volume FROM ohlcv "
                           f"WHERE date='{d:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")
    precos = executar_tarefas(cliente, "stocks", tarefas, sql, ["date", "act_symbol", "close", "volume"],
                              "volume financeiro")
    financeiro = (precos["close"] * precos["volume"]).groupby(precos["act_symbol"]).mean().sort_values(ascending=False)

    primeiro_dia = min(d for d in dias_opcoes if d >= inicio)
    topo = list(financeiro.index[:3 * n])
    com_opcoes = set()
    for lote in em_lotes(topo, 100):
        linhas = cliente.consultar("options", "SELECT DISTINCT act_symbol FROM option_chain "
                                   f"WHERE date='{primeiro_dia:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")
        com_opcoes |= {l["act_symbol"] for l in linhas}
    universo = [s for s in topo if s in com_opcoes][:n]
    return pd.DataFrame({"simbolo": universo, "volume_financeiro": financeiro.loc[universo].values})


def baixar_precos(cliente, simbolos, dias):
    tarefas = [(d, lote) for d in dias for lote in em_lotes(simbolos, 300)]
    sql = lambda d, lote: ("SELECT date, act_symbol, open, high, low, close, volume FROM ohlcv "
                           f"WHERE date='{d:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")
    return executar_tarefas(cliente, "stocks", tarefas, sql,
                            ["date", "act_symbol", "open", "high", "low", "close", "volume"], "preços")


def baixar_volatilidade(cliente, simbolos, dias):
    tarefas = [(d, lote) for d in dias for lote in em_lotes(simbolos, 300)]
    colunas = ["date", "act_symbol", "iv_current", "iv_year_high", "iv_year_low", "hv_current"]
    sql = lambda d, lote: (f"SELECT {', '.join(colunas)} FROM volatility_history "
                           f"WHERE date='{d:%Y-%m-%d}' AND act_symbol IN ({lista_sql(lote)})")
    return executar_tarefas(cliente, "options", tarefas, sql, colunas, "volatilidade")


def baixar_puts(cliente, simbolos, dias, tamanho=15):
    tarefas = [(d, lote) for d in dias for lote in em_lotes(simbolos, tamanho)]
    sql = lambda d, lote: (f"SELECT {', '.join(COLUNAS_PUTS)} FROM option_chain WHERE date='{d:%Y-%m-%d}' "
                           f"AND act_symbol IN ({lista_sql(lote)}) AND call_put='Put'")
    puts = executar_tarefas(cliente, "options", tarefas, sql, COLUNAS_PUTS, "puts")
    puts["act_symbol"] = puts["act_symbol"].astype("category")
    puts["call_put"] = puts["call_put"].astype("category")
    return puts.sort_values(["act_symbol", "date", "expiration", "strike"], ignore_index=True)


def baixar_desdobramentos(cliente, simbolos, inicio):
    linhas = cliente.consultar("stocks", "SELECT act_symbol, ex_date, to_factor, for_factor FROM split "
                               f"WHERE ex_date >= '{inicio:%Y-%m-%d}' AND act_symbol IN ({lista_sql(simbolos)})")
    registros = pd.DataFrame(linhas, columns=["act_symbol", "ex_date", "to_factor", "for_factor"])
    registros["ex_date"] = pd.to_datetime(registros["ex_date"])
    registros["razao"] = pd.to_numeric(registros["to_factor"]) / pd.to_numeric(registros["for_factor"])
    return registros


def confirmar_desdobramentos(precos, registros, tolerancia=0.15):
    """A tabela de desdobramentos (splits) do DoltHub tem registros duplicados e datas de anúncio.
    Só vale o desdobramento em que o preço de fato saltou na proporção, perto da data registrada.
    Devolve (simbolo, data, razao), onde `data` é o primeiro pregão já na escala nova."""
    confirmados = set()
    for reg in registros.itertuples():
        serie = precos.loc[precos["act_symbol"] == reg.act_symbol].set_index("date")["close"].sort_index()
        salto = (serie.shift(1) / serie).loc[reg.ex_date - pd.Timedelta(days=10):reg.ex_date + pd.Timedelta(days=30)]
        batem = salto[(salto / reg.razao - 1).abs() < tolerancia]
        if len(batem):
            confirmados.add((reg.act_symbol, batem.index[0], reg.razao))
    return pd.DataFrame(sorted(confirmados), columns=["simbolo", "data", "razao"])


def ajustar_desdobramentos(df, desdobramentos, colunas_preco, coluna_volume=None):
    """Leva preços (e strikes) de antes de cada desdobramento para a escala nova."""
    df = df.copy()
    for d in desdobramentos.itertuples():
        antes = (df["act_symbol"] == d.simbolo) & (df["date"] < d.data)
        df.loc[antes, colunas_preco] = df.loc[antes, colunas_preco] / d.razao
        if coluna_volume:
            df.loc[antes, coluna_volume] = df.loc[antes, coluna_volume] * d.razao
    return df


def escolher_put(cadeia, data):
    """Vencimento mais perto de DTE_ALVO (dentro de FAIXA_DTE) e put com delta mais perto
    de DELTA_ALVO (dentro de FAIXA_DELTA), com bid > 0. Devolve a linha ou None."""
    dte = (cadeia["expiration"] - pd.Timestamp(data)).dt.days
    validos = cadeia[(dte >= FAIXA_DTE[0]) & (dte <= FAIXA_DTE[1])]
    if validos.empty:
        return None
    dte_validos = (validos["expiration"] - pd.Timestamp(data)).dt.days
    vencimento = validos.loc[(dte_validos - DTE_ALVO).abs().idxmin(), "expiration"]
    opcoes = validos[(validos["expiration"] == vencimento) & validos["delta"].between(*FAIXA_DELTA)
                     & (validos["bid"] > 0) & (validos["ask"] >= validos["bid"])]
    if opcoes.empty:
        return None
    return opcoes.loc[(opcoes["delta"] - DELTA_ALVO).abs().idxmin()]


class Painel:
    """Acesso rápido às cadeias de puts e aos fechamentos por (ação, dia)."""

    def __init__(self, puts, precos):
        self.por_simbolo, self.indices = {}, {}
        for simbolo, grupo in puts.groupby("act_symbol", observed=True):
            grupo = grupo.reset_index(drop=True)
            self.por_simbolo[simbolo] = grupo
            self.indices[simbolo] = grupo.groupby("date").indices
        self.fechamento = precos.pivot_table(index="date", columns="act_symbol", values="close").sort_index()
        self.fechamento_ffill = self.fechamento.ffill()

    def cadeia(self, simbolo, data):
        posicoes = self.indices.get(simbolo, {}).get(data)
        return None if posicoes is None else self.por_simbolo[simbolo].iloc[posicoes]

    def preco(self, simbolo, data):
        """Fechamento no dia (ou no último pregão antes dele)."""
        if simbolo not in self.fechamento_ffill:
            return np.nan
        serie = self.fechamento_ffill[simbolo]
        i = serie.index.searchsorted(pd.Timestamp(data), side="right") - 1
        return float(serie.iat[i]) if i >= 0 else np.nan


def simular(simbolo, data, put, painel):
    """Acompanha uma put vendida até a saída. Devolve (operação, trajetória)."""
    vencimento, strike = put["expiration"], float(put["strike"])
    credito_mid = (put["bid"] + put["ask"]) / 2
    op = {"simbolo": simbolo, "data_entrada": data, "vencimento": vencimento, "strike": strike,
          "spot_ent": painel.preco(simbolo, data), "delta": put["delta"], "iv_put": put["vol"],
          "bid_ent": put["bid"], "ask_ent": put["ask"], "saida": None}
    trajetoria = []

    # 1) Enquanto o vencimento aparece na base (até ~11 dias antes), confere o alvo de 50% todo dia.
    do_vencimento = painel.por_simbolo[simbolo]
    do_vencimento = do_vencimento[(do_vencimento["expiration"] == vencimento) & (do_vencimento["date"] > data)]
    exatas = do_vencimento[do_vencimento["strike"] == strike].set_index("date")
    for dia, cadeia in do_vencimento.groupby("date"):
        linha = exatas.loc[dia] if dia in exatas.index else None
        if linha is not None and pd.notna(linha["bid"]) and linha["ask"] > 0 and linha["ask"] >= linha["bid"]:
            bid, ask, estimado = float(linha["bid"]), float(linha["ask"]), False
        else:  # o strike sumiu da base nesse dia: estima pelo sorriso de volatilidade
            bid, ask, estimado = cotar(cadeia, vencimento, strike, "Put", painel.preco(simbolo, dia), dia)
            if np.isnan(bid):
                continue
        trajetoria.append({"data": dia, "bid": bid, "ask": ask, "estimado": estimado})
        if (bid + ask) / 2 <= (1 - ALVO_LUCRO) * credito_mid:
            op.update(saida="alvo", data_saida=dia, bid_sai=bid, ask_sai=ask, estimado_sai=estimado)
            break

    # 2) Não bateu o alvo: vai até o vencimento, quando a put vale max(strike - ação, 0).
    if op["saida"] is None:
        ultimo_pregao = painel.fechamento.index[-1]
        spot_venc = painel.preco(simbolo, vencimento)
        op.update(data_saida=vencimento, spot_venc=spot_venc, bid_sai=np.nan, ask_sai=np.nan, estimado_sai=False,
                  saida="virou_po" if spot_venc >= strike else "exercida")
        if pd.Timestamp(vencimento) > ultimo_pregao:
            op["saida"] = "em_aberto"

    op["spot_sai"] = painel.preco(simbolo, op["data_saida"])

    # 3) Variante B: exercida -> fica com a ação até voltar ao strike (máx. MAX_PREGOES_ACOES pregões).
    op["data_saida_b"], op["spot_sai_b"], op["b_em_aberto"] = op["data_saida"], op["spot_sai"], False
    if op["saida"] == "exercida":
        depois = painel.fechamento[simbolo].loc[pd.Timestamp(vencimento) + pd.Timedelta(days=1):].dropna()
        janela = depois.iloc[:MAX_PREGOES_ACOES]
        recuperou = janela[janela >= strike]
        if len(recuperou):
            op["data_saida_b"], op["spot_sai_b"] = recuperou.index[0], float(recuperou.iloc[0])
        elif len(janela):
            op["data_saida_b"], op["spot_sai_b"] = janela.index[-1], float(janela.iloc[-1])
        op["b_em_aberto"] = bool(len(janela) < MAX_PREGOES_ACOES and not len(recuperou))
    return op, trajetoria


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inicio", default="2022-01-01")
    parser.add_argument("--fim", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--n", type=int, default=N_UNIVERSO, help="tamanho do universo")
    parser.add_argument("--saida", default="resultados_puts")
    parser.add_argument("--cache", default="dados/cache")
    parser.add_argument("--paralelismo", type=int, default=8)
    args = parser.parse_args(argv)

    cliente = DoltHub(args.cache, args.paralelismo)
    inicio, fim = pd.Timestamp(args.inicio), pd.Timestamp(args.fim)
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)

    log("1/5 Mapeando dias com dados...")
    pregoes = dias_com_dados(cliente, "stocks", "ohlcv", pd.Timestamp(f"{inicio.year - 1}-10-01"), fim)
    dias_opcoes = dias_com_dados(cliente, "options", "option_chain", inicio, fim)
    log(f"  {len(pregoes)} pregões, {len(dias_opcoes)} dias com opções")

    log("2/5 Escolhendo o universo...")
    universo = escolher_universo(cliente, pregoes, dias_opcoes, inicio, args.n)
    universo.to_csv(pasta / "universo.csv", index=False)
    simbolos = list(universo["simbolo"])
    log(f"  {len(simbolos)} ações: {', '.join(simbolos[:15])}...")

    log("3/5 Baixando preços e volatilidade...")
    dias_teste = pregoes[pregoes >= inicio - pd.Timedelta(days=45)]
    precos = baixar_precos(cliente, simbolos + [REFERENCIA], dias_teste)
    desdobramentos = confirmar_desdobramentos(precos, baixar_desdobramentos(cliente, simbolos, dias_teste[0]))
    desdobramentos.to_csv(pasta / "desdobramentos.csv", index=False)
    log(f"  desdobramentos confirmados: {', '.join(f'{d.simbolo} {d.data:%d/%m/%Y} ({d.razao:g}:1)' for d in desdobramentos.itertuples())}")
    precos = ajustar_desdobramentos(precos, desdobramentos, ["open", "high", "low", "close"], "volume")
    precos.to_csv(pasta / "precos.csv", index=False)
    semanas = pd.Series(dias_opcoes, index=dias_opcoes).groupby([dias_opcoes.isocalendar().year,
                                                                  dias_opcoes.isocalendar().week]).min()
    dias_entrada = pd.DatetimeIndex(semanas.values)
    vol = baixar_volatilidade(cliente, simbolos, dias_entrada)

    log(f"4/5 Baixando cadeias de puts ({len(dias_opcoes)} dias x {len(simbolos)} ações)...")
    puts = baixar_puts(cliente, simbolos, dias_opcoes)
    log(f"  {len(puts):,} linhas de puts".replace(",", "."))
    puts = ajustar_desdobramentos(puts, desdobramentos, ["strike", "bid", "ask"])
    puts["strike"] = puts["strike"].round(2)  # ex.: 250 / 3 = 83,33, o strike ajustado que a bolsa lista
    painel = Painel(puts, precos)
    del puts
    volume_30 = (precos.assign(fin=precos["close"] * precos["volume"])
                 .pivot_table(index="date", columns="act_symbol", values="fin").rolling(30, min_periods=20).mean())
    vol = vol.set_index(["date", "act_symbol"])

    log(f"5/5 Simulando {len(dias_entrada)} semanas...")
    operacoes, trajetorias = [], []
    for n_semana, data in enumerate(dias_entrada, 1):
        for simbolo in simbolos:
            cadeia = painel.cadeia(simbolo, data)
            if cadeia is None or np.isnan(painel.preco(simbolo, data)):
                continue
            put = escolher_put(cadeia, data)
            if put is None:
                continue
            op, trajetoria = simular(simbolo, data, put, painel)
            op["id"] = len(operacoes)
            if (data, simbolo) in vol.index:
                v = vol.loc[(data, simbolo)]
                faixa = v["iv_year_high"] - v["iv_year_low"]
                op["iv_rank"] = (v["iv_current"] - v["iv_year_low"]) / faixa if faixa > 0 else np.nan
                op["iv_atual"], op["hv_atual"] = v["iv_current"], v["hv_current"]
            op["volume_financeiro_30"] = volume_30[simbolo].get(data, np.nan) if simbolo in volume_30 else np.nan
            operacoes.append(op)
            trajetorias += [{"id": op["id"], **ponto} for ponto in trajetoria]
        if n_semana % 25 == 0:
            log(f"  {n_semana}/{len(dias_entrada)} semanas, {len(operacoes)} puts")

    trades = pd.DataFrame(operacoes)
    trades.to_csv(pasta / "trades.csv", index=False)
    pd.DataFrame(trajetorias).to_csv(pasta / "trajetorias.csv", index=False)
    log(f"Pronto: {len(trades)} puts. Saídas: {trades['saida'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
