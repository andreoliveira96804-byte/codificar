"""Gera o relatório (Markdown) a partir de resultados/trades.csv.

Uso:
    python -m backtest_earnings.relatorio --pasta resultados
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .analise import (LIMITES_VIDEO, classificar, curva_capital, decis, kelly, limites_por_quantil,
                      monte_carlo, queda_maxima, resumo, resumo_monte_carlo)
from .estrategias import retorno_calendar, retorno_straddle

ESTRATEGIAS = {"straddle": ("Straddle vendido", retorno_straddle), "calendar": ("Calendar", retorno_calendar)}
PREDITORES = {
    "ts_slope_0_45": "Inclinação da estrutura a termo (0→45 dias)",
    "iv30_rv30": "IV30 / RV30",
    "volume_medio_30": "Volume médio de 30 dias",
}


def pct(x, casas=1, sinal=True):
    return "—" if pd.isna(x) else f"{x * 100:{'+' if sinal else ''}.{casas}f}%"


def num(x):
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e5:
        return f"{x / 1e6:.2f} mi"
    if abs(x) < 0.1:
        return f"{x:.4f}"
    return f"{x:.2f}"


def tabela(linhas, cabecalho):
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    saida += ["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(saida)


def linha_resumo(rotulo, r):
    s = resumo(r)
    if s["n"] == 0:
        return [rotulo, 0] + ["—"] * 6
    return [rotulo, s["n"], pct(s["media"]), pct(s["mediana"]), pct(s["desvio"], 0, sinal=False),
            f"{s['acerto']:.0%}", pct(s["p5"], 0), pct(s["pior"], 0)]


CAB_RESUMO = ["", "n", "Média", "Mediana", "Desvio", "Acerto", "5% piores até", "Pior"]


def carregar(pasta):
    df = pd.read_csv(Path(pasta) / "trades.csv",
                     parse_dates=["data_anuncio", "data_entrada", "data_saida", "front", "back"])
    for chave, (_, funcao) in ESTRATEGIAS.items():
        valido = df[f"ret_{chave}"].notna()
        for k in (0, 0.5, 1):
            df[f"r_{chave}_k{k}"] = funcao(df, k=k).where(valido)
        df[f"r_{chave}"] = df[f"r_{chave}_k0.5"]
    df["temporada"] = df["data_entrada"].dt.to_period("Q").astype(str)
    return df


def secao_funil(pasta, df):
    partes = ["## 1. Funil de eventos\n"]
    arquivo = Path(pasta) / "funil.csv"
    if arquivo.exists():
        funil = pd.read_csv(arquivo, index_col=0)
        partes.append(tabela([[etapa, f"{int(n):,}".replace(",", ".")] for etapa, n in funil["eventos"].items()],
                             ["Etapa", "Eventos"]))
    estimadas = {perna: df[[f"{perna}_est_ent", f"{perna}_est_sai"]].any(axis=1).mean() for perna in ("fc", "fp", "bc")}
    partes.append(
        f"\nPeríodo: {df['data_entrada'].min():%d/%m/%Y} a {df['data_saida'].max():%d/%m/%Y}. "
        f"Operações com datas exatas (sem defasagem): {df['exato'].mean():.0%}. "
        f"Primeiro vencimento disponível: mediana de {df['dte_primeiro'].median():.0f} dias.\n\n"
        "Pernas com preço ESTIMADO (Black-Scholes pelo sorriso do dia) em algum momento: "
        f"call curta {estimadas['fc']:.0%}, put curta {estimadas['fp']:.0%}, call longa {estimadas['bc']:.0%}.\n")
    return "\n".join(partes)


def secao_sem_filtro(df):
    linhas = []
    for chave, (nome, _) in ESTRATEGIAS.items():
        for k, rotulo in ((0, "preço médio"), (0.5, "meio spread"), (1, "spread inteiro")):
            linhas.append(linha_resumo(f"{nome}, k={k} ({rotulo})", df[f"r_{chave}_k{k}"]))
    return ("## 2. Todos os eventos, sem filtro\n\n"
            "No vídeo, operar todos os eventos dá retorno médio perto de zero.\n\n"
            + tabela(linhas, CAB_RESUMO) + "\n")


def secao_decis(df):
    partes = ["## 3. Decis (k = 0,5)\n",
              "Cada variável dividida em 10 grupos do mesmo tamanho (1 = menores valores). "
              "Se o filtro funciona, o retorno deve melhorar de forma consistente numa direção.\n"]
    for coluna, titulo in PREDITORES.items():
        partes.append(f"### {titulo}\n")
        d = {chave: decis(df, coluna, f"r_{chave}") for chave in ESTRATEGIAS}
        linhas = [[i, f"{num(d['straddle'].loc[i, 'de'])} a {num(d['straddle'].loc[i, 'ate'])}", int(d["straddle"].loc[i, "n"]),
                   pct(d["straddle"].loc[i, "media"]), f"{d['straddle'].loc[i, 'acerto']:.0%}",
                   pct(d["calendar"].loc[i, "media"]) if i in d["calendar"].index else "—",
                   f"{d['calendar'].loc[i, 'acerto']:.0%}" if i in d["calendar"].index else "—"]
                  for i in d["straddle"].index]
        partes.append(tabela(linhas, ["Decil", "Faixa", "n", "Straddle média", "Straddle acerto",
                                      "Calendar média", "Calendar acerto"]) + "\n")
    return "\n".join(partes)


def secao_classes(df, limites, titulo, texto):
    classes = classificar(df, limites)
    linhas = []
    for classe in ("Recommended", "Consider", "Avoid"):
        grupo = df[classes == classe]
        for chave, (nome, _) in ESTRATEGIAS.items():
            linhas.append(linha_resumo(f"{classe} — {nome}", grupo[f"r_{chave}"]))
    limites_txt = (f"volume ≥ {num(limites['volume_medio_30'])}, IV30/RV30 ≥ {limites['iv30_rv30']:.2f}, "
                   f"inclinação ≤ {limites['ts_slope_0_45']:.5f}")
    return f"{titulo}\n\n{texto}\n\nLimites: {limites_txt}.\n\n" + tabela(linhas, CAB_RESUMO) + "\n"


def secao_fora_da_amostra(df):
    corte = df["data_entrada"].quantile(0.5)
    treino, teste = df[df["data_entrada"] < corte], df[df["data_entrada"] >= corte]
    limites = limites_por_quantil(treino)
    linhas = []
    for nome_periodo, parte in (("Treino", treino), ("Teste (fora da amostra)", teste)):
        recomendados = parte[classificar(parte, limites) == "Recommended"]
        for chave, (nome, _) in ESTRATEGIAS.items():
            linhas.append(linha_resumo(f"{nome_periodo} — {nome}, todos", parte[f"r_{chave}"]))
            linhas.append(linha_resumo(f"{nome_periodo} — {nome}, Recommended", recomendados[f"r_{chave}"]))
    texto = (f"Os limites foram calculados só com o período de TREINO (entradas antes de {corte:%d/%m/%Y}) "
             "usando quantis fixados antes de ver o resultado: inclinação no terço mais negativo, "
             "IV30/RV30 no terço mais alto e volume acima da mediana. Depois foram aplicados, "
             "congelados, no período de TESTE.\n\n"
             f"Limites do treino: volume ≥ {num(limites['volume_medio_30'])}, "
             f"IV30/RV30 ≥ {limites['iv30_rv30']:.2f}, inclinação ≤ {limites['ts_slope_0_45']:.5f}.")
    return ("## 5. Filtros recalibrados e teste fora da amostra\n\n" + texto + "\n\n"
            + tabela(linhas, CAB_RESUMO) + "\n"), limites, corte


def secao_por_ano(df, limites):
    df = df.assign(ano=df["data_entrada"].dt.year, classe=classificar(df, limites))
    linhas = []
    for ano, grupo in df.groupby("ano"):
        rec = grupo[grupo["classe"] == "Recommended"]
        linhas.append([ano, len(grupo), pct(grupo["r_straddle"].mean()), pct(grupo["r_calendar"].mean()),
                       len(rec), pct(rec["r_straddle"].mean()), pct(rec["r_calendar"].mean())])
    return ("## 6. Por ano (k = 0,5; limites recalibrados)\n\n"
            + tabela(linhas, ["Ano", "n todos", "Straddle todos", "Calendar todos",
                              "n Recommended", "Straddle Rec.", "Calendar Rec."]) + "\n")


def secao_acumulado(df, limites, fracao=0.05):
    df = df.assign(classe=classificar(df, limites))
    linhas = []
    for rotulo, parte in (("Todos", df), ("Recommended", df[df["classe"] == "Recommended"])):
        for chave, (nome, _) in ESTRATEGIAS.items():
            por_dia = parte.dropna(subset=[f"r_{chave}"]).groupby("data_entrada")[f"r_{chave}"].mean()
            if por_dia.empty:
                continue
            curva = curva_capital(por_dia.values, fracao)
            linhas.append([f"{rotulo} — {nome}", len(por_dia), f"US$ {curva[-1]:,.0f}".replace(",", "."),
                           pct(curva[-1] / 10_000 - 1, 0), pct(-queda_maxima(np.r_[10_000, curva]), 0)])
    return (f"## 7. Retorno acumulado (US$ 10.000, {fracao:.0%} do capital por dia de operação, k = 0,5)\n\n"
            "Quando várias operações entram no mesmo dia, o capital daquele dia é dividido igualmente "
            "entre elas (usamos o retorno médio do dia).\n\n"
            + tabela(linhas, ["Carteira", "Dias com operação", "Capital final", "Retorno", "Queda máxima"]) + "\n")


def secao_kelly(df, limites, corte):
    teste = df[(df["data_entrada"] >= corte) & (classificar(df, limites) == "Recommended")]
    anos = max((teste["data_entrada"].max() - teste["data_entrada"].min()).days / 365, 0.25) if len(teste) else 1
    partes = ["## 8. Kelly e Monte Carlo (Recommended, período de teste, k = 0,5)\n",
              "Monte Carlo: 10.000 caminhos de 1 ano, começando com US$ 10.000. "
              "Sorteamos TEMPORADAS inteiras de resultados (e não operações soltas), para que "
              "perdas que acontecem juntas continuem juntas. Obs.: a simulação faz uma operação "
              "de cada vez; na prática várias ficam abertas juntas, o que aumenta o risco.\n"]
    linhas = []
    for chave, (nome, _) in ESTRATEGIAS.items():
        r = teste[f"r_{chave}"].dropna()
        if len(r) < 20:
            linhas.append([nome, "amostra pequena demais"] + ["—"] * 7)
            continue
        f_kelly = kelly(r)
        n_ano = int(round(len(r) / anos))
        for rotulo, fracao in (("Kelly cheio", f_kelly), ("1/4 Kelly", f_kelly / 4), ("1/10 Kelly", f_kelly / 10)):
            if fracao <= 0:
                linhas.append([nome, rotulo, "0% (média ≤ 0: não apostar)"] + ["—"] * 6)
                continue
            s = resumo_monte_carlo(monte_carlo(r, fracao, n_ano, grupos=teste["temporada"]))
            linhas.append([nome, rotulo, f"{fracao:.1%}", n_ano,
                           f"US$ {s['capital_mediano']:,.0f}".replace(",", "."),
                           f"US$ {s['capital_p5']:,.0f}".replace(",", "."),
                           f"{s['prob_prejuizo']:.0%}", f"{s['prob_quebra']:.1%}", pct(-s["queda_max_mediana"], 0)])
    partes.append(tabela(linhas, ["Estratégia", "Tamanho", "% do capital por operação", "Operações/ano",
                                  "Capital mediano", "5% piores", "Prob. prejuízo", "Prob. quebra (−95%)",
                                  "Queda máx. mediana"]) + "\n")
    return "\n".join(partes)


def gerar(pasta):
    df = carregar(pasta)
    secao5, limites, corte = secao_fora_da_amostra(df)
    partes = [
        "# Relatório do backtest — venda de volatilidade em resultados\n",
        "Backtest APROXIMADO com dados de fim de dia (EOD) do DoltHub: entrada no fechamento antes do "
        "anúncio, saída no fechamento depois dele. k = fração do spread paga em cada execução; "
        "comissão de US$ 0,65 por contrato. Retorno do straddle sobre o prêmio recebido; do calendar "
        "sobre o débito pago.\n",
        secao_funil(pasta, df),
        secao_sem_filtro(df),
        secao_decis(df),
        secao_classes(df, LIMITES_VIDEO, "## 4. Filtros com os limites do vídeo",
                      "Atenção: aqui o primeiro vencimento fica a ~2 semanas (no vídeo, a poucos dias), então "
                      "a escala da inclinação é diferente e o limite do vídeo não é diretamente comparável."),
        secao5,
        secao_por_ano(df, limites),
        secao_acumulado(df, limites),
        secao_kelly(df, limites, corte),
    ]
    texto = "\n".join(partes)
    (Path(pasta) / "relatorio.md").write_text(texto)
    return texto


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pasta", default="resultados")
    args = parser.parse_args(argv)
    print(gerar(args.pasta))


if __name__ == "__main__":
    main()
