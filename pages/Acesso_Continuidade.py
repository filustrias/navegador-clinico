"""
Página: Acesso e Continuidade do Cuidado
Análise de padrões de acesso por carga de morbidade, índices de longitudinalidade
e violin plots comparativos por subdivisão territorial.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.bigquery_client import get_bigquery_client
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
    anonimizar_nome, mostrar_badge_anonimo, MODO_ANONIMO
)
import config
from utils import theme as T

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
    st.markdown(f"""
    <h1 style='margin: 0; padding: 0; color: {T.TEXT};'>
        🏥 Navegador Clínico de Multimorbidade e Polifarmácia
    </h1>
    """, unsafe_allow_html=True)
with col2:
    info_lines = [f"<strong>{nome}</strong>"]
    if esf     != 'N/A': info_lines.append(f"ESF: {esf}")
    if clinica != 'N/A': info_lines.append(f"Clínica: {clinica}")
    if ap      != 'N/A': info_lines.append(f"AP: {ap}")
    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: {T.TEXT}; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Continuidade"   # ← ÚNICA linha que muda em cada página
ROTAS = {
    "Home":          "Home.py",
    "População":     "pages/Minha_Populacao.py",
    "Pacientes":     "pages/Meus_Pacientes.py",
    "Lacunas":       "pages/Lacunas_de_Cuidado.py",
    "Continuidade":  "pages/Acesso_Continuidade.py",
    "Polifarmácia":  "pages/Polifarmacia_ACB.py",
    "Diabetes":      "pages/Diabetes.py",
    "Hipertensão":   "pages/Hipertensao.py",
    "Risco CV":      "pages/Risco_Cardiovascular.py",
}

ICONES_MENU = [
    "house-fill",               # Home
    "people-fill",              # População
    "person-lines-fill",        # Pacientes
    "exclamation-triangle-fill",# Lacunas
    "arrow-repeat",             # Continuidade
    "capsule",                  # Polifarmácia
    "droplet-fill",             # Diabetes
    "heart-pulse-fill",         # Hipertensão
    "heart-fill",               # Risco CV
]
selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES_MENU,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0!important",
            "background-color": T.NAV_BG,
        },
        "icon": {
            "font-size": "22px",
            "color": T.TEXT,
            "display": "block",
            "margin-bottom": "4px",
        },
        "nav-link": {
            "font-size": "11px",
            "text-align": "center",
            "margin": "0px",
            "padding": "10px 18px",
            "color": T.NAV_LINK,
            "background-color": T.SECONDARY_BG,
            "--hover-color": T.NAV_HOVER,
            "display": "flex",
            "flex-direction": "column",
            "align-items": "center",
            "line-height": "1.2",
            "white-space": "nowrap",
        },
        "nav-link-selected": {
            "background-color": T.NAV_SELECTED_BG,
            "color": T.NAV_SELECTED_TEXT,
            "font-weight": "600",
        },
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
        'label': '% fragmentação do cuidado',
        'descricao': (
            'Proporção de pacientes cujas consultas médicas ocorrem predominantemente '
            'fora da unidade de cadastro (>50% fora). Reflete fragmentação do cuidado '
            'e menor vínculo com a equipe de referência.'
        ),
    },
    'pct_alto_risco_baixo_acesso': {
        'label': '% alto risco + baixo acesso',
        'descricao': (
            'Pacientes com carga de morbidade muito alta (escore ≥ 7) que consultam '
            'abaixo do P25 do seu grupo de pares. É o principal indicador de iniquidade '
            'em saúde: quem mais precisa, menos acessa.'
        ),
    },
    'pct_regular': {
        'label': '% com > de 6 meses com consulta no ano',
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
        ROUND(AVG(consultas_medicas_365d), 1)                      AS consultas_medicas_media,
        ROUND(AVG(consultas_enfermagem_365d), 1)                   AS consultas_enfermagem_media,
        ROUND(AVG(consultas_tecnico_enfermagem_365d), 1)           AS consultas_tecnico_media,
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
def carregar_ausencia_por_profissional(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """
    % de pacientes sem consulta há >180 e >365 dias por profissional,
    estratificado por charlson_categoria.
    """
    where = _where(ap, clinica, esf, extra_clauses=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        COUNT(*) AS total,

        -- Médico
        ROUND(COUNTIF(dias_desde_ultima_medica > 180)  * 100.0 / COUNT(*), 1)
            AS pct_sem_medico_180d,
        ROUND(COUNTIF(dias_desde_ultima_medica > 365)  * 100.0 / COUNT(*), 1)
            AS pct_sem_medico_365d,

        -- Enfermeiro
        ROUND(COUNTIF(dias_desde_ultima_enfermagem > 180) * 100.0 / COUNT(*), 1)
            AS pct_sem_enfermagem_180d,
        ROUND(COUNTIF(dias_desde_ultima_enfermagem > 365) * 100.0 / COUNT(*), 1)
            AS pct_sem_enfermagem_365d,

        -- Técnico de enfermagem
        ROUND(COUNTIF(dias_desde_ultima_tecnico_enfermagem > 180) * 100.0 / COUNT(*), 1)
            AS pct_sem_tecnico_180d,
        ROUND(COUNTIF(dias_desde_ultima_tecnico_enfermagem > 365) * 100.0 / COUNT(*), 1)
            AS pct_sem_tecnico_365d,

        -- Qualquer profissional clínico (médico OU enfermeiro OU técnico)
        ROUND(COUNTIF(
            dias_desde_ultima_medica         > 180 AND
            dias_desde_ultima_enfermagem     > 180 AND
            dias_desde_ultima_tecnico_enfermagem > 180
        ) * 100.0 / COUNT(*), 1) AS pct_sem_clinico_180d,
        ROUND(COUNTIF(
            dias_desde_ultima_medica         > 365 AND
            dias_desde_ultima_enfermagem     > 365 AND
            dias_desde_ultima_tecnico_enfermagem > 365
        ) * 100.0 / COUNT(*), 1) AS pct_sem_clinico_365d

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY charlson_categoria
    ORDER BY
        CASE charlson_categoria
            WHEN 'Muito Alto' THEN 1
            WHEN 'Alto'       THEN 2
            WHEN 'Moderado'   THEN 3
            WHEN 'Baixo'      THEN 4
        END
    """
    return run_query(sql)


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
                -- IF(tireoide IS NOT NULL,  'Tireoide', NULL),
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
                 label_x: str, titulo: str,
                 modo_strip: bool = False) -> go.Figure:
    """
    Violin com px.violin quando há múltiplas categorias.
    Strip plot (px.strip) quando há apenas uma categoria — 1 ponto por ESF.
    Cada ponto = unidade do nível inferior (clínica ou ESF).
    """
    if df.empty or col_y not in df.columns:
        return None

    categorias_ord = sorted(df['categoria'].dropna().unique().tolist())

    layout_comum = dict(
        showlegend=False,
        font=dict(size=13, color=T.TEXT),
        title_font=dict(size=15),
        margin=dict(l=60, r=40, t=70, b=110),
        plot_bgcolor=T.PLOT_BG,
        paper_bgcolor=T.PAPER_BG,
    )
    xaxes_comum = dict(
        type='category',
        tickangle=-30,
        tickfont=dict(size=11),
        title_font=dict(size=13),
    )
    yaxes_comum = dict(
        tickfont=dict(size=12),
        title_font=dict(size=14),
        gridcolor=T.GRID,
        zeroline=False,
    )

    if modo_strip:
        # Strip plot — 1 ponto por ESF, eixo X = nome da ESF
        fig = px.strip(
            df,
            x='unidade',
            y=col_y,
            color='unidade',
            title=titulo,
            labels={col_y: label_y, 'unidade': label_x},
            height=480,
            hover_data={'total_pacientes': True, 'unidade': True},
            color_discrete_sequence=px.colors.qualitative.Bold,
        )
        fig.update_traces(
            marker=dict(size=14, opacity=0.85, line=dict(width=1, color=T.BORDER)),
            jitter=0,
        )
        fig.update_xaxes(**xaxes_comum,
                         categoryorder='array',
                         categoryarray=sorted(df['unidade'].dropna().unique().tolist()))
        fig.update_yaxes(**yaxes_comum)
        fig.update_layout(**layout_comum)
    else:
        # Violin plot — distribuição por categoria
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
            color_discrete_sequence=px.colors.qualitative.Bold,
        )
        fig.update_traces(
            marker=dict(size=9, opacity=0.65, line=dict(width=0)),
            jitter=0.4,
            pointpos=0,
            meanline_visible=True,
            spanmode='hard',
        )
        fig.update_xaxes(**xaxes_comum,
                         categoryorder='array',
                         categoryarray=categorias_ord)
        fig.update_yaxes(**yaxes_comum)
        fig.update_layout(**layout_comum)

    return fig

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
st.sidebar.title("Filtros")

@st.cache_data(show_spinner=False, ttl=1800)
def _carregar_opcoes_territorio() -> dict:
    sql = f"""
    SELECT DISTINCT
        area_programatica_cadastro AS ap,
        nome_clinica_cadastro      AS clinica,
        nome_esf_cadastro          AS esf
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro IS NOT NULL
      AND nome_clinica_cadastro IS NOT NULL
      AND nome_esf_cadastro IS NOT NULL
    ORDER BY ap, clinica, esf
    """
    try:
        df = run_query(sql)
        areas = sorted(df['ap'].unique().tolist())
        clinicas_por_ap = {
            ap: sorted(df[df['ap'] == ap]['clinica'].unique().tolist())
            for ap in areas
        }
        esf_por_clinica = {
            cli: sorted(df[df['clinica'] == cli]['esf'].unique().tolist())
            for cli in df['clinica'].unique()
        }
        return {'areas': areas, 'clinicas': clinicas_por_ap, 'esf': esf_por_clinica}
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar filtros: {e}")
        return {'areas': [], 'clinicas': {}, 'esf': {}}

opcoes = _carregar_opcoes_territorio()

# ── Callbacks para reset hierárquico ─────────────────────────
def _ac_reset_cli_esf():
    st.session_state['ac_cli'] = "Todas as Clínicas"
    st.session_state['ac_esf'] = "Todas as ESFs"

def _ac_reset_esf():
    st.session_state['ac_esf'] = "Todas as ESFs"

# Inicializar session_state
if 'ac_ap' not in st.session_state:
    st.session_state['ac_ap'] = "Todas as Áreas Programáticas"
if 'ac_cli' not in st.session_state:
    st.session_state['ac_cli'] = "Todas as Clínicas"
if 'ac_esf' not in st.session_state:
    st.session_state['ac_esf'] = "Todas as ESFs"

# Área Programática
ap_opcoes = ["Todas as Áreas Programáticas"] + opcoes['areas']
ap_sel_raw = st.sidebar.selectbox(
    "📍 Área Programática", options=ap_opcoes,
    format_func=lambda x: x if x == "Todas as Áreas Programáticas" else anonimizar_ap(str(x)),
    key="ac_ap", on_change=_ac_reset_cli_esf,
)
ap_sel = None if ap_sel_raw == "Todas as Áreas Programáticas" else ap_sel_raw

# Clínica — filtra pela AP se selecionada
if ap_sel and ap_sel in opcoes['clinicas']:
    clinicas_disp = opcoes['clinicas'][ap_sel]
else:
    clinicas_disp = sorted({c for clist in opcoes['clinicas'].values() for c in clist})
cli_opcoes = ["Todas as Clínicas"] + clinicas_disp

# Garantir que o valor em session_state é válido para a AP atual
if st.session_state.get('ac_cli') not in cli_opcoes:
    st.session_state['ac_cli'] = "Todas as Clínicas"

cli_sel_raw = st.sidebar.selectbox(
    "🏥 Clínica da Família", options=cli_opcoes,
    format_func=lambda x: x if x == "Todas as Clínicas" else anonimizar_clinica(x),
    key="ac_cli", disabled=not clinicas_disp,
    on_change=_ac_reset_esf,
)
cli_sel = None if cli_sel_raw == "Todas as Clínicas" else cli_sel_raw

# ESF — filtra pela clínica se selecionada
esfs_disp = opcoes['esf'].get(cli_sel, []) if cli_sel else []
esf_opcoes = ["Todas as ESFs"] + esfs_disp

# Garantir que o valor em session_state é válido para a clínica atual
if st.session_state.get('ac_esf') not in esf_opcoes:
    st.session_state['ac_esf'] = "Todas as ESFs"

esf_sel_raw = st.sidebar.selectbox(
    "👥 Equipe ESF", options=esf_opcoes,
    format_func=lambda x: x if x == "Todas as ESFs" else anonimizar_esf(x),
    key="ac_esf", disabled=not esfs_disp,
)
esf_sel = None if esf_sel_raw == "Todas as ESFs" else esf_sel_raw

territorio = {
    'ap':      ap_sel,
    'clinica': cli_sel,
    'esf':     esf_sel,
}

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

    # ── Tabela resumo visual ─────────────────────────────────────
    st.subheader("📋 Resumo por Categoria de Carga de Morbidade")
    st.caption(
        "Cada linha corresponde a uma categoria de carga de morbidade. "
        "Leia da esquerda para a direita: quantos são, com que frequência acessam, "
        "há quanto tempo estão sem médico, e quantos enfrentam barreiras de equidade."
    )

    ordem_cat = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
    df_exib = df_tot[[
        'charlson_categoria', 'total_pacientes',
        'intervalo_mediano_medio', 'consultas_365d_media',
        'pct_sem_medico_180d',
        'pct_regular', 'pct_baixa_long', 'pct_alto_risco_baixo_acesso',
        'alto_risco_baixo_acesso',
    ]].copy()
    df_exib['_ord'] = df_exib['charlson_categoria'].map(
        {c: i for i, c in enumerate(ordem_cat)}
    )
    df_exib = df_exib.sort_values('_ord').drop(columns='_ord')

    CORES_CAT = {
        'Muito Alto': '#C0392B',
        'Alto':       '#E67E22',
        'Moderado':   '#F1C40F',
        'Baixo':      '#2ECC71',
    }

    def _barra(val, cor):
        pct = min(val, 100)
        return (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="flex:1;background:{T.PROGRESS_BAR_BG};border-radius:3px;height:8px">'
            f'<div style="width:{pct:.0f}%;background:{cor};height:8px;border-radius:3px"></div>'
            f'</div>'
            f'<span style="white-space:nowrap;font-size:0.85em">{val:.1f}%</span>'
            f'</div>'
        )

    headers = [
        "Carga de<br>Morbidade",
        "Pacientes",
        "Intervalo<br>mediano<br>(dias)",
        "Consultas<br>médicas<br>por ano",
        "% sem médico<br>há mais de<br>180 dias",
        "% com > de 6<br>meses com<br>consulta no ano",
        "% fragmentação<br>do cuidado",
        "% alto risco<br>+ baixo<br>acesso",
        "N alto risco<br>+ baixo<br>acesso",
    ]

    rows_html = ""
    for _, row in df_exib.iterrows():
        cat = row['charlson_categoria']
        cor = CORES_CAT.get(cat, '#888')
        rows_html += (
            f'<tr>'
            f'<td><span style="color:{cor};font-weight:700">{cat}</span></td>'
            f'<td style="text-align:right">{int(row["total_pacientes"]):,}</td>'
            f'<td style="text-align:right">{row["intervalo_mediano_medio"]:.1f} d</td>'
            f'<td style="text-align:right">{row["consultas_365d_media"]:.1f}</td>'
            f'<td>{_barra(row["pct_sem_medico_180d"], "#E74C3C")}</td>'
            f'<td>{_barra(row["pct_regular"], "#27AE60")}</td>'
            f'<td>{_barra(row["pct_baixa_long"], "#E67E22")}</td>'
            f'<td>{_barra(row["pct_alto_risco_baixo_acesso"], "#8E44AD")}</td>'
            f'<td style="text-align:right">{int(row["alto_risco_baixo_acesso"]):,}</td>'
            f'</tr>'
        )

    th = (
        f"background:{T.TABLE_HEADER_BG};color:{T.TABLE_HEADER_TEXT};font-size:0.78em;font-weight:600;"
        f"text-align:center;padding:8px 10px;border-bottom:2px solid {T.TABLE_BORDER};"
        f"vertical-align:bottom;line-height:1.4;"
    )
    td = f"padding:8px 10px;border-bottom:1px solid {T.TABLE_BORDER};font-size:0.88em;color:{T.TABLE_CELL_TEXT};vertical-align:middle;"
    headers_html = "".join(f'<th style="{th}">{h}</th>' for h in headers)

    table_html = f"""
    <style>
      .nav-table {{width:100%;border-collapse:collapse;background:{T.TABLE_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
      .nav-table td {{{td}}}
      .nav-table tr:hover td {{background:{T.TABLE_HOVER};}}
    </style>
    <table class="nav-table">
      <thead><tr>{headers_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    st.components.v1.html(table_html, height=215, scrolling=False)

    # ── Legenda abaixo da tabela ─────────────────────────────────
    with st.expander("ℹ️ O que significa cada coluna?"):
        st.markdown("""
| Coluna | Descrição detalhada |
|---|---|
| **Carga de Morbidade** | Categoria do escore: **Muito Alto** (≥10 pts), **Alto** (7–9), **Moderado** (3–6), **Baixo** (≤2). Combina morbidades, idade e número de medicamentos. |
| **Pacientes** | Total de pacientes cadastrados nessa categoria no território selecionado. |
| **Intervalo mediano (dias)** | Mediana dos dias entre consultas médicas consecutivas nos últimos 12 meses. Menor = mais frequente. Pacientes de maior risco deveriam ter intervalos **menores**. |
| **Consultas médicas por ano** | Média de consultas com médico nos últimos 365 dias. Reflete a intensidade do acompanhamento clínico. |
| **% sem médico >180 dias** | Proporção do grupo sem consulta médica há mais de 6 meses. Indica abandono ou barreira de acesso ao cuidado médico. |
| **% com > de 6 meses com consulta no ano** | Proporção com pelo menos 6 meses distintos com consulta (médico, enfermeiro ou técnico) nos últimos 12 meses. |
| **% fragmentação do cuidado** | Proporção que realizou mais de 50% das consultas médicas fora da unidade de referência. Indica fragmentação do cuidado e menor vínculo com a equipe. |
| **% alto risco + baixo acesso** | Proporção com carga de morbidade muito alta (escore ≥7) que consulta abaixo do P25 do seu grupo de pares. Principal indicador de **iniquidade no cuidado**. |
| **N alto risco + baixo acesso** | Número absoluto de pacientes em situação de alto risco com baixo acesso — útil para dimensionar a magnitude do problema no território. |
        """)


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
            # Clínica filtrada → strip com ESFs daquela clínica
            df_viol   = carregar_violin_esfs(
                ap_filtro=ap_ativo, clinica_filtro=clinica_ativo,
                charlson_cats=cats_violin
            )
            label_x   = "Clínica"
            nivel_txt = f"ESFs — {anonimizar_clinica(clinica_ativo) if MODO_ANONIMO else clinica_ativo}"
            ponto_txt = "ESF"
        elif ap_ativo:
            # AP filtrada → violin por clínica (cada ponto = ESF)
            df_viol   = carregar_violin_esfs(
                ap_filtro=ap_ativo, charlson_cats=cats_violin
            )
            label_x   = "Clínica"
            nivel_txt = f"Clínicas — AP {anonimizar_ap(ap_ativo) if MODO_ANONIMO else ap_ativo}"
            ponto_txt = "ESF"
        else:
            # Sem filtro → violin por AP (cada ponto = clínica)
            df_viol   = carregar_violin_clinicas(charlson_cats=cats_violin)
            label_x   = "Área Programática"
            nivel_txt = "Clínicas por Área Programática"
            ponto_txt = "Clínica"

        # Sufixo descritivo se há filtro de Charlson
        if cats_violin and set(cats_violin) != set(charlson_opts):
            nivel_txt += f" | Carga: {', '.join(cats_violin)}"

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
            titulo=f"{ind_sel_label} — {nivel_txt}",
            modo_strip=bool(clinica_ativo),
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
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        categorias_sel = st.multiselect(
            "Carga de Morbidade",
            options=['Muito Alto', 'Alto', 'Moderado', 'Baixo'],
            default=['Muito Alto', 'Alto', 'Moderado', 'Baixo'],
            key="cat_charlson"
        )
    with col_f2:
        n_exibir = st.selectbox(
            "Exibir", options=[50, 100, 250, 500, 1000, 5000], index=1,
            key="n_exibir"
        )

    ordenar_ica = st.toggle(
        "Ordenar pelo ICA (pacientes mais complexos com menor acesso primeiro)",
        value=True,
        key="ordenar_ica",
        help="ICA — Índice Composto de Acesso: combina carga de morbidade com déficit de acesso. "
             "Quanto mais próximo de 1, maior a prioridade de atenção."
    )
    # Peso fixo em 0.5 (igual peso entre necessidade e acesso)
    peso = 0.5

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
        # Ordenar pelo ICA se toggle ativo, senão por carga de morbidade
        if ordenar_ica and 'ICA' in df_lista.columns:
            df_lista = df_lista.sort_values('ICA', ascending=False)
        elif 'charlson_score' in df_lista.columns:
            df_lista = df_lista.sort_values('charlson_score', ascending=False)

        total_lista  = len(df_lista)
        alto_risco_l = int(df_lista['alto_risco_baixo_acesso'].sum())

        st.markdown(
            f"**{total_lista:,} pacientes** · "
            f"**{alto_risco_l:,}** com alto risco e baixo acesso"
        )

        df_exib = df_lista.head(n_exibir).copy()
        df_exib['regularidade_acompanhamento'] = df_exib['regularidade_acompanhamento'].replace(
            {'regular': 'Assíduo', 'irregular': 'Irregular',
             'esporadico': 'Esporádico', 'sem_acompanhamento': 'Sem acompanhamento'})
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
            df_exib['nome_esf_cadastro']         = df_exib['nome_esf_cadastro'].apply(anonimizar_esf)
            df_exib['nome_clinica_cadastro']      = df_exib['nome_clinica_cadastro'].apply(anonimizar_clinica)
            df_exib['area_programatica_cadastro'] = df_exib['area_programatica_cadastro'].apply(anonimizar_ap)

        # ── Nova ordem: identificação → morbidade → acesso → medicamentos
        colunas_lista = {
            # Identificação
            'nome':                          'Paciente',
            'nome_esf_cadastro':             'ESF',
            'idade':                         'Idade',
            # Carga de morbidade
            'charlson_categoria':            'Carga de Morbidade',
            'charlson_score':                'Score',
            'total_morbidades':              'Nº de Morbidades',
            'morbidades_lista':              'Morbidades',
            # Acesso e continuidade
            'intervalo_mediano_dias':        'Intervalo Mediano entre Consultas (dias)',
            'dias_desde_ultima_medica':      'Dias sem Consulta Médica',
            'consultas_365d':                'Consultas Clínicas no Último Ano',
            'meses_com_consulta_12m':        'Meses com Consulta nos Últimos 12 Meses',
            'regularidade_acompanhamento':   'Regularidade do Acompanhamento',
            'baixa_longitudinalidade':       'Fragmentação do Cuidado',
            'alto_risco_baixo_acesso':       'Alto Risco + Baixo Acesso',
            'usuario_frequente_urgencia':    'Uso Frequente de Urgência',
            'ICA':                           'ICA',
            # Medicamentos
            'total_medicamentos_cronicos':   'Nº de Medicamentos',
            'medicamentos_lista':            'Medicamentos em Uso',
            'polifarmacia':                  'Polifarmácia',
            'hiperpolifarmacia':             'Hiperpolifarmácia',
            'data_ultima_prescricao_cronica':'Última Prescrição',
        }
        cols_presentes = {k: v for k, v in colunas_lista.items() if k in df_exib.columns}
        df_render = df_exib[list(cols_presentes.keys())].rename(columns=cols_presentes).copy()

        # ── Tabela HTML com cabeçalhos com quebra de linha ───────
        HEADERS_QUEBRA = {
            'Paciente':                                  'Paciente',
            'ESF':                                       'ESF',
            'Idade':                                     'Idade',
            'Carga de Morbidade':                        'Carga de<br>Morbidade',
            'Score':                                     'Score',
            'Nº de Morbidades':                          'Nº de<br>Morbidades',
            'Morbidades':                                'Morbidades',
            'Intervalo Mediano entre Consultas (dias)':  'Intervalo<br>Mediano<br>(dias)',
            'Dias sem Consulta Médica':                  'Dias sem<br>Consulta<br>Médica',
            'Consultas Clínicas no Último Ano':          'Consultas<br>no Último<br>Ano',
            'Meses com Consulta nos Últimos 12 Meses':   'Meses com<br>Consulta<br>(12m)',
            'Regularidade do Acompanhamento':            'Regulari-<br>dade',
            'Fragmentação do Cuidado':                   'Fragmen-<br>tação do<br>Cuidado',
            'Alto Risco + Baixo Acesso':                 'Alto Risco<br>+ Baixo<br>Acesso',
            'Uso Frequente de Urgência':                 'Uso Freq.<br>Urgência',
            'ICA':                                       'ICA',
            'Nº de Medicamentos':                        'Nº de<br>Medica-<br>mentos',
            'Medicamentos em Uso':                       'Medicamentos<br>em Uso',
            'Polifarmácia':                              'Poli-<br>farmácia',
            'Hiperpolifarmácia':                         'Hiper-<br>polifar-<br>mácia',
            'Última Prescrição':                         'Última<br>Prescrição',
        }

        CORES_CAT = {
            'Muito Alto': '#C0392B', 'Alto': '#E67E22',
            'Moderado': '#F1C40F',   'Baixo': '#2ECC71',
        }
        BADGE_COLORS = {
            '🔴 Sim': '#C0392B', '⚠️ Sim': '#E67E22',
            '🚨 Sim': '#C0392B', '💊 Sim': '#8E44AD',
            '💊💊 Sim': '#6C3483', '✅ Não': '#27AE60',
        }

        th = (
            f"background:{T.TABLE_HEADER_BG};color:{T.TABLE_HEADER_TEXT};font-size:0.75em;font-weight:600;"
            f"text-align:center;padding:7px 8px;border-bottom:2px solid {T.TABLE_BORDER};"
            f"vertical-align:bottom;line-height:1.35;white-space:normal;"
        )
        td_base = (
            f"padding:6px 8px;border-bottom:1px solid {T.TABLE_BORDER};"
            f"font-size:0.83em;color:{T.TABLE_CELL_TEXT};vertical-align:middle;"
            f"white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;"
        )

        cols_render = [c for c in df_render.columns if c in HEADERS_QUEBRA]
        headers_html = "".join(
            f'<th style="{th}">{HEADERS_QUEBRA[c]}</th>'
            for c in cols_render
        )

        rows_html = ""
        for _, row in df_render.iterrows():
            cells = ""
            for col in cols_render:
                val = row.get(col, '')
                val_str = '' if pd.isna(val) or val is None else str(val)

                # Estilo especial por coluna
                if col == 'Carga de Morbidade':
                    cor = CORES_CAT.get(val_str, '#888')
                    cell = f'<td style="{td_base}"><span style="color:{cor};font-weight:700">{val_str}</span></td>'
                elif col in ('Alto Risco + Baixo Acesso', 'Fragmentação do Cuidado',
                             'Uso Frequente de Urgência', 'Polifarmácia', 'Hiperpolifarmácia'):
                    cor = BADGE_COLORS.get(val_str, 'transparent')
                    if '—' in val_str or 'Não' in val_str:
                        cell = f'<td style="{td_base};color:{T.TEXT_MUTED}">{val_str}</td>'
                    else:
                        cell = (
                            f'<td style="{td_base}">'
                            f'<span style="background:{cor};color:white;padding:2px 6px;'
                            f'border-radius:3px;font-size:0.85em">{val_str}</span></td>'
                        )
                elif col == 'ICA':
                    try:
                        v = float(val_str)
                        cor_ica = f'hsl({int((1-v)*120)},70%,45%)'
                        cell = f'<td style="{td_base};text-align:right"><span style="color:{cor_ica};font-weight:600">{v:.3f}</span></td>'
                    except Exception:
                        cell = f'<td style="{td_base}">{val_str}</td>'
                elif col in ('Morbidades', 'Medicamentos em Uso'):
                    cell = (
                        f'<td style="{td_base};white-space:normal;max-width:220px;'
                        f'font-size:0.78em;color:{T.TEXT_MUTED}" title="{val_str}">{val_str}</td>'
                    )
                elif col in ('Intervalo Mediano entre Consultas (dias)',
                             'Dias sem Consulta Médica', 'Score',
                             'Nº de Morbidades', 'Nº de Medicamentos',
                             'Consultas Clínicas no Último Ano',
                             'Meses com Consulta nos Últimos 12 Meses'):
                    cell = f'<td style="{td_base};text-align:right">{val_str}</td>'
                else:
                    cell = f'<td style="{td_base}">{val_str}</td>'

                cells += cell
            rows_html += f'<tr style="cursor:default">{cells}</tr>'

        table_html = f"""
        <style>
          .pac-table {{
            width:100%;border-collapse:collapse;
            background:{T.TABLE_BG};
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          }}
          .pac-table tr:hover td {{ background:{T.TABLE_HOVER}; }}
        </style>
        <div style="overflow-x:auto;max-height:520px;overflow-y:auto">
          <table class="pac-table">
            <thead style="position:sticky;top:0;z-index:2">
              <tr>{headers_html}</tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """
        n_rows = len(df_render)
        altura_html = min(560, 56 + n_rows * 38)
        st.components.v1.html(table_html, height=altura_html, scrolling=True)

        # Legenda abaixo da tabela
        with st.expander("ℹ️ O que significa cada coluna?"):
            st.markdown("""
| Coluna | Descrição detalhada |
|---|---|
| **Paciente / ESF / Idade** | Identificação do paciente e equipe de saúde responsável. |
| **Carga de Morbidade** | Categoria do escore: **Muito Alto** (≥10 pts), **Alto** (7–9), **Moderado** (3–6), **Baixo** (≤2). |
| **Score** | Pontuação numérica do escore de carga de morbidade. Quanto maior, maior a complexidade clínica. |
| **Nº de Morbidades** | Total de condições crônicas ativas registradas para este paciente. |
| **Morbidades Ativas** | Lista das condições crônicas identificadas no registro. |
| **Intervalo Mediano entre Consultas (dias)** | Mediana dos dias entre consultas consecutivas nos últimos 12 meses. Menor = mais frequente. Nulo se não houve consultas no período. |
| **Dias sem Consulta Médica** | Dias desde a última consulta médica. Acima de 180 dias indica possível abandono. |
| **Consultas Clínicas no Último Ano** | Total de consultas com médico, enfermeiro ou técnico de enfermagem nos últimos 365 dias. |
| **Meses com Consulta (12 meses)** | Meses distintos com pelo menos uma consulta nos últimos 12 meses. **Assíduo** = ≥6 · **Irregular** = 3–5 · **Esporádico** = 1–2 · **Sem acompanhamento** = 0. |
| **Regularidade** | Classificação derivada dos meses com consulta: Assíduo, Irregular, Esporádico ou Sem acompanhamento. |
| **Fragmentação do Cuidado** | Mais de 50% das consultas ocorreram fora da unidade de referência — indica fragmentação do cuidado. |
| **Alto Risco + Baixo Acesso** | Score ≥7 com consultas abaixo do P25 do grupo. Principal indicador de iniquidade no cuidado. |
| **Uso Frequente de Urgência** | ≥3 atendimentos em urgência nos últimos 365 dias. Pode indicar falha no acesso à APS. |
| **ICA** | Índice Composto de Acesso (0 a 1). Combina necessidade clínica e déficit de acesso. Quanto maior, maior a prioridade de atenção. |
| **Nº de Medicamentos** | Total de medicamentos crônicos prescritos. ≥5 = polifarmácia · ≥10 = hiperpolifarmácia. |
| **Medicamentos em Uso** | Lista dos medicamentos crônicos ativos no último registro de prescrição. |
| **Polifarmácia / Hiperpolifarmácia** | ≥5 ou ≥10 medicamentos crônicos em uso simultâneo. |
| **Última Prescrição** | Data da última prescrição de medicamentos crônicos no sistema. |
            """)

        st.caption(
            f"**ICA:** peso Necessidade = {peso:.0%} | peso Acesso = {1-peso:.0%}. "
            "Ajuste os pesos pelo controle acima para priorizar conforme o contexto da equipe."
        )

        csv = df_lista[list(cols_presentes.keys())].rename(columns=cols_presentes).to_csv(
            index=False, sep=';', encoding='utf-8-sig'
        )
        st.download_button("⬇️ Baixar lista completa (.csv)", csv,
                           "lista_acesso_continuidade.csv", "text/csv")


# ──────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
# ABA 4 — FREQUÊNCIA E ABANDONO (unificada)
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("""
    ### ⏱️ Frequência de Acesso e Abandono do Cuidado

    Esta aba responde duas perguntas complementares sobre o acesso dos pacientes:

    | | Pergunta | O que mostra |
    |---|---|---|
    | **Gráfico 1** | Com que frequência cada grupo consulta por profissional? | Média de consultas por ano — médico, enfermeiro e técnico |
    | **Gráfico 2** | Quantos % estão sem consulta há mais de 6 ou 12 meses? | Proporção de abandono por profissional |

    Lidos juntos: *"este grupo fez X consultas médicas no ano... mas Y% está há mais de 6 meses sem ver um médico."*
    """)

    st.markdown("---")

    # Controles fora de qualquer bloco condicional — persistem entre reruns
    ctrl1, ctrl2 = st.columns(2)
    with ctrl1:
        estratificar_sexo = st.toggle(
            "Estratificar por sexo (Gráfico 1)", value=False, key="long_sexo"
        )
    with ctrl2:
        janela_sel = st.radio(
            "Janela de ausência (Gráfico 2)",
            options=["Mais de 6 meses (>180 dias)", "Mais de 12 meses (>365 dias)"],
            horizontal=True,
            key="g2_janela",
        )
    sufixo = "180d" if "6" in janela_sel else "365d"

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

        df_tpc['_ord'] = df_tpc['charlson_categoria'].map(
            {c: i for i, c in enumerate(ordem_cat)}
        )
        df_tpc = df_tpc.sort_values(['_ord', 'sexo'])

        # ──────────────────────────────────────────────────────
        # GRÁFICO 1 — Consultas por ano por profissional
        # ──────────────────────────────────────────────────────
        st.subheader("📊 Gráfico 1 — Consultas por Ano por Profissional")
        st.caption(
            "Média de consultas realizadas nos últimos 365 dias por tipo de profissional. "
            "Mostra o **volume de atendimento** por grupo de carga de morbidade. "
            "Pacientes de **Muito Alto risco** deveriam ter os maiores valores."
        )

        df_pan['_ord'] = df_pan['charlson_categoria'].map(
            {c: i for i, c in enumerate(ordem_cat)}
        )
        df_pan_s = df_pan.sort_values('_ord')

        fig_g1 = go.Figure()

        if estratificar_sexo:
            profissionais_g1_sx = [
                ('consultas_medicas_media',    '🩺 Médico',     '#4A86C8', '#2C5F8A'),
                ('consultas_enfermagem_media', '💉 Enfermeiro',  '#5DAD47', '#3A7A2E'),
                ('consultas_tecnico_media',    '🩹 Técnico',     '#F0A050', '#C07020'),
            ]
            for col_p, label_p, cor_f, cor_m in profissionais_g1_sx:
                for sexo, cor in [('Feminino', cor_f), ('Masculino', cor_m)]:
                    df_s = df_pan_s[df_pan_s['sexo'] == sexo]
                    if df_s.empty or col_p not in df_s.columns:
                        continue
                    fig_g1.add_trace(go.Bar(
                        name=f"{label_p} · {sexo}",
                        x=df_s['charlson_categoria'],
                        y=df_s[col_p],
                        marker_color=cor,
                        text=df_s[col_p].apply(lambda v: f"{v:.1f}"),
                        textposition='outside',
                        hovertemplate=(
                            f"<b>%{{x}} — {sexo}</b><br>"
                            f"{label_p}: %{{y:.1f}} consultas/ano<br>"
                            "<extra></extra>"
                        )
                    ))
        else:
            df_g1 = df_pan_s.groupby('charlson_categoria').agg(
                consultas_medicas_media=('consultas_medicas_media', 'mean'),
                consultas_enfermagem_media=('consultas_enfermagem_media', 'mean'),
                consultas_tecnico_media=('consultas_tecnico_media', 'mean'),
            ).reset_index()
            df_g1['_ord'] = df_g1['charlson_categoria'].map(
                {c: i for i, c in enumerate(ordem_cat)}
            )
            df_g1 = df_g1.sort_values('_ord')

            profissionais_g1 = [
                ('consultas_medicas_media',    '🩺 Médico',                '#5B9BD5'),
                ('consultas_enfermagem_media', '💉 Enfermeiro',             '#70AD47'),
                ('consultas_tecnico_media',    '🩹 Técnico de Enfermagem',  '#ED7D31'),
            ]
            for col_p, label_p, cor_p in profissionais_g1:
                if col_p not in df_g1.columns:
                    continue
                fig_g1.add_trace(go.Bar(
                    name=label_p,
                    x=df_g1['charlson_categoria'],
                    y=df_g1[col_p],
                    marker_color=cor_p,
                    text=df_g1[col_p].apply(lambda v: f"{v:.1f}"),
                    textposition='outside',
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>"
                        f"{label_p}: %{{y:.1f}} consultas/ano<br>"
                        "<extra></extra>"
                    )
                ))

        fig_g1.update_layout(
            barmode='group',
            font=dict(color=T.TEXT),
            xaxis=dict(
                title="Carga de Morbidade",
                categoryorder='array', categoryarray=ordem_cat,
                tickfont=dict(size=12),
            ),
            yaxis=dict(title="Consultas por ano (média)", gridcolor=T.GRID),
            legend=dict(
                title="Profissional",
                orientation='v', x=1.01, xanchor='left', y=0.5, yanchor='middle',
            ),
            bargap=0.25, bargroupgap=0.06,
            height=420,
            margin=dict(t=40, b=60, r=200),
            paper_bgcolor=T.PAPER_BG,
            plot_bgcolor=T.PLOT_BG,
        )
        st.plotly_chart(fig_g1, use_container_width=True)
        st.caption(
            "Barras mais **altas** = mais consultas no ano. "
            "Compare médico, enfermeiro e técnico dentro de cada grupo "
            "para entender o perfil de cuidado compartilhado."
        )

        st.markdown("---")

        # ──────────────────────────────────────────────────────
        # GRÁFICO 2 — % sem consulta por profissional
        # ──────────────────────────────────────────────────────
        st.subheader("📊 Gráfico 2 — % de Pacientes sem Consulta por Profissional")
        st.caption(
            "Proporção de pacientes de cada grupo sem consulta no período selecionado. "
            "Valores mais altos indicam abandono ou barreira de acesso. "
            "O esperado é que pacientes de **Muito Alto risco** tenham os menores percentuais."
        )

        with st.spinner("Carregando dados de ausência..."):
            df_aus = carregar_ausencia_por_profissional(
                ap=territorio['ap'],
                clinica=territorio['clinica'],
                esf=territorio['esf']
            )

        if df_aus.empty:
            st.warning("Nenhum dado encontrado.")
        else:
            df_aus['_ord'] = df_aus['charlson_categoria'].map(
                {c: i for i, c in enumerate(ordem_cat)}
            )
            df_aus = df_aus.sort_values('_ord')

            profissionais_g2 = [
                (f'pct_sem_medico_{sufixo}',     '🩺 Médico',                       '#5B9BD5'),
                (f'pct_sem_enfermagem_{sufixo}', '💉 Enfermeiro',                    '#70AD47'),
                (f'pct_sem_tecnico_{sufixo}',    '🩹 Técnico de Enfermagem',         '#ED7D31'),
                (f'pct_sem_clinico_{sufixo}',    '⚕️ Qualquer profissional clínico', '#9B59B6'),
            ]

            fig_g2 = go.Figure()
            for col_p, label_p, cor_p in profissionais_g2:
                if col_p not in df_aus.columns:
                    continue
                fig_g2.add_trace(go.Bar(
                    name=label_p,
                    x=df_aus['charlson_categoria'],
                    y=df_aus[col_p],
                    marker_color=cor_p,
                    text=df_aus[col_p].apply(
                        lambda v: f"{v:.1f}%" if pd.notna(v) else ""
                    ),
                    textposition='outside',
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>"
                        f"{label_p}: %{{y:.1f}}%<br>"
                        "<extra></extra>"
                    )
                ))

            janela_txt = "mais de 6 meses" if "6" in janela_sel else "mais de 12 meses"
            fig_g2.update_layout(
                barmode='group',
                font=dict(color=T.TEXT),
                xaxis=dict(
                    title="Carga de Morbidade",
                    categoryorder='array', categoryarray=ordem_cat,
                    tickfont=dict(size=12),
                ),
                yaxis=dict(
                    title=f"% sem consulta há {janela_txt}",
                    ticksuffix='%', range=[0, 100], gridcolor=T.GRID,
                ),
                legend=dict(
                    title="Profissional",
                    orientation='v', x=1.01, xanchor='left', y=0.5, yanchor='middle',
                ),
                bargap=0.25, bargroupgap=0.06,
                height=440,
                margin=dict(t=40, b=60, r=220),
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
            )
            st.plotly_chart(fig_g2, use_container_width=True)
            st.caption(
                "**Qualquer profissional clínico** = paciente sem consulta com médico, "
                "enfermeiro **e** técnico de enfermagem no período. "
                "Barras mais **baixas** = melhor acesso."
            )

# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ | Navegador Clínico | Acesso e Continuidade do Cuidado")