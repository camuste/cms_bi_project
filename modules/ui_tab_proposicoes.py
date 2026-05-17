# =============================================================================
# modules/ui_tab_proposicoes.py — CMS BI Project
# Componente da aba "Proposições Internas" do dashboard.
#
# RESPONSABILIDADE:
#   Renderiza KPIs, gráficos e tabela interativa de proposições internas
#   coletadas de https://cmsalvador.sys.inf.br/cl/prop_interna/
#
# ENTRADA:
#   df_prop       — DataFrame de carregar_proposicao_interna() (pode ser None)
#   vereadores_sel — lista de vereadores selecionados na sidebar
#   anos_sel       — lista de anos selecionados na sidebar
#
# FILTROS APLICADOS INTERNAMENTE:
#   - Ano via coluna "ano"
#   - Autor via coluna "nome_norm" (comparação normalizada sem acentos)
#
# DESIGN:
#   - Segue o mesmo padrão dark das outras abas (via _aplicar_dark de ui_charts)
#   - Dois gráficos lado a lado: proposições por tipo e top 15 autores
#   - Tabela detalhada com busca por ementa e botão de download CSV
# =============================================================================

import unicodedata

import streamlit as st
import pandas as pd
import plotly.express as px

from modules.ui_charts import _aplicar_dark, _NEON, _SCALE_RB


# -----------------------------------------------------------------------------
# Helper interno — normalização de nomes para filtro
# -----------------------------------------------------------------------------

def _norm(nome: str) -> str:
    """
    Remove acentos e converte para title case para comparar nomes
    com a coluna 'nome_norm' do DataFrame de proposições.
    """
    if not isinstance(nome, str) or not nome.strip():
        return ""
    nome = " ".join(nome.split()).strip()
    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ascii", "ignore").decode("ascii")
    return nome.title()


# -----------------------------------------------------------------------------
# Componente principal da aba
# -----------------------------------------------------------------------------

def render_tab_proposicoes(
    df_prop: pd.DataFrame | None,
    vereadores_sel: list,
    anos_sel: list,
) -> None:
    """
    Renderiza a aba de Proposições Internas com KPIs, gráficos e tabela.

    Estrutura da aba:
      1. KPIs: total de proposições, tipos distintos, autores únicos
      2. Gráfico de barras: proposições por tipo
      3. Gráfico de barras: top 15 autores
      4. Tabela detalhada com busca por ementa + download CSV

    Parâmetros:
      df_prop        — DataFrame carregado pelo data_loader (None se não coletado)
      vereadores_sel — nomes dos vereadores selecionados na sidebar
      anos_sel       — anos selecionados na sidebar
    """
    st.header("Proposições Internas")
    st.caption(
        "Proposições registradas no sistema público da CMS Salvador · "
        "Fonte: cmsalvador.sys.inf.br · Legislatura 2025+"
    )

    if df_prop is None or df_prop.empty:
        st.info(
            "Dados de proposições internas ainda não disponíveis. "
            "Use o botão **'🔄 Coletar Dados Agora'** na barra lateral para iniciar a coleta."
        )
        return

    # ── Aplica filtros ────────────────────────────────────────────────────────
    df = df_prop.copy()

    if "ano" in df.columns and anos_sel:
        df = df[df["ano"].isin(anos_sel)]

    if vereadores_sel and "nome_norm" in df.columns:
        nomes_norm_sel = {_norm(v) for v in vereadores_sel}
        df = df[df["nome_norm"].isin(nomes_norm_sel)]

    if df.empty:
        st.warning("Nenhuma proposição encontrada para os filtros selecionados.")
        return

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total   = len(df)
    autores = df["autor"].nunique() if "autor" in df.columns else "—"

    # Tipo de proposição inferido do número (ex: "PIN-210/2026" → "PIN")
    if "numero" in df.columns:
        df["_tipo"] = df["numero"].str.extract(r"^([A-Z]+)", expand=False).fillna("Outros")
        tipos_unicos = df["_tipo"].nunique()
    else:
        df["_tipo"] = "Outros"
        tipos_unicos = "—"

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Proposições", total)
    c2.metric("Tipos Distintos",      tipos_unicos)
    c3.metric("Autores",              autores)
    st.divider()

    # ── Gráficos lado a lado ──────────────────────────────────────────────────
    col_esq, col_dir = st.columns(2)

    with col_esq:
        df_tipo = (
            df.groupby("_tipo", as_index=False)
            .size()
            .rename(columns={"size": "quantidade"})
            .sort_values("quantidade", ascending=True)
        )
        fig_tipo = px.bar(
            df_tipo,
            x="quantidade",
            y="_tipo",
            orientation="h",
            title="Proposições por Tipo",
            labels={"quantidade": "Quantidade", "_tipo": "Tipo"},
            color="quantidade",
            color_continuous_scale=[_NEON, "#00C853"],
            text="quantidade",
        )
        fig_tipo.update_coloraxes(showscale=False)
        fig_tipo.update_traces(textposition="outside")
        _aplicar_dark(
            fig_tipo,
            height=max(320, len(df_tipo) * 30),
            margin=dict(l=100, r=60, t=40, b=20),
        )
        st.plotly_chart(fig_tipo, width="stretch")

    with col_dir:
        if "autor" in df.columns:
            df_autor = (
                df.groupby("autor", as_index=False)
                .size()
                .rename(columns={"size": "quantidade"})
                .sort_values("quantidade", ascending=False)
                .head(15)
                .sort_values("quantidade", ascending=True)
            )
            fig_autor = px.bar(
                df_autor,
                x="quantidade",
                y="autor",
                orientation="h",
                title="Top 15 Autores por Proposições",
                labels={"quantidade": "Proposições", "autor": ""},
                color="quantidade",
                color_continuous_scale=_SCALE_RB,
                text="quantidade",
            )
            fig_autor.update_coloraxes(showscale=False)
            fig_autor.update_traces(textposition="outside")
            _aplicar_dark(
                fig_autor,
                height=max(320, min(15, len(df_autor)) * 30),
                margin=dict(l=180, r=60, t=40, b=20),
            )
            st.plotly_chart(fig_autor, width="stretch")

    # ── Tabela detalhada ──────────────────────────────────────────────────────
    st.subheader("Tabela Detalhada")

    if "ementa" in df.columns:
        busca = st.text_input(
            "🔍 Buscar na ementa",
            placeholder="Ex: transporte, saúde, educação…",
        )
        if busca:
            df = df[df["ementa"].str.contains(busca, case=False, na=False)]

    colunas_display = {
        "numero":      "Proposição",
        "autor":       "Autor",
        "data":        "Movimentado",
        "localizacao": "Localização",
        "situacao":    "Situação",
        "ementa":      "Ementa",
        "ano":         "Ano",
    }
    cols_disp = [c for c in colunas_display if c in df.columns]
    df_disp = df[cols_disp].rename(columns=colunas_display)

    st.dataframe(df_disp, width="stretch", hide_index=True)

    csv = df_disp.to_csv(index=False, encoding="utf-8-sig")
    anos_str = "_".join(str(a) for a in sorted(anos_sel)) if anos_sel else "todos"
    st.download_button(
        label="⬇️ Baixar CSV de Proposições",
        data=csv,
        file_name=f"prop_interna_cms_{anos_str}.csv",
        mime="text/csv",
    )
