"""Estatísticas do backtest: resumo, decis, filtros, Kelly e Monte Carlo."""

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

# Limites do script que acompanha o vídeo.
LIMITES_VIDEO = {"volume_medio_30": 1_500_000, "iv30_rv30": 1.25, "ts_slope_0_45": -0.00406}


def resumo(retornos):
    """Estatísticas básicas de uma série de retornos por operação."""
    r = pd.Series(retornos).dropna()
    if r.empty:
        return {"n": 0}
    return {
        "n": len(r),
        "media": r.mean(),
        "mediana": r.median(),
        "desvio": r.std(),
        "acerto": (r > 0).mean(),
        "p1": r.quantile(0.01),
        "p5": r.quantile(0.05),
        "pior": r.min(),
        "melhor": r.max(),
    }


def decis(df, coluna, retorno, grupos=10):
    """Divide os eventos em `grupos` faixas iguais de `coluna` e mede o retorno de cada uma."""
    dados = df[[coluna, retorno]].dropna()
    faixa = pd.qcut(dados[coluna], grupos, labels=False, duplicates="drop")
    tabela = dados.groupby(faixa).agg(
        de=(coluna, "min"), ate=(coluna, "max"), n=(retorno, "size"),
        media=(retorno, "mean"), mediana=(retorno, "median"),
        acerto=(retorno, lambda r: (r > 0).mean()),
    )
    tabela.index = tabela.index + 1
    tabela.index.name = "decil"
    return tabela


def passa_filtros(df, limites):
    """Três colunas booleanas: se cada evento passa em cada filtro."""
    return pd.DataFrame({
        "volume": df["volume_medio_30"] >= limites["volume_medio_30"],
        "iv_rv": df["iv30_rv30"] >= limites["iv30_rv30"],
        "slope": df["ts_slope_0_45"] <= limites["ts_slope_0_45"],
    })


def classificar(df, limites):
    """Classes do scanner do vídeo.

    Recommended: passa nos 3 filtros.
    Consider: passa em 2, sendo um deles a inclinação.
    Avoid: não passa na inclinação (ou só passa nela).
    """
    f = passa_filtros(df, limites)
    n = f.sum(axis=1)
    return pd.Series(np.where(n == 3, "Recommended", np.where(f["slope"] & (n == 2), "Consider", "Avoid")),
                     index=df.index)


def limites_por_quantil(df, q_slope=1 / 3, q_iv_rv=2 / 3, q_volume=1 / 2):
    """Recalibra os limites com os dados (sem otimizar retorno, para evitar sobreajuste):

    inclinação no terço mais negativo, IV30/RV30 no terço mais alto e volume
    acima da mediana. Os quantis são fixados ANTES de olhar o resultado.
    """
    return {
        "ts_slope_0_45": df["ts_slope_0_45"].quantile(q_slope),
        "iv30_rv30": df["iv30_rv30"].quantile(q_iv_rv),
        "volume_medio_30": df["volume_medio_30"].quantile(q_volume),
    }


def kelly(retornos):
    """Fração de Kelly: a que maximiza o crescimento médio do log do capital, E[log(1 + f·r)].

    Aqui f é a fração do capital colocada em risco como prêmio (straddle) ou
    débito (calendar). Como uma perda pode passar de 100% do valor em risco,
    limitamos f para que o pior retorno observado não zere a conta.
    """
    r = pd.Series(retornos).dropna().values
    if len(r) == 0 or r.mean() <= 0:
        return 0.0
    f_max = 0.999 / -r.min() if r.min() < 0 else 10.0
    resultado = minimize_scalar(lambda f: -np.mean(np.log1p(f * r)), bounds=(0, f_max), method="bounded")
    return float(resultado.x)


def curva_capital(retornos_por_dia, fracao, capital=10_000):
    """Evolução do capital apostando `fracao` em cada operação (juros compostos).

    Operações que entram no mesmo dia dividem o mesmo capital.
    """
    return capital * np.cumprod(1 + fracao * np.asarray(retornos_por_dia))


def queda_maxima(curva):
    """Maior queda do pico ao fundo (drawdown máximo), em fração."""
    curva = np.asarray(curva, float)
    pico = np.maximum.accumulate(curva, axis=-1)
    return (1 - curva / pico).max(axis=-1)


def monte_carlo(retornos, fracao, n_trades, n_caminhos=10_000, capital=10_000, grupos=None, semente=0):
    """Simula `n_caminhos` futuros possíveis sorteando operações do histórico.

    - grupos=None: sorteia operações soltas (como no vídeo).
    - grupos=<Series com o rótulo da temporada de cada operação>: sorteia
      TEMPORADAS inteiras ("block bootstrap"). Assim perdas que aconteceram
      juntas continuam juntas, e a queda máxima fica mais realista.
    Devolve capital final e queda máxima de cada caminho.
    """
    rng = np.random.default_rng(semente)
    r = pd.Series(retornos).dropna()
    if grupos is None:
        sorteio = rng.choice(r.values, size=(n_caminhos, n_trades))
    else:
        blocos = [g.values for _, g in r.groupby(grupos.loc[r.index])]
        sorteio = np.empty((n_caminhos, n_trades))
        for i in range(n_caminhos):
            caminho = []
            while len(caminho) < n_trades:
                caminho.extend(blocos[rng.integers(len(blocos))])
            sorteio[i] = caminho[:n_trades]
    fatores = np.maximum(1 + fracao * sorteio, 0)  # capital não fica negativo: quebrou, parou
    curvas = capital * np.cumprod(fatores, axis=1)
    curvas = np.concatenate([np.full((n_caminhos, 1), float(capital)), curvas], axis=1)
    return pd.DataFrame({"capital_final": curvas[:, -1], "queda_maxima": queda_maxima(curvas)})


def resumo_monte_carlo(sim, capital=10_000):
    return {
        "capital_mediano": sim["capital_final"].median(),
        "capital_p5": sim["capital_final"].quantile(0.05),
        "capital_p95": sim["capital_final"].quantile(0.95),
        "prob_prejuizo": (sim["capital_final"] < capital).mean(),
        "prob_quebra": (sim["capital_final"] < 0.05 * capital).mean(),
        "queda_max_mediana": sim["queda_maxima"].median(),
        "prob_queda_50": (sim["queda_maxima"] > 0.5).mean(),
    }
