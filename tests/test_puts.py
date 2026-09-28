import numpy as np
import pandas as pd
import pytest

from backtest_puts.carteira import Valorizador, metricas, retornos, simular_carteira
from backtest_puts.executar import Painel, escolher_put, simular


def puts_do_dia(data, simbolo, vencimento, linhas):
    """linhas: [(strike, bid, ask, delta)]"""
    return [{"date": pd.Timestamp(data), "act_symbol": simbolo, "expiration": pd.Timestamp(vencimento),
             "strike": k, "call_put": "Put", "bid": b, "ask": a, "vol": 0.3, "delta": d} for k, b, a, d in linhas]


def precos(simbolo, fechamentos):
    return pd.DataFrame([{"date": pd.Timestamp(d), "act_symbol": simbolo, "close": c} for d, c in fechamentos.items()])


def test_escolher_put_vencimento_e_delta():
    data = pd.Timestamp("2025-01-06")
    cadeia = pd.DataFrame(
        puts_do_dia(data, "X", "2025-01-17", [(95, 1.0, 1.1, -0.25)])                        # 11 dias: fora da faixa
        + puts_do_dia(data, "X", "2025-02-07", [(90, 0.5, 0.6, -0.15), (95, 1.0, 1.1, -0.27),
                                                (97, 1.5, 1.6, -0.33)])                        # 32 dias: o escolhido
        + puts_do_dia(data, "X", "2025-03-21", [(95, 2.0, 2.2, -0.25)]))                       # 74 dias: fora da faixa
    put = escolher_put(cadeia, data)
    assert put["expiration"] == pd.Timestamp("2025-02-07") and put["strike"] == 95


def test_escolher_put_sem_delta_na_faixa():
    data = pd.Timestamp("2025-01-06")
    cadeia = pd.DataFrame(puts_do_dia(data, "X", "2025-02-07", [(80, 0.1, 0.2, -0.05)]))
    assert escolher_put(cadeia, data) is None


def montar(fechamentos, cotacoes):
    """cotacoes: {data: (bid, ask)} da put 95 com vencimento 07/02/2025."""
    linhas = []
    for data, (bid, ask) in cotacoes.items():
        linhas += puts_do_dia(data, "X", "2025-02-07", [(90, bid / 2, ask / 2, -0.1), (95, bid, ask, -0.25)])
    return Painel(pd.DataFrame(linhas), precos("X", fechamentos))


def test_simular_sai_no_alvo_de_50_por_cento():
    painel = montar({"2025-01-06": 100, "2025-01-08": 102, "2025-01-10": 104, "2025-02-07": 105},
                    {"2025-01-06": (1.0, 1.0), "2025-01-08": (0.7, 0.7), "2025-01-10": (0.45, 0.45)})
    put = painel.cadeia("X", pd.Timestamp("2025-01-06")).iloc[1]
    op, trajetoria = simular("X", pd.Timestamp("2025-01-06"), put, painel)
    assert op["saida"] == "alvo" and op["data_saida"] == pd.Timestamp("2025-01-10")
    assert len(trajetoria) == 2


def test_simular_exercida_e_variante_b_espera_voltar_ao_strike():
    fechamentos = {"2025-01-06": 100, "2025-01-08": 97, "2025-02-07": 90, "2025-02-10": 93, "2025-02-11": 96}
    painel = montar(fechamentos, {"2025-01-06": (1.0, 1.0), "2025-01-08": (2.0, 2.0)})
    put = painel.cadeia("X", pd.Timestamp("2025-01-06")).iloc[1]
    op, _ = simular("X", pd.Timestamp("2025-01-06"), put, painel)
    assert op["saida"] == "exercida" and op["spot_venc"] == 90
    assert op["data_saida_b"] == pd.Timestamp("2025-02-11") and op["spot_sai_b"] == 96


def test_retornos_variantes():
    t = pd.DataFrame({"saida": ["alvo", "virou_po", "exercida"], "bid_ent": [1.0, 1.0, 1.0], "ask_ent": [1.0, 1.0, 1.0],
                      "bid_sai": [0.5, np.nan, np.nan], "ask_sai": [0.5, np.nan, np.nan], "strike": [100.0] * 3,
                      "spot_venc": [np.nan, 105.0, 90.0], "spot_sai_b": [np.nan, 105.0, 101.0]})
    r_a, r_b = retornos(t, k=0)
    c = 0.0065
    assert r_a.tolist() == pytest.approx([(1 - 0.5 - 2 * c) / 100, (1 - c) / 100, (1 - 10 - c) / 100])
    assert r_b.iloc[2] == pytest.approx((1 - c + 101 - 100) / 100)


def test_carteira_respeita_limite_de_garantia():
    datas = [pd.Timestamp("2025-01-06")] * 30 + [pd.Timestamp("2025-01-13")]
    t = pd.DataFrame({"id": range(31), "simbolo": [f"S{i}" for i in range(31)], "data_entrada": datas,
                      "data_saida": [pd.Timestamp("2025-03-01")] * 31, "data_saida_b": [pd.Timestamp("2025-03-01")] * 31,
                      "vencimento": [pd.Timestamp("2025-03-01")] * 31, "iv_rank": np.linspace(1, 0, 31),
                      "strike": [100.0] * 31, "bid_ent": [1.0] * 31, "ask_ent": [1.0] * 31, "saida": ["virou_po"] * 31})
    trajetorias = pd.DataFrame({"id": [0], "data": [pd.Timestamp("2025-01-13")], "bid": [1.0], "ask": [1.0]})
    fechamento = pd.DataFrame({f"S{i}": [100.0] for i in range(31)}, index=[pd.Timestamp("2025-01-06")])
    curva = simular_carteira(t, pd.Series(0.01, index=t.index), Valorizador(trajetorias, fechamento), fracao=0.05)
    assert list(curva.index) == [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-13")]
    assert curva.iloc[-1] == pytest.approx(100_000)  # 20 posições abertas (100%), nada realizado ainda


def test_metricas():
    curva = pd.Series([100.0, 110.0, 88.0, 121.0], index=pd.date_range("2022-01-03", periods=4, freq="W-MON"))
    m = metricas(curva)
    assert m["final"] == pytest.approx(1.21)
    assert m["queda_max"] == pytest.approx(-0.2)


def test_confirma_so_o_desdobramento_que_aparece_no_preco():
    from backtest_puts.executar import ajustar_desdobramentos, confirmar_desdobramentos

    datas = pd.bdate_range("2024-06-03", "2024-06-14")
    fechamentos = [1150, 1160, 1224, 1210, 1209, 121.8, 120.9, 125.2, 129.6, 131.9]
    p = pd.DataFrame({"date": datas, "act_symbol": "NVDA", "close": fechamentos, "volume": 1e6})
    registros = pd.DataFrame({"act_symbol": ["NVDA", "NVDA"], "razao": [10.0, 10.0],
                              "ex_date": pd.to_datetime(["2024-05-24", "2024-06-10"])})  # registro duplicado
    d = confirmar_desdobramentos(p, registros)
    assert len(d) == 1 and d.iloc[0]["data"] == pd.Timestamp("2024-06-10") and d.iloc[0]["razao"] == 10
    ajustado = ajustar_desdobramentos(p, d, ["close"], "volume")
    assert ajustado["close"].iloc[0] == pytest.approx(115.0)
    assert ajustado["close"].iloc[-1] == pytest.approx(131.9)
    assert ajustado["volume"].iloc[0] == pytest.approx(1e7)
