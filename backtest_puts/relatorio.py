"""Relatório (Markdown) do backtest de venda de puts.

Uso:
    python -m backtest_puts.relatorio --pasta resultados_puts
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_earnings.analise import decis, resumo
from backtest_earnings.relatorio import CAB_RESUMO, linha_resumo, num, pct, tabela

from .carteira import Valorizador, carregar_trades, metricas, retornos, simular_carteira
from .executar import REFERENCIA

VARIANTES = {"a": "A (exercida: vende a ação no vencimento)", "b": "B (exercida: fica com a ação)"}


def anualizado(r, dias):
    """Retorno médio por dia de capital travado, anualizado de forma simples."""
    return r.mean() / dias.mean() * 365 if dias.mean() > 0 else np.nan


def secao_universo(pasta, t):
    universo = pd.read_csv(Path(pasta) / "universo.csv")
    todas = pd.read_csv(Path(pasta) / "trades.csv", usecols=["saida"])
    trajetorias = pd.read_csv(Path(pasta) / "trajetorias.csv", usecols=["estimado"])
    saidas = todas["saida"].value_counts()
    nomes = {"alvo": "recomprada no alvo de 50%", "virou_po": "virou pó no vencimento",
             "exercida": "exercida (ação abaixo do strike)", "em_aberto": "ainda aberta (fora da análise)"}
    otm = (t["strike"] / t["spot_ent"] - 1)
    return ("## 1. Universo e operações\n\n"
            f"{len(universo)} ações: {', '.join(universo['simbolo'])}.\n\n"
            + tabela([[nomes.get(s, s), f"{n:,}".replace(",", "."), f"{n / saidas.sum():.0%}"] for s, n in saidas.items()],
                     ["Como a put terminou", "Puts", "%"])
            + f"\n\nPeríodo: {t['data_entrada'].min():%d/%m/%Y} a {t['data_saida'].max():%d/%m/%Y}. "
            f"Medianas na entrada: {(t['vencimento'] - t['data_entrada']).dt.days.median():.0f} dias até o vencimento, "
            f"strike {abs(otm.median()):.1%} abaixo da ação, prêmio de {((t['bid_ent'] + t['ask_ent']) / 2 / t['strike']).median():.2%} "
            f"do strike, spread de {t['spread_rel'].median():.1%} do preço da put. "
            f"Cotações diárias estimadas pelo sorriso de volatilidade: {trajetorias['estimado'].mean():.0%}.\n")


def secao_por_operacao(t):
    linhas = []
    for k, rotulo in ((0, "preço médio"), (0.5, "meio spread"), (1, "spread inteiro")):
        r_a, r_b = retornos(t, k)
        for chave, r in (("a", r_a), ("b", r_b)):
            linha = linha_resumo(f"Variante {chave.upper()}, k={k} ({rotulo})", r)
            dias = t[f"dias_{chave}"]
            linhas.append(linha + [f"{dias.mean():.0f}", pct(anualizado(r, dias)), pct(t[f"acao_{chave}"].mean()),
                                   pct(anualizado(t[f"acao_{chave}"], dias))])
    cab = CAB_RESUMO + ["Dias", "Anualizado", "Ação no mesmo período", "Ação anualizada"]
    return ("## 2. Resultado por operação (retorno sobre o strike, o capital travado)\n\n"
            f"- {VARIANTES['a']}\n- {VARIANTES['b']}\n"
            "- \"Ação no mesmo período\": quanto a própria ação rendeu entre a entrada e a saída da put "
            "(a referência: vender put tem que valer mais do que simplesmente ter a ação).\n"
            "- \"Anualizado\": retorno médio ÷ dias médios × 365 (aproximação simples).\n\n"
            + tabela(linhas, cab) + "\n")


def secao_decis(t, r_a):
    partes = ["## 3. Decis (variante A, k = 0,5)\n",
              "Se \"IV alta\" ajuda, o retorno deve melhorar nos decis de cima.\n"]
    for coluna, titulo in (("iv_rank", "IV rank (onde a IV de hoje está entre a mínima e a máxima de 1 ano)"),
                           ("iv_hv", "IV ÷ volatilidade histórica (HV)")):
        d = decis(t.assign(r=r_a), coluna, "r")
        dados = t.assign(r=r_a).dropna(subset=[coluna])
        faixa = pd.qcut(dados[coluna], 10, labels=False, duplicates="drop") + 1
        exercidas = (dados["saida"] == "exercida").groupby(faixa).mean()
        acao = dados["acao_a"].groupby(faixa).mean()
        linhas = [[i, f"{num(d.loc[i, 'de'])} a {num(d.loc[i, 'ate'])}", int(d.loc[i, "n"]), pct(d.loc[i, "media"], 2),
                   f"{d.loc[i, 'acerto']:.0%}", f"{exercidas.get(i, np.nan):.0%}", pct(acao.get(i, np.nan), 2)]
                  for i in d.index]
        partes.append(f"### {titulo}\n\n" + tabela(linhas, ["Decil", "Faixa", "n", "Média", "Acerto", "Exercidas",
                                                           "Ação no mesmo período"]) + "\n")
    return "\n".join(partes)


def secao_por_ano(t, r_a, r_b):
    linhas = []
    for ano, g in t.groupby(t["data_entrada"].dt.year):
        linhas.append([ano, len(g), pct(r_a[g.index].mean(), 2), f"{(r_a[g.index] > 0).mean():.0%}",
                       pct(r_b[g.index].mean(), 2), f"{(g['saida'] == 'exercida').mean():.0%}", pct(g["acao_a"].mean(), 2)])
    return ("## 4. Por ano (k = 0,5)\n\n2022 foi um ano de queda forte (bear market); 2023–2025, de alta.\n\n"
            + tabela(linhas, ["Ano", "Puts", "Média A", "Acerto A", "Média B", "Exercidas", "Ação no mesmo período"]) + "\n")


def secao_fora_da_amostra(t, r_a):
    corte = t["data_entrada"].quantile(0.5)
    treino, teste = t["data_entrada"] < corte, t["data_entrada"] >= corte
    limite = t.loc[treino, "iv_rank"].quantile(2 / 3)
    linhas = []
    for rotulo, periodo in (("Treino", treino), ("Teste (fora da amostra)", teste)):
        alta = periodo & (t["iv_rank"] >= limite)
        linhas.append(linha_resumo(f"{rotulo} — todas", r_a[periodo]) + [pct(t.loc[periodo, "acao_a"].mean(), 2)])
        linhas.append(linha_resumo(f"{rotulo} — IV rank ≥ {limite:.2f}", r_a[alta]) + [pct(t.loc[alta, "acao_a"].mean(), 2)])
    return ("## 5. Filtro de IV alta, com teste fora da amostra (variante A, k = 0,5)\n\n"
            f"Limite = terço mais alto do IV rank no TREINO (entradas antes de {corte:%d/%m/%Y}), "
            "aplicado congelado no TESTE.\n\n"
            + tabela(linhas, CAB_RESUMO + ["Ação no mesmo período"]) + "\n"), limite


def secao_carteira(pasta, t, limite):
    precos = pd.read_csv(Path(pasta) / "precos.csv", parse_dates=["date"])
    fechamento = precos.pivot_table(index="date", columns="act_symbol", values="close").sort_index()
    valorizador = Valorizador(pd.read_csv(Path(pasta) / "trajetorias.csv", parse_dates=["data"]), fechamento)
    r_a, r_b = retornos(t, 0.5)
    curvas = {
        "Puts — variante A, todas": simular_carteira(t, r_a, valorizador, "a"),
        f"Puts — variante A, só IV rank ≥ {limite:.2f}": simular_carteira(t, r_a, valorizador, "a", filtro=t["iv_rank"] >= limite),
        "Puts — variante B, todas (fica com a ação)": simular_carteira(t, r_b, valorizador, "b"),
    }
    datas = curvas["Puts — variante A, todas"].index
    universo = pd.read_csv(Path(pasta) / "universo.csv")["simbolo"]
    acoes = fechamento.reindex(columns=universo).ffill().reindex(datas, method="ffill")
    acoes = acoes.loc[:, acoes.iloc[0].notna()]
    curvas["Comprar e segurar as mesmas ações (pesos iguais)"] = (acoes / acoes.iloc[0]).mean(axis=1) * 100_000
    if REFERENCIA in fechamento:
        spy = fechamento[REFERENCIA].ffill().reindex(datas, method="ffill")
        curvas[f"Comprar e segurar o {REFERENCIA}"] = spy / spy.iloc[0] * 100_000
    linhas = []
    for nome, curva in curvas.items():
        m = metricas(curva)
        linhas.append([nome, f"US$ {curva.iloc[-1]:,.0f}".replace(",", "."), pct(m["cagr"]), pct(m["queda_max"], 0),
                       pct(m["vol"], 0, sinal=False), f"{m['sharpe']:.2f}", pct(m["ret_2022"], 0)])
    return ("## 6. Carteira (US$ 100.000, avaliada a mercado toda semana, k = 0,5)\n\n"
            "Cada put nova usa 5% do patrimônio como garantia (o tamanho que ela diz usar), sem passar de 100% "
            "(sem margem). Com mais candidatas que espaço, entram as de IV rank mais alta; uma posição por ação. "
            "Não inclui juros sobre o caixa de garantia (favoreceria as puts) nem dividendos (favoreceriam "
            "comprar e segurar).\n\n"
            + tabela(linhas, ["Carteira", "Capital final", "CAGR", "Queda máxima", "Volatilidade", "Sharpe", "2022"]) + "\n"), curvas


def gerar(pasta):
    t = carregar_trades(pasta)
    r_a, r_b = retornos(t, 0.5)
    secao5, limite = secao_fora_da_amostra(t, r_a)
    secao6, curvas = secao_carteira(pasta, t, limite)
    pd.DataFrame(curvas).to_csv(Path(pasta) / "curvas.csv")
    texto = "\n".join([
        "# Relatório do backtest — venda de puts em ações grandes (esqueleto da estratégia da Annie)\n",
        "Vende 1 put por ação por semana (delta ≈ −0,25, ~35 dias), recompra com 50% de lucro ou leva ao "
        "vencimento. Dados de fim de dia do DoltHub. Comissão de US$ 0,65 por contrato; k = fração do spread "
        "paga em cada execução. Não testa a parte discricionária (fluxo de baleias, GEX, Bookmap).\n",
        secao_universo(pasta, t),
        secao_por_operacao(t),
        secao_decis(t, r_a),
        secao_por_ano(t, r_a, r_b),
        secao5,
        secao6,
    ])
    (Path(pasta) / "relatorio.md").write_text(texto)
    return texto


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pasta", default="resultados_puts")
    print(gerar(parser.parse_args(argv).pasta))


if __name__ == "__main__":
    main()
