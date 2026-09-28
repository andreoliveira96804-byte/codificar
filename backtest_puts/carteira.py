"""Retorno por operação e simulação de carteira da venda de puts.

Toda put vendida é "coberta por caixa" (cash-secured): reserva strike x 100 em
dinheiro como garantia. Por isso o retorno de cada operação é medido sobre o
strike (o capital travado).
"""

import numpy as np
import pandas as pd

from backtest_earnings.estrategias import COMISSAO_POR_CONTRATO, preco_execucao

COMISSAO_POR_ACAO = COMISSAO_POR_CONTRATO / 100


def carregar_trades(pasta):
    t = pd.read_csv(f"{pasta}/trades.csv", parse_dates=["data_entrada", "vencimento", "data_saida", "data_saida_b"])
    t = t[t["saida"] != "em_aberto"].copy()
    t["dias_a"] = (t["data_saida"] - t["data_entrada"]).dt.days
    t["dias_b"] = (t["data_saida_b"] - t["data_entrada"]).dt.days
    t["acao_a"] = t["spot_sai"] / t["spot_ent"] - 1      # a ação no mesmo período (referência)
    t["acao_b"] = t["spot_sai_b"] / t["spot_ent"] - 1
    t["iv_hv"] = t["iv_atual"] / t["hv_atual"]
    t["spread_rel"] = (t["ask_ent"] - t["bid_ent"]) / ((t["ask_ent"] + t["bid_ent"]) / 2)
    return t


def retornos(t, k=0.5):
    """Retorno de cada put sobre o strike.

    Variante A: se for exercida, vende a ação no vencimento (realiza o prejuízo).
    Variante B: se for exercida, fica com a ação até ela voltar ao strike (máx. ~6 meses).
    """
    credito = preco_execucao(t["bid_ent"], t["ask_ent"], False, k)
    no_alvo = t["saida"] == "alvo"
    recompra = np.where(no_alvo, preco_execucao(t["bid_sai"], t["ask_sai"], True, k),
                        np.maximum(t["strike"] - t["spot_venc"], 0))
    comissao = np.where(no_alvo, 2, 1) * COMISSAO_POR_ACAO
    r_a = (credito - recompra - comissao) / t["strike"]
    exercida = t["saida"] == "exercida"
    r_b = np.where(exercida, (credito - COMISSAO_POR_ACAO + t["spot_sai_b"] - t["strike"]) / t["strike"], r_a)
    return pd.Series(r_a, index=t.index), pd.Series(r_b, index=t.index)


class Valorizador:
    """Valor de mercado de uma put aberta numa data (para avaliar a carteira toda semana)."""

    def __init__(self, trajetorias, fechamento):
        self.fechamento = fechamento.ffill()
        self.pontos = {i: (g["data"].values, ((g["bid"] + g["ask"]) / 2).values)
                       for i, g in trajetorias.groupby("id")}

    def preco(self, simbolo, data):
        serie = self.fechamento[simbolo]
        i = serie.index.searchsorted(data, side="right") - 1
        return float(serie.iat[i]) if i >= 0 else np.nan

    def retorno_aberto(self, op, data, variante):
        """Retorno ainda não realizado (sobre o strike) de uma operação aberta em `data`."""
        credito_mid = (op.bid_ent + op.ask_ent) / 2
        if variante == "b" and op.saida == "exercida" and data >= op.vencimento:
            return (credito_mid + self.preco(op.simbolo, data) - op.strike) / op.strike
        datas, mids = self.pontos.get(op.id, (np.array([], "datetime64[ns]"), np.array([])))
        i = np.searchsorted(datas, np.datetime64(data), side="right") - 1
        if i < 0:
            mid = credito_mid  # ainda sem cotação depois da entrada: sem ganho nem perda
        elif i == len(datas) - 1 and np.datetime64(data) > datas[-1]:
            # a trajetória acabou: é a reta final (~11 dias) em que o vencimento some da base,
            # então usa o valor intrínseco
            mid = max(op.strike - self.preco(op.simbolo, data), 0.0)
        else:
            mid = mids[i]
        return (credito_mid - mid) / op.strike


def simular_carteira(t, r_final, valorizador, variante="a", fracao=0.05, capital=100_000, filtro=None):
    """Carteira semanal: cada put nova usa `fracao` do patrimônio como garantia, sem passar de
    100% do patrimônio (sem margem). Com mais candidatas que espaço, prefere a IV rank mais alta.
    Uma posição por ação de cada vez. Devolve o patrimônio semana a semana (a mercado)."""
    t = t.assign(r_final=r_final, fim=t["data_saida_b"] if variante == "b" else t["data_saida"])
    if filtro is not None:
        t = t[filtro]
    datas = sorted(set(t["data_entrada"]))
    caixa, abertas, curva = float(capital), [], []
    for data in datas:
        ainda = []
        for op, alocado in abertas:
            if op.fim <= data:
                caixa += alocado * op.r_final
            else:
                ainda.append((op, alocado))
        abertas = ainda
        patrimonio = caixa + sum(a * valorizador.retorno_aberto(op, data, variante) for op, a in abertas)
        em_uso = sum(a for _, a in abertas)
        ocupadas = {op.simbolo for op, _ in abertas}
        candidatas = t[t["data_entrada"] == data].sort_values("iv_rank", ascending=False)
        for op in candidatas.itertuples():
            alocar = fracao * patrimonio
            if em_uso + alocar > patrimonio:
                break
            if op.simbolo in ocupadas:
                continue
            abertas.append((op, alocar))
            ocupadas.add(op.simbolo)
            em_uso += alocar
        curva.append((data, patrimonio))
    return pd.Series(dict(curva)).sort_index()


def metricas(curva):
    """CAGR (crescimento anual composto), queda máxima, volatilidade e Sharpe anuais."""
    curva = curva.dropna()
    anos = (curva.index[-1] - curva.index[0]).days / 365.25
    semanais = curva.pct_change().dropna()
    pico = curva.cummax()
    ano_2022 = curva[curva.index.year == 2022]
    return {
        "final": curva.iloc[-1] / curva.iloc[0],
        "cagr": (curva.iloc[-1] / curva.iloc[0]) ** (1 / anos) - 1 if anos > 0 else np.nan,
        "queda_max": (curva / pico - 1).min(),
        "vol": semanais.std() * np.sqrt(52),
        "sharpe": semanais.mean() / semanais.std() * np.sqrt(52) if semanais.std() > 0 else np.nan,
        "ret_2022": ano_2022.iloc[-1] / ano_2022.iloc[0] - 1 if len(ano_2022) > 1 else np.nan,
    }
