# =============================================================================
# modules/ui_sidebar.py — CMS BI Project
# Responsável por toda a interface da barra lateral (sidebar).
#
# RESPONSABILIDADES:
#   1. Exibir status de atualização dos dados e botão de coleta manual.
#   2. Renderizar os 3 filtros interativos: Ano, Mês/Ano e Vereador(es).
#   3. Aplicar os filtros nos DataFrames brutos e retornar um dicionário
#      de contexto (ctx) com os DataFrames já filtrados.
#
# FLUXO:
#   render_sidebar() → ctx dict → app.py distribui para tabs
#
# FILTROS:
#   - Ano         → filtra df_ranking, df_presenca (campo "ano")
#   - Mês/Ano     → filtra df_frequencia (campo "mes_ano"), usado no heatmap
#   - Vereador(es)→ filtra todos os DataFrames (campo "parlamentar")
#
# ATUALIZAÇÃO INSTANTÂNEA:
#   Não há botão "Aplicar". O Streamlit re-executa o script a cada mudança
#   de multiselect, aplicando os filtros automaticamente.
# =============================================================================

import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd

from transformer import run_full_pipeline, cache_valido
from modules.data_loader import limpar_cache
import config


# Mapeamento de número de mês para abreviatura em PT-BR
_MESES_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def _ultima_atualizacao() -> str:
    """
    Lê o arquivo last_run.json e retorna a data da última coleta
    no formato 'AAAA-MM-DD HH:MM:SS', ou 'Nunca' se não houver coleta.
    """
    if not os.path.exists(config.LAST_RUN_FILE):
        return "Nunca"
    with open(config.LAST_RUN_FILE, encoding="utf-8") as f:
        dados = json.load(f)
    if not dados:
        return "Nunca"
    # Filtra apenas valores que parecem timestamps ISO
    timestamps = [v for v in dados.values() if isinstance(v, str) and "T" in v]
    if not timestamps:
        return "Desconhecido"
    return max(timestamps)[:19].replace("T", " ")


def _cache_expirado() -> bool:
    """
    Retorna True se qualquer um dos 3 datasets principais estiver com
    cache vencido (mais de CACHE_MAX_HORAS horas desde a última coleta).
    """
    return not all(cache_valido(n) for n in ["frequencia", "presenca", "ranking"])


def _formatar_mes(mes_ano: str) -> str:
    """
    Converte o valor interno '2026-04' para o rótulo legível 'Abr/2026'.
    Usada como format_func no st.multiselect de meses.
    """
    try:
        ano, mes = mes_ano.split("-")
        return f"{_MESES_PT.get(mes, mes)}/{ano}"
    except Exception:
        return mes_ano


def _aplicar_filtros(
    df_ranking: pd.DataFrame,
    df_presenca: pd.DataFrame | None,
    df_frequencia: pd.DataFrame | None,
    anos_sel: list,
    meses_sel: list,
    vereadores_sel: list,
) -> dict:
    """
    Aplica os três filtros (ano, mês, vereador) nos DataFrames recebidos.

    Regras de filtragem:
      - df_ranking   → ano + vereador
      - df_presenca  → ano + vereador
      - df_frequencia → mes_ano + vereador  (o heatmap usa o filtro de mês)

    Retorna um dicionário com os três DataFrames filtrados.
    """
    # --- Filtra ranking ---
    mask_rank = (
        df_ranking["ano"].isin(anos_sel) &
        df_ranking["parlamentar"].isin(vereadores_sel)
    )
    df_rank_fil = df_ranking[mask_rank].copy()

    # --- Filtra presença ---
    if df_presenca is not None and not df_presenca.empty:
        mask_pres = (
            df_presenca["ano"].isin(anos_sel) &
            df_presenca["parlamentar"].isin(vereadores_sel)
        )
        df_pres_fil = df_presenca[mask_pres].copy()
    else:
        df_pres_fil = pd.DataFrame()

    # --- Filtra frequência (inclui filtro de mês) ---
    if df_frequencia is not None and not df_frequencia.empty:
        mask_freq = (
            df_frequencia["mes_ano"].isin(meses_sel) &
            df_frequencia["parlamentar"].isin(vereadores_sel)
        )
        df_freq_fil = df_frequencia[mask_freq].copy()
    else:
        df_freq_fil = pd.DataFrame()

    return {
        "df_rank_fil":  df_rank_fil,
        "df_pres_fil":  df_pres_fil,
        "df_freq_fil":  df_freq_fil,
    }


def render_sidebar(
    df_ranking: pd.DataFrame | None,
    df_presenca: pd.DataFrame | None,
    df_frequencia: pd.DataFrame | None,
) -> dict:
    """
    Renderiza a barra lateral completa e retorna o dicionário de contexto (ctx).

    Parâmetros:
      df_ranking    — DataFrame de ranking (usado para opções de ano e vereador).
      df_presenca   — DataFrame de taxas de presença agregadas.
      df_frequencia — DataFrame de frequência bruta (usado para opções de mês).

    Retorna:
      ctx = {
        "anos_sel":        list[int],   — Anos selecionados
        "meses_sel":       list[str],   — Meses selecionados ('YYYY-MM')
        "vereadores_sel":  list[str],   — Nomes dos vereadores selecionados
        "df_rank_fil":     DataFrame,   — Ranking filtrado
        "df_pres_fil":     DataFrame,   — Presença filtrada
        "df_freq_fil":     DataFrame,   — Frequência filtrada
      }
    """
    with st.sidebar:
        # ── Cabeçalho ────────────────────────────────────────────────────
        st.markdown("## 🏛️ CMS BI Salvador")
        st.caption("Câmara Municipal de Salvador — Dados Públicos")
        st.divider()

        # ── Status de atualização ─────────────────────────────────────────
        ultima = _ultima_atualizacao()
        if ultima == "Nunca":
            st.error("Sem dados locais. Colete agora.")
        elif _cache_expirado():
            st.warning(f"Desatualizado · {ultima}")
        else:
            st.success(f"✅ Atualizado · {ultima}")

        # ── Botão de coleta manual ────────────────────────────────────────
        # Executa o pipeline completo (scraping + transform + parquet).
        # Após a coleta, invalida o cache do st.cache_data para que os
        # novos dados sejam lidos imediatamente na próxima renderização.
        if st.button("🔄 Coletar Dados Agora", type="primary", use_container_width=True):
            with st.spinner("Coletando dados… pode levar alguns minutos."):
                resultado = run_full_pipeline(force=True)
            limpar_cache()   # invalida cache para refletir novos dados
            st.success("Coleta concluída!")
            with st.expander("Detalhes da coleta"):
                for k, v in resultado.items():
                    icone = "✅" if "ok" in v else ("📦" if "cache" in v else "❌")
                    st.write(f"{icone} **{k}**: {v}")
            st.rerun()

        st.divider()

        # ── Guarda de dados: para sem dados locais ────────────────────────
        dados_ok = df_ranking is not None and not df_ranking.empty
        if not dados_ok:
            st.info("Use o botão acima para coletar os dados pela primeira vez.")
            st.stop()  # interrompe toda a execução do script Streamlit

        # ── Seção de Filtros ──────────────────────────────────────────────
        st.subheader("🔍 Filtros")
        st.caption("Atualizados instantaneamente ao selecionar.")

        # --- Filtro 1: Ano ---
        # Extrai anos únicos do ranking, restrito à legislatura atual (2025+).
        todos_anos = sorted(
            [int(a) for a in df_ranking["ano"].dropna().unique().tolist()
             if int(a) >= config.ANO_INICIO_LEGISLATURA],
            reverse=True,
        )
        anos_sel = st.multiselect(
            label="📅 Ano(s)",
            options=todos_anos,
            default=[todos_anos[0]] if todos_anos else [],
            help="Filtra todos os gráficos pelo(s) ano(s) legislativo(s) selecionado(s).",
        )
        # Se nenhum ano for selecionado, assume todos (evita tela em branco).
        if not anos_sel:
            anos_sel = todos_anos

        # --- Filtro 2: Mês/Ano ---
        # Disponível apenas quando o parquet de frequência está carregado.
        # Afeta somente o Heatmap de Presença (aba Frequência).
        meses_disponiveis: list[str] = []
        if df_frequencia is not None and "mes_ano" in df_frequencia.columns:
            meses_disponiveis = sorted(
                df_frequencia["mes_ano"].dropna().unique().tolist(), reverse=True
            )

        meses_sel = st.multiselect(
            label="🗓️ Mês/Ano",
            options=meses_disponiveis,
            default=[],
            format_func=_formatar_mes,
            placeholder="Todos os meses",
            help="Filtra o Heatmap de Presença pelo(s) mês(es) selecionado(s).",
        )
        # Nenhum mês selecionado = mostrar todos
        if not meses_sel:
            meses_sel = meses_disponiveis

        # --- Filtro 3: Vereador(es) ---
        # Lista de nomes únicos do ranking, ordenados alfabeticamente.
        todos_vereadores = sorted(
            df_ranking["parlamentar"].dropna().unique().tolist()
        )
        vereadores_sel = st.multiselect(
            label="👤 Vereador(es)",
            options=todos_vereadores,
            default=[],
            placeholder="Todos os vereadores",
            help="Filtra todos os gráficos pelos vereadores selecionados.",
        )
        # Nenhum vereador selecionado = mostrar todos
        if not vereadores_sel:
            vereadores_sel = todos_vereadores

    # ── Aplica filtros fora do bloco `with st.sidebar` ────────────────────
    # Os DataFrames filtrados são calculados aqui e repassados via ctx.
    filtrados = _aplicar_filtros(
        df_ranking, df_presenca, df_frequencia,
        anos_sel, meses_sel, vereadores_sel,
    )

    return {
        "anos_sel":           anos_sel,
        "meses_sel":          meses_sel,
        "vereadores_sel":     vereadores_sel,
        "ultima_atualizacao": _ultima_atualizacao(),
        **filtrados,
    }
