"""Calendário de pregões, calendário de resultados e datas de entrada/saída.

Como os dados são de fim de dia (EOD, "End Of Day"), a regra aproximada é:

- Resultado DEPOIS do fechamento (AMC, "After Market Close") no dia D:
    entrada = fechamento de D,             saída = fechamento do pregão seguinte.
- Resultado ANTES da abertura (BMO, "Before Market Open") no dia D:
    entrada = fechamento do pregão anterior, saída = fechamento de D.

Até ~set/2024 a base de opções só tem segundas, quartas e sextas. Por isso
aceitamos antecipar a entrada / adiar a saída em até `folga_max` pregões e
anotamos essa defasagem em cada operação.
"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

QUANDO = {"After market close": "AMC", "Before market open": "BMO"}


def dias_com_dados(cliente, db, tabela, inicio, fim):
    """Lista os dias úteis em que a tabela tem pelo menos uma linha."""
    dias = pd.bdate_range(inicio, fim)

    def tem_dados(dia):
        sql = f"SELECT 1 AS ok FROM {tabela} WHERE date='{dia:%Y-%m-%d}' LIMIT 1"
        return bool(cliente.consultar(db, sql))

    with ThreadPoolExecutor(cliente.paralelismo) as executor:
        presentes = list(executor.map(tem_dados, dias))
    return pd.DatetimeIndex([d for d, ok in zip(dias, presentes) if ok])


def consultar_paginado(cliente, db, sql_base, ordem, tamanho=999):
    """Busca todas as linhas de uma consulta em páginas de `tamanho` linhas."""
    linhas, deslocamento = [], 0
    while True:
        pagina = cliente.consultar(db, f"{sql_base} ORDER BY {ordem} LIMIT {tamanho} OFFSET {deslocamento}")
        linhas.extend(pagina)
        if len(pagina) < tamanho:
            return linhas
        deslocamento += tamanho


def carregar_eventos(cliente, inicio, fim):
    """Resultados trimestrais com horário conhecido (AMC ou BMO) entre `inicio` e `fim`."""
    meses = pd.date_range(pd.Timestamp(inicio).replace(day=1), fim, freq="MS")

    def do_mes(mes):
        ate = min(mes + pd.offsets.MonthEnd(0), pd.Timestamp(fim))
        de = max(mes, pd.Timestamp(inicio))
        sql = ("SELECT act_symbol, date, `when` FROM earnings_calendar "
               f"WHERE date BETWEEN '{de:%Y-%m-%d}' AND '{ate:%Y-%m-%d}' AND `when` IS NOT NULL")
        return consultar_paginado(cliente, "earnings", sql, "date, act_symbol")

    with ThreadPoolExecutor(cliente.paralelismo) as executor:
        linhas = [linha for lote in executor.map(do_mes, meses) for linha in lote]

    eventos = pd.DataFrame(linhas, columns=["act_symbol", "date", "when"])
    eventos = eventos.rename(columns={"act_symbol": "simbolo", "date": "data_anuncio", "when": "quando"})
    eventos["data_anuncio"] = pd.to_datetime(eventos["data_anuncio"])
    eventos["quando"] = eventos["quando"].map(QUANDO)
    return eventos.dropna(subset=["quando"]).drop_duplicates(["simbolo", "data_anuncio"]).reset_index(drop=True)


def definir_datas(eventos, dias_pregao, dias_opcoes, folga_max=2):
    """Acrescenta as datas de entrada e saída (ideais e efetivas) de cada evento.

    - data_entrada_ideal / data_saida_ideal: o que a regra pede.
    - data_entrada / data_saida: dias em que existe cadeia de opções, no máximo
      `folga_max` pregões antes da entrada ideal e depois da saída ideal.
    - defasagem_entrada / defasagem_saida: quantos pregões de diferença.
    """
    pregoes = np.array(sorted(dias_pregao), dtype="datetime64[ns]")
    tem_opcoes = np.isin(pregoes, np.array(sorted(dias_opcoes), dtype="datetime64[ns]"))
    anuncio = eventos["data_anuncio"].values.astype("datetime64[ns]")
    amc = (eventos["quando"] == "AMC").values

    # Índice (na lista de pregões) da entrada e da saída ideais.
    ultimo_ate = np.searchsorted(pregoes, anuncio, side="right") - 1   # último pregão <= D
    ultimo_antes = np.searchsorted(pregoes, anuncio, side="left") - 1  # último pregão < D
    primeiro_depois = np.searchsorted(pregoes, anuncio, side="right")  # primeiro pregão > D
    primeiro_desde = np.searchsorted(pregoes, anuncio, side="left")    # primeiro pregão >= D
    i_entrada = np.where(amc, ultimo_ate, ultimo_antes)
    i_saida = np.where(amc, primeiro_depois, primeiro_desde)

    n = len(pregoes)
    ent_ideal, sai_ideal, ent, sai, def_ent, def_sai = [], [], [], [], [], []
    for ie, is_ in zip(i_entrada, i_saida):
        valido = 0 <= ie < n and 0 <= is_ < n
        ent_ideal.append(pregoes[ie] if valido else np.datetime64("NaT"))
        sai_ideal.append(pregoes[is_] if valido else np.datetime64("NaT"))
        achou_e = next((ie - k for k in range(folga_max + 1) if valido and ie - k >= 0 and tem_opcoes[ie - k]), None)
        achou_s = next((is_ + k for k in range(folga_max + 1) if valido and is_ + k < n and tem_opcoes[is_ + k]), None)
        ent.append(pregoes[achou_e] if achou_e is not None else np.datetime64("NaT"))
        sai.append(pregoes[achou_s] if achou_s is not None else np.datetime64("NaT"))
        def_ent.append(ie - achou_e if achou_e is not None else np.nan)
        def_sai.append(achou_s - is_ if achou_s is not None else np.nan)

    eventos = eventos.copy()
    eventos["data_entrada_ideal"] = pd.to_datetime(ent_ideal)
    eventos["data_saida_ideal"] = pd.to_datetime(sai_ideal)
    eventos["data_entrada"] = pd.to_datetime(ent)
    eventos["data_saida"] = pd.to_datetime(sai)
    eventos["defasagem_entrada"] = def_ent
    eventos["defasagem_saida"] = def_sai
    return eventos
