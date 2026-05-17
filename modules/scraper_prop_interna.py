# =============================================================================
# modules/scraper_prop_interna.py — CMS BI Project
# Scraper para o sistema de Proposições Legislativas da CMS Salvador.
#
# ALVO:
#   https://cmsalvador.sys.inf.br/cl/prop_interna/
#
# TECNOLOGIA:
#   ScriptCase — MESMO framework dos outros scrapers da CMS.
#   Página 1: dados embutidos no HTML do GET inicial.
#   Páginas seguintes: POST AJAX (nmgp_opcao=ajax_navigate, opc=nav_next).
#   Resposta AJAX: JSON com chave "setValue" contendo fragmentos HTML.
#
# ESTRUTURA DA TABELA HTML (confirmada via diagnóstico):
#   <TABLE class="scGridTabela">               ← tabela de dados
#     <TR class="scGridLabel ...">             ← cabeçalhos
#       <TD><div style="flex-grow:1">Proposição</div></TD>
#     <TR class="scGridFieldOdd|Even">         ← dados
#       <TD><span id="id_sc_field_proposicao_N">PIN-210/2026</span></TD>
#
# COLUNAS REAIS (confirmadas via diagnóstico em 2026-05-17):
#   proposição | autor | ementa | movimentado | localização | situação
#   autor/requerente/vistas/outros
#
# ESCOPO TEMPORAL:
#   A lista está ordenada por data DESC (mais recentes primeiro).
#   Paginação para quando encontra registros anteriores a ANO_INICIO_LEGISLATURA.
# =============================================================================

import re
import json
import time
import random
import logging
import os
from typing import Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

import config

os.makedirs(config.LOG_DIR, exist_ok=True)
_logger = logging.getLogger("ProposicaoInternaScraper")


# =============================================================================
# SCRAPER PRINCIPAL
# =============================================================================

class ProposicaoInternaScraper:
    """
    Coleta proposições legislativas da CMS Salvador (legislatura 2025+).

    Usa o mesmo protocolo ScriptCase dos outros scrapers:
      - script_case_init extraído do HTML (valor observado: "905")
      - Paginação via POST AJAX com opc=nav_next
      - Para automaticamente ao encontrar registros anteriores a 2025
    """

    # Valor de script_case_init observado no HTML da página (fallback)
    _SC_INIT_PADRAO = "905"

    def __init__(self):
        self.base_url    = config.URL_PROP_INTERNA
        self._ano_inicio = config.ANO_INICIO_LEGISLATURA
        self._sc_init    = self._SC_INIT_PADRAO
        self.session     = requests.Session()
        self.session.headers.update(config.HEADERS_BASE)
        self.session.headers["Referer"] = self.base_url
        _logger.info(f"ProposicaoInternaScraper inicializado | URL: {self.base_url}")

    # -------------------------------------------------------------------------
    # HTTP — GET com retry
    # -------------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        before_sleep=before_sleep_log(_logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.encoding = "utf-8"
        _logger.info(f"GET {url} | status={resp.status_code} | {len(resp.text)} chars")
        if resp.status_code != 200:
            raise requests.HTTPError(f"HTTP {resp.status_code}")
        time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))
        return resp

    # -------------------------------------------------------------------------
    # HTTP — POST AJAX ScriptCase com retry
    # -------------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        before_sleep=before_sleep_log(_logger, logging.WARNING),
        reraise=True,
    )
    def _post_ajax(self, opc: str, parm: str = "") -> str:
        """
        POST para o endpoint ScriptCase com opc de navegação.
        Retorna o texto bruto da resposta (JSON ou HTML).
        """
        payload = {
            "nmgp_opcao":       "ajax_navigate",
            "script_case_init": self._sc_init,
            "opc":              opc,
            "parm":             parm,
        }
        resp = self.session.post(self.base_url, data=payload,
                                 timeout=config.REQUEST_TIMEOUT)
        resp.encoding = "utf-8"
        _logger.info(
            f"POST {self.base_url} | opc={opc} | status={resp.status_code} | "
            f"{len(resp.text)} chars"
        )
        if resp.status_code != 200:
            raise requests.HTTPError(f"HTTP {resp.status_code}")
        time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))
        return resp.text

    # -------------------------------------------------------------------------
    # DIAGNÓSTICO — salva HTML para inspeção
    # -------------------------------------------------------------------------

    def salvar_html_diagnostico(self, html: str, sufixo: str = "") -> str:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        nome = f"prop_interna_debug{sufixo}.html"
        caminho = os.path.join(config.LOG_DIR, nome)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(html)
        _logger.info(f"HTML diagnóstico salvo: {caminho}")
        return caminho

    # -------------------------------------------------------------------------
    # EXTRAÇÃO — script_case_init
    # -------------------------------------------------------------------------

    def _extrair_sc_init(self, html: str) -> str:
        """
        Extrai o valor de script_case_init do HTML da página.
        Procura padrão: script_case_init: "905" ou script_case_init=905
        """
        m = re.search(r'script_case_init["\s:=]+["\']?(\d+)["\']?', html)
        if m:
            valor = m.group(1)
            _logger.info(f"script_case_init extraído: {valor}")
            return valor
        _logger.warning(f"script_case_init não encontrado — usando padrão: {self._SC_INIT_PADRAO}")
        return self._SC_INIT_PADRAO

    # -------------------------------------------------------------------------
    # EXTRAÇÃO — tabela de proposições de um fragmento HTML
    # -------------------------------------------------------------------------

    def _extrair_tabela_html(self, html: str) -> list[dict]:
        """
        Extrai proposições do HTML (página completa ou fragmento AJAX).

        Estratégia ScriptCase:
          1. Localiza <td id="sc_grid_body"> (página completa) OU
             usa o soup diretamente (fragmento AJAX)
          2. Dentro: encontra <TABLE class="scGridTabela">
          3. Cabeçalhos: <TR class="scGridLabel"> com texto em <div style="flex-grow:1">
          4. Dados: <TR class="scGridFieldOdd|scGridFieldEven">
                    com <span id="id_sc_field_*"> dentro de cada TD
        """
        soup = BeautifulSoup(html, "lxml")

        # Localiza a scGridTabela
        grid_body = soup.find(id="sc_grid_body")
        if grid_body:
            tabela = grid_body.find("table", class_="scGridTabela")
        else:
            tabela = soup.find("table", class_="scGridTabela")

        if tabela is None:
            _logger.warning("scGridTabela não encontrada.")
            return []

        # Cabeçalhos
        header_row = tabela.find("tr", class_=re.compile(r"scGridLabel"))
        if header_row is None:
            _logger.warning("Linha de cabeçalho (scGridLabel) não encontrada.")
            return []

        cabecalhos = []
        for td in header_row.find_all("td"):
            # ScriptCase coloca o rótulo em <div style="flex-grow: 1">
            flex = td.find("div", style=re.compile(r"flex-grow", re.I))
            if flex:
                texto = flex.get_text(strip=True).lower()
            else:
                texto = td.get_text(strip=True).lower()
            cabecalhos.append(texto)

        _logger.info(f"Cabeçalhos detectados: {cabecalhos}")

        # Linhas de dados
        data_rows = tabela.find_all(
            "tr", class_=re.compile(r"scGridFieldOdd|scGridFieldEven")
        )

        resultados = []
        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) != len(cabecalhos):
                continue

            valores = []
            for cell in cells:
                # Dados ficam em <span id="id_sc_field_*">
                span = cell.find("span", id=re.compile(r"id_sc_field_"))
                if span:
                    valores.append(span.get_text(strip=True))
                else:
                    valores.append(cell.get_text(strip=True))

            # Monta dicionário ignorando colunas sem cabeçalho (hidden col)
            row_dict = {
                k: v for k, v in zip(cabecalhos, valores)
                if k and k.strip("\xa0")
            }
            if any(row_dict.values()):
                resultados.append(row_dict)

        _logger.info(f"Extraídas {len(resultados)} linhas.")
        return resultados

    # -------------------------------------------------------------------------
    # EXTRAÇÃO — resposta AJAX (JSON com fragmentos HTML)
    # -------------------------------------------------------------------------

    def _extrair_de_ajax(self, resposta: str) -> list[dict]:
        """
        Processa a resposta do POST AJAX ScriptCase.

        Formatos suportados:
          1. JSON: {"setValue": [{"field": "sc_grid_body", "value": "..."}]}
          2. HTML direto: trata como fragmento e extrai scGridTabela
        """
        if resposta.lstrip().startswith("{"):
            try:
                data = json.loads(resposta)
                fragmentos = [
                    sv["value"]
                    for sv in data.get("setValue", [])
                    if sv.get("field") in ("sc_grid_body", "sc_grid_toobar_bot")
                ]
                if fragmentos:
                    html_frag = "\n".join(fragmentos)
                    return self._extrair_tabela_html(html_frag)
                else:
                    _logger.warning("JSON AJAX sem campo sc_grid_body.")
                    return []
            except json.JSONDecodeError:
                _logger.warning("Resposta pareceu JSON mas não parseou — tentando como HTML.")

        # Fallback: trata como HTML puro
        return self._extrair_tabela_html(resposta)

    # -------------------------------------------------------------------------
    # FILTRO TEMPORAL
    # -------------------------------------------------------------------------

    def _inferir_ano(self, registro: dict) -> Optional[int]:
        """Infere o ano do registro buscando padrão 20XX em qualquer campo."""
        for valor in registro.values():
            m = re.search(r"\b(20\d{2})\b", str(valor))
            if m:
                return int(m.group(1))
        return None

    def _filtrar_por_ano(self, registros: list[dict]) -> list[dict]:
        """Remove registros anteriores a ANO_INICIO_LEGISLATURA."""
        filtrados = [
            r for r in registros
            if (ano := self._inferir_ano(r)) is None or ano >= self._ano_inicio
        ]
        removidos = len(registros) - len(filtrados)
        if removidos:
            _logger.info(f"Filtro: {removidos} registros anteriores a {self._ano_inicio} removidos.")
        return filtrados

    def _tem_registros_antigos(self, registros: list[dict]) -> bool:
        """True se a lista contém ao menos um registro com ano < ANO_INICIO_LEGISLATURA."""
        return any(
            (ano := self._inferir_ano(r)) is not None and ano < self._ano_inicio
            for r in registros
        )

    # -------------------------------------------------------------------------
    # MÉTODO PÚBLICO
    # -------------------------------------------------------------------------

    def extract(
        self,
        salvar_diagnostico: bool = True,
        apenas_primeira_pagina: bool = False,
    ) -> list[dict]:
        """
        Coleta todas as proposições de ANO_INICIO_LEGISLATURA+.

        Fluxo:
          1. GET na URL base → extrai dados + script_case_init
          2. POST AJAX nav_next para páginas seguintes
          3. Para quando página contém registros antigos ou está vazia
          4. Aplica filtro temporal final

        Parâmetros:
          salvar_diagnostico      — salva HTML da 1ª página em logs/ (debug)
          apenas_primeira_pagina  — se True, processa somente a 1ª página (teste)
        """
        _logger.info(f"Iniciando coleta (≥ {self._ano_inicio})")
        todos_registros = []
        pagina = 1

        # ── Página 1: GET puro ─────────────────────────────────────────────
        try:
            resp = self._get(self.base_url)
        except Exception as e:
            _logger.error(f"Falha ao acessar {self.base_url}: {e}")
            return []

        if salvar_diagnostico:
            self.salvar_html_diagnostico(resp.text, "_pag1")

        self._sc_init = self._extrair_sc_init(resp.text)
        registros = self._extrair_tabela_html(resp.text)

        if not registros:
            _logger.warning("Nenhum registro na 1ª página — abortando.")
            return []

        todos_registros.extend(registros)

        if apenas_primeira_pagina:
            _logger.info("Modo teste: somente 1ª página.")
            return self._filtrar_por_ano(todos_registros)

        if self._tem_registros_antigos(registros):
            _logger.info("Registros antigos na pág. 1 — paginação desnecessária.")
            return self._filtrar_por_ano(todos_registros)

        # ── Páginas seguintes: POST AJAX nav_next ──────────────────────────
        MAX_PAGINAS = 500  # 500 × 20 = 10.000 registros máx.
        while pagina < MAX_PAGINAS:
            pagina += 1
            _logger.info(f"Coletando página {pagina}...")
            try:
                resposta = self._post_ajax("nav_next")
            except Exception as e:
                _logger.error(f"Erro AJAX página {pagina}: {e}")
                break

            registros = self._extrair_de_ajax(resposta)
            if not registros:
                _logger.info("Página vazia — fim da paginação.")
                break

            todos_registros.extend(registros)

            if self._tem_registros_antigos(registros):
                _logger.info(
                    f"Registros anteriores a {self._ano_inicio} detectados "
                    f"na página {pagina} — paginação encerrada."
                )
                break

        todos_registros = self._filtrar_por_ano(todos_registros)
        _logger.info(
            f"Coleta concluída: {len(todos_registros)} proposições "
            f"em {pagina} páginas."
        )
        return todos_registros


# =============================================================================
# TESTE ISOLADO — valida extração na 1ª página com break provisório
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    print("=" * 60)
    print("TESTE ISOLADO — ProposicaoInternaScraper (1ª página)")
    print("=" * 60)

    scraper = ProposicaoInternaScraper()
    registros = scraper.extract(
        salvar_diagnostico=True,
        apenas_primeira_pagina=True,  # BREAK PROVISÓRIO — somente 1ª página
    )

    if registros:
        print(f"\n✅ {len(registros)} proposições extraídas com sucesso!\n")
        print("── Primeiros 3 registros ──")
        for i, r in enumerate(registros[:3], 1):
            print(f"\n[{i}]")
            for k, v in r.items():
                print(f"  {k}: {v[:80] if len(str(v)) > 80 else v}")
        print(f"\nColunas: {list(registros[0].keys())}")
    else:
        print("\n❌ Nenhum registro extraído. Verifique os logs acima.")
