# =============================================================================
# modules/ui_kpis.py — CMS BI Project
# Renderiza os KPI cards (métricas destacadas) de cada aba do dashboard.
#
# DESIGN:
#   Cada função recebe um DataFrame já filtrado e renderiza diretamente
#   os st.metric() usando st.columns(). Não retorna nada — efeito colateral
#   puro de UI (padrão Streamlit para componentes de saída).
#
# CSS:
#   O estilo visual dos cards (borda azul, sombra, fundo escuro) é aplicado
#   via o CSS injetado em app.py sobre o seletor
#   div[data-testid="metric-container"].
# =============================================================================

import streamlit as st
import pandas as pd


def kpis_frequencia(df_pres: pd.DataFrame) -> None:
    """
    Exibe 4 KPI cards para a aba de Frequência:
      - Média de Presença (%)
      - Total de Sessões analisadas
      - Vereador mais presente (com sua taxa)
      - Vereador menos presente (com delta negativo)

    Parâmetro: df_pres — DataFrame de presença filtrado.
    Não renderiza nada se o DataFrame estiver vazio.
    """
    if df_pres.empty:
        return

    media      = df_pres["taxa_presenca"].mean()
    total_sess = (
        int(df_pres["total_sessoes"].max())
        if "total_sessoes" in df_pres.columns else 0
    )

    idx_max   = df_pres["taxa_presenca"].idxmax()
    idx_min   = df_pres["taxa_presenca"].idxmin()
    top_parl  = df_pres.loc[idx_max, "parlamentar"]
    bot_parl  = df_pres.loc[idx_min, "parlamentar"]
    top_taxa  = df_pres.loc[idx_max, "taxa_presenca"]
    bot_taxa  = df_pres.loc[idx_min, "taxa_presenca"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Média de Presença",  f"{media:.1f}%")
    c2.metric("Total de Sessões",   total_sess)
    c3.metric("Mais Presente",      top_parl,  f"{top_taxa:.1f}%")
    c4.metric("Menos Presente",     bot_parl,  f"-{100 - bot_taxa:.1f}%")


def kpis_produtividade(df_prod: pd.DataFrame) -> None:
    """
    Exibe 3 KPI cards para a aba de Produtividade:
      - Total de proposições no período
      - Média de proposições por vereador
      - Vereador mais produtivo

    Parâmetro: df_prod — DataFrame de produtividade filtrado.
    Não renderiza nada se a coluna total_proposicoes estiver ausente.
    """
    if df_prod.empty or "total_proposicoes" not in df_prod.columns:
        return

    total_prop = int(df_prod["total_proposicoes"].sum())
    media_prop = df_prod["total_proposicoes"].mean()
    top_prod   = df_prod.loc[df_prod["total_proposicoes"].idxmax(), "parlamentar"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Proposições", total_prop)
    c2.metric("Média por Vereador",   f"{media_prop:.1f}")
    c3.metric("Mais Produtivo",        top_prod)


def kpis_ranking(df_rank_show: pd.DataFrame) -> None:
    """
    Exibe 3 KPI cards para a aba de Ranking Geral:
      - Nome do vereador em 1º lugar
      - Índice composto máximo
      - Quantidade de vereadores analisados

    Parâmetro: df_rank_show — DataFrame de ranking já agregado e ordenado
               por indice_composto (decrescente), com coluna 'parlamentar'.
    """
    if df_rank_show.empty:
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("🥇 1º Lugar",            df_rank_show.iloc[0]["parlamentar"])
    c2.metric("Índice Máximo",           f"{df_rank_show.iloc[0]['indice_composto']:.3f}")
    c3.metric("Vereadores Analisados",   len(df_rank_show))
