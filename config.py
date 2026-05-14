# =============================================================================
# config.py — CMS BI Project
# Câmara Municipal de Salvador — Configurações Centrais
# =============================================================================
# TODOS os valores de URL, payload e constantes vivem aqui.
# Nunca importe estado mutável deste módulo.
# =============================================================================

# ── URLs ──────────────────────────────────────────────────────────────────────
URL_FREQUENCIA    = "http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/"
URL_PRODUTIVIDADE = "http://45.4.247.157/leg/salvador/LEG_SYS_produtividade_parlamentar/"
URL_PROPOSICAO    = "http://45.4.247.157/leg/salvador/LEG_SYS_produtividade_parlamentar_proposicao/"
URL_COMISSAO      = "http://45.4.247.157/leg/salvador/LEG_SYS_comissao/"
URL_VEREADORES    = "https://www.cms.ba.gov.br/vereadores"

# ── Encoding ──────────────────────────────────────────────────────────────────
# CRÍTICO: todas as páginas do IP 45.4.247.157 usam ISO-8859-1.
# Sem definir explicitamente, nomes acentuados viram lixo binário.
ENCODING_LEGSYS = "iso-8859-1"
ENCODING_CMS    = "utf-8"

# ── ScriptCase AJAX — Payload Base ────────────────────────────────────────────
# Capturado via DevTools (engenharia reversa confirmada).
# 'script_case_init' é preenchido dinamicamente por ScriptCaseScraper._init_session().
# Valor observado: 3373 / 5569 — muda a cada nova sessão HTTP.
PAYLOAD_BASE = {
    "nmgp_opcao":       "ajax_navigate",
    "script_case_init": "",   # preenchido em runtime
    "opc":              "",   # preenchido por cada operação
    "parm":             "",   # preenchido por cada filtro/ação
}

# ── Operações ScriptCase (opc) ────────────────────────────────────────────────
OPC_SEARCH   = "interativ_search"  # aplicar filtro
OPC_NAV_NEXT = "nav_next"          # próxima página
OPC_NAV_PREV = "nav_prev"          # página anterior
OPC_NAV_END  = "nav_end"           # última página (para capturar total)
OPC_NAV_FIRST= "nav_first"         # primeira página
OPC_NAV_GOTO = "nav_goto"          # ir para página por offset

# ── Mapa de Campos por Fonte ───────────────────────────────────────────────────
# Estrutura: (nome_campo_POST, label_display, tipo_scriptcase)
# Tipos ScriptCase confirmados via engenharia reversa:
#   'dh' = date/hour  → ex: filtro de mês/ano
#   'nn' = number/name → ex: número de sessão, código de parlamentar
#   'tx' = text        → ex: nome de comissão
#
# Payload confirmado #1 (filtro por mês):
#   parm = pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__2026-04##@@04/2026 __DL__S
#
# Payload confirmado #2 (filtro por sessão):
#   parm = pre_ses_numero__DL__No. da Sessão__DL__nn__DL__21##@@21__DL__S

FIELD_MAP = {
    "frequencia": {
        "mes_ano":    ("pre_pre_data_presenca", "Mês e Ano",     "dh"),
        "num_sessao": ("pre_ses_numero",        "No. da Sessão", "nn"),
    },
    # Os campos abaixo são descobertos em runtime por _discover_fields()
    # pois podem variar. Os valores abaixo são hipóteses baseadas no padrão ScriptCase.
    "produtividade": {
        "parlamentar": ("pro_par_codigo", "Parlamentar/Autor", "nn"),
        "periodo":     ("pro_ano",        "Periodo",           "nn"),
    },
    "proposicao": {
        "parlamentar": ("pro_par_codigo", "Parlamentar", "nn"),
        "periodo":     ("pro_ano",        "Periodo",     "nn"),
    },
    "comissao": {
        "comissao": ("comissao", "Comissão", "tx"),
    },
}

# ── Headers HTTP ──────────────────────────────────────────────────────────────
# ScriptCase verifica Referer. User-Agent realista evita bloqueio.
HEADERS_BASE = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
}

# ── Throttling ────────────────────────────────────────────────────────────────
DELAY_MIN      = 2.0   # segundos — mínimo entre requests
DELAY_MAX      = 5.0   # segundos — máximo entre requests
REQUEST_TIMEOUT = 30   # segundos — timeout por request

# ── Cobertura de Dados ────────────────────────────────────────────────────────
ANOS_COBERTURA = list(range(2019, 2027))

# ── Caminhos ──────────────────────────────────────────────────────────────────
CACHE_DIR    = "data/"
LOG_DIR      = "logs/"
LOG_FILE     = "logs/scraper.log"
LAST_RUN_FILE = "data/last_run.json"

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_MAX_HORAS = 24  # horas antes do cache ser considerado expirado
