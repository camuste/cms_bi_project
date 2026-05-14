# =============================================================================
# app.py — CMS BI Project
# Câmara Municipal de Salvador — Dashboard Streamlit
# =============================================================================
# Execução: streamlit run app.py
# =============================================================================

import os
import json
from datetime import datetime

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from transformer import (
    load_parquet,
    cache_valido,
    run_full_pipeline,
)
import config

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================

st.set_page_config(
    page_title="CMS BI — Vereadores de Salvador",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS mínimo para melhorar aparência
st.markdown("""
<style>
    .metric-card { background: #f0f2f6; border-radius: 8px; padding: 1rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 20px; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def _ultima_atualizacao() -> str:
    if not os.path.exists(config.LAST_RUN_FILE):
        return "Nunca"
    with open(config.LAST_RUN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return "Nunca"
    timestamps = [v for v in data.values() if isinstance(v, str) and "T" in v]
    if not timestamps:
        return "Desconhecido"
    ultima = min(timestamps)
    return ultima[:19].replace("T", " ")


def _cache_expirado() -> bool:
    return not all(cache_valido(n) for n in ["frequencia", "presenca", "ranking"])


def _cor_presenca(taxa: float) -> str:
    if taxa >= 85:
        return "#2e7d32"   # verde escuro
    if taxa >= 70:
        return "#f9a825"   # amarelo
    return "#c62828"       # vermelho


# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.title("🏛️ CMS BI Salvador")
    st.caption("Câmara Municipal de Salvador\nDados Públicos — Acesso Livre")
    st.divider()

    # Status do cache
    ultima = _ultima_atualizacao()
    if ultima == "Nunca":
        st.error("⚠️ Sem dados locais.")
    elif _cache_expirado():
        st.warning(f"⚠️ Dados desatualizados\n{ultima}")
    else:
        st.success(f"✅ Dados atualizados\n{ultima}")

    # Botão de coleta
    if st.button("🔄 Coletar Dados Agora", type="primary", use_container_width=True):
        with st.spinner("Coletando dados... Pode levar alguns minutos."):
            resultado = run_full_pipeline(force=True)
        st.success("Coleta concluída!")
        with st.expander("Detalhes da coleta"):
            for k, v in resultado.items():
                icon = "✅" if "ok" in v else ("📦" if "cache" in v else "❌")
                st.write(f"{icon} **{k}**: {v}")
        st.rerun()

    st.divider()

    # Carregar dados para os filtros
    df_ranking = load_parquet("ranking")
    df_presenca = load_parquet("presenca")

    if df_ranking is None or df_ranking.empty:
        st.info("Use o botão acima para coletar os dados pela primeira vez.")
        st.stop()

    # Filtros
    st.subheader("Filtros")

    todos_anos = sorted(
        df_ranking["ano"].dropna().unique().tolist(), reverse=True
    )
    anos_sel = st.multiselect(
        "Ano(s)",
        options=todos_anos,
        default=[todos_anos[0]] if todos_anos else [],
    )
    if not anos_sel:
        anos_sel = todos_anos

    todos_partidos = ["Todos"] + sorted(
        df_ranking["parlamentar"].dropna().unique().tolist()
    )

    # Filtrar DataFrame pelo ano selecionado
    df_rank_fil = df_ranking[df_ranking["ano"].isin(anos_sel)]
    df_pres_fil = df_presenca[df_presenca["ano"].isin(anos_sel)] \
        if df_presenca is not None else pd.DataFrame()


# =============================================================================
# CONTEÚDO PRINCIPAL
# =============================================================================

st.title("🏛️ Observatório Parlamentar — Câmara Municipal de Salvador")
st.caption(
    f"Dados coletados automaticamente das fontes públicas da CMS. "
    f"Última atualização: **{_ultima_atualizacao()}**"
)

tab1, tab2, tab3 = st.tabs([
    "📅  Frequência",
    "📋  Produtividade",
    "🏆  Ranking Geral",
])


# =============================================================================
# TAB 1 — FREQUÊNCIA
# =============================================================================

with tab1:
    st.header("Frequência em Sessões Plenárias")

    if df_pres_fil.empty:
        st.info("Dados de frequência não disponíveis para o período selecionado.")
    else:
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        media = df_pres_fil["taxa_presenca"].mean()
        total_sessoes = df_pres_fil["total_sessoes"].max() if "total_sessoes" in df_pres_fil.columns else 0
        top_parl = df_pres_fil.loc[df_pres_fil["taxa_presenca"].idxmax(), "parlamentar"] \
            if not df_pres_fil.empty else "—"
        bot_parl = df_pres_fil.loc[df_pres_fil["taxa_presenca"].idxmin(), "parlamentar"] \
            if not df_pres_fil.empty else "—"

        col1.metric("Média de Presença", f"{media:.1f}%")
        col2.metric("Total de Sessões", int(total_sessoes))
        col3.metric("Mais Presente", top_parl)
        col4.metric("Menos Presente", bot_parl)

        st.divider()

        # Bar chart: taxa de presença por vereador
        df_bar = df_pres_fil.groupby("parlamentar", as_index=False)["taxa_presenca"].mean()
        df_bar = df_bar.sort_values("taxa_presenca", ascending=True)
        df_bar["cor"] = df_bar["taxa_presenca"].apply(_cor_presenca)

        fig_bar = px.bar(
            df_bar,
            x="taxa_presenca",
            y="parlamentar",
            orientation="h",
            color="taxa_presenca",
            color_continuous_scale=["#c62828", "#f9a825", "#2e7d32"],
            range_color=[0, 100],
            title=f"Taxa de Presença por Vereador — {', '.join(str(a) for a in anos_sel)}",
            labels={"taxa_presenca": "% Presença", "parlamentar": ""},
            text=df_bar["taxa_presenca"].round(1).astype(str) + "%",
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            height=max(500, len(df_bar) * 24),
            coloraxis_showscale=False,
            margin=dict(l=180, r=60),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Heatmap: presença por mês
        df_freq = load_parquet("frequencia")
        if df_freq is not None and "mes_ano" in df_freq.columns:
            df_hm = df_freq[df_freq["ano"].isin(anos_sel)].copy()
            if not df_hm.empty:
                pivot = (
                    df_hm.groupby(["parlamentar", "mes_ano"])["presente"]
                    .mean()
                    .reset_index()
                    .pivot(index="parlamentar", columns="mes_ano", values="presente")
                    * 100
                ).round(0)
                pivot = pivot.sort_index()
                fig_hm = px.imshow(
                    pivot,
                    color_continuous_scale=["#c62828", "#f9a825", "#2e7d32"],
                    range_color=[0, 100],
                    title="Heatmap de Presença por Mês/Vereador (%)",
                    labels={"color": "% Presença"},
                    aspect="auto",
                )
                fig_hm.update_layout(height=max(400, len(pivot) * 20))
                st.plotly_chart(fig_hm, use_container_width=True)

        # Tabela exportável
        st.subheader("Tabela Detalhada")
        df_show = df_pres_fil[["parlamentar", "ano", "total_sessoes",
                                "presencas", "ausencias", "taxa_presenca"]] \
            .sort_values("taxa_presenca", ascending=False)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # Botão de download CSV
        csv = df_show.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ Baixar CSV de Frequência",
            data=csv,
            file_name=f"frequencia_cms_{'_'.join(str(a) for a in anos_sel)}.csv",
            mime="text/csv",
        )


# =============================================================================
# TAB 2 — PRODUTIVIDADE
# =============================================================================

with tab2:
    st.header("Produtividade Legislativa")

    df_prod = load_parquet("produtividade")
    df_prop = load_parquet("proposicoes")

    if df_prod is None and df_prop is None:
        st.info("Dados de produtividade não disponíveis. Colete os dados primeiro.")
    else:
        df_use = df_prod if df_prod is not None else df_prop
        df_use = df_use[df_use["ano"].isin(anos_sel)] if df_use is not None else pd.DataFrame()

        if df_use.empty:
            st.info("Sem dados de produtividade para o período selecionado.")
        else:
            # KPIs
            total_prop = int(df_use["total_proposicoes"].sum()) if "total_proposicoes" in df_use.columns else 0
            media_prop = df_use["total_proposicoes"].mean() if "total_proposicoes" in df_use.columns else 0
            top_prod   = df_use.loc[df_use["total_proposicoes"].idxmax(), "parlamentar"] \
                if "total_proposicoes" in df_use.columns else "—"

            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Proposições", total_prop)
            col2.metric("Média por Vereador",   f"{media_prop:.1f}")
            col3.metric("Mais Produtivo",        top_prod)

            st.divider()

            # Bar chart: proposições por vereador
            if "total_proposicoes" in df_use.columns:
                df_prod_bar = (
                    df_use.groupby("parlamentar", as_index=False)["total_proposicoes"]
                    .sum()
                    .sort_values("total_proposicoes", ascending=True)
                )
                fig_prod = px.bar(
                    df_prod_bar,
                    x="total_proposicoes",
                    y="parlamentar",
                    orientation="h",
                    color="total_proposicoes",
                    color_continuous_scale="Blues",
                    title="Total de Proposições por Vereador",
                    labels={"total_proposicoes": "Proposições", "parlamentar": ""},
                    text="total_proposicoes",
                )
                fig_prod.update_traces(textposition="outside")
                fig_prod.update_layout(
                    height=max(500, len(df_prod_bar) * 24),
                    coloraxis_showscale=False,
                    margin=dict(l=180, r=60),
                )
                st.plotly_chart(fig_prod, use_container_width=True)

            # Evolução temporal (se múltiplos anos)
            if len(anos_sel) > 1 and "total_proposicoes" in df_use.columns:
                df_evol = (
                    df_use.groupby(["ano", "parlamentar"], as_index=False)["total_proposicoes"]
                    .sum()
                )
                fig_evol = px.line(
                    df_evol,
                    x="ano", y="total_proposicoes",
                    color="parlamentar",
                    title="Evolução de Proposições por Vereador",
                    labels={"total_proposicoes": "Proposições", "ano": "Ano"},
                    markers=True,
                )
                st.plotly_chart(fig_evol, use_container_width=True)

            # Scatter: presença × produtividade
            if not df_rank_fil.empty and "total_proposicoes" in df_rank_fil.columns:
                df_scatter = df_rank_fil.groupby("parlamentar", as_index=False).agg(
                    taxa_presenca=("taxa_presenca", "mean"),
                    total_proposicoes=("total_proposicoes", "sum"),
                )
                fig_scat = px.scatter(
                    df_scatter,
                    x="taxa_presenca",
                    y="total_proposicoes",
                    text="parlamentar",
                    title="Presença vs. Produtividade",
                    labels={
                        "taxa_presenca": "Taxa de Presença (%)",
                        "total_proposicoes": "Total de Proposições",
                    },
                    color="total_proposicoes",
                    color_continuous_scale="Viridis",
                )
                fig_scat.update_traces(textposition="top center", textfont_size=9)
                fig_scat.update_layout(height=550)
                st.plotly_chart(fig_scat, use_container_width=True)


# =============================================================================
# TAB 3 — RANKING GERAL
# =============================================================================

with tab3:
    st.header("Ranking Geral de Atuação")
    st.caption(
        "**Índice composto:** 50% Taxa de Presença (normalizada) + "
        "50% Total de Proposições (normalizada). Normalização min-max por ano."
    )

    if df_rank_fil.empty:
        st.info("Dados de ranking não disponíveis para o período selecionado.")
    else:
        # Agregar se múltiplos anos
        df_rank_show = df_rank_fil.groupby("parlamentar", as_index=False).agg(
            taxa_presenca=("taxa_presenca", "mean"),
            total_proposicoes=("total_proposicoes", "sum")
            if "total_proposicoes" in df_rank_fil.columns
            else ("ranking", "count"),
            indice_composto=("indice_composto", "mean"),
        ).sort_values("indice_composto", ascending=False)
        df_rank_show["ranking"] = range(1, len(df_rank_show) + 1)
        df_rank_show["taxa_presenca"] = df_rank_show["taxa_presenca"].round(1)
        df_rank_show["indice_composto"] = df_rank_show["indice_composto"].round(4)

        # KPIs
        col1, col2, col3 = st.columns(3)
        col1.metric("1º Lugar", df_rank_show.iloc[0]["parlamentar"])
        col2.metric("Índice Máximo", f"{df_rank_show.iloc[0]['indice_composto']:.3f}")
        col3.metric("Vereadores Analisados", len(df_rank_show))

        st.divider()

        # Tabela
        st.dataframe(
            df_rank_show[["ranking", "parlamentar", "taxa_presenca",
                          "total_proposicoes", "indice_composto"]].rename(columns={
                "ranking":            "🏆 Pos.",
                "parlamentar":        "Vereador",
                "taxa_presenca":      "% Presença",
                "total_proposicoes":  "Proposições",
                "indice_composto":    "Índice (0-1)",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Bar chart horizontal
        fig_rank = px.bar(
            df_rank_show.sort_values("indice_composto"),
            x="indice_composto",
            y="parlamentar",
            orientation="h",
            color="indice_composto",
            color_continuous_scale=["#c62828", "#f9a825", "#2e7d32"],
            range_color=[0, 1],
            title="Ranking por Índice Composto de Atuação",
            labels={"indice_composto": "Índice (0-1)", "parlamentar": ""},
            text=df_rank_show.sort_values("indice_composto")["indice_composto"]
                 .round(3).astype(str),
        )
        fig_rank.update_traces(textposition="outside")
        fig_rank.update_layout(
            height=max(500, len(df_rank_show) * 24),
            coloraxis_showscale=False,
            margin=dict(l=180, r=80),
        )
        st.plotly_chart(fig_rank, use_container_width=True)

        # Download
        csv_rank = df_rank_show.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ Baixar Ranking CSV",
            data=csv_rank,
            file_name=f"ranking_cms_{'_'.join(str(a) for a in anos_sel)}.csv",
            mime="text/csv",
        )
