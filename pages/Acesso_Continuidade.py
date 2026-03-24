"""
Página: Acesso e Continuidade do Cuidado
Análise de padrões de acesso por carga de morbidade, índices de longitudinalidade
e violin plots comparativos por subdivisão territorial.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from components.filtros import filtros_territoriais
from utils.bigquery_client import get_bigquery_client
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
    anonimizar_nome, mostrar_badge_anonimo, MODO_ANONIMO
)
import config

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']
if isinstance(usuario_logado, dict):
    nome = usuario_logado.get('nome_completo', 'Usuário')
    esf  = usuario_logado.get('esf') or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap   = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO CONSISTENTE
# ═══════════════════════════════════════════════════════════════
from streamlit_option_menu import option_menu

st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    <h1 style='margin: 0; padding: 0; color: #FAFAFA;'>
        🏥 Navegador Clínico <small style='color: #999; font-size: 0.5em;'>SMS-RJ</small>
    </h1>
    """, unsafe_allow_html=True)
with col2:
    info_lines = [f"<strong>{nome}</strong>"]
    if esf     != 'N/A': info_lines.append(f"ESF: {esf}")
    if clinica != 'N/A': info_lines.append(f"Clínica: {clinica}")
    if ap      != 'N/A': info_lines.append(f"AP: {ap}")
    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: #FAFAFA; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Acesso e Continuidade"
ROTAS = {
    "Home":                  "Home.py",
    "Minha População":       "pages/Minha_Populacao.py",
    "Meus Pacientes":        "pages/Meus_Pacientes.py",
    "Lacunas de Cuidado":    "pages/Lacunas_de_Cuidado.py",
    "Acesso e Continuidade": "pages/Acesso_Continuidade.py",
    "Polifarmácia":          "pages/Polifarmacia_ACB.py",
}
ICONES = ['house-fill', 'people-fill', 'person-lines-fill',
          'exclamation-triangle-fill', 'arrow-repeat', 'capsule']

selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#0E1117"},
        "icon": {"color": "#FAFAFA", "font-size": "18px"},
        "nav-link": {
            "font-size": "16px", "text-align": "center", "margin": "0px",
            "padding": "10px 20px", "color": "#FAFAFA",
            "background-color": "#262730", "--hover-color": "#404040"
        },
        "nav-link-selected": {"background-color": "#404040", "color": "#FAFAFA", "font-weight": "bold"},
    }
)

if selected != PAGINA_ATUAL:
    st.switch_page(ROTAS[selected])

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Acesso e Continuidade - Navegador Clínico",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"

@st.cache_data(show_spinner=False, ttl=900)
def run_query(query: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(query).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro ao executar query: {str(e)}")
        return pd.DataFrame()

# ═══════════════════════════════════════════════════════════════
# DEFINIÇÃO DOS INDICADORES (usados nos violin plots)
# ═══════════════════════════════════════════════════════════════
INDICADORES_VIOLIN = {
    'pct_sem_medico_180d': {
        'label': '% sem médico há >180 dias',
        'descricao': (
            'Proporção de pacientes da unidade que não tiveram nenhuma consulta '
            'médica nos últimos 180 dias. Valores altos indicam abandono do '
            'acompanhamento — especialmente crítico em pacientes com doenças crônicas.'
        ),
    },
    'pct_baixa_longitudinalidade': {
        'label': '% baixa longitudinalidade',
        'descricao': (
            'Proporção de pacientes cujas consultas médicas ocorrem predominantemente '
            'fora da unidade de cadastro (>50% fora). Reflete fragmentação do cuidado '
            'e menor vínculo com a equipe de referência.'
        ),
    },
    'pct_alto_risco_baixo_acesso': {
        'label': '% alto risco + baixo acesso',
        'descricao': (
            'Pacientes com Charlson ≥ 7 (muito alta carga de morbidade) que consultam '
            'abaixo do P25 do seu grupo de pares. É o principal indicador de iniquidade '
            'em saúde: quem mais precisa, menos acessa.'
        ),
    },
    'pct_regular': {
        'label': '% acompanhamento regular',
        'descricao': (
            'Proporção de pacientes com pelo menos 6 meses distintos com consulta '
            'nos últimos 12 meses. Mede regularidade do cuidado ao longo do ano — '
            'valores baixos indicam acompanhamento esporádico ou ausente.'
        ),
    },
    'intervalo_mediano_medio': {
        'label': 'Intervalo mediano entre consultas (dias)',
        'descricao': (
            'Mediana dos intervalos entre consultas consecutivas nos últimos 365 dias. '
            'Representa o ritmo habitual de acesso do paciente. O ideal é que pacientes '
            'com maior carga de morbidade tenham intervalos menores.'
        ),
    },
    'pct_sem_consulta_365d': {
        'label': '% sem consulta no ano',
        'descricao': (
            'Proporção de pacientes que não registraram nenhuma consulta '
            'nos últimos 365 dias. Pacientes ativos no cadastro mas sem acesso '
            'ao sistema no período.'
        ),
    },
    'pct_frequente_urgencia': {
        'label': '% uso frequente de urgência',
        'descricao': (
            'Proporção de pacientes com 3 ou mais atendimentos em UPA, CER ou '
            'hospital de urgência nos últimos 365 dias. Uso frequente de urgência '
            'pode indicar falha no acesso à atenção primária.'
        ),
    },
}

# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════
def _where(ap=None, clinica=None, esf=None, extra_clauses=None) -> str:
    """
    Monta cláusula WHERE completa.
    extra_clauses: lista de strings SQL adicionais (sem WHERE/AND).
    Nunca gera WHERE duplo.
    """
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if extra_clauses:
        clauses.extend(extra_clauses)
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""

# ── Query de panorama agregado por categoria Charlson ─────────
@st.cache_data(show_spinner=False, ttl=900)
def carregar_panorama(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Agrega por charlson_categoria × genero para permitir estratificação."""
    where = _where(ap, clinica, esf, extra_clauses=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        CASE
            WHEN LOWER(genero) IN ('feminino', 'f', 'fem') THEN 'Feminino'
            WHEN LOWER(genero) IN ('masculino', 'm', 'mas') THEN 'Masculino'
            ELSE 'Não informado'
        END AS sexo,
        COUNT(*)                                                   AS total_pacientes,
        ROUND(AVG(intervalo_mediano_dias), 1)                      AS intervalo_mediano_medio,
        ROUND(AVG(consultas_365d), 1)                              AS consultas_365d_media,
        ROUND(AVG(dias_desde_ultima_medica), 1)                    AS dias_sem_medico_medio,
        COUNTIF(dias_desde_ultima_medica > 180)                    AS sem_medico_180d,
        COUNTIF(consultas_365d = 0)                                AS sem_consulta_365d,
        COUNTIF(regularidade_acompanhamento = 'regular')           AS regulares,
        COUNTIF(regularidade_acompanhamento = 'irregular')         AS irregulares,
        COUNTIF(regularidade_acompanhamento = 'esporadico')        AS esporadicos,
        COUNTIF(regularidade_acompanhamento = 'sem_acompanhamento') AS sem_acompanhamento,
        COUNTIF(baixa_longitudinalidade = TRUE)                    AS baixa_longitudinalidade,
        ROUND(AVG(pct_consultas_medicas_na_unidade_365d), 1)       AS pct_na_unidade_medio,
        COUNTIF(usuario_frequente_urgencia = TRUE)                 AS frequente_urgencia,
        COUNTIF(alto_risco_baixo_acesso = TRUE)                    AS alto_risco_baixo_acesso,
        COUNTIF(alto_risco_intervalo_longo = TRUE)                 AS alto_risco_intervalo_longo
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY charlson_categoria, sexo
    ORDER BY
        CASE charlson_categoria
            WHEN 'Muito Alto' THEN 1
            WHEN 'Alto'       THEN 2
            WHEN 'Moderado'   THEN 3
            WHEN 'Baixo'      THEN 4
        END, sexo
    """
    df = run_query(sql)
    if not df.empty:
        t = df['total_pacientes'].replace(0, 1)
        df['pct_sem_medico_180d']         = (df['sem_medico_180d']        / t * 100).round(1)
        df['pct_regular']                 = (df['regulares']              / t * 100).round(1)
        df['pct_baixa_long']              = (df['baixa_longitudinalidade'] / t * 100).round(1)
        df['pct_alto_risco_baixo_acesso'] = (df['alto_risco_baixo_acesso']/ t * 100).round(1)
    return df


@st.cache_data(show_spinner=False, ttl=900)
def carregar_tempo_proxima_consulta(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    where = _where(ap, clinica, esf, extra_clauses=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        CASE
            WHEN LOWER(genero) IN ('feminino', 'f', 'fem') THEN 'Feminino'
            WHEN LOWER(genero) IN ('masculino', 'm', 'mas') THEN 'Masculino'
            ELSE 'Não informado'
        END AS sexo,
        COUNT(*)                                               AS total_pacientes,
        ROUND(AVG(dias_desde_ultima_medica), 0)                AS dias_medico,
        ROUND(AVG(dias_desde_ultima_enfermagem), 0)            AS dias_enfermagem,
        ROUND(AVG(dias_desde_ultima_acs), 0)                   AS dias_acs,
        ROUND(AVG(dias_desde_ultima_tecnico_enfermagem), 0)    AS dias_tecnico,
        -- percentis para mostrar dispersão
        ROUND(APPROX_QUANTILES(dias_desde_ultima_medica, 4)[OFFSET(1)], 0)     AS p25_medico,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_medica, 4)[OFFSET(2)], 0)     AS p50_medico,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_medica, 4)[OFFSET(3)], 0)     AS p75_medico,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_enfermagem, 4)[OFFSET(1)], 0) AS p25_enfermagem,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_enfermagem, 4)[OFFSET(2)], 0) AS p50_enfermagem,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_enfermagem, 4)[OFFSET(3)], 0) AS p75_enfermagem,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_acs, 4)[OFFSET(1)], 0)        AS p25_acs,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_acs, 4)[OFFSET(2)], 0)        AS p50_acs,
        ROUND(APPROX_QUANTILES(dias_desde_ultima_acs, 4)[OFFSET(3)], 0)        AS p75_acs
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY charlson_categoria, sexo
    ORDER BY
        CASE charlson_categoria
            WHEN 'Muito Alto' THEN 1
            WHEN 'Alto'       THEN 2
            WHEN 'Moderado'   THEN 3
            WHEN 'Baixo'      THEN 4
        END, sexo
    """
    return run_query(sql)

# ── Query para lista de pacientes ─────────────────────────────
@st.cache_data(show_spinner=False, ttl=900)
def carregar_lista_pacientes(ap=None, clinica=None, esf=None,
                              categorias=None, peso_necessidade=0.5) -> pd.DataFrame:
    extra = [
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'",
    ]
    if categorias:
        cats = "', '".join(categorias)
        extra.append(f"charlson_categoria IN ('{cats}')")
    where = _where(ap, clinica, esf, extra_clauses=extra)

    sql = f"""
    SELECT
        nome, nome_esf_cadastro, nome_clinica_cadastro,
        area_programatica_cadastro, idade, genero,
        charlson_categoria, charlson_score, total_morbidades,
        intervalo_mediano_dias, intervalo_medio_dias,
        dias_desde_ultima_medica, dias_desde_ultima_consulta,
        consultas_365d, consultas_medicas_365d,
        meses_com_consulta_12m, regularidade_acompanhamento,
        perfil_cuidado_365d, baixa_longitudinalidade,
        pct_consultas_medicas_na_unidade_365d,
        usuario_frequente_urgencia,
        alto_risco_baixo_acesso, alto_risco_intervalo_longo,
        -- Morbidades como string agrupada
        ARRAY_TO_STRING(
            ARRAY(SELECT m FROM UNNEST([
                IF(HAS IS NOT NULL,       'HAS', NULL),
                IF(DM IS NOT NULL,        'DM', NULL),
                IF(pre_DM IS NOT NULL,    'Pré-DM', NULL),
                IF(CI IS NOT NULL,        'CI', NULL),
                IF(ICC IS NOT NULL,       'ICC', NULL),
                IF(stroke IS NOT NULL,    'AVC', NULL),
                IF(IRC IS NOT NULL,       'IRC', NULL),
                IF(COPD IS NOT NULL,      'DPOC', NULL),
                IF(arritmia IS NOT NULL,  'Arritmia', NULL),
                IF(dementia IS NOT NULL,  'Demência', NULL),
                IF(HIV IS NOT NULL,       'HIV', NULL),
                IF(psicoses IS NOT NULL,  'Psicose', NULL),
                IF(depre_ansiedade IS NOT NULL, 'Depressão/Ans.', NULL),
                IF(obesidade_consolidada IS NOT NULL, 'Obesidade', NULL),
                IF(tireoide IS NOT NULL,  'Tireoide', NULL),
                IF(reumato IS NOT NULL,   'Reumato', NULL),
                IF(epilepsy IS NOT NULL,  'Epilepsia', NULL),
                IF(parkinsonism IS NOT NULL, 'Parkinson', NULL),
                IF(alcool IS NOT NULL,    'Álcool', NULL),
                IF(tabaco IS NOT NULL,    'Tabagismo', NULL),
                IF(liver IS NOT NULL,     'Hepatopatia', NULL),
                IF(neoplasia_mama IS NOT NULL
                   OR neoplasia_colo_uterino IS NOT NULL
                   OR neoplasia_feminina_estrita IS NOT NULL
                   OR neoplasia_masculina_estrita IS NOT NULL
                   OR neoplasia_ambos_os_sexos IS NOT NULL
                   OR leukemia IS NOT NULL
                   OR lymphoma IS NOT NULL
                   OR metastasis IS NOT NULL, 'Neoplasia', NULL)
            ]) AS m WHERE m IS NOT NULL),
        ', ') AS morbidades_lista,
        -- Medicamentos crônicos
        total_medicamentos_cronicos,
        nucleo_cronico_atual          AS medicamentos_lista,
        polifarmacia,
        hiperpolifarmacia,
        data_ultima_prescricao_cronica
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    ORDER BY charlson_score DESC, intervalo_mediano_dias DESC NULLS LAST
    LIMIT 5000
    """
    df = run_query(sql)
    if df.empty:
        return df

    max_charlson  = df['charlson_score'].max() or 1
    max_intervalo = df['intervalo_mediano_dias'].max() or 1
    df['charlson_norm']  = df['charlson_score'] / max_charlson
    df['intervalo_norm'] = df['intervalo_mediano_dias'].fillna(0) / max_intervalo
    df['ICA'] = (
        peso_necessidade * df['charlson_norm'] +
        (1 - peso_necessidade) * df['intervalo_norm']
    ).round(3)

    if MODO_ANONIMO:
        df['nome'] = df.apply(
            lambda r: anonimizar_nome(str(r.get('nome', '')), r.get('genero', '')), axis=1
        )
    return df.sort_values('ICA', ascending=False)

# ── Query para longitudinalidade por ESF ──────────────────────
@st.cache_data(show_spinner=False, ttl=900)
def carregar_longitudinalidade(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    where = _where(ap, clinica, esf, extra_clauses=["nome_esf_cadastro IS NOT NULL"])
    sql = f"""
    SELECT
        nome_esf_cadastro                                         AS esf,
        nome_clinica_cadastro                                     AS clinica,
        COUNT(*)                                                  AS total_pacientes,
        ROUND(AVG(pct_consultas_medicas_na_unidade_365d), 1)      AS pct_na_unidade,
        ROUND(AVG(pct_medico_esf_vs_medicos_365d), 1)             AS pct_medico_esf,
        COUNTIF(baixa_longitudinalidade = TRUE)                   AS baixa_longitudinalidade,
        COUNTIF(perfil_cuidado_365d = 'medico_centrado')          AS medico_centrado,
        COUNTIF(perfil_cuidado_365d = 'compartilhado')            AS compartilhado,
        COUNTIF(perfil_cuidado_365d = 'enfermagem_centrado')      AS enfermagem_centrado,
        COUNTIF(perfil_cuidado_365d = 'sem_consultas')            AS sem_consultas,
        COUNTIF(alto_risco_baixo_acesso = TRUE)                   AS alto_risco_baixo_acesso,
        COUNTIF(alto_risco_intervalo_longo = TRUE)                AS alto_risco_intervalo_longo
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY nome_esf_cadastro, nome_clinica_cadastro
    ORDER BY pct_na_unidade DESC
    """
    return run_query(sql)

# ── Query para violin — nível clínica (pontos = clínicas por AP)
@st.cache_data(show_spinner=False, ttl=900)
def carregar_violin_clinicas(ap_filtro=None, charlson_cats=None) -> pd.DataFrame:
    """1 linha por clínica, com AP como categoria."""
    extra = ["nome_clinica_cadastro IS NOT NULL", "area_programatica_cadastro IS NOT NULL"]
    if ap_filtro:
        extra.append(f"area_programatica_cadastro = '{ap_filtro}'")
    if charlson_cats:
        cats = "', '".join(charlson_cats)
        extra.append(f"charlson_categoria IN ('{cats}')")
    where = _where(extra_clauses=extra)
    sql = f"""
    SELECT
        area_programatica_cadastro                                AS categoria,
        nome_clinica_cadastro                                     AS unidade,
        COUNT(*)                                                  AS total_pacientes,
        ROUND(AVG(intervalo_mediano_dias), 1)                     AS intervalo_mediano_medio,
        ROUND(COUNTIF(dias_desde_ultima_medica > 180) * 100.0 / COUNT(*), 1)
                                                                  AS pct_sem_medico_180d,
        ROUND(COUNTIF(regularidade_acompanhamento = 'regular') * 100.0 / COUNT(*), 1)
                                                                  AS pct_regular,
        ROUND(COUNTIF(baixa_longitudinalidade = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_baixa_longitudinalidade,
        ROUND(COUNTIF(alto_risco_baixo_acesso = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_alto_risco_baixo_acesso,
        ROUND(COUNTIF(consultas_365d = 0) * 100.0 / COUNT(*), 1) AS pct_sem_consulta_365d,
        ROUND(COUNTIF(usuario_frequente_urgencia = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_frequente_urgencia
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY area_programatica_cadastro, nome_clinica_cadastro
    """
    df = run_query(sql)
    if not df.empty and MODO_ANONIMO:
        df['categoria'] = df['categoria'].apply(anonimizar_ap)
        df['unidade']   = df['unidade'].apply(anonimizar_clinica)
    return df

# ── Query para violin — nível ESF (pontos = ESFs por clínica) ─
@st.cache_data(show_spinner=False, ttl=900)
def carregar_violin_esfs(ap_filtro=None, clinica_filtro=None, charlson_cats=None) -> pd.DataFrame:
    """1 linha por ESF, com clínica como categoria."""
    clauses = ["nome_esf_cadastro IS NOT NULL", "nome_clinica_cadastro IS NOT NULL"]
    if ap_filtro:      clauses.append(f"area_programatica_cadastro = '{ap_filtro}'")
    if clinica_filtro: clauses.append(f"nome_clinica_cadastro = '{clinica_filtro}'")
    if charlson_cats:
        cats = "', '".join(charlson_cats)
        clauses.append(f"charlson_categoria IN ('{cats}')")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        nome_clinica_cadastro                                     AS categoria,
        nome_esf_cadastro                                         AS unidade,
        COUNT(*)                                                  AS total_pacientes,
        ROUND(AVG(intervalo_mediano_dias), 1)                     AS intervalo_mediano_medio,
        ROUND(COUNTIF(dias_desde_ultima_medica > 180) * 100.0 / COUNT(*), 1)
                                                                  AS pct_sem_medico_180d,
        ROUND(COUNTIF(regularidade_acompanhamento = 'regular') * 100.0 / COUNT(*), 1)
                                                                  AS pct_regular,
        ROUND(COUNTIF(baixa_longitudinalidade = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_baixa_longitudinalidade,
        ROUND(COUNTIF(alto_risco_baixo_acesso = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_alto_risco_baixo_acesso,
        ROUND(COUNTIF(consultas_365d = 0) * 100.0 / COUNT(*), 1) AS pct_sem_consulta_365d,
        ROUND(COUNTIF(usuario_frequente_urgencia = TRUE) * 100.0 / COUNT(*), 1)
                                                                  AS pct_frequente_urgencia
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY nome_clinica_cadastro, nome_esf_cadastro
    """
    df = run_query(sql)
    if not df.empty and MODO_ANONIMO:
        df['categoria'] = df['categoria'].apply(anonimizar_clinica)
        df['unidade']   = df['unidade'].apply(anonimizar_esf)
    return df

# ═══════════════════════════════════════════════════════════════
# VIOLIN PLOT — baseado em px.violin (abordagem do código de referência)
# ═══════════════════════════════════════════════════════════════

def criar_violin(df: pd.DataFrame, col_y: str, label_y: str,
                 label_x: str, titulo: str) -> go.Figure:
    """
    Violin com px.violin — uma cor por categoria, box interno, pontos com jitter.
    Cada ponto = unidade do nível inferior (clínica ou ESF).
    """
    if df.empty or col_y not in df.columns:
        return None

    # Ordenar categorias alfabeticamente para eixo X consistente
    categorias_ord = sorted(df['categoria'].dropna().unique().tolist())

    fig = px.violin(
        df,
        x='categoria',
        y=col_y,
        color='categoria',
        title=titulo,
        labels={col_y: label_y, 'categoria': label_x},
        height=620,
        hover_data={'unidade': True, 'total_pacientes': True, 'categoria': False},
        category_orders={'categoria': categorias_ord},
        box=True,
        points='all',
    )

    # Pontos maiores, semi-transparentes, com jitter
    fig.update_traces(
        marker=dict(size=9, opacity=0.65, line=dict(width=0)),
        jitter=0.4,
        pointpos=0,
        meanline_visible=True,
        spanmode='hard',
    )

    fig.update_xaxes(
        type='category',
        categoryorder='array',
        categoryarray=categorias_ord,
        tickangle=-30,
        tickfont=dict(size=12),
        title_font=dict(size=14),
    )
    fig.update_yaxes(
        tickfont=dict(size=12),
        title_font=dict(size=14),
        gridcolor='rgba(255,255,255,0.06)',
        zeroline=False,
    )
    fig.update_layout(
        showlegend=False,
        font=dict(size=13),
        title_font=dict(size=15),
        margin=dict(l=60, r=40, t=70, b=110),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )
    return fig

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo()
st.sidebar.title("Filtros")

territorio = filtros_territoriais(
    key_prefix="acesso",
    obrigatorio_esf=False,
    mostrar_todas_opcoes=True
)

# ═══════════════════════════════════════════════════════════════
# PERSISTÊNCIA DE ABA ATIVA
# ═══════════════════════════════════════════════════════════════
# Streamlit reseta para a aba 0 a cada rerun. Para manter a aba
# ativa, usamos session_state + on_change callback.
if 'aba_ativa' not in st.session_state:
    st.session_state['aba_ativa'] = 0

NOMES_ABAS = [
    "📊 Panorama Populacional",
    "🗺️ Distribuição por Território",
    "📋 Lista de Pacientes",
    "⏱️ Frequência e Abandono",
]

# Seletor de aba na sidebar (complementa as tabs e persiste o estado)
st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
aba_escolhida = st.sidebar.radio(
    "",
    options=range(len(NOMES_ABAS)),
    format_func=lambda i: NOMES_ABAS[i],
    index=st.session_state['aba_ativa'],
    key="nav_aba",
    label_visibility="collapsed",
)
st.session_state['aba_ativa'] = aba_escolhida

# ═══════════════════════════════════════════════════════════════
# TÍTULO
# ═══════════════════════════════════════════════════════════════
st.title("🔄 Acesso e Continuidade do Cuidado")
st.markdown(
    "Análise dos padrões de acesso, longitudinalidade e equidade "
    "no atendimento por carga de morbidade e território."
)
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# ABAS — renderização condicional pela aba ativa
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs(NOMES_ABAS)

# ──────────────────────────────────────────────────────────────
# ABA 1 — PANORAMA
# ──────────────────────────────────────────────────────────────
with tab1:
    with st.spinner("Carregando panorama..."):
        df_pan = carregar_panorama(
            ap=territorio['ap'],
            clinica=territorio['clinica'],
            esf=territorio['esf']
        )

    if df_pan.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # Agregar totais (somando sexos) para os cards
    df_tot = df_pan.groupby('charlson_categoria').agg(
        total_pacientes=('total_pacientes','sum'),
        sem_medico_180d=('sem_medico_180d','sum'),
        alto_risco_baixo_acesso=('alto_risco_baixo_acesso','sum'),
        frequente_urgencia=('frequente_urgencia','sum'),
        intervalo_mediano_medio=('intervalo_mediano_medio','mean'),
        consultas_365d_media=('consultas_365d_media','mean'),
        dias_sem_medico_medio=('dias_sem_medico_medio','mean'),
        pct_sem_medico_180d=('pct_sem_medico_180d','mean'),
        pct_regular=('pct_regular','mean'),
        pct_baixa_long=('pct_baixa_long','mean'),
        pct_alto_risco_baixo_acesso=('pct_alto_risco_baixo_acesso','mean'),
    ).reset_index()
    ordem_cat = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
    df_tot['_ord'] = df_tot['charlson_categoria'].map({c: i for i, c in enumerate(ordem_cat)})
    df_tot = df_tot.sort_values('_ord').drop(columns='_ord')

    total_geral    = int(df_tot['total_pacientes'].sum())
    sem_medico_180 = int(df_tot['sem_medico_180d'].sum())
    alto_risco_ba  = int(df_tot['alto_risco_baixo_acesso'].sum())
    frequente_urg  = int(df_tot['frequente_urgencia'].sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Total de Pacientes", f"{total_geral:,}")
    c2.metric("⏳ Sem médico há >180 dias", f"{sem_medico_180:,}",
              delta=f"{sem_medico_180/total_geral*100:.1f}%" if total_geral else "—",
              delta_color="inverse")
    c3.metric("⚠️ Alto risco + baixo acesso", f"{alto_risco_ba:,}",
              delta=f"{alto_risco_ba/total_geral*100:.1f}%" if total_geral else "—",
              delta_color="inverse")
    c4.metric("🚨 Uso frequente de urgência", f"{frequente_urg:,}",
              delta=f"{frequente_urg/total_geral*100:.1f}%" if total_geral else "—",
              delta_color="inverse")

    st.markdown("---")

    # ── Tabela resumo ───────────────────────────────────────────
    st.subheader("📋 Resumo por Categoria")
    st.dataframe(
        df_tot[[
            'charlson_categoria', 'total_pacientes',
            'intervalo_mediano_medio', 'consultas_365d_media',
            'dias_sem_medico_medio', 'pct_sem_medico_180d',
            'pct_regular', 'pct_baixa_long', 'pct_alto_risco_baixo_acesso',
            'alto_risco_baixo_acesso',
        ]].rename(columns={
            'charlson_categoria': 'Categoria Charlson',
            'total_pacientes': 'Pacientes',
            'intervalo_mediano_medio': 'Interv. mediano (d)',
            'consultas_365d_media': 'Consultas/ano',
            'dias_sem_medico_medio': 'Dias s/ médico (média)',
            'pct_sem_medico_180d': '% s/ médico 180d',
            'pct_regular': '% regular',
            'pct_baixa_long': '% baixa longit.',
            'pct_alto_risco_baixo_acesso': '% alto risco b. acesso',
            'alto_risco_baixo_acesso': 'N alto risco b. acesso',
        }),
        hide_index=True, use_container_width=True
    )


# ──────────────────────────────────────────────────────────────
# ABA 2 — VIOLIN PLOTS
# ──────────────────────────────────────────────────────────────
with tab2:

    st.markdown("""
    ### 🗺️ Acesso e Continuidade por Território

    Cada **ponto** representa uma unidade do nível imediatamente inferior ao filtro ativo.
    A **forma do violino** mostra onde estão concentradas as unidades — mais larga onde
    há mais unidades com aquele valor. A **linha central** indica a mediana.

    | Filtro ativo | Eixo X | Cada ponto |
    |---|---|---|
    | Nenhum (visão geral) | Área Programática | 1 Clínica |
    | AP selecionada | Clínica da AP | 1 ESF |
    | Clínica selecionada | ESF da Clínica | 1 ESF |
    """)

    # Seletor do indicador Y
    ind_sel_label = st.selectbox(
        "📊 Indicador para o eixo Y",
        options=[v['label'] for v in INDICADORES_VIOLIN.values()],
        index=0,
        key="violin_ind"
    )
    # Reverter label → chave e pegar descrição
    ind_sel_col   = next(k for k, v in INDICADORES_VIOLIN.items() if v['label'] == ind_sel_label)
    ind_descricao = INDICADORES_VIOLIN[ind_sel_col]['descricao']

    # Filtro de carga de morbidade
    charlson_opts = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
    charlson_violin = st.multiselect(
        "🏥 Filtrar por carga de morbidade",
        options=charlson_opts,
        default=charlson_opts,
        key="violin_charlson",
        help="Filtra quais pacientes entram no cálculo de cada unidade. "
             "Ex: selecionar apenas 'Muito Alto' mostra o indicador só para pacientes de alto risco."
    )
    cats_violin = charlson_violin if charlson_violin else None

    # Exibir descrição do indicador selecionado
    st.info(f"ℹ️ **{ind_sel_label}** — {ind_descricao}")

    st.markdown("---")

    with st.spinner("Carregando dados para violin..."):
        ap_ativo      = territorio['ap']
        clinica_ativo = territorio['clinica']

        if clinica_ativo:
            df_viol   = carregar_violin_esfs(
                ap_filtro=ap_ativo, clinica_filtro=clinica_ativo,
                charlson_cats=cats_violin
            )
            label_x   = "Clínica"
            nivel_txt = f"ESFs — {anonimizar_clinica(clinica_ativo) if MODO_ANONIMO else clinica_ativo}"
            ponto_txt = "ESF"
        elif ap_ativo:
            df_viol   = carregar_violin_esfs(
                ap_filtro=ap_ativo, charlson_cats=cats_violin
            )
            label_x   = "Clínica"
            nivel_txt = f"ESFs por Clínica — AP {anonimizar_ap(ap_ativo) if MODO_ANONIMO else ap_ativo}"
            ponto_txt = "ESF"
        else:
            df_viol   = carregar_violin_clinicas(charlson_cats=cats_violin)
            label_x   = "Área Programática"
            nivel_txt = "Clínicas por Área Programática"
            ponto_txt = "Clínica"

        # Sufixo descritivo se há filtro de Charlson
        if cats_violin and set(cats_violin) != set(charlson_opts):
            nivel_txt += f" | Charlson: {', '.join(cats_violin)}"

    if df_viol.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        n_categorias = df_viol['categoria'].nunique()
        n_unidades   = len(df_viol)

        st.caption(
            f"**{n_unidades} {ponto_txt}s** distribuídas em "
            f"**{n_categorias} {label_x}s**  ·  "
            f"Indicador: **{ind_sel_label}**"
        )

        fig_viol = criar_violin(
            df=df_viol,
            col_y=ind_sel_col,
            label_y=ind_sel_label,
            label_x=label_x,
            titulo=f"{ind_sel_label} — {nivel_txt}"
        )

        if fig_viol:
            st.plotly_chart(fig_viol, use_container_width=True)
        else:
            st.warning(f"Coluna '{ind_sel_col}' não encontrada nos dados.")

        # Tabela de apoio
        with st.expander("📋 Ver dados brutos do violin"):
            df_show = df_viol[['categoria', 'unidade', 'total_pacientes', ind_sel_col]].copy()
            df_show.columns = [label_x, ponto_txt, 'Pacientes', ind_sel_label]
            df_show = df_show.sort_values([label_x, ind_sel_label])
            st.dataframe(df_show, hide_index=True, use_container_width=True)

            csv_v = df_show.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button("⬇️ Baixar dados (.csv)", csv_v,
                               "violin_dados.csv", "text/csv")


# ──────────────────────────────────────────────────────────────
# ABA 3 — LISTA DE PACIENTES
# ──────────────────────────────────────────────────────────────
with tab3:
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        categorias_sel = st.multiselect(
            "Categoria Charlson",
            options=['Muito Alto', 'Alto', 'Moderado', 'Baixo'],
            default=['Muito Alto', 'Alto', 'Moderado', 'Baixo'],
            key="cat_charlson"
        )
    with col_f2:
        peso = st.slider(
            "Peso: Necessidade (Charlson) vs Déficit de Acesso (Intervalo)",
            min_value=0.0, max_value=1.0, value=0.5, step=0.1,
            help="0 = só intervalo importa | 1 = só Charlson importa",
            key="peso_ica"
        )
    with col_f3:
        n_exibir = st.selectbox(
            "Exibir", options=[50, 100, 250, 500, 1000, 5000], index=1,
            key="n_exibir"
        )

    with st.spinner("Carregando lista de pacientes..."):
        df_lista = carregar_lista_pacientes(
            ap=territorio['ap'],
            clinica=territorio['clinica'],
            esf=territorio['esf'],
            categorias=categorias_sel if categorias_sel else None,
            peso_necessidade=peso
        )

    if df_lista.empty:
        st.warning("Nenhum paciente encontrado.")
    else:
        total_lista    = len(df_lista)
        alto_risco_l   = int(df_lista['alto_risco_baixo_acesso'].sum())

        st.markdown(
            f"**{total_lista:,} pacientes** · "
            f"**{alto_risco_l:,}** com alto risco e baixo acesso"
        )

        df_exib = df_lista.head(n_exibir).copy()
        df_exib['baixa_longitudinalidade']  = df_exib['baixa_longitudinalidade'].map(
            {True: '⚠️ Sim', False: '✅ Não'})
        df_exib['alto_risco_baixo_acesso']  = df_exib['alto_risco_baixo_acesso'].map(
            {True: '🔴 Sim', False: '—'})
        df_exib['usuario_frequente_urgencia'] = df_exib['usuario_frequente_urgencia'].map(
            {True: '🚨 Sim', False: '—'})
        df_exib['polifarmacia']    = df_exib['polifarmacia'].map({True: '💊 Sim', False: '—'})
        df_exib['hiperpolifarmacia'] = df_exib['hiperpolifarmacia'].map({True: '💊💊 Sim', False: '—'})
        if 'data_ultima_prescricao_cronica' in df_exib.columns:
            df_exib['data_ultima_prescricao_cronica'] = pd.to_datetime(
                df_exib['data_ultima_prescricao_cronica'], errors='coerce'
            ).dt.strftime('%d/%m/%Y')

        if MODO_ANONIMO:
            df_exib['nome_esf_cadastro']       = df_exib['nome_esf_cadastro'].apply(anonimizar_esf)
            df_exib['nome_clinica_cadastro']    = df_exib['nome_clinica_cadastro'].apply(anonimizar_clinica)
            df_exib['area_programatica_cadastro'] = df_exib['area_programatica_cadastro'].apply(anonimizar_ap)

        colunas_lista = {
            'nome':                          'Paciente',
            'nome_esf_cadastro':             'ESF',
            'idade':                         'Idade',
            'charlson_categoria':            'Charlson',
            'charlson_score':                'Score',
            'total_morbidades':              'N° Morb.',
            'morbidades_lista':              'Morbidades',
            'intervalo_mediano_dias':        'Interv. (d)',
            'dias_desde_ultima_medica':      'Dias s/ médico',
            'consultas_365d':                'Consultas/ano',
            'meses_com_consulta_12m':        'Meses c/ consulta',
            'regularidade_acompanhamento':   'Regularidade',
            'baixa_longitudinalidade':       'Baixa Longit.',
            'total_medicamentos_cronicos':   'N° Meds',
            'medicamentos_lista':            'Medicamentos em uso',
            'polifarmacia':                  'Polifarmácia',
            'hiperpolifarmacia':             'Hiperpolifarmácia',
            'data_ultima_prescricao_cronica':'Últ. prescrição',
            'alto_risco_baixo_acesso':       'Risco + Baixo Acesso',
            'usuario_frequente_urgencia':    'Urgência Freq.',
            'ICA':                           'ICA ↓',
        }
        # Só incluir colunas que existem no df
        cols_presentes = {k: v for k, v in colunas_lista.items() if k in df_exib.columns}

        st.dataframe(
            df_exib[list(cols_presentes.keys())].rename(columns=cols_presentes),
            hide_index=True, use_container_width=True, height=520,
            column_config={
                'Morbidades':        st.column_config.TextColumn(width='medium'),
                'Medicamentos em uso': st.column_config.TextColumn(width='large'),
            }
        )

        st.caption(
            "**ICA — Índice Composto de Acesso:** combina a necessidade clínica do paciente "
            "(Charlson normalizado — quanto mais doente, maior o peso) com o déficit de acesso "
            "(intervalo mediano normalizado — quanto mais tempo sem consulta, maior o peso). "
            "O resultado vai de 0 a 1: **ICA próximo de 1 = paciente complexo com pouco acesso**, "
            "ou seja, maior prioridade para ação da equipe. "
            f"Nesta lista: peso Necessidade = {peso:.0%} | peso Acesso = {1-peso:.0%}."
        )

        csv = df_lista[list(cols_presentes.keys())].rename(columns=cols_presentes).to_csv(
            index=False, sep=';', encoding='utf-8-sig'
        )
        st.download_button("⬇️ Baixar lista completa (.csv)", csv,
                           "lista_acesso_continuidade.csv", "text/csv")


# ──────────────────────────────────────────────────────────────
# ABA 4 — FREQUÊNCIA E ABANDONO (unificada)
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("""
    ### ⏱️ Frequência de Acesso e Abandono do Cuidado

    Esta aba responde duas perguntas complementares sobre o acesso dos pacientes:

    | | Pergunta | Dimensão temporal |
    |---|---|---|
    | **Gráfico 1** | Com que frequência esse paciente consulta? | Histórico — padrão ao longo do ano |
    | **Gráfico 2** | Há quanto tempo esse paciente não consulta? | Pontual — estado atual |

    Lidos juntos, revelam a narrativa completa: *"este grupo consulta a cada X dias em média...
    mas está há Y dias sem atendimento agora."*
    """)

    st.markdown("---")

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        estratificar_sexo = st.toggle(
            "Estratificar por sexo", value=False, key="long_sexo"
        )
    with col_opt2:
        metrica_long = st.selectbox(
            "Métrica para o Gráfico 2",
            options=['Média de dias', 'Mediana (P50)', 'P75 (maioria dos pacientes)'],
            key="long_metrica"
        )

    with st.spinner("Carregando dados..."):
        df_tpc = carregar_tempo_proxima_consulta(
            ap=territorio['ap'],
            clinica=territorio['clinica'],
            esf=territorio['esf']
        )

    if df_tpc.empty or df_pan.empty:
        st.warning("Nenhum dado encontrado.")
    else:
        ordem_cat = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
        cores_sexo = {'Feminino': '#8FBC8F', 'Masculino': '#D4C06A', 'Não informado': '#A8A8A8'}

        df_tpc['_ord'] = df_tpc['charlson_categoria'].map(
            {c: i for i, c in enumerate(ordem_cat)}
        )
        df_tpc = df_tpc.sort_values(['_ord', 'sexo'])

        # ──────────────────────────────────────────────────────
        # GRÁFICO 1 — Intervalo mediano (histórico, por sexo)
        # ──────────────────────────────────────────────────────
        st.subheader("📊 Gráfico 1 — Intervalo Mediano entre Consultas (padrão histórico)")
        st.caption(
            "Mediana dos intervalos entre consultas consecutivas nos últimos 365 dias. "
            "Mostra o **ritmo habitual** de acompanhamento. "
            "Pacientes de **Muito Alto risco** deveriam ter os menores intervalos."
        )

        df_pan['_ord'] = df_pan['charlson_categoria'].map(
            {c: i for i, c in enumerate(ordem_cat)}
        )
        df_pan_s = df_pan.sort_values('_ord')

        fig_g1 = go.Figure()
        if estratificar_sexo:
            for sexo in ['Feminino', 'Masculino']:
                df_s = df_pan_s[df_pan_s['sexo'] == sexo]
                if df_s.empty:
                    continue
                fig_g1.add_trace(go.Bar(
                    name=sexo,
                    x=df_s['charlson_categoria'],
                    y=df_s['intervalo_mediano_medio'],
                    marker_color=cores_sexo[sexo],
                    text=df_s['intervalo_mediano_medio'].apply(lambda v: f"{v:.0f}d"),
                    textposition='outside',
                    hovertemplate=(
                        f"<b>%{{x}} — {sexo}</b><br>"
                        "Intervalo mediano: %{y:.0f} dias<br>"
                        "<extra></extra>"
                    )
                ))
        else:
            df_g1 = df_pan_s.groupby('charlson_categoria').agg(
                intervalo_mediano_medio=('intervalo_mediano_medio', 'mean')
            ).reset_index()
            df_g1['_ord'] = df_g1['charlson_categoria'].map(
                {c: i for i, c in enumerate(ordem_cat)}
            )
            df_g1 = df_g1.sort_values('_ord')
            cores_cat = {'Muito Alto': '#C0392B', 'Alto': '#E67E22',
                         'Moderado': '#F4D03F', 'Baixo': '#2ECC71'}
            fig_g1.add_trace(go.Bar(
                x=df_g1['charlson_categoria'],
                y=df_g1['intervalo_mediano_medio'],
                marker_color=[cores_cat.get(c, '#888') for c in df_g1['charlson_categoria']],
                text=df_g1['intervalo_mediano_medio'].apply(lambda v: f"{v:.0f}d"),
                textposition='outside',
                hovertemplate="<b>%{x}</b><br>Intervalo mediano: %{y:.0f} dias<extra></extra>"
            ))

        fig_g1.update_layout(
            barmode='group',
            xaxis=dict(title="Carga de Morbidade (Charlson)",
                       categoryorder='array', categoryarray=ordem_cat),
            yaxis=dict(title="Intervalo mediano (dias)"),
            legend=dict(title="Sexo", orientation='h',
                        yanchor='bottom', y=1.02, xanchor='right', x=1),
            height=400,
            margin=dict(t=60, b=60),
            showlegend=estratificar_sexo,
        )
        st.plotly_chart(fig_g1, use_container_width=True)

        st.markdown("---")

        # ──────────────────────────────────────────────────────
        # GRÁFICO 2 — Dias desde a última consulta (estado atual)
        # ──────────────────────────────────────────────────────
        st.subheader(f"📊 Gráfico 2 — Dias desde a Última Consulta por Profissional ({metrica_long})")
        st.caption(
            "Mostra o **estado atual**: há quantos dias os pacientes estão sem atendimento "
            "de cada tipo de profissional. Diferente do Gráfico 1, não depende do histórico — "
            "captura pacientes que saíram do radar recentemente."
        )

        map_metrica = {
            'Média de dias':               ('dias_medico',   'dias_enfermagem',   'dias_acs'),
            'Mediana (P50)':               ('p50_medico',    'p50_enfermagem',    'p50_acs'),
            'P75 (maioria dos pacientes)': ('p75_medico',    'p75_enfermagem',    'p75_acs'),
        }
        col_med, col_enf, col_acs = map_metrica[metrica_long]

        profissionais = [
            (col_med, '🩺 Médico',     '#5B9BD5'),
            (col_enf, '💉 Enfermeiro', '#70AD47'),
            (col_acs, '🏠 ACS',        '#ED7D31'),
        ]

        fig_g2 = go.Figure()

        if estratificar_sexo:
            for col_p, label_p, cor_p in profissionais:
                for sexo, pattern in zip(['Feminino', 'Masculino'], ['', '/']):
                    df_s = df_tpc[df_tpc['sexo'] == sexo]
                    if df_s.empty:
                        continue
                    fig_g2.add_trace(go.Bar(
                        name=f"{label_p} · {sexo}",
                        x=df_s['charlson_categoria'],
                        y=df_s[col_p],
                        marker=dict(
                            color=cor_p,
                            opacity=0.9 if sexo == 'Feminino' else 0.55,
                            pattern=dict(shape=pattern, size=4),
                        ),
                        text=df_s[col_p].apply(lambda v: f"{v:.0f}d" if pd.notna(v) else ""),
                        textposition='outside',
                        hovertemplate=(
                            f"<b>%{{x}} — {sexo}</b><br>"
                            f"{label_p}: %{{y:.0f}} dias<br>"
                            "<extra></extra>"
                        )
                    ))
        else:
            df_agg = df_tpc.groupby('charlson_categoria').agg(
                dias_medico=('dias_medico','mean'),
                dias_enfermagem=('dias_enfermagem','mean'),
                dias_acs=('dias_acs','mean'),
                p50_medico=('p50_medico','mean'),
                p50_enfermagem=('p50_enfermagem','mean'),
                p50_acs=('p50_acs','mean'),
                p75_medico=('p75_medico','mean'),
                p75_enfermagem=('p75_enfermagem','mean'),
                p75_acs=('p75_acs','mean'),
            ).reset_index()
            df_agg['_ord'] = df_agg['charlson_categoria'].map(
                {c: i for i, c in enumerate(ordem_cat)}
            )
            df_agg = df_agg.sort_values('_ord')

            for col_p, label_p, cor_p in profissionais:
                fig_g2.add_trace(go.Bar(
                    name=label_p,
                    x=df_agg['charlson_categoria'],
                    y=df_agg[col_p],
                    marker_color=cor_p,
                    text=df_agg[col_p].apply(lambda v: f"{v:.0f}d" if pd.notna(v) else ""),
                    textposition='outside',
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>"
                        f"{label_p}: %{{y:.0f}} dias<br>"
                        "<extra></extra>"
                    )
                ))

        fig_g2.update_layout(
            barmode='group',
            xaxis=dict(title="Carga de Morbidade (Charlson)",
                       categoryorder='array', categoryarray=ordem_cat),
            yaxis=dict(title="Dias desde o último atendimento"),
            legend=dict(title="Profissional", orientation='h',
                        yanchor='bottom', y=1.02, xanchor='right', x=1),
            height=460,
            margin=dict(t=80, b=60)
        )
        st.plotly_chart(fig_g2, use_container_width=True)
        st.caption(
            "Barras mais **baixas** = pacientes acompanhados mais recentemente. "
            "O esperado é que pacientes de **Muito Alto risco** tenham as barras mais baixas "
            "em todos os profissionais."
        )

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ | Navegador Clínico | Acesso e Continuidade do Cuidado")