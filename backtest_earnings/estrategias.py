"""Straddle vendido e calendar de call comprado: contratos, cotações e retorno.

Nomes das colunas de cotação em cada operação:
    fc = call do vencimento curto (front), fp = put do vencimento curto,
    bc = call do vencimento longo (back).
    Sufixos: _bid_ent / _ask_ent (entrada), _bid_sai / _ask_sai (saída) e
    _est_ent / _est_sai (True quando a cotação foi ESTIMADA, ver `cotar`).
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from .indicadores import sorriso

COMISSAO_POR_CONTRATO = 0.65  # US$, parecido com a Interactive Brokers
EXECUCOES = 4                 # 2 pernas para abrir + 2 pernas para fechar
TAXA_JUROS = 0.04             # juros anuais usados no Black-Scholes (efeito pequeno em prazos curtos)


def escolher_contratos(cadeia, spot, data_saida, distancia_back=30):
    """Escolhe strike e vencimentos da operação.

    - vencimento curto: o primeiro que vence DEPOIS da saída;
    - vencimento longo: o mais próximo de (curto + `distancia_back` dias);
    - strike: o mais próximo do preço da ação entre os que têm call e put no
      vencimento curto.
    Devolve None quando não dá para montar.
    """
    exp = pd.to_datetime(cadeia["expiration"])
    futuros = sorted(v for v in exp.unique() if v > pd.Timestamp(data_saida))
    if len(futuros) < 2:
        return None
    front = futuros[0]
    alvo = front + pd.Timedelta(days=distancia_back)
    back = min(futuros[1:], key=lambda v: abs((v - alvo).days))

    curto = cadeia[exp == front]
    comuns = np.array(sorted(set(curto.loc[curto["call_put"] == "Call", "strike"])
                             & set(curto.loc[curto["call_put"] == "Put", "strike"])))
    if len(comuns) == 0:
        return None
    strike = comuns[np.argmin(np.abs(comuns - spot))]
    return {"front": front, "back": back, "strike": float(strike)}


def black_scholes(spot, strike, dias, sigma, tipo, taxa=TAXA_JUROS):
    """Preço teórico de uma opção europeia (sem dividendos)."""
    t = max(dias, 0.5) / 365
    d1 = (np.log(spot / strike) + (taxa + sigma ** 2 / 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    if tipo == "Call":
        return spot * norm.cdf(d1) - strike * np.exp(-taxa * t) * norm.cdf(d2)
    return strike * np.exp(-taxa * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def cotar(cadeia, vencimento, strike, tipo, spot, data):
    """Devolve (bid, ask, estimado) de uma opção num dia.

    A base do DoltHub só guarda ~20 strikes por vencimento, e eles mudam de um
    dia para o outro. Quando a ação anda muito, o strike da entrada pode sumir
    na saída — justamente nas maiores perdas. Descartar esses casos deixaria o
    resultado otimista demais, então estimamos o preço:
      mid = Black-Scholes com a IV do sorriso daquele dia no nosso strike;
      spread = média dos spreads das 2 opções do mesmo tipo mais próximas.
    """
    venc = cadeia[cadeia["expiration"] == vencimento]
    if venc.empty:
        return np.nan, np.nan, False
    exata = venc[(venc["strike"] == strike) & (venc["call_put"] == tipo)]
    if not exata.empty:
        bid, ask = exata["bid"].iloc[0], exata["ask"].iloc[0]
        if pd.notna(bid) and pd.notna(ask) and ask > 0 and ask >= bid:
            return float(bid), float(ask), False

    curva = sorriso(venc, spot)
    if curva is None:
        return np.nan, np.nan, False
    dias = (pd.Timestamp(vencimento) - pd.Timestamp(data)).days
    mid = black_scholes(spot, strike, dias, curva(strike), tipo)
    mesmas = venc[(venc["call_put"] == tipo) & venc["bid"].notna() & (venc["ask"] >= venc["bid"])]
    if mesmas.empty:
        meio_spread = 0.05 * mid
    else:
        vizinhas = mesmas.iloc[np.argsort(np.abs(mesmas["strike"].values - strike))[:2]]
        meio_spread = float(((vizinhas["ask"] - vizinhas["bid"]) / 2).mean())
    return max(mid - meio_spread, 0.0), mid + meio_spread, True


def preco_execucao(bid, ask, comprando, k):
    """Preço médio (mid) ± k × meio spread.

    k = 0   -> executa no mid (otimista);
    k = 0.5 -> paga metade do spread (realista);
    k = 1   -> compra no ask e vende no bid (pessimista).
    """
    mid = (bid + ask) / 2
    meio = (ask - bid) / 2
    return mid + k * meio if comprando else mid - k * meio


def custo_comissao(comissao=COMISSAO_POR_CONTRATO):
    """Comissão total por ação (1 contrato = 100 ações)."""
    return EXECUCOES * comissao / 100


def retorno_straddle(df, k=0.5, comissao=COMISSAO_POR_CONTRATO):
    """Straddle VENDIDO: retorno sobre o prêmio recebido (pode passar de -100%)."""
    credito = (preco_execucao(df["fc_bid_ent"], df["fc_ask_ent"], False, k)
               + preco_execucao(df["fp_bid_ent"], df["fp_ask_ent"], False, k))
    recompra = (preco_execucao(df["fc_bid_sai"], df["fc_ask_sai"], True, k)
                + preco_execucao(df["fp_bid_sai"], df["fp_ask_sai"], True, k))
    retorno = (credito - recompra - custo_comissao(comissao)) / credito
    return retorno.where(credito > 0)


def retorno_calendar(df, k=0.5, comissao=COMISSAO_POR_CONTRATO):
    """Calendar de call COMPRADO: retorno sobre o débito pago (perda máx. ≈ -100% - comissões)."""
    debito = (preco_execucao(df["bc_bid_ent"], df["bc_ask_ent"], True, k)
              - preco_execucao(df["fc_bid_ent"], df["fc_ask_ent"], False, k))
    desmonte = (preco_execucao(df["bc_bid_sai"], df["bc_ask_sai"], False, k)
                - preco_execucao(df["fc_bid_sai"], df["fc_ask_sai"], True, k))
    retorno = (desmonte - debito - custo_comissao(comissao)) / debito
    return retorno.where(debito > 0)
