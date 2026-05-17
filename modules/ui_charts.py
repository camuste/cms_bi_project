# =============================================================================
# modules/ui_charts.py — CMS BI Project
# Repositório central de todos os gráficos Plotly do dashboard.
#
# DESIGN:
#   - Cada função recebe um DataFrame já filtrado e retorna um go.Figure.
#   - O app.py chama st.plotly_chart(fig) — as funções aqui NÃO chamam st.*
#     diretamente (exceto quando necessário para sub-componentes).
#   - Todas as figuras compartilham o tema dark via _aplicar_dark().
#
# CONSTANTES VISUAIS:
#   _BG, _PLOT_BG, _NEON, _GRID, _SCALE_RB são definidas aqui e usadas
#   em todos os gráficos para garantir consistência visual.
# =============================================================================

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# =============================================================================
# CONSTANTES DE TEMA DARK
# =============================================================================

# Cor de fundo do papel (área fora do plot)
_BG = "#121212"

# Cor de fundo da área do gráfico
_PLOT_BG = "#1A1A1A"

# Azul primário da paleta CMS Salvador
_NEON = "#004A99"

# Cor das linhas de grade (levemente visível no fundo escuro)
_GRID = "rgba(255,255,255,0.06)"

# Escala de cores vermelho → amarelo → verde neon (para presença e ranking)
_SCALE_RB = ["#c62828", "#f9a825", "#00C853"]

# Layout base aplicado a todos os gráficos
_LAYOUT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor=_BG,
    plot_bgcolor=_PLOT_BG,
    font=dict(family="Inter, sans-serif", color="#E0E0E0"),
    margin=dict(t=48, b=24),
)

# Cores de linha para o gráfico de radar (8 vereadores = 8 cores)
_CORES_RADAR = [
    "#004A99", "#00C853", "#FF6D00", "#D500F9",
    "#F9A825", "#00BCD4", "#E53935", "#8BC34A",
]

# Cores fill do radar com transparência (correspondentes às linhas, formato RGBA)
_FILL_RADAR = [
    "rgba(0,74,153,0.18)",   "rgba(0,200,83,0.18)",
    "rgba(255,109,0,0.18)",  "rgba(213,0,249,0.18)",
    "rgba(249,168,37,0.18)", "rgba(0,188,212,0.18)",
    "rgba(229,57,53,0.18)",  "rgba(139,195,74,0.18)",
]


# =============================================================================
# HELPER INTERNO
# =============================================================================

def _aplicar_dark(fig: go.Figure, **extra) -> go.Figure:
    """
    Aplica o tema dark padrão a qualquer figura Plotly.

    Estratégia de merge: {**_LAYOUT_BASE, **extra} garante que os valores
    passados em `extra` sobrescrevam as chaves do layout base (ex.: margin,
    height), sem gerar o erro 'multiple values for keyword argument'.

    Parâmetros:
      fig   — figura Plotly a ser atualizada.
      extra — kwargs adicionais que sobrescrevem o layout base.
    """
    fig.update_layout(**{**_LAYOUT_BASE, **extra})
    fig.update_xaxes(gridcolor=_GRID, zerolinecolor=_GRID)
    fig.update_yaxes(gridcolor=_GRID, zerolinecolor=_GRID)
    return fig


# =============================================================================
# ABA 1 — FREQUÊNCIA
# =============================================================================

def grafico_bar_frequencia(df_pres: pd.DataFrame, anos_sel: list) -> go.Figure:
    """
    Gráfico de barras horizontais: taxa de presença por vereador.

    Entrada: df_pres — DataFrame de presença filtrado (uma linha por vereador×ano).
    Retorna: Figure com barras coloridas em escala vermelho→verde.
    """
    # Agrega múltiplos anos tirando a média da taxa de presença
    df_bar = (
        df_pres
        .groupby("parlamentar", as_index=False)["taxa_presenca"]
        .mean()
        .sort_values("taxa_presenca", ascending=True)
    )

    anos_str = ", ".join(str(a) for a in sorted(anos_sel))

    fig = px.bar(
        df_bar,
        x="taxa_presenca",
        y="parlamentar",
        orientation="h",
        color="taxa_presenca",
        color_continuous_scale=_SCALE_RB,
        range_color=[0, 100],
        title=f"Taxa de Presença por Vereador — {anos_str}",
        labels={"taxa_presenca": "% Presença", "parlamentar": ""},
        text=df_bar["taxa_presenca"].round(1).astype(str) + "%",
    )
    fig.update_traces(textposition="outside", textfont_size=11)
    fig.update_coloraxes(showscale=False)
    return _aplicar_dark(
        fig,
        height=max(520, len(df_bar) * 26),
        margin=dict(l=180, r=80, t=48, b=24),
    )


def grafico_heatmap_presenca(df_freq: pd.DataFrame) -> go.Figure | None:
    """
    Heatmap de presença: eixo Y = vereadores, eixo X = meses, cor = % presença.

    Entrada: df_freq — DataFrame de frequência bruta filtrado.
    Retorna: Figure do heatmap, ou None se não houver dados suficientes.
    """
    if df_freq.empty or "mes_ano" not in df_freq.columns:
        return None

    # Pivoteia: média de presença (0–1) por parlamentar × mês, converte para %
    pivot = (
        df_freq.groupby(["parlamentar", "mes_ano"])["presente"]
        .mean()
        .reset_index()
        .pivot(index="parlamentar", columns="mes_ano", values="presente")
        .mul(100)
        .round(1)
        .sort_index()
    )

    # Ordena colunas cronologicamente (formato YYYY-MM já ordena lexicograficamente)
    pivot = pivot[sorted(pivot.columns)]

    fig = px.imshow(
        pivot,
        color_continuous_scale=_SCALE_RB,
        range_color=[0, 100],
        title="Heatmap de Presença por Mês / Vereador (%)",
        labels={"color": "% Presença", "x": "Mês/Ano", "y": "Vereador"},
        aspect="auto",
        text_auto=".0f",
    )
    fig.update_traces(
        textfont=dict(size=10, color="white"),
        hoverongaps=False,
    )
    fig.update_coloraxes(
        colorbar=dict(
            title="% Pres.",
            ticksuffix="%",
            thickness=12,
            len=0.8,
        )
    )
    return _aplicar_dark(
        fig,
        height=max(420, len(pivot) * 22),
        margin=dict(l=180, r=80, t=48, b=60),
        xaxis=dict(tickangle=-35),
    )


# =============================================================================
# ABA 2 — PRODUTIVIDADE
# =============================================================================

def grafico_bar_produtividade(df_prod: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras horizontais: total de proposições por vereador.

    Entrada: df_prod — DataFrame de produtividade filtrado.
    Retorna: Figure com barras em escala azul→verde.
    """
    df_bar = (
        df_prod.groupby("parlamentar", as_index=False)["total_proposicoes"]
        .sum()
        .sort_values("total_proposicoes", ascending=True)
    )
    fig = px.bar(
        df_bar,
        x="total_proposicoes",
        y="parlamentar",
        orientation="h",
        color="total_proposicoes",
        color_continuous_scale=["#1565C0", _NEON, "#00C853"],
        title="Total de Proposições por Vereador",
        labels={"total_proposicoes": "Proposições", "parlamentar": ""},
        text="total_proposicoes",
    )
    fig.update_traces(textposition="outside")
    fig.update_coloraxes(showscale=False)
    return _aplicar_dark(
        fig,
        height=max(520, len(df_bar) * 26),
        margin=dict(l=180, r=80, t=48, b=24),
    )


def grafico_linha_evolucao(df_prod: pd.DataFrame) -> go.Figure:
    """
    Gráfico de linhas: evolução anual de proposições por vereador.
    Só é renderizado quando há mais de 1 ano selecionado.

    Entrada: df_prod — DataFrame de produtividade filtrado.
    Retorna: Figure de linhas com marcadores.
    """
    df_evol = (
        df_prod.groupby(["ano", "parlamentar"], as_index=False)["total_proposicoes"]
        .sum()
    )
    fig = px.line(
        df_evol,
        x="ano",
        y="total_proposicoes",
        color="parlamentar",
        title="Evolução de Proposições por Ano",
        labels={"total_proposicoes": "Proposições", "ano": "Ano"},
        markers=True,
    )
    return _aplicar_dark(fig, height=450)


def grafico_radar_performance(df_rank: pd.DataFrame) -> go.Figure:
    """
    Gráfico de radar (Scatterpolar): compara os top 8 vereadores em 3 dimensões.
      - Assiduidade (%)        → taxa_presenca
      - Proposições (0–100)    → total_proposicoes normalizado
      - Índice Composto (0–100) → indice_composto × 100

    Estruturado para receber automaticamente os dados de produtividade
    assim que o scraper de proposições for executado.

    Entrada: df_rank — DataFrame de ranking filtrado.
    Retorna: Figure do radar.
    """
    # Agrega e seleciona top 8 por índice composto
    df_radar = (
        df_rank.groupby("parlamentar", as_index=False).agg(
            assiduidade=("taxa_presenca", "mean"),
            proposicoes=("total_proposicoes", "sum"),
            indice=("indice_composto", "mean"),
        )
        .sort_values("indice", ascending=False)
        .head(8)
        .reset_index(drop=True)
    )

    # Normaliza proposições e índice para escala 0–100
    prop_max = df_radar["proposicoes"].max() or 1
    df_radar["prop_norm"] = (df_radar["proposicoes"] / prop_max * 100).round(1)
    df_radar["idx_norm"]  = (df_radar["indice"] * 100).round(1)

    categorias        = ["Assiduidade (%)", "Proposições", "Índice Composto"]
    categorias_fechadas = categorias + [categorias[0]]   # fecha o polígono

    fig = go.Figure()

    for i, linha in df_radar.iterrows():
        valores = [
            linha["assiduidade"],
            linha["prop_norm"],
            linha["idx_norm"],
            linha["assiduidade"],   # fecha o polígono repetindo o 1º valor
        ]
        cor_linha = _CORES_RADAR[i % len(_CORES_RADAR)]
        cor_fill  = _FILL_RADAR[i % len(_FILL_RADAR)]

        fig.add_trace(go.Scatterpolar(
            r=valores,
            theta=categorias_fechadas,
            fill="toself",
            fillcolor=cor_fill,
            line=dict(color=cor_linha, width=2),
            name=linha["parlamentar"],
            hovertemplate=(
                f"<b>{linha['parlamentar']}</b><br>"
                "Assiduidade: %{r:.1f}%<extra></extra>"
            ),
        ))

    fig.update_layout(
        **{**_LAYOUT_BASE,
           "polar": dict(
               bgcolor=_PLOT_BG,
               radialaxis=dict(
                   visible=True,
                   range=[0, 100],
                   tickfont=dict(size=9, color="#9E9E9E"),
                   gridcolor=_GRID,
                   linecolor=_GRID,
               ),
               angularaxis=dict(
                   gridcolor=_GRID,
                   linecolor=_GRID,
                   tickfont=dict(size=12, color="#E0E0E0"),
               ),
           ),
           "legend": dict(orientation="v", x=1.05, y=0.5, font=dict(size=11)),
           "title": dict(text="Top 8 Vereadores — Radar de Performance", x=0.5),
           "height": 520,
        }
    )
    return fig


# =============================================================================
# ABA 3 — RANKING GERAL
# =============================================================================

def grafico_bar_ranking(df_rank_show: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras horizontais: índice composto de atuação por vereador.

    Entrada: df_rank_show — DataFrame de ranking já agregado e ordenado.
    Retorna: Figure com barras em escala vermelho→verde.
    """
    df_ord = df_rank_show.sort_values("indice_composto")
    fig = px.bar(
        df_ord,
        x="indice_composto",
        y="parlamentar",
        orientation="h",
        color="indice_composto",
        color_continuous_scale=_SCALE_RB,
        range_color=[0, 1],
        title="Índice Composto de Atuação Parlamentar",
        labels={"indice_composto": "Índice (0–1)", "parlamentar": ""},
        text=df_ord["indice_composto"].round(3).astype(str),
    )
    fig.update_traces(textposition="outside", textfont_size=11)
    fig.update_coloraxes(showscale=False)
    return _aplicar_dark(
        fig,
        height=max(520, len(df_ord) * 26),
        margin=dict(l=180, r=100, t=48, b=24),
    )


def grafico_scatter_presenca_prod(df_rank_show: pd.DataFrame) -> go.Figure:
    """
    Scatter bidirecional: Presença (%) × Proposições.
    O tamanho da bolha representa o Índice Composto.

    Entrada: df_rank_show — DataFrame de ranking já agregado.
    Retorna: Figure de scatter com bolhas dimensionadas.
    """
    col_y = "total_proposicoes" if "total_proposicoes" in df_rank_show.columns else "indice_composto"
    label_y = "Proposições" if col_y == "total_proposicoes" else "Índice Composto"

    fig = px.scatter(
        df_rank_show,
        x="taxa_presenca",
        y=col_y,
        text="parlamentar",
        color="indice_composto",
        color_continuous_scale=["#1565C0", _NEON, "#00C853"],
        size="indice_composto",
        size_max=30,
        title="Presença × Produtividade (bolha = Índice Composto)",
        labels={
            "taxa_presenca":     "% Presença",
            col_y:               label_y,
            "indice_composto":   "Índice",
        },
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=9),
        marker=dict(opacity=0.85, line=dict(width=1, color="#FFFFFF")),
    )
    fig.update_coloraxes(
        colorbar=dict(title="Índice", thickness=12, len=0.7)
    )
    return _aplicar_dark(fig, height=520)
