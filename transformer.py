# =============================================================================
# transformer.py -- CMS BI Project
# Camara Municipal de Salvador -- Transformacao e Persistencia
# =============================================================================

import os
import re
import json
import unicodedata
import logging
from datetime import datetime, timedelta
from difflib import get_close_matches
from typing import Optional

import pandas as pd

import config

# -- Logging ------------------------------------------------------------------
os.makedirs(config.LOG_DIR, exist_ok=True)
os.makedirs(config.CACHE_DIR, exist_ok=True)
logger = logging.getLogger("transformer")


# =============================================================================
# SECAO 1 -- Normalizacao de Nomes
# =============================================================================

def normalizar_nome(nome: str) -> str:
    """
    Normaliza nome para uso como chave de join entre datasets.
    Pipeline: strip -> espacos duplos -> remove acentos -> title case.

    Exemplo:
      "MARTA LULA RODRIGUES " -> "Marta Lula Rodrigues"
      "Andre Fraga"            -> "Andre Fraga"
    """
    if not isinstance(nome, str) or not nome.strip():
        return ""
    nome = nome.strip()
    nome = " ".join(nome.split())
    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ascii", "ignore").decode("ascii")
    return nome.title()


def fuzzy_match_nome(
    nome: str,
    catalogo: list,
    cutoff: float = 0.75
) -> Optional[str]:
    """
    Encontra o nome mais proximo no catalogo usando difflib.
    Retorna o nome ORIGINAL do catalogo ou None.

    Uso: quando join exato por nome_norm falha (ex: apelido vs nome completo).
    Exemplo:
      "Marta Lula Rodrigues" -> match em ["Marta Rodrigues"] -> "Marta Rodrigues"
    """
    if not nome or not catalogo:
        return None
    nome_norm = normalizar_nome(nome)
    catalogo_norm = [normalizar_nome(c) for c in catalogo]
    matches = get_close_matches(nome_norm, catalogo_norm, n=1, cutoff=cutoff)
    if matches:
        idx = catalogo_norm.index(matches[0])
        return catalogo[idx]
    return None


# =============================================================================
# SECAO 2 -- Transformadores por Dataset
# =============================================================================

def transform_frequencia(raw: list) -> pd.DataFrame:
    """
    Transforma dados crus da FrequenciaScraper em DataFrame tipado.

    Entrada esperada (dict com qualquer combinacao de):
      num_sessao | ano | parlamentar | status | mes_ano

    Saida:
      nome_norm | parlamentar | num_sessao | ano | mes_ano | status | presente
    """
    if not raw:
        logger.warning("transform_frequencia: lista vazia recebida")
        return pd.DataFrame(columns=["nome_norm", "parlamentar", "num_sessao",
                                     "ano", "mes_ano", "status", "presente"])

    df = pd.DataFrame(raw)

    for col in ["num_sessao", "ano", "parlamentar", "status", "mes_ano"]:
        if col not in df.columns:
            df[col] = None

    df["num_sessao"] = pd.to_numeric(df["num_sessao"], errors="coerce").astype("Int64")
    df["ano"]        = pd.to_numeric(df["ano"],        errors="coerce").astype("Int64")

    df["parlamentar"] = df["parlamentar"].astype(str).str.strip()
    df["status"]      = df["status"].astype(str).str.strip()
    df["mes_ano"]     = df["mes_ano"].astype(str).str.strip().replace("None", None)

    df["nome_norm"] = df["parlamentar"].apply(normalizar_nome)

    status_presente = {"presente", "p", "sim", "s", "yes", "y"}
    df["presente"] = df["status"].str.lower().str.strip().isin(status_presente)

    df = df.drop_duplicates(subset=["num_sessao", "ano", "nome_norm"])
    df = df[df["nome_norm"] != ""]

    return df[["nome_norm", "parlamentar", "num_sessao", "ano",
               "mes_ano", "status", "presente"]].reset_index(drop=True)


def transform_produtividade(raw: list) -> pd.DataFrame:
    """
    Transforma dados crus de ProdutividadeScraper / ProposicaoScraper.

    Entrada: dicts com campos variaveis + _parlamentar + _ano (metadados).
    Saida: nome_norm | parlamentar | ano | [colunas proposicoes] | total_proposicoes
    """
    if not raw:
        logger.warning("transform_produtividade: lista vazia recebida")
        return pd.DataFrame(columns=["nome_norm", "parlamentar", "ano", "total_proposicoes"])

    df = pd.DataFrame(raw)

    col_parl = "_parlamentar" if "_parlamentar" in df.columns else \
               next((c for c in df.columns if "parlamentar" in c.lower()), None)
    col_ano  = "_ano" if "_ano" in df.columns else \
               next((c for c in df.columns if "ano" in c.lower() or "periodo" in c.lower()), None)

    df["parlamentar"] = df[col_parl].astype(str).str.strip() if col_parl else "Desconhecido"
    df["ano"]         = pd.to_numeric(df[col_ano], errors="coerce").astype("Int64") \
                        if col_ano else pd.NA
    df["nome_norm"]   = df["parlamentar"].apply(normalizar_nome)

    cols_skip = {"nome_norm", "parlamentar", "ano", "_parlamentar", "_ano"}
    for col in df.columns:
        if col in cols_skip:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    cols_num = [c for c in df.select_dtypes(include="number").columns if c not in {"ano"}]
    df["total_proposicoes"] = df[cols_num].sum(axis=1)

    df = df.drop(columns=["_parlamentar", "_ano"], errors="ignore")

    return df.reset_index(drop=True)


def transform_vereadores(raw: list) -> pd.DataFrame:
    """Transforma dados crus do VereadorScraper."""
    if not raw:
        return pd.DataFrame(columns=["nome_norm", "nome_display", "partido",
                                     "email", "telefone", "gabinete"])

    df = pd.DataFrame(raw)

    col_nome    = next((c for c in df.columns if "vereador" in c.lower() or "nome" in c.lower()), df.columns[0])
    col_email   = next((c for c in df.columns if "mail" in c.lower()), None)
    col_tel     = next((c for c in df.columns if "tel" in c.lower() or "fax" in c.lower()), None)
    col_gab     = next((c for c in df.columns if "gab" in c.lower() or "edf" in c.lower()), None)
    col_partido = next((c for c in df.columns if "partido" in c.lower()), None)

    result = pd.DataFrame()
    result["nome_display"] = df[col_nome].astype(str).str.strip()
    result["nome_norm"]    = result["nome_display"].apply(normalizar_nome)
    result["email"]        = df[col_email].astype(str).str.strip()   if col_email   else None
    result["telefone"]     = df[col_tel].astype(str).str.strip()     if col_tel     else None
    result["gabinete"]     = df[col_gab].astype(str).str.strip()     if col_gab     else None
    result["partido"]      = df[col_partido].astype(str).str.strip() if col_partido else None

    if "telefone" in result.columns and result["telefone"] is not None:
        result["telefone"] = result["telefone"].str.replace(r"[^\d\s\-\+\(\)]", "", regex=True)

    return result[result["nome_norm"] != ""].reset_index(drop=True)


def transform_proposicao_interna(raw: list) -> pd.DataFrame:
    """
    Transforma dados crus da ProposicaoInternaScraper em DataFrame tipado.

    Colunas reais confirmadas via diagnóstico (2026-05-17):
      proposição  → numero    (ex: "PIN-210/2026")
      autor       → autor
      ementa      → ementa
      movimentado → data      (data da última movimentação)
      localização → localizacao
      situação    → situacao
      autor/requerente/vistas/outros → autor_doc (ignorado na exibição)

    Usa correspondência por substring para tolerar variações futuras.
    """
    if not raw:
        logger.warning("transform_proposicao_interna: lista vazia recebida")
        return pd.DataFrame(columns=[
            "numero", "ementa", "autor", "data", "localizacao",
            "situacao", "ano", "nome_norm"
        ])

    df = pd.DataFrame(raw)

    def _encontrar_coluna(*termos: str) -> Optional[str]:
        for t in termos:
            for c in df.columns:
                if t in c.lower():
                    return c
        return None

    # Colunas confirmadas + termos de fallback para robustez futura
    col_numero    = _encontrar_coluna("prop", "num")
    col_ementa    = _encontrar_coluna("ement", "descri", "objeto")
    col_autor     = _encontrar_coluna("autor", "propon", "vereador")
    col_data      = _encontrar_coluna("mov", "data", "dt_", "data")
    col_local     = _encontrar_coluna("localiz", "destino", "local")
    col_situacao  = _encontrar_coluna("situ", "status", "andamento")

    result = pd.DataFrame()
    for campo, col_orig in [
        ("numero",      col_numero),
        ("ementa",      col_ementa),
        ("autor",       col_autor),
        ("data",        col_data),
        ("localizacao", col_local),
        ("situacao",    col_situacao),
    ]:
        result[campo] = df[col_orig].astype(str).str.strip() if col_orig else ""

    def _extrair_ano(row) -> Optional[int]:
        for v in row.values:
            m = re.search(r"\b(20\d{2})\b", str(v))
            if m:
                return int(m.group(1))
        return None

    result["ano"]       = df.apply(_extrair_ano, axis=1)
    result["nome_norm"] = result["autor"].apply(normalizar_nome)

    result = result[
        result["ano"].isna() | (result["ano"] >= config.ANO_INICIO_LEGISLATURA)
    ]

    logger.info(f"transform_proposicao_interna: {len(result)} registros transformados.")
    return result.reset_index(drop=True)


# =============================================================================
# SECAO 3 -- Metricas e Indices
# =============================================================================

def calcular_taxa_presenca(df_freq: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula taxa de presenca por vereador x ano.

    Retorna: nome_norm | parlamentar | ano | total_sessoes | presencas | ausencias | taxa_presenca
    """
    if df_freq.empty:
        return pd.DataFrame(columns=["nome_norm", "parlamentar", "ano",
                                     "total_sessoes", "presencas", "ausencias", "taxa_presenca"])

    grp = df_freq.groupby(["nome_norm", "parlamentar", "ano"], dropna=False)

    result = grp["presente"].agg(
        total_sessoes="count",
        presencas="sum"
    ).reset_index()

    result["ausencias"]     = result["total_sessoes"] - result["presencas"]
    result["taxa_presenca"] = (
        result["presencas"] / result["total_sessoes"] * 100
    ).round(2)

    return result.sort_values("taxa_presenca", ascending=False).reset_index(drop=True)


def _minmax_transform(series: pd.Series) -> pd.Series:
    """Normalizacao min-max de uma Series. Retorna 0.0 se min == max."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.0] * len(series), index=series.index)
    return (series - mn) / (mx - mn)


def calcular_indice_composto(
    df_presenca: pd.DataFrame,
    df_prod: pd.DataFrame
) -> pd.DataFrame:
    """
    Indice composto de atuacao parlamentar.
    Formula: 50% frequencia (normalizada) + 50% produtividade (normalizada).
    Normalizacao: min-max dentro de cada metrica, agrupado por ano.

    Retorna: nome_norm | parlamentar | ano | taxa_presenca | total_proposicoes
             | idx_presenca_norm | idx_prod_norm | indice_composto | ranking
    """
    if df_presenca.empty:
        return pd.DataFrame()

    # Agregar produtividade
    if df_prod is not None and not df_prod.empty and "total_proposicoes" in df_prod.columns:
        df_prod_agg = (
            df_prod.groupby(["nome_norm", "ano"])["total_proposicoes"]
            .sum()
            .reset_index()
        )
    else:
        df_prod_agg = pd.DataFrame(columns=["nome_norm", "ano", "total_proposicoes"])

    df = df_presenca[["nome_norm", "parlamentar", "ano", "taxa_presenca"]].merge(
        df_prod_agg, on=["nome_norm", "ano"], how="left"
    )
    df["total_proposicoes"] = df["total_proposicoes"].fillna(0)

    # Normalizacao min-max por ano usando transform (sem FutureWarning)
    df["idx_presenca_norm"] = df.groupby("ano")["taxa_presenca"].transform(_minmax_transform)
    df["idx_prod_norm"]     = df.groupby("ano")["total_proposicoes"].transform(_minmax_transform)

    df["indice_composto"] = (
        df["idx_presenca_norm"] * 0.5 +
        df["idx_prod_norm"]     * 0.5
    ).round(4)

    df["ranking"] = df.groupby("ano")["indice_composto"].rank(
        ascending=False, method="min"
    ).astype("Int64")

    return df.sort_values(["ano", "ranking"]).reset_index(drop=True)


# =============================================================================
# SECAO 4 -- Persistencia
# =============================================================================

def save_parquet(df: pd.DataFrame, nome: str) -> None:
    """Salva DataFrame em data/{nome}.parquet e atualiza last_run.json."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"{nome}.parquet")
    df.to_parquet(path, index=False)
    logger.info(f"Salvo: {path} ({len(df)} registros)")

    last_run = {}
    if os.path.exists(config.LAST_RUN_FILE):
        with open(config.LAST_RUN_FILE, encoding="utf-8") as f:
            last_run = json.load(f)
    last_run[nome] = datetime.now().isoformat()
    with open(config.LAST_RUN_FILE, "w", encoding="utf-8") as f:
        json.dump(last_run, f, indent=2, ensure_ascii=False)


def load_parquet(nome: str) -> Optional[pd.DataFrame]:
    """Carrega data/{nome}.parquet. Retorna None se nao existir."""
    path = os.path.join(config.CACHE_DIR, f"{nome}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    return None


def cache_valido(nome: str, max_horas: int = None) -> bool:
    """Verifica se o cache de {nome} ainda esta dentro do prazo."""
    max_h = max_horas or config.CACHE_MAX_HORAS
    if not os.path.exists(config.LAST_RUN_FILE):
        return False
    with open(config.LAST_RUN_FILE, encoding="utf-8") as f:
        last_run = json.load(f)
    if nome not in last_run:
        return False
    ultima = datetime.fromisoformat(last_run[nome])
    return (datetime.now() - ultima) < timedelta(hours=max_h)


# =============================================================================
# SECAO 5 -- Pipeline Completo
# =============================================================================

def run_full_pipeline(force: bool = False) -> dict:
    """
    Executa coleta -> transformacao -> persistencia de todos os datasets.

    force=True: ignora cache e recoleta tudo.
    Retorna dict {dataset: status_string}.
    """
    from scraper import (
        FrequenciaScraper,
        ProdutividadeScraper,
        ProposicaoScraper,
        VereadorScraper,
    )
    from modules.scraper_prop_interna import ProposicaoInternaScraper

    resultados = {}

    # Vereadores
    nome = "vereadores"
    if force or not cache_valido(nome):
        try:
            raw = VereadorScraper().extract()
            df  = transform_vereadores(raw)
            save_parquet(df, nome)
            resultados[nome] = f"ok ({len(df)} registros)"
        except Exception as e:
            logger.error(f"{nome}: {e}", exc_info=True)
            resultados[nome] = f"erro: {e}"
    else:
        resultados[nome] = "cache valido"

    # Frequencia
    nome = "frequencia"
    if force or not cache_valido(nome):
        try:
            raw = FrequenciaScraper().extract()
            df  = transform_frequencia(raw)
            save_parquet(df, nome)
            resultados[nome] = f"ok ({len(df)} registros)"
        except Exception as e:
            logger.error(f"{nome}: {e}", exc_info=True)
            resultados[nome] = f"erro: {e}"
    else:
        resultados[nome] = "cache valido"

    # Produtividade
    nome = "produtividade"
    if force or not cache_valido(nome):
        try:
            raw = ProdutividadeScraper().extract(anos=[str(a) for a in config.ANOS_COBERTURA])
            df  = transform_produtividade(raw)
            save_parquet(df, nome)
            resultados[nome] = f"ok ({len(df)} registros)"
        except Exception as e:
            logger.error(f"{nome}: {e}", exc_info=True)
            resultados[nome] = f"erro: {e}"
    else:
        resultados[nome] = "cache valido"

    # Proposicoes
    nome = "proposicoes"
    if force or not cache_valido(nome):
        try:
            raw = ProposicaoScraper().extract(anos=[str(a) for a in config.ANOS_COBERTURA])
            df  = transform_produtividade(raw)
            save_parquet(df, nome)
            resultados[nome] = f"ok ({len(df)} registros)"
        except Exception as e:
            logger.error(f"{nome}: {e}", exc_info=True)
            resultados[nome] = f"erro: {e}"
    else:
        resultados[nome] = "cache valido"

    # Proposicoes Internas
    nome = "prop_interna"
    if force or not cache_valido(nome):
        try:
            raw = ProposicaoInternaScraper().extract()
            df  = transform_proposicao_interna(raw)
            save_parquet(df, nome)
            resultados[nome] = f"ok ({len(df)} registros)"
        except Exception as e:
            logger.error(f"{nome}: {e}", exc_info=True)
            resultados[nome] = f"erro: {e}"
    else:
        resultados[nome] = "cache valido"

    # Metricas derivadas
    df_freq = load_parquet("frequencia")
    df_prod = load_parquet("produtividade")

    if df_freq is not None and not df_freq.empty:
        try:
            df_pres = calcular_taxa_presenca(df_freq)
            save_parquet(df_pres, "presenca")
            resultados["presenca"] = f"ok ({len(df_pres)} registros)"

            df_rank = calcular_indice_composto(df_pres, df_prod)
            if not df_rank.empty:
                save_parquet(df_rank, "ranking")
                resultados["ranking"] = f"ok ({len(df_rank)} registros)"
        except Exception as e:
            logger.error(f"Metricas derivadas: {e}", exc_info=True)
            resultados["presenca"] = f"erro: {e}"
            resultados["ranking"]  = f"erro: {e}"

    logger.info(f"Pipeline concluido: {resultados}")
    return resultados


# =============================================================================
# SMOKE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SMOKE TEST -- transformer.py")
    print("=" * 60)

    # 1. normalizar_nome
    assert normalizar_nome("MARTA LULA RODRIGUES ") == "Marta Lula Rodrigues"
    assert normalizar_nome("Andre Fraga")            == "Andre Fraga"
    assert normalizar_nome("")                        == ""
    print("[1] normalizar_nome: OK")

    # 2. fuzzy_match_nome
    cat = ["Marta Rodrigues", "Alexandre Aleluia", "Aladilce Souza"]
    r = fuzzy_match_nome("Marta Lula Rodrigues", cat, cutoff=0.6)
    print(f"[2] fuzzy_match: 'Marta Lula Rodrigues' -> '{r}'")

    # 3. transform_frequencia com dados mockados
    raw_mock = [
        {"num_sessao": "21", "ano": "2026", "parlamentar": "Aladilce Souza",    "status": "Presente",  "mes_ano": "2026-04"},
        {"num_sessao": "21", "ano": "2026", "parlamentar": "Alexandre Aleluia", "status": "Presente",  "mes_ano": "2026-04"},
        {"num_sessao": "21", "ano": "2026", "parlamentar": "Anderson Ninho",    "status": "Licenciado","mes_ano": "2026-04"},
        {"num_sessao": "22", "ano": "2026", "parlamentar": "Aladilce Souza",    "status": "Presente",  "mes_ano": "2026-04"},
        {"num_sessao": "22", "ano": "2026", "parlamentar": "Alexandre Aleluia", "status": "Ausente",   "mes_ano": "2026-04"},
    ]
    df = transform_frequencia(raw_mock)
    assert "nome_norm" in df.columns
    assert "presente"  in df.columns
    assert df["presente"].dtype == bool
    print(f"[3] transform_frequencia: {len(df)} registros -- OK")

    # 4. calcular_taxa_presenca
    df_pres = calcular_taxa_presenca(df)
    aladilce = df_pres[df_pres["nome_norm"] == "Aladilce Souza"]
    assert not aladilce.empty
    assert aladilce.iloc[0]["taxa_presenca"] == 100.0, \
        f"Esperado 100.0, got {aladilce.iloc[0]['taxa_presenca']}"
    print("[4] calcular_taxa_presenca: OK -- Aladilce 100%")

    # 5. calcular_indice_composto
    raw_prod_mock = [
        {"_parlamentar": "Aladilce Souza",    "_ano": "2026", "projetos_lei": "5"},
        {"_parlamentar": "Alexandre Aleluia", "_ano": "2026", "projetos_lei": "3"},
    ]
    df_prod = transform_produtividade(raw_prod_mock)
    df_rank = calcular_indice_composto(df_pres, df_prod)
    assert not df_rank.empty
    assert "indice_composto" in df_rank.columns
    assert "ranking"         in df_rank.columns
    print(f"[5] calcular_indice_composto: {len(df_rank)} registros -- OK")
    print(df_rank[["parlamentar", "taxa_presenca", "total_proposicoes",
                   "indice_composto", "ranking"]].to_string(index=False))

    print("\nTodos os asserts passaram.")
