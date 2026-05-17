# =============================================================================
# modules/data_loader.py — CMS BI Project
# Responsável por toda leitura de arquivos .parquet do disco.
#
# DESIGN:
#   Cada função é decorada com @st.cache_data(ttl=3600) para que o Streamlit
#   armazene o DataFrame em memória por até 1 hora. Isso garante que filtros
#   interativos na sidebar NÃO relêem o disco a cada clique — apenas na
#   primeira execução ou após o TTL expirar.
#
# CONVENÇÃO:
#   - Retorna None quando o arquivo ainda não existe (antes da primeira coleta).
#   - O chamador (app.py) trata o None exibindo mensagem de orientação.
# =============================================================================

import os
import pandas as pd
import streamlit as st

# Importa as constantes de caminho do config raiz do projeto.
# Funciona porque o Streamlit é sempre iniciado a partir da raiz do projeto,
# que já está no sys.path.
import config


# -----------------------------------------------------------------------------
# Função auxiliar interna
# -----------------------------------------------------------------------------

def _ler_parquet(nome: str) -> pd.DataFrame | None:
    """
    Tenta carregar o arquivo data/{nome}.parquet.
    Retorna o DataFrame ou None se o arquivo não existir.
    """
    caminho = os.path.join(config.CACHE_DIR, f"{nome}.parquet")
    if os.path.exists(caminho):
        return pd.read_parquet(caminho)
    return None


# -----------------------------------------------------------------------------
# Loaders cacheados — um por dataset
# Usar funções separadas permite invalidar o cache de cada dataset
# individualmente via st.cache_data.clear() se necessário.
# -----------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_frequencia() -> pd.DataFrame | None:
    """
    Carrega o parquet de frequência bruta das sessões plenárias.
    Colunas esperadas: nome_norm, parlamentar, num_sessao, ano, mes_ano, status, presente.
    """
    return _ler_parquet("frequencia")


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_presenca() -> pd.DataFrame | None:
    """
    Carrega o parquet de taxas de presença agregadas por vereador × ano.
    Colunas esperadas: nome_norm, parlamentar, ano, total_sessoes, presencas,
                       ausencias, taxa_presenca.
    """
    return _ler_parquet("presenca")


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_ranking() -> pd.DataFrame | None:
    """
    Carrega o parquet do ranking composto (50% presença + 50% produtividade).
    Colunas esperadas: nome_norm, parlamentar, ano, taxa_presenca,
                       total_proposicoes, indice_composto, ranking.
    """
    return _ler_parquet("ranking")


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_produtividade() -> pd.DataFrame | None:
    """
    Carrega o parquet de produtividade parlamentar (total de proposições por tipo).
    Gerado pelo ProdutividadeScraper.
    """
    return _ler_parquet("produtividade")


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_proposicoes() -> pd.DataFrame | None:
    """
    Carrega o parquet de proposições detalhadas por vereador.
    Gerado pelo ProposicaoScraper.
    """
    return _ler_parquet("proposicoes")


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_proposicao_interna() -> pd.DataFrame | None:
    """
    Carrega o parquet de proposições internas do sistema cmsalvador.sys.inf.br.
    Gerado pelo ProposicaoInternaScraper (HTTP GET puro, legislatura 2025+).
    Colunas esperadas: numero, tipo, ementa, autor, data, situacao, ano, nome_norm.
    """
    return _ler_parquet("prop_interna")


def limpar_cache() -> None:
    """
    Invalida o cache de todos os datasets.
    Chamado pelo botão 'Coletar Dados Agora' após nova coleta,
    para que os gráficos reflitam os dados frescos imediatamente.
    """
    carregar_frequencia.clear()
    carregar_presenca.clear()
    carregar_ranking.clear()
    carregar_produtividade.clear()
    carregar_proposicoes.clear()
    carregar_proposicao_interna.clear()
