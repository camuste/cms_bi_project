# =============================================================================
# scraper.py -- CMS BI Project
# Camara Municipal de Salvador -- Extracao de Dados
# =============================================================================
# ScriptCaseScraper   : classe base (sessao, AJAX, paginacao)
# FrequenciaScraper   : frequencia em sessoes plenarias
# ProdutividadeScraper: produtividade parlamentar por vereador/ano
# ProposicaoScraper   : proposicoes legislativas por vereador/ano
# VereadorScraper     : lista de vereadores ativos (cms.ba.gov.br)
# =============================================================================

import re
import json
import time
import random
import logging
import copy
import io
import os
from abc import ABC, abstractmethod
from collections import Counter
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

# -- Logging ------------------------------------------------------------------
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("scraper")


# =============================================================================
# CLASSE BASE
# =============================================================================

class ScriptCaseScraper(ABC):
    """
    Classe base para scrapers do sistema ScriptCase da CMS Salvador.

    Mecanica confirmada via DevTools:
    - POST para index.php com nmgp_opcao=ajax_navigate
    - 'script_case_init' e um token capturado do HTML inicial (ex: 3373)
    - Filtros usam campo 'parm' com delimitador __DL__ e sufixo __DL__S
    - Paginacao: opc = nav_next / nav_prev / nav_end / nav_first
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.endpoint = base_url + "index.php"
        self.session  = requests.Session()
        self.session.headers.update(config.HEADERS_BASE)
        self.session.headers["Referer"] = base_url
        self.sc_init = ""
        self._log = logging.getLogger(self.__class__.__name__)

    # -------------------------------------------------------------------------

    def _init_session(self) -> None:
        """GET inicial: captura cookies e o token script_case_init do HTML."""
        self._log.info(f"Iniciando sessao em: {self.base_url}")
        resp = self.session.get(self.base_url, timeout=config.REQUEST_TIMEOUT)
        resp.encoding = config.ENCODING_LEGSYS
        html = resp.text

        # Estrategia 1: variavel JavaScript
        m = re.search(r"var\s+script_case_init\s*=\s*['\"]?(\d+)['\"]?", html)
        if m:
            self.sc_init = m.group(1)
            self._log.info(f"sc_init (JS var): {self.sc_init}")
            return

        # Estrategia 2: input hidden
        soup = BeautifulSoup(html, "lxml")
        inp  = soup.find("input", {"name": "script_case_init"})
        if inp and inp.get("value"):
            self.sc_init = inp["value"]
            self._log.info(f"sc_init (input hidden): {self.sc_init}")
            return

        # Estrategia 3: qualquer numero apos script_case_init
        m2 = re.search(r"script_case_init['\"]?\s*[=:,]\s*['\"]?(\d{3,6})", html)
        if m2:
            self.sc_init = m2.group(1)
            self._log.info(f"sc_init (regex fallback): {self.sc_init}")
            return

        self._log.warning("sc_init NAO encontrado -- usando '0'. Verifique o HTML.")
        self.sc_init = "0"

    # -------------------------------------------------------------------------

    def _build_parm(self, field: str, label: str, dtype: str,
                    value: str, display: str) -> str:
        """
        Constroi o campo 'parm' no formato ScriptCase.

        Payload confirmado via DevTools:
          pre_pre_data_presenca__DL__Mes e Ano__DL__dh__DL__2026-04##@@04/2026 __DL__S
          pre_ses_numero__DL__No. da Sessao__DL__nn__DL__21##@@21__DL__S

        Nota: ha um espaco antes de __DL__S -- presente no payload real.
        """
        return f"{field}__DL__{label}__DL__{dtype}__DL__{value}##@@{display} __DL__S"

    def _build_payload(self, opc: str, parm: str = "") -> dict:
        """Monta payload completo para POST AJAX."""
        payload = copy.deepcopy(config.PAYLOAD_BASE)
        payload["script_case_init"] = self.sc_init
        payload["opc"]  = opc
        payload["parm"] = parm
        return payload

    # -------------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _post_ajax(self, payload: dict) -> BeautifulSoup:
        """POST para o endpoint ScriptCase com retry automatico.

        ScriptCase retorna JSON com fragmentos HTML em setValue.
        Detectamos isso e montamos um soup com sc_grid_body + toolbar.
        """
        t0   = time.time()
        resp = self.session.post(self.endpoint, data=payload,
                                  timeout=config.REQUEST_TIMEOUT)
        resp.encoding = config.ENCODING_LEGSYS
        elapsed = time.time() - t0

        self._log.info(
            f"POST opc={payload.get('opc')} | "
            f"status={resp.status_code} | {elapsed:.2f}s | {len(resp.text)} chars"
        )

        if resp.status_code != 200:
            raise requests.HTTPError(f"HTTP {resp.status_code}")

        time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))

        text = resp.text
        # ScriptCase AJAX retorna JSON com fragmentos HTML em setValue
        if text.lstrip().startswith("{"):
            try:
                data = json.loads(text)
                # Armazena vars de paginacao para _get_pagination_info
                self._last_set_var = {
                    v["var"].strip(): v["value"]
                    for v in data.get("setVar", [])
                }
                # Extrai fragmentos HTML relevantes
                fragments = [
                    sv["value"]
                    for sv in data.get("setValue", [])
                    if sv.get("field") in ("sc_grid_body", "sc_grid_toobar_bot")
                ]
                combined = "\n".join(fragments)
                self._log.debug(
                    f"JSON ScriptCase: scQtReg={self._last_set_var.get('scQtReg')} | "
                    f"{len(combined)} chars de HTML extraidos"
                )
                return BeautifulSoup(combined, "lxml")
            except (json.JSONDecodeError, KeyError, StopIteration):
                pass

        self._last_set_var = {}
        return BeautifulSoup(text, "lxml")

    # -------------------------------------------------------------------------

    def _extract_table(self, soup: BeautifulSoup) -> list:
        """Extrai dados da(s) tabela(s) HTML retornada(s) pelo ScriptCase.

        ScriptCase envolve os dados em <TABLE class='scGridTabela'> com
        linhas de cabecalho mistas (filtros, grupos, depois colunas reais).
        Usa a contagem modal de celulas para identificar o cabecalho correto.
        A primeira coluna costuma ser vazia (checkbox); filtramos pela chave.
        """
        results = []
        # Textos de navegacao (nunca sao dados reais)
        nav_texts = {"Primeiro", "Anterior", "Proximo", "Ultimo", "Próximo", "Último"}

        # Prioriza scGridTabela; cai para qualquer tabela como fallback
        target_tables = (
            soup.find_all("table", class_="scGridTabela")
            or soup.find_all("table")
        )

        for table in target_tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # Contagem modal: quantas celulas tem a linha mais comum (dados)
            counts = Counter(
                len(r.find_all(["td", "th"]))
                for r in rows
                if r.find_all(["td", "th"])
            )
            if not counts:
                continue
            target_n = counts.most_common(1)[0][0]

            # Cabecalho: primeira linha com target_n celulas sem "=>"
            header_idx = None
            for i, row in enumerate(rows):
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if len(cells) == target_n and not any("=>" in c for c in cells):
                    header_idx = i
                    break

            if header_idx is None:
                continue

            headers = [
                c.get_text(strip=True)
                for c in rows[header_idx].find_all(["th", "td"])
            ]
            if not any(h for h in headers if h):
                continue

            for row in rows[header_idx + 1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) != len(headers):
                    continue
                values = [c.get_text(strip=True) for c in cells]
                if not any(values):
                    continue
                # Ignora linhas de navegacao (Primeiro, Anterior...)
                # usando o primeiro valor NAO-vazio (ScriptCase tem col. vazia no inicio)
                first_val = next((v for v in values if v), "")
                if first_val in nav_texts:
                    continue
                # Remove entradas com chave vazia (coluna checkbox do ScriptCase)
                row_dict = {k: v for k, v in zip(headers, values) if k}
                if not row_dict or all(v == "" for v in row_dict.values()):
                    continue
                results.append(row_dict)

            if results:
                break

        return results

    # -------------------------------------------------------------------------

    def _get_pagination_info(self, soup: BeautifulSoup) -> tuple:
        """
        Extrai (registros_por_pagina, total_registros).

        Prioridade 1: setVar do JSON ScriptCase (scQtReg, nm_gp_rec_fim/ini).
        Prioridade 2: texto HTML padrao '[1 a 43 de 22485]'.
        """
        sv = getattr(self, "_last_set_var", {})
        if sv and sv.get("scQtReg") is not None:
            total    = int(sv["scQtReg"])
            ini      = int(sv.get("nm_gp_rec_ini", 0))
            fim      = int(sv.get("nm_gp_rec_fim", 0))
            per_page = fim - ini if fim > ini else total
            self._log.info(f"Paginacao (JSON): {per_page}/pag | total: {total}")
            return per_page, total

        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d+)\s+a\s+(\d+)\s+de\s+(\d+)", text)
        if m:
            inicio = int(m.group(1))
            fim    = int(m.group(2))
            total  = int(m.group(3))
            return (fim - inicio + 1), total
        return 0, 0

    # -------------------------------------------------------------------------

    def _paginate_all(self, filter_payload: Optional[dict] = None) -> list:
        """Coleta TODAS as paginas de dados para o filtro aplicado."""
        all_records = []

        if filter_payload:
            soup = self._post_ajax(filter_payload)
        else:
            soup = self._post_ajax(self._build_payload(config.OPC_NAV_FIRST))

        records = self._extract_table(soup)
        all_records.extend(records)

        per_page, total = self._get_pagination_info(soup)
        self._log.info(f"Paginacao: {per_page}/pag | total: {total}")

        if total == 0 or per_page == 0:
            return all_records

        pages_done = 1
        max_pages  = (total // max(per_page, 1)) + 2

        while len(all_records) < total and pages_done < max_pages:
            soup    = self._post_ajax(self._build_payload(config.OPC_NAV_NEXT))
            records = self._extract_table(soup)
            if not records:
                self._log.info("Paginacao: pagina vazia -- encerrando")
                break
            all_records.extend(records)
            pages_done += 1
            self._log.info(f"  {len(all_records)}/{total} ({pages_done} pags)")

        return all_records

    # -------------------------------------------------------------------------

    def _try_export_csv(self) -> Optional[pd.DataFrame]:
        """Tenta obter export CSV direto (mais eficiente que paginar)."""
        export_opcs = ["exportar", "csv_export", "sc_export", "export_csv"]

        for opc in export_opcs:
            try:
                payload = self._build_payload(opc)
                resp = self.session.post(self.endpoint, data=payload,
                                          timeout=config.REQUEST_TIMEOUT)
                ct = resp.headers.get("Content-Type", "")

                if "csv" in ct or "excel" in ct or "octet" in ct:
                    resp.encoding = config.ENCODING_LEGSYS
                    df = pd.read_csv(io.StringIO(resp.text),
                                     encoding=config.ENCODING_LEGSYS,
                                     on_bad_lines="skip")
                    self._log.info(f"Export CSV via opc='{opc}': {len(df)} linhas")
                    return df

                # Detectar CSV pelo conteudo
                resp.encoding = config.ENCODING_LEGSYS
                first = resp.text.strip().split("\n")[0] if resp.text.strip() else ""
                if ";" in first or "," in first:
                    sep = ";" if first.count(";") >= first.count(",") else ","
                    try:
                        df = pd.read_csv(io.StringIO(resp.text), sep=sep,
                                         encoding=config.ENCODING_LEGSYS,
                                         on_bad_lines="skip")
                        if len(df.columns) >= 2:
                            self._log.info(f"Export CSV detectado (opc='{opc}'): {len(df)} linhas")
                            return df
                    except Exception:
                        pass
            except Exception as e:
                self._log.debug(f"Export opc='{opc}' falhou: {e}")

        self._log.info("Export CSV nao disponivel -- usando paginacao")
        return None

    # -------------------------------------------------------------------------

    def _discover_fields(self, soup: BeautifulSoup) -> dict:
        """
        Extrai mapeamento de campos a partir dos links nm_proc_int_search.
        Retorna: {label_lower: (field, label, dtype)}
        """
        fields = {}
        pattern = re.compile(
            r"nm_proc_int_search\s*\(\s*"
            r"'[^']*'\s*,\s*"
            r"'([^']*)'\s*,\s*"   # dtype
            r"'([^']*)'\s*,\s*"   # label
            r"'([^']*)'\s*,\s*"   # field name
        )
        for m in pattern.finditer(str(soup)):
            dtype = m.group(1)
            label = m.group(2)
            field = m.group(3)
            if field and label:
                fields[label.lower().strip()] = (field, label, dtype)
        self._log.info(f"Campos descobertos: {list(fields.keys())}")
        return fields

    # -------------------------------------------------------------------------

    @abstractmethod
    def extract(self, **kwargs) -> list:
        pass


# =============================================================================
# FREQUENCIA
# =============================================================================

class FrequenciaScraper(ScriptCaseScraper):
    """
    Coleta frequencia dos vereadores em sessoes plenarias.

    Campos confirmados via DevTools (engenharia reversa):
      Mes/Ano  : parm = pre_pre_data_presenca__DL__Mes e Ano__DL__dh__DL__2026-04##@@04/2026 __DL__S
      Nr Sessao: parm = pre_ses_numero__DL__No. da Sessao__DL__nn__DL__21##@@21__DL__S

    Colunas retornadas: No. da Sessao | Ano da Sessao | Parlamentar | Status
    Total estimado: ~22.000 registros historicos
    """

    def __init__(self):
        super().__init__(config.URL_FREQUENCIA)

    def _get_meses_disponiveis(self, html: str) -> list:
        """Extrai lista de meses do filtro. Retorna [(valor, display), ...]"""
        meses = []
        pattern = re.compile(
            r"nm_proc_int_search\([^)]*'pre_pre_data_presenca',\s*"
            r"'(\d{4}-\d{2})##@@([^']+)'"
        )
        for m in pattern.finditer(html):
            valor   = m.group(1).strip()
            display = m.group(2).strip()
            meses.append((valor, display))
        self._log.info(f"Meses disponiveis: {len(meses)}")
        return meses

    def _normalizar(self, record: dict) -> dict:
        """Converte cabecalhos originais para snake_case."""
        mapping = {
            "No. da Sessao":   "num_sessao",
            "No. da Sessão": "num_sessao",
            "Ano da Sessao":   "ano",
            "Ano da Sessão": "ano",
            "Parlamentar":     "parlamentar",
            "Status":          "status",
        }
        return {mapping.get(k, k.lower().replace(" ", "_")): v for k, v in record.items()}

    def extract(self, mes_ano: Optional[str] = None, **kwargs) -> list:
        """
        Extrai frequencia.
        mes_ano: "2026-04" para mes especifico. None coleta todos os meses.
        """
        self._init_session()

        # Tentar export CSV primeiro
        df_export = self._try_export_csv()
        if df_export is not None and not df_export.empty:
            records = df_export.to_dict("records")
            records = [self._normalizar(r) for r in records]
            for r in records:
                r.setdefault("mes_ano", mes_ano)
            self._log.info(f"FrequenciaScraper (export): {len(records)} registros")
            return records

        # Fallback: paginacao AJAX
        if mes_ano:
            field, label, dtype = config.FIELD_MAP["frequencia"]["mes_ano"]
            parts   = mes_ano.split("-")
            display = f"{parts[1]}/{parts[0]}" if len(parts) == 2 else mes_ano
            parm    = self._build_parm(field, label, dtype, mes_ano, display)
            records = self._paginate_all(self._build_payload(config.OPC_SEARCH, parm))
            records = [self._normalizar(r) for r in records]
            for r in records:
                r["mes_ano"] = mes_ano
        else:
            resp = self.session.get(self.base_url, timeout=config.REQUEST_TIMEOUT)
            resp.encoding = config.ENCODING_LEGSYS
            meses = self._get_meses_disponiveis(resp.text)

            if not meses:
                self._log.warning("Nenhum mes encontrado -- coletando sem filtro")
                records = [self._normalizar(r) for r in self._paginate_all()]
                for r in records:
                    r["mes_ano"] = None
                return records

            records = []
            for i, (valor, display) in enumerate(meses):
                self._log.info(f"[{i+1}/{len(meses)}] Mes: {valor}")
                field, label, dtype = config.FIELD_MAP["frequencia"]["mes_ano"]
                parm = self._build_parm(field, label, dtype, valor, display)
                fp   = self._build_payload(config.OPC_SEARCH, parm)
                for r in self._paginate_all(fp):
                    nr = self._normalizar(r)
                    nr["mes_ano"] = valor
                    records.append(nr)
                self._post_ajax(self._build_payload(config.OPC_NAV_FIRST))

        self._log.info(f"FrequenciaScraper: {len(records)} registros")
        return records


# =============================================================================
# PRODUTIVIDADE PARLAMENTAR
# =============================================================================

class ProdutividadeScraper(ScriptCaseScraper):
    """
    Coleta produtividade parlamentar (total de proposicoes por tipo).
    Requer selecao de parlamentar + periodo antes de exibir dados.
    """

    def __init__(self):
        super().__init__(config.URL_PRODUTIVIDADE)

    def _get_opcoes(self, html: str, field_name: str) -> list:
        """Extrai [(valor, display)] de um campo de filtro."""
        opcoes = []
        pattern = re.compile(
            rf"'{re.escape(field_name)}',\s*'([^#']+?)##@@([^']+?)'\s*,"
        )
        for m in pattern.finditer(html):
            opcoes.append((m.group(1).strip(), m.group(2).strip()))
        return opcoes

    def _fetch_um(self, parl_field: str, parl_label: str, parl_dtype: str,
                   parl_valor: str, parl_display: str,
                   ano_field: str,  ano_label: str,  ano_dtype: str,
                   ano_valor: str) -> list:
        """Coleta dados de UM parlamentar em UM ano."""
        parm_parl = self._build_parm(parl_field, parl_label, parl_dtype,
                                      parl_valor, parl_display)
        self._post_ajax(self._build_payload(config.OPC_SEARCH, parm_parl))

        parm_ano = self._build_parm(ano_field, ano_label, ano_dtype,
                                     ano_valor, ano_valor)
        records  = self._paginate_all(self._build_payload(config.OPC_SEARCH, parm_ano))

        for r in records:
            r["_parlamentar"] = parl_display
            r["_ano"]         = ano_valor
        return records

    def extract(self, anos: Optional[list] = None, **kwargs) -> list:
        """Coleta produtividade para todos os parlamentares nos anos indicados."""
        self._init_session()

        resp = self.session.get(self.base_url, timeout=config.REQUEST_TIMEOUT)
        resp.encoding = config.ENCODING_LEGSYS
        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        fields = self._discover_fields(soup)

        parl_key = next((k for k in fields if "parlamentar" in k or "autor" in k), None)
        ano_key  = next((k for k in fields if "periodo" in k or "ano" in k), None)

        if parl_key:
            parl_field, parl_label, parl_dtype = fields[parl_key]
        else:
            parl_field, parl_label, parl_dtype = config.FIELD_MAP["produtividade"]["parlamentar"]
            self._log.warning("Campo parlamentar nao descoberto -- usando FIELD_MAP")

        if ano_key:
            ano_field, ano_label, ano_dtype = fields[ano_key]
        else:
            ano_field, ano_label, ano_dtype = config.FIELD_MAP["produtividade"]["periodo"]

        parlamentares = self._get_opcoes(html, parl_field)
        anos_disp     = self._get_opcoes(html, ano_field)

        if not parlamentares:
            self._log.error("Nenhum parlamentar encontrado.")
            return []

        anos_filtrar = [str(a) for a in (anos or [str(a) for a in config.ANOS_COBERTURA])]
        anos_usar    = [(v, d) for v, d in anos_disp if v in anos_filtrar] or \
                       [(a, a) for a in anos_filtrar]

        total = len(parlamentares) * len(anos_usar)
        self._log.info(f"{len(parlamentares)} parlamentares x {len(anos_usar)} anos = {total}")

        all_records = []
        for i, (pv, pd_) in enumerate(parlamentares):
            for j, (av, _) in enumerate(anos_usar):
                idx = i * len(anos_usar) + j + 1
                self._log.info(f"[{idx}/{total}] {pd_} / {av}")
                try:
                    recs = self._fetch_um(parl_field, parl_label, parl_dtype, pv, pd_,
                                          ano_field,  ano_label,  ano_dtype,  av)
                    all_records.extend(recs)
                except Exception as e:
                    self._log.error(f"Erro em {pd_}/{av}: {e}")
                finally:
                    self._post_ajax(self._build_payload(config.OPC_NAV_FIRST))

        self._log.info(f"ProdutividadeScraper: {len(all_records)} registros")
        return all_records


# =============================================================================
# PROPOSICOES
# =============================================================================

class ProposicaoScraper(ProdutividadeScraper):
    """
    Coleta produtividade por tipo de proposicao.
    Mesma mecanica do ProdutividadeScraper com URL diferente.
    """

    def __init__(self):
        ScriptCaseScraper.__init__(self, config.URL_PROPOSICAO)


# =============================================================================
# VEREADORES
# =============================================================================

class VereadorScraper:
    """
    Extrai lista de vereadores ativos da 20a Legislatura (2025-2028).
    Fonte: https://www.cms.ba.gov.br/vereadores
    HTML direto, UTF-8, sem ScriptCase.
    """

    def __init__(self):
        self._log = logging.getLogger("VereadorScraper")
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS_BASE)

    def extract(self, **kwargs) -> list:
        self._log.info(f"Coletando vereadores: {config.URL_VEREADORES}")
        resp = self.session.get(config.URL_VEREADORES, timeout=config.REQUEST_TIMEOUT)
        resp.encoding = config.ENCODING_CMS
        soup = BeautifulSoup(resp.text, "lxml")
        records = []

        table = soup.find("table")
        if table is None:
            try:
                tables = pd.read_html(resp.text, encoding=config.ENCODING_CMS)
                return tables[0].to_dict("records")
            except Exception as e:
                self._log.error(f"Nenhuma tabela encontrada: {e}")
                return []

        rows    = table.find_all("tr")
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) == len(headers) and any(cells):
                records.append(dict(zip(headers, cells)))

        self._log.info(f"VereadorScraper: {len(records)} vereadores")
        return records


# =============================================================================
# SMOKE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SMOKE TEST -- ScriptCaseScraper + FrequenciaScraper")
    print("=" * 60)

    # 1. Sessao base
    s = FrequenciaScraper()
    s._init_session()
    print(f"\n[1] sc_init : {s.sc_init}")
    print(f"    Cookies : {dict(s.session.cookies)}")

    # 2. build_parm
    parm = s._build_parm(
        "pre_pre_data_presenca", "Mes e Ano", "dh", "2026-04", "04/2026"
    )
    esperado = "pre_pre_data_presenca__DL__Mes e Ano__DL__dh__DL__2026-04##@@04/2026 __DL__S"
    assert parm == esperado, f"FALHOU\n  got:      {repr(parm)}\n  esperado: {repr(esperado)}"
    print(f"\n[2] build_parm OK")

    # 3. Coleta real (abril/2026)
    print("\n[3] Coletando abril/2026...")
    fs   = FrequenciaScraper()
    dados = fs.extract(mes_ano="2026-04")
    print(f"    Registros: {len(dados)}")
    if dados:
        print(f"    Amostra  : {dados[0]}")
        campos = {"num_sessao", "ano", "parlamentar", "status", "mes_ano"}
        for d in dados[:5]:
            faltando = campos - set(d.keys())
            if faltando:
                print(f"    AVISO -- campos faltando: {faltando}")

    print("\nSmoke test concluido.")
