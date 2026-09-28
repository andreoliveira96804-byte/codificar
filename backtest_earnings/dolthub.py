"""Cliente simples da API SQL do DoltHub (bases públicas da post-no-preference).

- Cada consulta é guardada em cache no disco (JSON compactado), então rodar de
  novo o backtest não baixa tudo outra vez.
- A API devolve no máximo 1.000 linhas por consulta. Quando o limite é atingido,
  levantamos LimiteDeLinhas para quem chamou dividir a consulta em pedaços menores.
"""

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL_BASE = "https://www.dolthub.com/api/v1alpha1/post-no-preference/{db}/master"


class LimiteDeLinhas(Exception):
    """A consulta passou de 1.000 linhas e veio cortada."""


class ErroConsulta(Exception):
    pass


class DoltHub:
    def __init__(self, pasta_cache="dados/cache", paralelismo=8, tentativas=5, so_cache=False):
        """so_cache=True: não baixa nada; consulta fora do cache devolve lista vazia."""
        self.pasta_cache = Path(pasta_cache)
        self.pasta_cache.mkdir(parents=True, exist_ok=True)
        self.paralelismo = paralelismo
        self.tentativas = tentativas
        self.so_cache = so_cache

    def _arquivo_cache(self, db, sql):
        chave = hashlib.sha1(f"{db}\n{sql}".encode()).hexdigest()
        return self.pasta_cache / chave[:2] / f"{chave}.json.gz"

    def consultar(self, db, sql):
        """Executa uma consulta SQL e devolve a lista de linhas (dicts com valores em texto)."""
        arquivo = self._arquivo_cache(db, sql)
        if arquivo.exists():
            try:
                with gzip.open(arquivo, "rt") as f:
                    return json.load(f)
            except (OSError, EOFError, json.JSONDecodeError):
                pass  # arquivo incompleto (outro processo ainda gravando): trata como fora do cache
        if self.so_cache:
            return []

        url = URL_BASE.format(db=db) + "?" + urllib.parse.urlencode({"q": sql})
        ultimo_erro = None
        for tentativa in range(self.tentativas):
            try:
                with urllib.request.urlopen(url, timeout=120) as resposta:
                    dados = json.load(resposta)
                status = dados.get("query_execution_status")
                if status == "RowLimit":
                    raise LimiteDeLinhas(sql[:200])
                if status != "Success":
                    raise ErroConsulta(f"{status}: {dados.get('query_execution_message', '')[:300]}")
                linhas = dados.get("rows", [])
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                temporario = arquivo.with_suffix(f".{os.getpid()}.tmp")
                with gzip.open(temporario, "wt") as f:
                    json.dump(linhas, f)
                os.replace(temporario, arquivo)  # grava de uma vez: quem lê nunca vê arquivo pela metade
                return linhas
            except LimiteDeLinhas:
                raise
            except (urllib.error.URLError, TimeoutError, ErroConsulta, json.JSONDecodeError) as erro:
                ultimo_erro = erro
                time.sleep(2 ** tentativa)
        raise ErroConsulta(f"falhou após {self.tentativas} tentativas: {ultimo_erro}")

    def consultar_varias(self, db, sqls):
        """Executa várias consultas em paralelo, mantendo a ordem dos resultados."""
        with ThreadPoolExecutor(self.paralelismo) as executor:
            return list(executor.map(lambda sql: self.consultar(db, sql), sqls))


def lista_sql(valores):
    """Formata uma lista de textos para usar dentro de IN (...)."""
    return ",".join("'" + str(v).replace("'", "''") + "'" for v in valores)
