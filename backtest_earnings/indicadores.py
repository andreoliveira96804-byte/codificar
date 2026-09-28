"""Os 3 filtros do vídeo, calculados no momento da entrada.

1. ts_slope_0_45: inclinação da estrutura a termo da IV (volatilidade implícita),
   do primeiro vencimento até 45 dias. Negativa = IV curta acima da longa
   ("backwardation").
2. volume_medio_30: volume médio da ação nos últimos 30 pregões (liquidez).
3. iv30_rv30: IV de 30 dias dividida pela RV (volatilidade realizada) de 30 dias.
"""

import numpy as np
import pandas as pd


def yang_zhang(ohlc, janela=30, pregoes_ano=252):
    """Volatilidade realizada anualizada pelo estimador de Yang-Zhang.

    Usa abertura, máxima, mínima e fechamento dos últimos `janela` pregões
    (e o fechamento do pregão anterior a eles). Combina três partes:
    - o salto da noite (abertura vs. fechamento anterior),
    - o movimento do dia (fechamento vs. abertura),
    - o estimador de Rogers-Satchell (usa máxima e mínima).
    """
    ohlc = ohlc.tail(janela + 1)
    if len(ohlc) < janela + 1:
        return np.nan
    o, h, l, c = (ohlc[col].astype(float).values for col in ("open", "high", "low", "close"))
    noite = np.log(o[1:] / c[:-1])
    dia = np.log(c[1:] / o[1:])
    rs = np.log(h[1:] / c[1:]) * np.log(h[1:] / o[1:]) + np.log(l[1:] / c[1:]) * np.log(l[1:] / o[1:])
    n = janela
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    variancia = noite.var(ddof=1) + k * dia.var(ddof=1) + (1 - k) * rs.mean()
    return float(np.sqrt(variancia * pregoes_ano))


def sorriso(cadeia_vencimento, spot):
    """Curva IV x strike (o "sorriso de volatilidade") de UM vencimento.

    Em cada strike usa a IV da opção fora do dinheiro (OTM, "Out of The
    Money"): call acima do preço da ação, put abaixo, que é a mais confiável.
    Entre strikes interpola em linha reta; fora da faixa, repete a ponta.
    Devolve None se não houver IV nenhuma.
    """
    c = cadeia_vencimento[cadeia_vencimento["vol"] > 0]
    calls = c[c["call_put"] == "Call"].set_index("strike")["vol"]
    puts = c[c["call_put"] == "Put"].set_index("strike")["vol"]
    strikes = sorted(set(calls.index) | set(puts.index))
    if not strikes:
        return None
    ivs = []
    for k in strikes:
        preferida, outra = (calls, puts) if k >= spot else (puts, calls)
        ivs.append(preferida.get(k, outra.get(k)))
    ks, vs = np.array(strikes, float), np.array(ivs, float)
    return lambda strike: float(np.interp(strike, ks, vs))


def iv_atm_por_vencimento(cadeia, spot, data):
    """IV "no dinheiro" (ATM, "At The Money") de cada vencimento: o sorriso no preço da ação.

    Espera colunas: expiration, strike, call_put, vol.
    """
    linhas = []
    for vencimento, grupo in cadeia.groupby("expiration"):
        curva = sorriso(grupo, spot)
        dte = (pd.Timestamp(vencimento) - pd.Timestamp(data)).days
        if curva is not None and dte > 0:
            linhas.append({"expiration": pd.Timestamp(vencimento), "dte": dte, "iv_atm": curva(spot)})
    return pd.DataFrame(linhas, columns=["expiration", "dte", "iv_atm"]).sort_values("dte")


def estrutura_a_termo(dtes, ivs):
    """Curva IV x dias até o vencimento: interpolação linear, reta nas pontas."""
    dtes, ivs = np.asarray(dtes, float), np.asarray(ivs, float)
    return lambda dte: float(np.interp(dte, dtes, ivs))


def calcular_filtros(cadeia, spot, data, historico, janela=30):
    """Calcula os 3 filtros para um evento.

    cadeia: opções do dia da entrada (perto do dinheiro).
    historico: OHLCV diário da ação até o dia da entrada (inclusive).
    """
    atm = iv_atm_por_vencimento(cadeia, spot, data)
    resultado = {"ts_slope_0_45": np.nan, "iv30": np.nan, "dte_primeiro": np.nan, "n_vencimentos": len(atm)}
    if len(atm) >= 2 and atm["dte"].iloc[0] < 45:
        curva = estrutura_a_termo(atm["dte"], atm["iv_atm"])
        d0 = atm["dte"].iloc[0]
        resultado["ts_slope_0_45"] = (curva(45) - curva(d0)) / (45 - d0)
        resultado["iv30"] = curva(30)
        resultado["dte_primeiro"] = d0

    resultado["rv30"] = yang_zhang(historico, janela)
    resultado["volume_medio_30"] = float(historico["volume"].astype(float).tail(janela).mean()) if len(historico) >= janela else np.nan
    resultado["iv30_rv30"] = resultado["iv30"] / resultado["rv30"] if resultado["rv30"] else np.nan
    return resultado
