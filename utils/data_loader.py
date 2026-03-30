"""
Carregamento otimizado de dados com cache
"""
import streamlit as st
import pandas as pd
from utils.bigquery_client import get_bigquery_client
from config import PROJECT_ID, DATASET_ID, TABELA_FATO, TABELA_PIRAMIDES

@st.cache_data(ttl=3600)  # Cache de 1 hora
def carregar_pacientes_filtrados(
    ap=None, 
    clinica=None, 
    esf=None, 
    filtros_morbidades=None,
    busca_texto=None,
    ordenar_por=None,
    limite=None
):
    """
    Carrega pacientes da tabela fato com filtros aplicados no BigQuery
    
    Args:
        ap: Área Programática
        clinica: Nome da Clínica
        esf: Nome da Equipe ESF
        filtros_morbidades: Dict com morbidades para filtrar
        busca_texto: Texto para buscar em nome ou CPF
        ordenar_por: Tuple (campo, direcao) ex: ('idade', 'DESC')
        limite: Número máximo de registros
    
    Returns:
        DataFrame com pacientes filtrados
    """
    client = get_bigquery_client()
    
    if not client:
        return pd.DataFrame()
    
    # Construir WHERE dinâmico
    condicoes = []
    
    if ap:
        condicoes.append(f"area_programatica_cadastro = '{ap}'")
    
    if clinica:
        condicoes.append(f"nome_clinica_cadastro = '{clinica}'")
    
    if esf:
        condicoes.append(f"nome_esf_cadastro = '{esf}'")
    
    # Busca por nome ou CPF
    if busca_texto:
        busca_texto = busca_texto.strip()
        condicoes.append(f"(LOWER(nome) LIKE LOWER('%{busca_texto}%') OR cpf LIKE '%{busca_texto}%')")
    
    # Adicionar filtros de morbidades se houver
    if filtros_morbidades:
        for campo, valor in filtros_morbidades.items():
            if valor:
                condicoes.append(f"{campo} IS NOT NULL")
    
    where_clause = " AND ".join(condicoes) if condicoes else "1=1"
    
    # Ordenação
    order_clause = ""
    if ordenar_por:
        campo, direcao = ordenar_por
        order_clause = f"ORDER BY {campo} {direcao}"
    
    # Query com campos corretos da sua tabela
    query = f"""
    SELECT 
        cpf,
        nome,
        idade,
        genero,
        area_programatica_cadastro,
        nome_clinica_cadastro,
        nome_esf_cadastro,
        nome_medico_esf_cadastro,
        nome_enfermeiro_esf_cadastro,
        
        -- Morbidades principais (campos DATE na sua tabela)
        DM,
        HAS,
        dislipidemia,
        obesidade,
        IRC as doenca_renal_cronica,
        CI,
        ICC,
        stroke,
        
        -- Exames recentes
        hba1c_atual,
        data_hba1c_atual,
        pressao_sistolica,
        pressao_diastolica,
        data_ultima_pa,
        dias_desde_ultima_pa,
        
        -- Lipídios
        colesterol_total,
        ldl,
        hdl,
        triglicerides,
        data_colesterol,
        
        -- Função renal
        creatinina,
        egfr,
        ckd_stage,
        
        -- Risco CV
        risco_cardiovascular as categoria_risco_final,
        percentual_risco_final,
        motivo_reclassificacao,
        
        -- Medicamentos
        total_medicamentos_cronicos,
        polifarmacia,
        hiperpolifarmacia,
        
        -- Contadores
        total_morbidades,
        charlson_score,
        charlson_categoria,
        
        -- Controle
        status_controle_glicemico,
        status_controle_pressorio,
        tendencia_hba1c,
        tendencia_pa,
        
        -- Lacunas principais
        lacuna_DM_sem_HbA1c_recente,
        lacuna_DM_descontrolado,
        lacuna_HAS_descontrolado_menor80,
        lacuna_HAS_descontrolado_80mais,
        lacuna_rastreio_PA_adulto,
        
        -- Consultas
        consultas_365d,
        consultas_medicas_365d,
        consultas_enfermagem_365d,
        dias_desde_ultima_consulta,
        data_ultima_consulta,
        regularidade_acompanhamento
        
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABELA_FATO}`
    WHERE {where_clause}
    {order_clause}
    {f'LIMIT {limite}' if limite else ''}
    """
    
    try:
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {str(e)}")
        st.code(query)  # Mostrar query para debug
        return pd.DataFrame()


@st.cache_data(ttl=7200)  # Cache de 2 horas
def carregar_piramides(ap=None, clinica=None, esf=None):
    """
    Carrega dados das pirâmides populacionais
    """
    client = get_bigquery_client()
    
    if not client:
        return pd.DataFrame()
    
    # Construir WHERE
    condicoes = []
    
    if ap:
        condicoes.append(f"area_programatica_cadastro = '{ap}'")
    
    if clinica:
        condicoes.append(f"nome_clinica_cadastro = '{clinica}'")
    
    if esf:
        condicoes.append(f"nome_esf_cadastro = '{esf}'")
    
    where_clause = " AND ".join(condicoes) if condicoes else "1=1"
    
    query = f"""
    SELECT *
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABELA_PIRAMIDES}`
    WHERE {where_clause}
    """
    
    try:
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar pirâmides: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=86400)  # Cache de 24 horas
def carregar_opcoes_filtros():
    """
    Carrega opções únicas para os filtros (AP, Clínicas, ESF)
    """
    client = get_bigquery_client()
    
    if not client:
        return {
            'areas': [],
            'clinicas': {},
            'esf': {}
        }
    
    query = f"""
    SELECT DISTINCT
        area_programatica_cadastro,
        nome_clinica_cadastro,
        nome_esf_cadastro
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABELA_FATO}`
    WHERE area_programatica_cadastro IS NOT NULL
        AND nome_clinica_cadastro IS NOT NULL
        AND nome_esf_cadastro IS NOT NULL
    ORDER BY area_programatica_cadastro, nome_clinica_cadastro, nome_esf_cadastro
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        # Organizar hierarquicamente
        areas = sorted(df['area_programatica_cadastro'].unique().tolist())
        
        # Clínicas por AP
        clinicas_por_ap = {}
        for ap in areas:
            clinicas_por_ap[ap] = sorted(
                df[df['area_programatica_cadastro'] == ap]['nome_clinica_cadastro'].unique().tolist()
            )
        
        # ESF por Clínica
        esf_por_clinica = {}
        for clinica in df['nome_clinica_cadastro'].unique():
            esf_por_clinica[clinica] = sorted(
                df[df['nome_clinica_cadastro'] == clinica]['nome_esf_cadastro'].unique().tolist()
            )
        
        return {
            'areas': areas,
            'clinicas': clinicas_por_ap,
            'esf': esf_por_clinica
        }
    except Exception as e:
        st.error(f"❌ Erro ao carregar opções de filtros: {str(e)}")
        return {
            'areas': [],
            'clinicas': {},
            'esf': {}
        }


def limpar_cache():
    """
    Limpa todo o cache de dados
    """
    st.cache_data.clear()
    st.success("✅ Cache limpo com sucesso!")

@st.cache_data(ttl=900, show_spinner=False)
def carregar_metricas_resumo(ap=None, clinica=None, esf=None) -> dict:
    """
    Carrega métricas populacionais agregadas para a Home.
    Fonte: MM_piramides_populacionais (tabela já agregada — resposta rápida).

    Retorna dict com chaves:
        total_pop, multimorbidos, polifarmacia, hiperpolifarmacia
    """
    client = get_bigquery_client()

    if not client:
        return {'total_pop': 0, 'multimorbidos': 0, 'polifarmacia': 0, 'hiperpolifarmacia': 0}

    where_clauses = []
    if ap:
        where_clauses.append(f"area_programatica = '{ap}'")
    if clinica:
        where_clauses.append(f"clinica_familia = '{clinica}'")
    if esf:
        where_clauses.append(f"ESF = '{esf}'")

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
    SELECT
        SUM(total_pacientes)                                          AS total_pop,
        SUM(n_morb_2 + n_morb_3 + n_morb_4 + n_morb_5
            + n_morb_6 + n_morb_7 + n_morb_8 + n_morb_9
            + n_morb_10mais)                                          AS multimorbidos,
        SUM(n_polifarmacia)                                           AS polifarmacia,
        SUM(n_hiperpolifarmacia)                                      AS hiperpolifarmacia
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABELA_PIRAMIDES}`
    {where_sql}
    """

    try:
        df = client.query(query).result().to_dataframe(create_bqstorage_client=False)
        if not df.empty:
            row = df.iloc[0].to_dict()
            # Garantir que None vira 0
            return {k: int(v) if v is not None else 0 for k, v in row.items()}
    except Exception as e:
        st.warning(f"⚠️ Não foi possível carregar métricas resumo: {e}")

    return {'total_pop': 0, 'multimorbidos': 0, 'polifarmacia': 0, 'hiperpolifarmacia': 0}