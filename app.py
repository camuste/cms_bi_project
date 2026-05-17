# =============================================================================
# app.py — CMS BI Project  |  Orquestrador Principal
# Câmara Municipal de Salvador — Dashboard Streamlit (Dark Mode Premium)
#
# ARQUITETURA:
#   Este arquivo é o ponto de entrada do Streamlit. Sua única responsabilidade
#   é orquestrar: configurar a página, injetar CSS, carregar dados, delegar
#   filtros à sidebar e compor as abas chamando os módulos especializados.
#
#   Módulos importados:
#     modules/data_loader.py  → leitura cacheada dos .parquet
#     modules/ui_sidebar.py   → sidebar com filtros Ano / Mês / Vereador
#     modules/ui_charts.py    → todas as figuras Plotly
#     modules/ui_kpis.py      → KPI metric cards
#
# EXECUÇÃO:
#   streamlit run app.py
# =============================================================================

import os
import json

import streamlit as st
import pandas as pd

# ── Módulos do projeto ────────────────────────────────────────────────────────
from modules.data_loader import (
    carregar_frequencia,
    carregar_presenca,
    carregar_ranking,
    carregar_produtividade,
    carregar_proposicoes,
    carregar_proposicao_interna,
)
from modules.ui_sidebar import render_sidebar
from modules.ui_kpis import kpis_frequencia, kpis_produtividade, kpis_ranking
from modules.ui_tab_proposicoes import render_tab_proposicoes
from modules.ui_charts import (
    grafico_bar_frequencia,
    grafico_heatmap_presenca,
    grafico_bar_produtividade,
    grafico_linha_evolucao,
    grafico_radar_performance,
    grafico_bar_ranking,
    grafico_scatter_presenca_prod,
)
import config


# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# Deve ser a primeira chamada Streamlit do script.
# =============================================================================

st.set_page_config(
    page_title="CMS BI — Vereadores de Salvador",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# CSS PREMIUM — Dark Mode
# Estiliza: KPI cards, tabs, sidebar, dataframes e scrollbar.
# O seletor div[data-testid="metric-container"] é o container nativo dos
# st.metric(), garantindo compatibilidade com atualizações do Streamlit.
# =============================================================================

st.markdown("""
<style>
/* ── KPI Metric Cards ─────────────────────────────────────────────────── */
div[data-testid="metric-container"] {
    background-color : #1E1E1E;
    border-radius    : 10px;
    padding          : 18px 20px 14px 20px;
    box-shadow       : 2px 4px 10px rgba(0, 0, 0, 0.4);
    border-left      : 4px solid #004A99;
}
div[data-testid="metric-container"] label {
    color          : #9E9E9E !important;
    font-size      : 0.78rem !important;
    letter-spacing : 0.05em;
    text-transform : uppercase;
}
div[data-testid="metric-container"] div[data-testid="metric-value"] {
    color       : #E0E0E0 !important;
    font-size   : 1.6rem !important;
    font-weight : 700;
}

/* ── Tabs ─────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap              : 6px;
    background-color : #1E1E1E;
    border-radius    : 8px;
    padding          : 4px 6px;
}
.stTabs [data-baseweb="tab"] {
    background-color : transparent;
    border-radius    : 6px;
    padding          : 8px 22px;
    color            : #9E9E9E;
    font-weight      : 500;
}
.stTabs [aria-selected="true"] {
    background-color : #004A99 !important;
    color            : #FFFFFF !important;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background-color : #1A1A2E;
    border-right     : 1px solid #2A2A3E;
}

/* ── Dataframe ────────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] {
    border        : 1px solid #2A2A2A;
    border-radius : 8px;
    overflow      : hidden;
}

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar       { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #1E1E1E; }
::-webkit-scrollbar-thumb { background: #004A99; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# CARREGAMENTO DE DADOS  (todos cacheados via @st.cache_data)
# A leitura do disco ocorre apenas na primeira execução ou após 1 hora (TTL).
# Cliques nos filtros NÃO relêem o disco — usam o cache em memória.
# =============================================================================

df_frequencia      = carregar_frequencia()
df_presenca        = carregar_presenca()
df_ranking         = carregar_ranking()
df_produtividade   = carregar_produtividade()
df_proposicoes     = carregar_proposicoes()
df_prop_interna    = carregar_proposicao_interna()


# =============================================================================
# SIDEBAR — FILTROS DINÂMICOS
# render_sidebar() devolve `ctx`, um dicionário com:
#   ctx["anos_sel"]       → lista de anos selecionados
#   ctx["meses_sel"]      → lista de meses selecionados (formato YYYY-MM)
#   ctx["vereadores_sel"] → lista de nomes de vereadores selecionados
#   ctx["df_rank_fil"]    → ranking filtrado
#   ctx["df_pres_fil"]    → presença filtrada
#   ctx["df_freq_fil"]    → frequência filtrada (por mês + vereador)
# =============================================================================

ctx = render_sidebar(df_ranking, df_presenca, df_frequencia)


# =============================================================================
# CABEÇALHO PRINCIPAL
# =============================================================================

st.markdown("## 🏛️ Observatório Parlamentar · Câmara Municipal de Salvador")
st.caption(
    "Dados públicos coletados automaticamente das fontes da CMS · "
    f"Última atualização: **{ctx.get('ultima_atualizacao', '—')}**"
    if "ultima_atualizacao" in ctx
    else "Dados públicos coletados automaticamente das fontes da CMS."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "📅  Frequência",
    "📋  Produtividade",
    "🏆  Ranking Geral",
    "📜  Proposições Internas",
])


# =============================================================================
# ABA 1 — FREQUÊNCIA
# Exibe: KPIs de presença, gráfico de barras e heatmap mensal.
# Fonte de dados: df_pres_fil (barras/KPIs) e df_freq_fil (heatmap).
# =============================================================================

with tab1:
    st.header("Frequência em Sessões Plenárias")

    if ctx["df_pres_fil"].empty:
        st.info(
            "Nenhum dado de frequência disponível para o período selecionado. "
            "Ajuste os filtros ou colete os dados pela primeira vez."
        )
    else:
        # Métricas destacadas
        kpis_frequencia(ctx["df_pres_fil"])
        st.divider()

        # Gráfico de barras: taxa de presença por vereador
        st.plotly_chart(
            grafico_bar_frequencia(ctx["df_pres_fil"], ctx["anos_sel"]),
            width="stretch",
        )

        # Heatmap: presença mensal (disponível quando frequência bruta existe)
        fig_hm = grafico_heatmap_presenca(ctx["df_freq_fil"])
        if fig_hm is not None:
            st.plotly_chart(fig_hm, width="stretch")
        else:
            st.info("Selecione ao menos um mês para exibir o Heatmap de Presença.")

        # Tabela exportável
        st.subheader("Tabela Detalhada")
        colunas_tabela = [c for c in
            ["parlamentar", "ano", "total_sessoes", "presencas", "ausencias", "taxa_presenca"]
            if c in ctx["df_pres_fil"].columns
        ]
        df_tabela = ctx["df_pres_fil"][colunas_tabela].sort_values("taxa_presenca", ascending=False)
        st.dataframe(df_tabela, width="stretch", hide_index=True)

        csv_freq = df_tabela.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="⬇️ Baixar CSV de Frequência",
            data=csv_freq,
            file_name=f"frequencia_cms_{'_'.join(str(a) for a in ctx['anos_sel'])}.csv",
            mime="text/csv",
        )


# =============================================================================
# ABA 2 — PRODUTIVIDADE
# Exibe: KPIs, barras de proposições, evolução anual e radar de performance.
# Fonte: df_produtividade/df_proposicoes (filtrados aqui) e df_rank_fil (radar).
# =============================================================================

with tab2:
    st.header("Produtividade Legislativa")

    # Determina o DataFrame de produtividade a usar (produtividade ou proposições)
    df_prod_base = df_produtividade if df_produtividade is not None else df_proposicoes

    if df_prod_base is not None and not df_prod_base.empty:
        # Aplica filtros de ano e vereador na produtividade
        mask_prod = (
            df_prod_base["ano"].isin(ctx["anos_sel"]) &
            df_prod_base["parlamentar"].isin(ctx["vereadores_sel"])
        )
        df_prod_fil = df_prod_base[mask_prod]
    else:
        df_prod_fil = pd.DataFrame()

    if df_prod_fil.empty:
        st.info(
            "Dados de produtividade ainda não disponíveis. "
            "Use o botão 'Coletar Dados Agora' na barra lateral para iniciar a coleta."
        )
    else:
        kpis_produtividade(df_prod_fil)
        st.divider()

        # Barras horizontais de proposições
        st.plotly_chart(
            grafico_bar_produtividade(df_prod_fil),
            width="stretch",
        )

        # Linha de evolução temporal (só com múltiplos anos selecionados)
        if len(ctx["anos_sel"]) > 1:
            st.plotly_chart(
                grafico_linha_evolucao(df_prod_fil),
                width="stretch",
            )

    # ── Radar de Performance ──────────────────────────────────────────────
    # Sempre exibido quando há dados de ranking, mesmo com produtividade zerada.
    # Permite visualizar a dimensão de assiduidade imediatamente,
    # e a dimensão de proposições se preencherá automaticamente após coleta.
    st.divider()
    st.subheader("Radar de Performance Parlamentar")
    st.caption(
        "Compara os **top 8 vereadores** em 3 dimensões: Assiduidade, Proposições e Índice Composto. "
        "O eixo Proposições atualiza automaticamente após a coleta de produtividade."
    )

    if not ctx["df_rank_fil"].empty:
        st.plotly_chart(
            grafico_radar_performance(ctx["df_rank_fil"]),
            width="stretch",
        )
    else:
        st.info("Sem dados de ranking para o período selecionado.")


# =============================================================================
# ABA 3 — RANKING GERAL
# Exibe: KPIs, tabela interativa, barras de índice composto e scatter.
# Fonte: df_rank_fil agregado por parlamentar.
# =============================================================================

with tab3:
    st.header("Ranking Geral de Atuação")
    st.caption(
        "**Índice composto:** 50 % Assiduidade (normalizada) + "
        "50 % Proposições (normalizadas) · Normalização min-max por ano."
    )

    if ctx["df_rank_fil"].empty:
        st.info("Sem dados de ranking para o período selecionado.")
    else:
        # Agrega múltiplos anos: média de taxa_presenca e índice, soma de proposições
        agg = {"taxa_presenca": ("taxa_presenca", "mean"),
               "indice_composto": ("indice_composto", "mean")}
        if "total_proposicoes" in ctx["df_rank_fil"].columns:
            agg["total_proposicoes"] = ("total_proposicoes", "sum")

        df_rank_show = (
            ctx["df_rank_fil"]
            .groupby("parlamentar", as_index=False)
            .agg(**agg)
            .sort_values("indice_composto", ascending=False)
            .reset_index(drop=True)
        )
        df_rank_show.insert(0, "ranking", range(1, len(df_rank_show) + 1))
        df_rank_show["taxa_presenca"]   = df_rank_show["taxa_presenca"].round(1)
        df_rank_show["indice_composto"] = df_rank_show["indice_composto"].round(4)

        # KPI cards do ranking
        kpis_ranking(df_rank_show)
        st.divider()

        # Tabela interativa com colunas em PT-BR
        renomear = {
            "ranking":          "🏆 Pos.",
            "parlamentar":      "Vereador",
            "taxa_presenca":    "% Presença",
            "indice_composto":  "Índice (0–1)",
        }
        if "total_proposicoes" in df_rank_show.columns:
            renomear["total_proposicoes"] = "Proposições"

        colunas_rank = [c for c in renomear if c in df_rank_show.columns]
        st.dataframe(
            df_rank_show[colunas_rank].rename(columns=renomear),
            width="stretch",
            hide_index=True,
        )

        # Barras horizontais do índice composto
        st.plotly_chart(
            grafico_bar_ranking(df_rank_show),
            width="stretch",
        )

        # Scatter: Presença × Produtividade
        st.plotly_chart(
            grafico_scatter_presenca_prod(df_rank_show),
            width="stretch",
        )

        # Download do ranking em CSV
        csv_rank = df_rank_show.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="⬇️ Baixar Ranking CSV",
            data=csv_rank,
            file_name=f"ranking_cms_{'_'.join(str(a) for a in ctx['anos_sel'])}.csv",
            mime="text/csv",
        )


# =============================================================================
# ABA 4 — PROPOSIÇÕES INTERNAS
# Dados de https://cmsalvador.sys.inf.br/cl/prop_interna/ (legislatura 2025+).
# Filtros de ano e vereador são repassados do ctx gerado pela sidebar.
# =============================================================================

with tab4:
    render_tab_proposicoes(
        df_prop_interna,
        ctx["vereadores_sel"],
        ctx["anos_sel"],
    )
