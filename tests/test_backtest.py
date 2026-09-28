import numpy as np
import pandas as pd
import pytest

from backtest_earnings.analise import classificar, kelly, monte_carlo, queda_maxima
from backtest_earnings.estrategias import (black_scholes, cotar, escolher_contratos, preco_execucao,
                                           retorno_calendar, retorno_straddle)
from backtest_earnings.eventos import definir_datas
from backtest_earnings.indicadores import calcular_filtros, estrutura_a_termo, sorriso, yang_zhang


def cadeia_sintetica(data, spot, vencimentos, strikes, iv=0.3):
    """Cadeia com preços de Black-Scholes e spread de 2% (mínimo de US$ 0,02)."""
    linhas = []
    for venc in vencimentos:
        dias = (pd.Timestamp(venc) - pd.Timestamp(data)).days
        for k in strikes:
            for tipo in ("Call", "Put"):
                mid = black_scholes(spot, k, dias, iv, tipo)
                meio = max(0.01 * mid, 0.01)
                linhas.append({"date": pd.Timestamp(data), "act_symbol": "XYZ", "expiration": pd.Timestamp(venc),
                               "strike": float(k), "call_put": tipo, "bid": mid - meio, "ask": mid + meio, "vol": iv})
    return pd.DataFrame(linhas)


# --- indicadores -------------------------------------------------------------

def test_yang_zhang_preco_constante_da_zero():
    ohlc = pd.DataFrame({"open": [100.0] * 31, "high": [100.0] * 31, "low": [100.0] * 31, "close": [100.0] * 31})
    assert yang_zhang(ohlc) == pytest.approx(0.0)


def test_yang_zhang_recupera_volatilidade_simulada():
    # 1.500 dias, cada um com salto noturno e um caminho de 390 minutos durante o pregão
    rng = np.random.default_rng(1)
    sigma_noite, sigma_pregao, dias, passos = 0.01, 0.02, 1500, 390
    fechamento, linhas = 100.0, []
    for _ in range(dias):
        abertura = fechamento * np.exp(rng.normal(0, sigma_noite))
        caminho = abertura * np.exp(np.cumsum(rng.normal(0, sigma_pregao / np.sqrt(passos), passos)))
        fechamento = caminho[-1]
        linhas.append({"open": abertura, "high": max(abertura, caminho.max()),
                       "low": min(abertura, caminho.min()), "close": fechamento})
    esperado = np.sqrt((sigma_noite ** 2 + sigma_pregao ** 2) * 252)
    assert yang_zhang(pd.DataFrame(linhas), janela=dias - 1) == pytest.approx(esperado, rel=0.05)


def test_yang_zhang_sem_historico_suficiente():
    ohlc = pd.DataFrame({"open": [1.0] * 10, "high": [1.0] * 10, "low": [1.0] * 10, "close": [1.0] * 10})
    assert np.isnan(yang_zhang(ohlc, janela=30))


def test_estrutura_a_termo_interpola_e_repete_as_pontas():
    curva = estrutura_a_termo([10, 40], [0.6, 0.3])
    assert curva(25) == pytest.approx(0.45)
    assert curva(5) == pytest.approx(0.6)
    assert curva(90) == pytest.approx(0.3)


def test_sorriso_usa_opcao_fora_do_dinheiro():
    cadeia = pd.DataFrame({"strike": [90.0, 90.0, 110.0, 110.0], "call_put": ["Call", "Put", "Call", "Put"],
                           "vol": [0.9, 0.4, 0.3, 0.8]})
    curva = sorriso(cadeia, spot=100)
    assert curva(90) == pytest.approx(0.4)   # abaixo do preço: put
    assert curva(110) == pytest.approx(0.3)  # acima do preço: call
    assert curva(100) == pytest.approx(0.35)


def test_filtros_detectam_backwardation():
    data = pd.Timestamp("2025-01-02")
    curta = cadeia_sintetica(data, 100, ["2025-01-17"], [95, 100, 105], iv=0.6)
    longa = cadeia_sintetica(data, 100, ["2025-02-21"], [95, 100, 105], iv=0.3)
    historico = pd.DataFrame({"open": [100.0] * 31, "high": [101.0] * 31, "low": [99.0] * 31,
                              "close": [100.0] * 31, "volume": [2e6] * 31})
    f = calcular_filtros(pd.concat([curta, longa]), 100, data, historico)
    assert f["ts_slope_0_45"] < 0
    assert f["volume_medio_30"] == pytest.approx(2e6)
    assert f["iv30_rv30"] > 1


# --- eventos -----------------------------------------------------------------

def test_datas_de_entrada_e_saida_amc_e_bmo():
    pregoes = pd.bdate_range("2025-03-03", "2025-03-14")
    eventos = pd.DataFrame({"simbolo": ["A", "B"], "quando": ["AMC", "BMO"],
                            "data_anuncio": pd.to_datetime(["2025-03-05", "2025-03-05"])})
    d = definir_datas(eventos, pregoes, pregoes)
    assert list(d["data_entrada"]) == list(pd.to_datetime(["2025-03-05", "2025-03-04"]))
    assert list(d["data_saida"]) == list(pd.to_datetime(["2025-03-06", "2025-03-05"]))
    assert list(d["defasagem_entrada"]) == [0, 0]


def test_datas_usam_folga_quando_falta_dia_de_opcoes():
    pregoes = pd.bdate_range("2025-03-03", "2025-03-14")
    so_seg_qua_sex = [d for d in pregoes if d.weekday() in (0, 2, 4)]
    eventos = pd.DataFrame({"simbolo": ["A"], "quando": ["AMC"], "data_anuncio": [pd.Timestamp("2025-03-04")]})
    d = definir_datas(eventos, pregoes, so_seg_qua_sex, folga_max=2).iloc[0]
    assert d["data_entrada"] == pd.Timestamp("2025-03-03")  # terça sem dados -> segunda
    assert d["data_saida"] == pd.Timestamp("2025-03-05")    # quarta tem dados
    assert d["defasagem_entrada"] == 1 and d["defasagem_saida"] == 0


# --- estratégias --------------------------------------------------------------

def test_escolhe_front_depois_da_saida_back_30_dias_e_strike_mais_proximo():
    data = pd.Timestamp("2025-01-02")
    cadeia = cadeia_sintetica(data, 101.2, ["2025-01-10", "2025-01-17", "2025-02-14", "2025-03-21"], [95, 100, 105])
    c = escolher_contratos(cadeia, 101.2, data_saida=pd.Timestamp("2025-01-13"))
    assert c == {"front": pd.Timestamp("2025-01-17"), "back": pd.Timestamp("2025-02-14"), "strike": 100.0}


def test_cotar_devolve_cotacao_real_quando_existe():
    data = pd.Timestamp("2025-01-02")
    cadeia = cadeia_sintetica(data, 100, ["2025-01-17"], [95, 100, 105])
    bid, ask, estimado = cotar(cadeia, pd.Timestamp("2025-01-17"), 100.0, "Call", 100, data)
    linha = cadeia[(cadeia.strike == 100) & (cadeia.call_put == "Call")].iloc[0]
    assert (bid, ask, estimado) == (pytest.approx(linha.bid), pytest.approx(linha.ask), False)


def test_cotar_estima_strike_que_sumiu():
    data = pd.Timestamp("2025-01-02")
    cadeia = cadeia_sintetica(data, 100, ["2025-01-17"], [90, 95, 105, 110])  # sem o 100
    bid, ask, estimado = cotar(cadeia, pd.Timestamp("2025-01-17"), 100.0, "Call", 100, data)
    assert estimado
    assert (bid + ask) / 2 == pytest.approx(black_scholes(100, 100, 15, 0.3, "Call"), rel=1e-6)
    assert ask > bid


def test_preco_execucao():
    assert preco_execucao(1.0, 1.2, comprando=True, k=0) == pytest.approx(1.1)
    assert preco_execucao(1.0, 1.2, comprando=True, k=1) == pytest.approx(1.2)
    assert preco_execucao(1.0, 1.2, comprando=False, k=1) == pytest.approx(1.0)


def operacao(**cotacoes):
    return pd.DataFrame([cotacoes])


def test_retorno_straddle_vendido():
    # vende a 2 + 2 = 4, recompra a 1 + 1 = 2, comissão 4 x 0,65 / 100 = 0,026
    op = operacao(fc_bid_ent=2, fc_ask_ent=2, fp_bid_ent=2, fp_ask_ent=2,
                  fc_bid_sai=1, fc_ask_sai=1, fp_bid_sai=1, fp_ask_sai=1)
    assert retorno_straddle(op).iloc[0] == pytest.approx((4 - 2 - 0.026) / 4)


def test_retorno_calendar():
    # compra a longa a 5 e vende a curta a 3: débito 2; desmonta a 4.5 - 1 = 3.5
    op = operacao(bc_bid_ent=5, bc_ask_ent=5, fc_bid_ent=3, fc_ask_ent=3,
                  bc_bid_sai=4.5, bc_ask_sai=4.5, fc_bid_sai=1, fc_ask_sai=1)
    assert retorno_calendar(op).iloc[0] == pytest.approx((3.5 - 2 - 0.026) / 2)


# --- análise ------------------------------------------------------------------

def test_kelly_aposta_binaria():
    # ganha 100% com 60% de chance, perde 100% com 40%: Kelly = 0,6 - 0,4 = 0,2
    r = np.array([1.0] * 60 + [-1.0] * 40)
    assert kelly(r) == pytest.approx(0.2, abs=1e-3)


def test_kelly_zero_quando_media_negativa():
    assert kelly(np.array([0.1, -0.5, 0.2])) == 0.0


def test_queda_maxima():
    assert queda_maxima([100, 120, 90, 130, 65]) == pytest.approx(0.5)


def test_monte_carlo_por_temporada():
    r = pd.Series([0.1, -0.1, 0.2, -0.2])
    temporadas = pd.Series(["T1", "T1", "T2", "T2"])
    sim = monte_carlo(r, 0.1, n_trades=10, n_caminhos=50, grupos=temporadas)
    assert len(sim) == 50 and (sim["capital_final"] > 0).all()


def test_classificar():
    df = pd.DataFrame({"volume_medio_30": [2e6, 2e6, 1e5], "iv30_rv30": [1.5, 1.0, 1.5],
                       "ts_slope_0_45": [-0.01, -0.01, 0.0]})
    limites = {"volume_medio_30": 1.5e6, "iv30_rv30": 1.25, "ts_slope_0_45": -0.005}
    assert list(classificar(df, limites)) == ["Recommended", "Consider", "Avoid"]


def test_dolthub_tenta_de_novo_quando_o_servidor_derruba_a_conexao(tmp_path, monkeypatch):
    import http.client
    import io
    import json as json_lib

    from backtest_earnings import dolthub

    chamadas = []

    def urlopen_falso(url, timeout):
        chamadas.append(url)
        if len(chamadas) == 1:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return io.BytesIO(json_lib.dumps({"query_execution_status": "Success", "rows": [{"a": "1"}]}).encode())

    monkeypatch.setattr(dolthub.urllib.request, "urlopen", urlopen_falso)
    monkeypatch.setattr(dolthub.time, "sleep", lambda s: None)
    cliente = dolthub.DoltHub(tmp_path)
    assert cliente.consultar("options", "SELECT 1") == [{"a": "1"}]
    assert len(chamadas) == 2


def test_dolthub_guarda_o_aviso_de_limite_de_linhas(tmp_path, monkeypatch):
    import io
    import json as json_lib

    from backtest_earnings import dolthub

    chamadas = []

    def urlopen_falso(url, timeout):
        chamadas.append(url)
        return io.BytesIO(json_lib.dumps({"query_execution_status": "RowLimit", "rows": []}).encode())

    monkeypatch.setattr(dolthub.urllib.request, "urlopen", urlopen_falso)
    cliente = dolthub.DoltHub(tmp_path)
    for _ in range(2):
        with pytest.raises(dolthub.LimiteDeLinhas):
            cliente.consultar("options", "SELECT muita_coisa")
    assert len(chamadas) == 1  # a segunda vez nem vai à internet
    assert cliente.em_cache("options", "SELECT muita_coisa")
