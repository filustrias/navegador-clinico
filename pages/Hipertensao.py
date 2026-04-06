"""
Page: Hipertensão Arterial Sistêmica
Prevalência, controle pressórico, tendência, comorbidades, lacunas e lista nominal.
"""
import re
import numpy as np
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from streamlit_option_menu import option_menu
from utils.bigquery_client import get_bigquery_client
from utils.data_loader import carregar_opcoes_filtros
from utils.anonimizador import (
    anonimizar_nome, anonimizar_ap, anonimizar_clinica,
    anonimizar_esf, mostrar_badge_anonimo, MODO_ANONIMO
)
import config
from utils import theme as T

st.set_page_config(
    page_title="Hipertensão · Navegador Clínico",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']
if isinstance(usuario_logado, dict):
    nome    = usuario_logado.get('nome_completo', 'Usuário')
    esf     = usuario_logado.get('esf')     or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap      = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

ctx = {
    'ap':      None if ap      == 'N/A' else ap,
    'clinica': None if clinica == 'N/A' else clinica,
    'esf':     None if esf     == 'N/A' else esf,
}

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"""
    <h1 style='margin: 0; padding: 0; color: {T.TEXT};'>
        🏥 Navegador Clínico <small style='color: {T.TEXT_MUTED}; font-size: 0.5em;'>SMS-RJ</small>
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

PAGINA_ATUAL = "Hipertensão"
ROTAS = {
    "Home":          "Home.py",
    "População":     "pages/Minha_Populacao.py",
    "Pacientes":     "pages/Meus_Pacientes.py",
    "Lacunas":       "pages/Lacunas_de_Cuidado.py",
    "Continuidade":  "pages/Acesso_Continuidade.py",
    "Polifarmácia":  "pages/Polifarmacia_ACB.py",
    "Diabetes":      "pages/Diabetes.py",
    "Hipertensão":   "pages/Hipertensao.py",
}
ICONES = [
    "house-fill", "people-fill", "person-lines-fill",
    "exclamation-triangle-fill", "arrow-repeat", "capsule",
    "droplet-fill", "heart-pulse-fill",
]
selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container":         {"padding": "0!important", "background-color": T.NAV_BG},
        "icon":              {"font-size": "22px", "color": T.TEXT, "display": "block", "margin-bottom": "4px"},
        "nav-link":          {"font-size": "11px", "text-align": "center", "margin": "0px",
                              "padding": "10px 18px", "color": T.NAV_LINK, "background-color": T.SECONDARY_BG,
                              "--hover-color": T.NAV_HOVER, "display": "flex", "flex-direction": "column",
                              "align-items": "center", "line-height": "1.2", "white-space": "nowrap"},
        "nav-link-selected": {"background-color": T.NAV_SELECTED_BG, "color": T.NAV_SELECTED_TEXT, "font-weight": "600"},
    }
)
if selected != PAGINA_ATUAL:
    st.switch_page(ROTAS[selected])

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name): return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"
def _p(n, d):   return round(n / d * 100, 1) if d else 0.0

@st.cache_data(show_spinner=False, ttl=900)
def bq(sql):
    try:
        client = get_bigquery_client()
        return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro na query: {e}")
        return pd.DataFrame()

# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=900)
def carregar_sumario_has(ap, clinica, esf):
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        COUNT(*) AS total_pop,

        -- Diagnóstico
        COUNTIF(HAS IS NOT NULL)                                         AS n_HAS,
        COUNTIF(has_por_cid IS NOT NULL)                                 AS n_HAS_por_cid,
        COUNTIF(has_por_medida_critica IS NOT NULL)                      AS n_HAS_medida_critica,
        COUNTIF(has_por_medidas_repetidas IS NOT NULL)                   AS n_HAS_medidas_repetidas,
        COUNTIF(has_por_medicamento IS NOT NULL)                         AS n_HAS_medicamento,
        COUNTIF(HAS_sem_CID = TRUE)                                      AS n_HAS_sem_cid,

        -- Controle pressórico
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')    AS n_HAS_controlado,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado') AS n_HAS_nao_controlado,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL)           AS n_HAS_sem_info,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pct_dias_has_controlado_365d END), 1) AS media_pct_has_ctrl,

        -- Por faixa etária
        COUNTIF(HAS IS NOT NULL AND idade < 80)                          AS n_HAS_menor80,
        COUNTIF(HAS IS NOT NULL AND idade < 80
                AND status_controle_pressorio = 'controlado')            AS n_HAS_ctrl_menor80,
        COUNTIF(HAS IS NOT NULL AND idade >= 80)                         AS n_HAS_80mais,
        COUNTIF(HAS IS NOT NULL AND idade >= 80
                AND status_controle_pressorio = 'controlado')            AS n_HAS_ctrl_80mais,

        -- Tendência
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')         AS n_HAS_melhorando,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')            AS n_HAS_estavel,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')           AS n_HAS_piorando,

        -- Comorbidades em hipertensos
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL)                      AS n_has_dm,
        COUNTIF(HAS IS NOT NULL AND IRC IS NOT NULL)                     AS n_has_irc,
        COUNTIF(HAS IS NOT NULL AND CI IS NOT NULL)                      AS n_has_ci,
        COUNTIF(HAS IS NOT NULL AND ICC IS NOT NULL)                     AS n_has_icc,
        COUNTIF(HAS IS NOT NULL AND stroke IS NOT NULL)                  AS n_has_avc,
        -- Pares
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL AND IRC IS NOT NULL)  AS n_has_dm_irc,
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL AND CI IS NOT NULL)   AS n_has_dm_ci,
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL AND ICC IS NOT NULL)  AS n_has_dm_icc,
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL AND stroke IS NOT NULL) AS n_has_dm_avc,
        COUNTIF(HAS IS NOT NULL AND IRC IS NOT NULL AND CI IS NOT NULL)  AS n_has_irc_ci,
        COUNTIF(HAS IS NOT NULL AND IRC IS NOT NULL AND ICC IS NOT NULL) AS n_has_irc_icc,
        COUNTIF(HAS IS NOT NULL AND IRC IS NOT NULL AND stroke IS NOT NULL) AS n_has_irc_avc,
        COUNTIF(HAS IS NOT NULL AND CI IS NOT NULL AND ICC IS NOT NULL)  AS n_has_ci_icc,
        COUNTIF(HAS IS NOT NULL AND CI IS NOT NULL AND stroke IS NOT NULL) AS n_has_ci_avc,
        COUNTIF(HAS IS NOT NULL AND ICC IS NOT NULL AND stroke IS NOT NULL) AS n_has_icc_avc,
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL AND IRC IS NOT NULL
                AND CI IS NOT NULL AND ICC IS NOT NULL AND stroke IS NOT NULL) AS n_has_todas5,

        -- Lacunas
        COUNTIF(lacuna_rastreio_PA_adulto = TRUE)                        AS n_lac_rastreio_pa,
        COUNTIF(lacuna_PA_hipertenso_180d = TRUE)                        AS n_lac_has_sem_pa_180d,
        COUNTIF(lacuna_HAS_descontrolado_menor80 = TRUE)                 AS n_lac_has_nao_ctrl_menor80,
        COUNTIF(lacuna_HAS_descontrolado_80mais = TRUE)                  AS n_lac_has_nao_ctrl_80mais,
        COUNTIF(lacuna_DM_HAS_PA_descontrolada = TRUE)                   AS n_lac_dm_has_pa,
        COUNTIF(HAS IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)     AS n_lac_has_creatinina,
        COUNTIF(HAS IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)     AS n_lac_has_colesterol,
        COUNTIF(HAS IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)            AS n_lac_has_eas,
        COUNTIF(HAS IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)            AS n_lac_has_ecg,
        COUNTIF(HAS IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)            AS n_lac_has_imc,
        -- Risco cardiovascular
        COUNTIF(HAS IS NOT NULL AND categoria_risco_final = 'MUITO ALTO') AS n_risco_muito_alto,
        COUNTIF(HAS IS NOT NULL AND categoria_risco_final = 'ALTO')       AS n_risco_alto,
        COUNTIF(HAS IS NOT NULL AND categoria_risco_final = 'INTERMEDIÁRIO') AS n_risco_intermediario,
        COUNTIF(HAS IS NOT NULL AND categoria_risco_final = 'BAIXO')      AS n_risco_baixo

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_resumo_pa(ap, clinica, esf):
    clauses = ["HAS IS NOT NULL"]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where_fato = "WHERE " + " AND ".join(clauses)
    sql = f"""
    WITH
    cpfs_territorio AS (
        SELECT cpf, categoria_risco_final, idade
        FROM `{_fqn(config.TABELA_FATO)}`
        {where_fato}
    ),
    mais_recente AS (
        SELECT p.cpf, ct.idade, ct.categoria_risco_final,
               p.tem_has, p.tem_dm, p.tem_ci, p.tem_icc,
               p.tem_stroke, p.tem_irc, p.tem_has_alto_risco,
               p.meta_pas, p.meta_pad, p.pas, p.pad,
               p.data_afericao, p.dias_desde_afericao,
               p.recencia, p.controle_pa, p.tendencia_pas,
               p.classificacao_pa, p.pa_elevada_sem_has
        FROM `rj-sms-sandbox.sub_pav_us.MM_pressao_arterial_historico` p
        INNER JOIN cpfs_territorio ct ON p.cpf = ct.cpf
        QUALIFY ROW_NUMBER() OVER (PARTITION BY p.cpf ORDER BY p.data_afericao DESC) = 1
    )
    SELECT
        COUNT(*)                                                     AS n_has,
        COUNTIF(dias_desde_afericao <= 90)                           AS n_afericao_90d,
        COUNTIF(dias_desde_afericao BETWEEN 91 AND 180)              AS n_afericao_91_180d,
        COUNTIF(dias_desde_afericao BETWEEN 181 AND 365)             AS n_afericao_181_365d,
        COUNTIF(dias_desde_afericao > 365)                           AS n_afericao_mais_365d,
        COUNTIF(controle_pa = 'controlado')                          AS n_ctrl,
        COUNTIF(controle_pa = 'nao_controlado')                      AS n_nao_ctrl,
        COUNTIF(idade < 80)                                          AS n_menor80,
        COUNTIF(idade < 80 AND controle_pa = 'controlado')           AS n_ctrl_menor80,
        COUNTIF(idade < 80 AND controle_pa = 'nao_controlado')       AS n_nctrl_menor80,
        COUNTIF(idade >= 80)                                         AS n_80mais,
        COUNTIF(idade >= 80 AND controle_pa = 'controlado')          AS n_ctrl_80mais,
        COUNTIF(idade >= 80 AND controle_pa = 'nao_controlado')      AS n_nctrl_80mais,
        COUNTIF(tendencia_pas = 'melhorando')                        AS n_mel,
        COUNTIF(tendencia_pas = 'piorando')                          AS n_pio,
        COUNTIF(tendencia_pas IN ('controlado_estavel', 'estavel'))  AS n_est,
        COUNTIF(tendencia_pas = 'sem_referencia')                    AS n_sem_ref,
        COUNTIF(classificacao_pa = 'Normal')                         AS n_pa_normal,
        COUNTIF(classificacao_pa = 'Elevada')                        AS n_pa_elevada,
        COUNTIF(classificacao_pa = 'HAS Grau 1')                     AS n_has_grau1,
        COUNTIF(classificacao_pa = 'HAS Grau 2')                     AS n_has_grau2,
        COUNTIF(classificacao_pa = 'HAS Grau 3 / Crise')             AS n_has_grau3,
        ROUND(AVG(pas), 1)                                           AS media_pas,
        ROUND(AVG(pad), 1)                                           AS media_pad
    FROM mais_recente
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_territorio_has(ap, clinica, esf):
    if clinica:  grupo_col, label_col = "nome_esf_cadastro", "ESF"
    elif ap:     grupo_col, label_col = "nome_clinica_cadastro", "Clínica"
    else:        grupo_col, label_col = "area_programatica_cadastro", "AP"
    clauses = [f"{grupo_col} IS NOT NULL"]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = "WHERE " + " AND ".join(clauses)
    sql = f"""
    SELECT
        {grupo_col} AS territorio,
        COUNT(*) AS total_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)  AS pct_has_ctrl,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)  AS pct_has_nao_ctrl,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)  AS pct_has_mel,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)  AS pct_has_pio,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')
              * 100.0 / COUNT(*), 1)                             AS pct_has_ctrl_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado')
              * 100.0 / COUNT(*), 1)                             AS pct_has_nao_ctrl_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL)
              * 100.0 / COUNT(*), 1)                             AS pct_has_seminfo_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')
              * 100.0 / COUNT(*), 1)                             AS pct_has_mel_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')
              * 100.0 / COUNT(*), 1)                             AS pct_has_est_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')
              * 100.0 / COUNT(*), 1)                             AS pct_has_pio_pop
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY {grupo_col}
    ORDER BY {grupo_col}
    """
    df = bq(sql)
    df['label_col'] = label_col
    return df


@st.cache_data(show_spinner=False, ttl=900)
def carregar_pacientes_has(ap, clinica, esf, limite=500,
                           filtro_carga=None, sem_pa_recente=False):
    """Lista nominal — filtros de carga e sem_pa_recente vão para o SQL."""
    clauses = ["HAS IS NOT NULL"]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if filtro_carga:
        cats = ", ".join(f"'{c}'" for c in filtro_carga)
        clauses.append(f"charlson_categoria IN ({cats})")
    if sem_pa_recente:
        clauses.append("(dias_desde_ultima_pa > 180 OR dias_desde_ultima_pa IS NULL)")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        cpf,
        genero,
        nome,
        idade,
        area_programatica_cadastro  AS ap,
        nome_clinica_cadastro       AS clinica,
        nome_esf_cadastro           AS esf,
        charlson_categoria          AS carga_morbidade,
        charlson_score,
        total_morbidades,
        pressao_sistolica,
        pressao_diastolica,
        data_ultima_pa,
        dias_desde_ultima_pa,
        status_controle_pressorio,
        tendencia_pa,
        meta_pas,
        dias_desde_ultima_medica,
        consultas_medicas_365d,
        meses_com_consulta_12m,
        categoria_risco_final       AS risco_cv,

        CASE WHEN HAS_sem_CID = TRUE THEN '⚠️ Sem CID' ELSE '✅ Com CID' END AS cid_status,

        -- Morbidades presentes
        ARRAY_TO_STRING(ARRAY(SELECT m FROM UNNEST([
            IF(DM IS NOT NULL,               'DM',                  NULL),
            IF(CI IS NOT NULL,               'CI',                  NULL),
            IF(ICC IS NOT NULL,              'ICC',                 NULL),
            IF(IRC IS NOT NULL,              'IRC',                 NULL),
            IF(stroke IS NOT NULL,           'AVC',                 NULL),
            IF(COPD IS NOT NULL,             'DPOC',                NULL),
            IF(asthma IS NOT NULL,           'Asma',                NULL),
            IF(dementia IS NOT NULL,         'Demência',            NULL),
            IF(depre_ansiedade IS NOT NULL,  'Depressão/Ansiedade', NULL),
            IF(obesidade IS NOT NULL OR obesidade_por_IMC = TRUE, 'Obesidade', NULL),
            IF(dislipidemia IS NOT NULL,     'Dislipidemia',        NULL),
            IF(tabaco IS NOT NULL,           'Tabagismo',           NULL),
            IF(alcool IS NOT NULL,           'Álcool',              NULL),
            IF(tireoide IS NOT NULL,         'Tireoide',            NULL),
            IF(reumato IS NOT NULL,          'Reumatológica',       NULL),
            IF(metastasis IS NOT NULL,       'Metástase',           NULL),
            IF(neoplasia_mama IS NOT NULL
               OR neoplasia_colo_uterino IS NOT NULL
               OR neoplasia_ambos_os_sexos IS NOT NULL
               OR neoplasia_feminina_estrita IS NOT NULL
               OR neoplasia_masculina_estrita IS NOT NULL, 'Neoplasia', NULL)
        ]) AS m WHERE m IS NOT NULL), ', ') AS morbidades_lista,

        -- Lacunas ativas
        ARRAY_TO_STRING(ARRAY(SELECT l FROM UNNEST([
            IF(lacuna_PA_hipertenso_180d = TRUE,            'Sem aferição de PA (>180d)',  NULL),
            IF(lacuna_HAS_descontrolado_menor80 = TRUE,     'PA não controlada (<80a)',    NULL),
            IF(lacuna_HAS_descontrolado_80mais = TRUE,      'PA não controlada (≥80a)',    NULL),
            IF(lacuna_DM_HAS_PA_descontrolada = TRUE,       'DM+HAS com PA >135/80',       NULL),
            IF(lacuna_creatinina_HAS_DM = TRUE,             'Sem creatinina',              NULL),
            IF(lacuna_colesterol_HAS_DM = TRUE,             'Sem colesterol',              NULL),
            IF(lacuna_eas_HAS_DM = TRUE,                    'Sem EAS',                     NULL),
            IF(lacuna_ecg_HAS_DM = TRUE,                    'Sem ECG',                     NULL),
            IF(lacuna_IMC_HAS_DM = TRUE,                    'Sem IMC',                     NULL),
            IF(lacuna_CI_sem_AAS = TRUE,                    'CI sem AAS',                  NULL),
            IF(lacuna_CI_sem_estatina_qualquer = TRUE,      'CI sem estatina',             NULL),
            IF(lacuna_ICC_sem_IECA_BRA = TRUE,              'ICC sem IECA/BRA',            NULL),
            IF(lacuna_ICC_sem_SGLT2 = TRUE,                 'ICC sem SGLT-2',              NULL)
        ]) AS l WHERE l IS NOT NULL), ' · ') AS lacunas_ativas,

        (IF(lacuna_PA_hipertenso_180d = TRUE, 1, 0)
         + IF(lacuna_HAS_descontrolado_menor80 = TRUE, 1, 0)
         + IF(lacuna_HAS_descontrolado_80mais = TRUE, 1, 0)
         + IF(lacuna_creatinina_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_colesterol_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_eas_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_ecg_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_IMC_HAS_DM = TRUE, 1, 0)) AS n_lacunas,

        total_medicamentos_cronicos,
        COALESCE(nucleo_cronico_atual, '—') AS medicamentos

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    LIMIT {limite}
    """
    return bq(sql)


def _ordenar_has(df: pd.DataFrame, ordem: str) -> pd.DataFrame:
    if df.empty: return df
    CONFIG = {
        'charlson_desc':   ('charlson_score',           False, 'last'),
        'morbidades_desc': ('total_morbidades',         False, 'last'),
        'idade_desc':      ('idade',                    False, 'last'),
        'sem_medico':      ('dias_desde_ultima_medica', False, 'first'),
        'pa_desc':         ('pressao_sistolica',        False, 'last'),
    }
    if ordem not in CONFIG: return df
    col, asc, na_pos = CONFIG[ordem]
    if col not in df.columns: return df
    return df.sort_values(col, ascending=asc, na_position=na_pos)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — FILTROS
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo()
st.sidebar.title("Filtros")

_opcoes = carregar_opcoes_filtros()
_areas  = _opcoes.get('areas', [])

def _has_reset_cli_esf():
    st.session_state['has_cli'] = None
    st.session_state['has_esf'] = None

def _has_reset_esf():
    st.session_state['has_esf'] = None

if 'has_ap'  not in st.session_state: st.session_state['has_ap']  = ctx.get('ap')
if 'has_cli' not in st.session_state: st.session_state['has_cli'] = ctx.get('clinica')
if 'has_esf' not in st.session_state: st.session_state['has_esf'] = ctx.get('esf')

ap_sel = st.sidebar.selectbox(
    "Área Programática",
    options=[None] + _areas,
    format_func=lambda x: "Todas" if x is None else anonimizar_ap(str(x)),
    key="has_ap", on_change=_has_reset_cli_esf,
)
_clinicas = sorted(_opcoes['clinicas'].get(ap_sel, [])) if ap_sel else []
if st.session_state.get('has_cli') not in _clinicas:
    st.session_state['has_cli'] = None

cli_sel = st.sidebar.selectbox(
    "Clínica da Família",
    options=[None] + _clinicas,
    format_func=lambda x: "Todas" if x is None else anonimizar_clinica(x),
    key="has_cli", disabled=not ap_sel, on_change=_has_reset_esf,
)
_esfs = sorted(_opcoes['esf'].get(cli_sel, [])) if cli_sel else []
if st.session_state.get('has_esf') not in _esfs:
    st.session_state['has_esf'] = None

esf_sel = st.sidebar.selectbox(
    "Equipe ESF",
    options=[None] + _esfs,
    format_func=lambda x: "Todas" if x is None else anonimizar_esf(x),
    key="has_esf", disabled=not cli_sel,
)

# Navegação sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
NOMES_ABAS = [
    "1️⃣ Diagnóstico e Prevalência",
    "2️⃣ Controle Pressórico",
    "3️⃣ Comorbidades",
    "4️⃣ Lacunas de Cuidado",
    "👤 Lista de Pacientes",
]
if 'has_aba' not in st.session_state:
    st.session_state['has_aba'] = 0
aba_sel = st.sidebar.radio(
    "", options=range(len(NOMES_ABAS)),
    format_func=lambda i: NOMES_ABAS[i],
    index=st.session_state['has_aba'],
    key="has_nav", label_visibility="collapsed",
)
st.session_state['has_aba'] = aba_sel

# ═══════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
with st.spinner("Carregando dados de hipertensão..."):
    sumario  = carregar_sumario_has(ap_sel, cli_sel, esf_sel)
    rpa      = carregar_resumo_pa(ap_sel, cli_sel, esf_sel)
    df_terr  = carregar_territorio_has(ap_sel, cli_sel, esf_sel)

if not sumario:
    st.error("❌ Não foi possível carregar os dados.")
    st.stop()

n_has = int(sumario.get('n_HAS', 0) or 1)
tot   = int(sumario.get('total_pop', 0) or 1)
lbl   = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'

# ═══════════════════════════════════════════════════════════════
# TÍTULO E MÉTRICAS TOPO
# ═══════════════════════════════════════════════════════════════
st.title("🩺 Hipertensão Arterial Sistêmica")
st.markdown("Panorama da HAS no território — do diagnóstico ao controle pressórico.")
st.caption("Fonte: tabela fato — dados individuais agregados por território.")
st.markdown("---")

n_ctrl   = int(rpa.get('n_ctrl', 0) or 0)
n_nctrl  = int(rpa.get('n_nao_ctrl', 0) or 0)
media_pas = rpa.get('media_pas') or 0
media_pad = rpa.get('media_pad') or 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("🩺 Hipertensos", f"{n_has:,}", f"{_p(n_has, tot):.1f}% da população")
m2.metric("✅ Controlados (PA recente)", f"{n_ctrl:,}",
          f"{_p(n_ctrl, n_has):.1f}% dos hipertensos")
m3.metric("⚠️ Não controlados", f"{n_nctrl:,}",
          f"{_p(n_nctrl, n_has):.1f}% dos hipertensos", delta_color="inverse")
m4.metric("📊 PA média (última aferição)",
          f"{media_pas:.0f}/{media_pad:.0f} mmHg" if media_pas else "—")
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# HELPER DE GRÁFICO
# ═══════════════════════════════════════════════════════════════
def _stacked_bar(df, cols_pop, labels, cores, titulo):
    if df is None or df.empty:
        st.info("Sem dados por território.")
        return
    def _ord(v):
        m = re.search(r"(\d+\.?\d*)", str(v))
        return float(m.group(1)) if m else 999
    df_s = df.copy()
    df_s['_ord'] = df_s['territorio'].apply(_ord)
    df_s = df_s.sort_values('_ord')
    terrs = [str(t) for t in df_s['territorio'].tolist()]
    fig = go.Figure()
    for col, label, cor in zip(cols_pop, labels, cores):
        vals = df_s[col].tolist() if col in df_s.columns else [0]*len(terrs)
        fig.add_trace(go.Bar(
            name=label, x=terrs, y=vals,
            marker_color=cor,
            text=[f"{v:.1f}%" for v in vals],
            textposition='inside',
            textfont=dict(size=9, color='white'),
        ))
    fig.update_layout(
        barmode='stack', height=320, bargap=0.35,
        margin=dict(l=10, r=160, t=50, b=60 if len(terrs)<=12 else 130),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        title=dict(text=titulo, font=dict(color=T.TEXT, size=13)),
        xaxis=dict(type='category', categoryorder='array', categoryarray=terrs,
                   tickfont=dict(color=T.TEXT, size=11 if len(terrs)<=12 else 9),
                   tickangle=0 if len(terrs)<=12 else -40),
        yaxis=dict(title='% da população total', tickfont=dict(color=T.TEXT_MUTED, size=10),
                   gridcolor=T.GRID, range=[0, 50]),
        legend=dict(orientation='v', xanchor='left', x=1.01, yanchor='middle', y=0.5,
                    font=dict(color=T.TEXT, size=11),
                    bgcolor=T.LEGEND_BG, bordercolor=T.LEGEND_BORDER, borderwidth=1),
    )
    st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs(NOMES_ABAS)


# ──────────────────────────────────────────────────────────────
# ABA 1 — DIAGNÓSTICO E PREVALÊNCIA
# ──────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### 1️⃣ Prevalência e como foram identificados")

    n_sem_cid = int(sumario.get('n_HAS_sem_cid', 0) or 0)
    pct_sem_cid = _p(n_sem_cid, n_has)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.metric("🩺 Hipertensos identificados", f"{n_has:,}",
                      f"{_p(n_has, tot):.1f}% da população",
                      help="Total identificados por qualquer critério.")
    with col2:
        with st.container(border=True):
            st.metric("📋 Por CID registrado", f"{sumario.get('n_HAS_por_cid', 0):,}",
                      f"{_p(sumario.get('n_HAS_por_cid', 0), n_has):.1f}% dos hipertensos",
                      help="CID I10–I16, O10–O11.")
    with col3:
        with st.container(border=True):
            st.metric("📏 Por medidas repetidas", f"{sumario.get('n_HAS_medidas_repetidas', 0):,}",
                      f"{_p(sumario.get('n_HAS_medidas_repetidas', 0), n_has):.1f}% dos hipertensos",
                      help="Duas ou mais medidas ≥140/90 mmHg em datas distintas.")
    with col4:
        with st.container(border=True):
            st.metric("⚠️ Sem CID registrado", f"{n_sem_cid:,}",
                      f"{pct_sem_cid:.1f}% dos hipertensos",
                      delta_color="inverse",
                      help="Identificados por medidas ou medicamento sem CID.")

    if pct_sem_cid > 20:
        st.warning(
            f"⚠️ **Alerta de subnotificação:** {pct_sem_cid:.1f}% dos hipertensos ({n_sem_cid:,}) "
            "não têm CID registrado. Subnotificação compromete a qualidade do cuidado prestado."
        )

    st.markdown("##### Como estes pacientes foram identificados")
    st.caption("Um mesmo paciente pode ser identificado por mais de um critério.")

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("**📏 Por medida crítica (≥180/110 mmHg)**")
            st.metric("Pacientes", f"{sumario.get('n_HAS_medida_critica', 0):,}",
                      f"{_p(sumario.get('n_HAS_medida_critica', 0), n_has):.1f}% dos hipertensos")
            st.caption("Uma única medida ≥180/110 mmHg é suficiente para diagnóstico.")
    with c2:
        with st.container(border=True):
            st.markdown("**📏 Por medidas repetidas (≥140/90 mmHg)**")
            st.metric("Pacientes", f"{sumario.get('n_HAS_medidas_repetidas', 0):,}",
                      f"{_p(sumario.get('n_HAS_medidas_repetidas', 0), n_has):.1f}% dos hipertensos")
            st.caption("Duas ou mais aferições elevadas em ocasiões distintas.")
    with c3:
        with st.container(border=True):
            st.markdown("**💊 Por uso de anti-hipertensivo**")
            st.metric("Pacientes", f"{sumario.get('n_HAS_medicamento', 0):,}",
                      f"{_p(sumario.get('n_HAS_medicamento', 0), n_has):.1f}% dos hipertensos")
            st.caption("Prescrição de anti-hipertensivo sem CID registrado — diagnóstico implícito.")


# ──────────────────────────────────────────────────────────────
# ABA 2 — CONTROLE PRESSÓRICO
# ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 2️⃣ Controle pressórico — situação atual")
    st.caption("Última aferição registrada por paciente hipertenso.")

    n_afericao_90d     = int(rpa.get('n_afericao_90d', 0) or 0)
    n_afericao_180d    = int(rpa.get('n_afericao_91_180d', 0) or 0)
    n_afericao_365d    = int(rpa.get('n_afericao_181_365d', 0) or 0)
    n_afericao_mais365 = int(rpa.get('n_afericao_mais_365d', 0) or 0)
    n_ctrl_menor80     = int(rpa.get('n_ctrl_menor80', 0) or 0)
    n_nctrl_menor80    = int(rpa.get('n_nctrl_menor80', 0) or 0)
    n_menor80          = int(rpa.get('n_menor80', 0) or 0)
    n_ctrl_80mais      = int(rpa.get('n_ctrl_80mais', 0) or 0)
    n_nctrl_80mais     = int(rpa.get('n_nctrl_80mais', 0) or 0)
    n_80mais           = int(rpa.get('n_80mais', 0) or 0)

    st.markdown("**🗓️ Recência da última aferição de PA**")
    rc1, rc2, rc3, rc4 = st.columns(4)
    for col, emoji, label, n, caption in [
        (rc1, "🟢", "PA ≤ 90 dias",         n_afericao_90d,     "Aferição recente — monitoramento adequado."),
        (rc2, "🟡", "PA 91–180 dias",        n_afericao_180d,    "Aferição aceitável — dentro do semestre."),
        (rc3, "🟠", "PA 181–365 dias",       n_afericao_365d,    "Aferição desatualizada — agendar consulta."),
        (rc4, "🔴", "PA há mais de 365 dias", n_afericao_mais365, "Sem aferição no último ano — prioridade de busca ativa."),
    ]:
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{label}**")
                st.markdown(f"## {_p(n, n_has):.1f}%")
                st.metric("Hipertensos", f"{n:,}")
                st.caption(caption)

    st.markdown("---")
    st.markdown("**🎯 Controle por faixa etária**")
    st.caption("Meta: <140/90 mmHg para menores de 80 anos · <150/90 mmHg para 80 anos ou mais.")

    fa1, fa2 = st.columns(2)
    with fa1:
        with st.container(border=True):
            st.markdown("**🧑 Menores de 80 anos** — meta <140/90 mmHg")
            st.markdown(f"## {_p(n_ctrl_menor80, n_menor80):.1f}% controlados")
            c1a, c1b = st.columns(2)
            c1a.metric("✅ Controlados", f"{n_ctrl_menor80:,}")
            c1b.metric("⚠️ Não controlados", f"{n_nctrl_menor80:,}", delta_color="inverse")
    with fa2:
        with st.container(border=True):
            st.markdown("**👴 80 anos ou mais** — meta <150/90 mmHg")
            st.markdown(f"## {_p(n_ctrl_80mais, n_80mais):.1f}% controlados")
            c2a, c2b = st.columns(2)
            c2a.metric("✅ Controlados", f"{n_ctrl_80mais:,}")
            c2b.metric("⚠️ Não controlados", f"{n_nctrl_80mais:,}", delta_color="inverse")

    _stacked_bar(df_terr,
        cols_pop=['pct_has_ctrl_pop', 'pct_has_nao_ctrl_pop', 'pct_has_seminfo_pop'],
        labels=['Controlados', 'Não controlados', 'Sem informação'],
        cores=['#2ECC71', '#E74C3C', '#777777'],
        titulo=f'Controle pressórico por {lbl} — altura = % HAS na população',
    )

    st.markdown("---")
    st.markdown("#### Tendência pressórica")
    st.caption("Comparação entre a última e a penúltima aferição de PA.")

    n_mel = int(rpa.get('n_mel', 0) or 0)
    n_pio = int(rpa.get('n_pio', 0) or 0)
    n_est = int(rpa.get('n_est', 0) or 0)
    n_sem_ref = int(rpa.get('n_sem_ref', 0) or 0)

    td1, td2, td3, td4 = st.columns(4)
    td1.metric("📈 Melhorando", f"{n_mel:,}", f"{_p(n_mel, n_has):.1f}%",
               help="PAS caiu ≥5 mmHg em relação à aferição anterior.")
    td2.metric("➡️ Estável",    f"{n_est:,}", f"{_p(n_est, n_has):.1f}%", delta_color="off")
    td3.metric("📉 Piorando",   f"{n_pio:,}", f"{_p(n_pio, n_has):.1f}%", delta_color="inverse",
               help="PAS subiu ≥5 mmHg em relação à aferição anterior.")
    td4.metric("❓ Sem aferição anterior", f"{n_sem_ref:,}", f"{_p(n_sem_ref, n_has):.1f}%",
               delta_color="off")

    _stacked_bar(df_terr,
        cols_pop=['pct_has_mel_pop', 'pct_has_est_pop', 'pct_has_pio_pop'],
        labels=['Melhorando', 'Estável', 'Piorando'],
        cores=['#2ECC71', '#F4D03F', '#E74C3C'],
        titulo=f'Tendência pressórica por {lbl} — altura = % HAS na população',
    )

    st.markdown("---")
    st.markdown("#### Classificação da PA")
    st.caption("Baseada na última aferição registrada.")

    cl1, cl2, cl3, cl4, cl5 = st.columns(5)
    for col, label, chave, cor in [
        (cl1, "Normal",             'n_pa_normal',   '🟢'),
        (cl2, "Elevada",            'n_pa_elevada',  '🟡'),
        (cl3, "HAS Grau 1",         'n_has_grau1',   '🟠'),
        (cl4, "HAS Grau 2",         'n_has_grau2',   '🔴'),
        (cl5, "HAS Grau 3 / Crise", 'n_has_grau3',   '🚨'),
    ]:
        with col:
            with st.container(border=True):
                n_v = int(rpa.get(chave, 0) or 0)
                st.markdown(f"{cor} **{label}**")
                st.markdown(f"## {n_v:,}")
                st.caption(f"{_p(n_v, n_has):.1f}% dos hipertensos")

    # Risco cardiovascular
    st.markdown("---")
    st.markdown("#### Risco Cardiovascular (Framingham + SBC)")
    rc_cols = st.columns(4)
    for col, label, chave, emoji in [
        (rc_cols[0], "Muito Alto", 'n_risco_muito_alto',    '🔴'),
        (rc_cols[1], "Alto",       'n_risco_alto',          '🟠'),
        (rc_cols[2], "Intermediário", 'n_risco_intermediario', '🟡'),
        (rc_cols[3], "Baixo",      'n_risco_baixo',         '🟢'),
    ]:
        with col:
            with st.container(border=True):
                n_v = int(sumario.get(chave, 0) or 0)
                st.markdown(f"{emoji} **{label}**")
                st.markdown(f"## {n_v:,}")
                st.caption(f"{_p(n_v, n_has):.1f}% dos hipertensos")


# ──────────────────────────────────────────────────────────────
# ABA 3 — COMORBIDADES
# ──────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 3️⃣ Comorbidades associadas à HAS")
    st.caption("Sobreposição entre hipertensão e comorbidades cardiovasculares e metabólicas.")

    n_has_dm  = int(sumario.get('n_has_dm',  0) or 0)
    n_has_irc = int(sumario.get('n_has_irc', 0) or 0)
    n_has_ci  = int(sumario.get('n_has_ci',  0) or 0)
    n_has_icc = int(sumario.get('n_has_icc', 0) or 0)
    n_has_avc = int(sumario.get('n_has_avc', 0) or 0)

    dmc1, dmc2, dmc3, dmc4, dmc5 = st.columns(5)
    for col, val, label, emoji, cor, ajuda in [
        (dmc1, n_has_dm,  'DM',  '🍬', '#F39C12', 'HAS+DM: meta PA <130/80 mmHg. IECA/BRA como 1ª linha.'),
        (dmc2, n_has_irc, 'IRC', '🫘', '#9B59B6', 'HAS+IRC: IECA/BRA + SGLT-2 para nefroproteção.'),
        (dmc3, n_has_ci,  'CI',  '💔', '#E74C3C', 'HAS+CI: estatina alta intensidade + AAS.'),
        (dmc4, n_has_icc, 'ICC', '🫀', '#E67E22', 'HAS+ICC: IECA/BRA/INRA + BB + ARM + SGLT-2.'),
        (dmc5, n_has_avc, 'AVC', '🧠', '#1ABC9C', 'HAS+AVC: controle rigoroso da PA reduz reincidência.'),
    ]:
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{label}**")
                st.markdown(f"## {val:,}")
                st.caption(f"{_p(val, n_has):.1f}% dos hipertensos")
                st.caption(ajuda)

    # Heatmap
    grupos   = ['DM', 'IRC', 'CI', 'ICC', 'AVC']
    totais   = [n_has_dm, n_has_irc, n_has_ci, n_has_icc, n_has_avc]
    cores_g  = ['#F39C12', '#9B59B6', '#E74C3C', '#E67E22', '#1ABC9C']
    pares    = {
        ('DM', 'IRC'): int(sumario.get('n_has_dm_irc', 0) or 0),
        ('DM', 'CI'):  int(sumario.get('n_has_dm_ci',  0) or 0),
        ('DM', 'ICC'): int(sumario.get('n_has_dm_icc', 0) or 0),
        ('DM', 'AVC'): int(sumario.get('n_has_dm_avc', 0) or 0),
        ('IRC','CI'):  int(sumario.get('n_has_irc_ci', 0) or 0),
        ('IRC','ICC'): int(sumario.get('n_has_irc_icc',0) or 0),
        ('IRC','AVC'): int(sumario.get('n_has_irc_avc',0) or 0),
        ('CI', 'ICC'): int(sumario.get('n_has_ci_icc', 0) or 0),
        ('CI', 'AVC'): int(sumario.get('n_has_ci_avc', 0) or 0),
        ('ICC','AVC'): int(sumario.get('n_has_icc_avc',0) or 0),
    }

    nd = len(grupos)
    mat_z   = np.zeros((nd, nd))
    mat_txt = [['']*nd for _ in range(nd)]
    for i in range(nd):
        for j in range(nd):
            val = totais[i] if i==j else pares.get((grupos[min(i,j)], grupos[max(i,j)]), 0)
            mat_z[i][j]   = val
            pct = _p(val, n_has)
            mat_txt[i][j] = f"<b>{val:,}</b><br>{pct:.1f}%" if i==j else f"{val:,}<br>{pct:.1f}%"

    col_hm, col_leg = st.columns([3, 2])
    with col_hm:
        def _hex_rgba(h, a=0.13):
            h = h.lstrip('#')
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"
        fig_hm = go.Figure(data=go.Heatmap(
            z=mat_z.tolist(), x=grupos, y=grupos,
            text=mat_txt, texttemplate="%{text}",
            textfont=dict(size=12, color=T.TEXT),
            colorscale=T.HEATMAP_COLORSCALE, showscale=True,
            colorbar=dict(title=dict(text='Pacientes', font=dict(color=T.TEXT_SECONDARY, size=11)),
                          tickfont=dict(color=T.TEXT_SECONDARY, size=9), thickness=14, len=0.85,
                          bgcolor=T.PAPER_BG, bordercolor=T.PAPER_BG),
            hovertemplate="<b>HAS + %{y} + %{x}</b><br>Pacientes: <b>%{z:,}</b><extra></extra>",
        ))
        for i, (nome_g, cor) in enumerate(zip(grupos, cores_g)):
            fig_hm.add_shape(type='rect', xref='x', yref='y',
                             x0=i-0.5, y0=i-0.5, x1=i+0.5, y1=i+0.5,
                             fillcolor=_hex_rgba(cor), line=dict(color=cor, width=3))
        fig_hm.update_layout(
            title=dict(text=f"Comorbidades em hipertensos<br>"
                            f"<sup style='color:{T.TEXT_MUTED}'>Total: {n_has:,} · Diagonal = HAS+comorbidade · Off-diagonal = interseção</sup>",
                       font=dict(size=13, color=T.TEXT), x=0.5),
            height=430, paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
            xaxis=dict(tickfont=dict(color=T.TEXT,size=13,family='monospace'), showgrid=False),
            yaxis=dict(tickfont=dict(color=T.TEXT,size=13,family='monospace'), autorange='reversed', showgrid=False),
            margin=dict(l=10, r=10, t=70, b=30),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

    with col_leg:
        sg, sp = st.columns(2)
        with sg:
            st.markdown(f"<p style='font-size:13px;font-weight:700;color:{T.TEXT_SECONDARY};margin-bottom:8px'>🩺 Grupos</p>", unsafe_allow_html=True)
            for nome_g, val, cor in zip(grupos, totais, cores_g):
                pct_g = _p(val, n_has)
                bar_w = max(4, int(pct_g * 1.5))
                st.markdown(
                    f"<div style='margin-bottom:10px'>"
                    f"<span style='color:{cor};font-size:15px'>⬤</span> "
                    f"<span style='font-weight:700;color:{T.TEXT}'>{nome_g}</span><br>"
                    f"<span style='font-size:13px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_g:.1f}%</span><br>"
                    f"<div style='background:{cor};height:4px;width:{bar_w}%;border-radius:2px;opacity:0.7'></div>"
                    f"</div>", unsafe_allow_html=True
                )
        with sp:
            st.markdown(f"<p style='font-size:13px;font-weight:700;color:{T.TEXT_SECONDARY};margin-bottom:8px'>🔗 Sobreposições</p>", unsafe_allow_html=True)
            for (g1,g2), val in sorted(pares.items(), key=lambda x: -x[1]):
                if val > 0:
                    c1 = cores_g[grupos.index(g1)]
                    c2 = cores_g[grupos.index(g2)]
                    st.markdown(
                        f"<div style='margin-bottom:8px'>"
                        f"<span style='color:{c1}'>⬤</span><span style='color:{c2}'>⬤</span> "
                        f"<span style='font-size:12px;color:{T.TEXT}'><b>{g1}+{g2}</b></span><br>"
                        f"<span style='font-size:12px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                        f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{_p(val,n_has):.1f}%</span>"
                        f"</div>", unsafe_allow_html=True
                    )
        n_todas5 = int(sumario.get('n_has_todas5', 0) or 0)
        if n_todas5 > 0:
            st.markdown(
                f"<div style='margin-top:12px;padding:8px 12px;"
                f"border-left:3px solid #E63946;"
                f"background:rgba(230,57,70,0.1);border-radius:4px'>"
                f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>HAS + todas as 5 comorbidades</span><br>"
                f"<span style='font-size:18px;font-weight:700;color:{T.TEXT}'>{n_todas5:,}</span> "
                f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>({_p(n_todas5, n_has):.1f}%)</span>"
                f"</div>", unsafe_allow_html=True
            )


# ──────────────────────────────────────────────────────────────
# ABA 4 — LACUNAS DE CUIDADO
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### 4️⃣ Lacunas de cuidado na HAS")

    def _card(col, emoji, titulo, val, denom, denom_label, caption_txt):
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{titulo}**")
                st.markdown(f"## {_p(val, denom):.1f}%")
                st.metric("Pacientes", f"{val:,}", f"de {denom:,} ({denom_label})",
                          delta_color="inverse")
                st.caption(caption_txt)

    # Monitoramento de PA
    st.markdown("**📏 Monitoramento da Pressão Arterial**")
    g_pa = st.columns(3)
    _card(g_pa[0], "🟣", "Adulto sem rastreamento de PA",
          int(sumario.get('n_lac_rastreio_pa', 0) or 0), tot, "da população total",
          "Adulto ≥18 anos sem hipertensão e sem aferição de PA nos últimos 365 dias.")
    _card(g_pa[1], "🟠", "Hipertenso sem aferição de PA (>180 dias)",
          int(sumario.get('n_lac_has_sem_pa_180d', 0) or 0), n_has, "dos hipertensos",
          "Hipertenso sem registro de PA nos últimos 6 meses.")
    _card(g_pa[2], "🔵", "DM+HAS com PA >135/80 mmHg",
          int(sumario.get('n_lac_dm_has_pa', 0) or 0), n_has, "dos hipertensos",
          "Meta mais restrita para diabéticos hipertensos: <135/80 mmHg.")

    st.markdown("---")
    # Controle pressórico
    st.markdown("**🎯 Controle Pressórico**")
    g_ctrl = st.columns(2)
    _card(g_ctrl[0], "🔴", "HAS não controlada (<80 anos)",
          int(sumario.get('n_lac_has_nao_ctrl_menor80', 0) or 0), n_has, "dos hipertensos",
          "PA ≥140/90 mmHg na última aferição. Meta: <140/90 mmHg.")
    _card(g_ctrl[1], "🟠", "HAS não controlada (≥80 anos)",
          int(sumario.get('n_lac_has_nao_ctrl_80mais', 0) or 0), n_has, "dos hipertensos",
          "PA ≥150/90 mmHg na última aferição. Meta ≥80 anos: <150/90 mmHg.")

    st.markdown("---")
    # Exames laboratoriais
    st.markdown("**🔬 Exames Laboratoriais Mínimos para Hipertensos**")
    st.caption("Todo hipertenso deve realizar estes exames ao menos uma vez ao ano.")
    g_lab = st.columns(5)
    for col, emoji, titulo, chave, caption in [
        (g_lab[0], "🧪", "Sem creatinina no último ano",  'n_lac_has_creatinina',
         "Avalia função renal — essencial para estadiamento e ajuste terapêutico."),
        (g_lab[1], "🧪", "Sem colesterol no último ano",  'n_lac_has_colesterol',
         "Perfil lipídico orienta risco cardiovascular e terapia com estatinas."),
        (g_lab[2], "🧪", "Sem EAS no último ano",         'n_lac_has_eas',
         "Exame de urina identifica proteinúria e hematúria — rastreio de nefropatia."),
        (g_lab[3], "💓", "Sem ECG no último ano",         'n_lac_has_ecg',
         "Identifica hipertrofia ventricular esquerda e arritmias associadas à HAS."),
        (g_lab[4], "⚖️", "Sem IMC calculável",            'n_lac_has_imc',
         "Peso e altura ausentes. IMC guia intervenção sobre obesidade — fator de risco modificável."),
    ]:
        _card(col, emoji, titulo, int(sumario.get(chave, 0) or 0), n_has, "dos hipertensos", caption)

    st.caption("Lacunas calculadas sobre o denominador indicado em cada card.")


# ──────────────────────────────────────────────────────────────
# ABA 5 — LISTA NOMINAL
# ──────────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 👤 Lista Nominal de Pacientes com HAS")
    st.caption(
        "Filtros de carga e PA são enviados ao banco — o limite respeita o universo filtrado. "
        "Ordenação e demais filtros são aplicados localmente."
    )

    # ── Linha 1: Filtros SQL ──────────────────────────────────
    sf1, sf2, sf3 = st.columns(3)
    with sf1:
        filtro_carga = st.multiselect(
            "Carga de Morbidade",
            options=["Muito Alto", "Alto", "Moderado", "Baixo"],
            default=[],
            placeholder="Todas",
            key="has_lista_carga",
            help="Vazio = todas as categorias.",
        )
    with sf2:
        sem_pa_recente = st.toggle(
            "Sem aferição de PA (>180 dias)",
            value=False, key="has_lista_sem_pa",
            help="Apenas hipertensos sem PA aferida nos últimos 180 dias.",
        )
    with sf3:
        n_exibir = st.selectbox(
            "Exibir até",
            options=[50, 100, 250, 500, 1000],
            index=1, key="has_lista_n",
        )

    # ── Linha 2: Ordenação + filtros locais ──────────────────
    lf1, lf2, lf3 = st.columns(3)
    with lf1:
        ORDEM_MAP = {
            "⚠️ Carga de morbidade (mais grave primeiro)":   "charlson_desc",
            "🔢 Número de morbidades (maior primeiro)":       "morbidades_desc",
            "👴 Idade (mais velhos primeiro)":                "idade_desc",
            "⏳ Mais tempo sem consulta médica":              "sem_medico",
            "🩺 PA mais alta (não controlados primeiro)":     "pa_desc",
        }
        ordem = st.selectbox(
            "Ordenar por",
            options=list(ORDEM_MAP.keys()),
            key="has_lista_ordem",
        )
        ordem_key = ORDEM_MAP[ordem]
    with lf2:
        TEND_LABEL = {
            "piorando":              "📉 Piorando",
            "estavel":               "➡️ Estável",
            "melhorando":            "📈 Melhorando",
            "sem_referencia_previa": "❓ Sem aferição anterior",
        }
        filtro_tendencia = st.multiselect(
            "Filtrar por Tendência",
            options=list(TEND_LABEL.keys()),
            default=[],
            placeholder="Todas",
            format_func=lambda v: TEND_LABEL.get(v, v),
            key="has_lista_tendencia",
            help="Quem não tem PA registrada é sempre incluído.",
        )
    with lf3:
        apenas_nao_ctrl = st.toggle(
            "Apenas não controlados",
            value=False, key="has_lista_nao_ctrl",
            help="PA acima da meta na última aferição.",
        )

    # ── Carregar ─────────────────────────────────────────────
    with st.spinner("Carregando lista de pacientes..."):
        df_pac = carregar_pacientes_has(
            ap_sel, cli_sel, esf_sel,
            limite=n_exibir,
            filtro_carga=filtro_carga if filtro_carga else None,
            sem_pa_recente=sem_pa_recente,
        )

    if df_pac.empty:
        st.info("Nenhum paciente encontrado para os critérios selecionados.")
    else:
        # Ordenação local
        df_pac = _ordenar_has(df_pac, ordem_key)
        n_total = len(df_pac)

        # Filtros locais
        if filtro_tendencia:
            tem = df_pac["tendencia_pa"].notna()
            df_pac = df_pac[~tem | df_pac["tendencia_pa"].isin(filtro_tendencia)]

        if apenas_nao_ctrl:
            df_pac = df_pac[df_pac["status_controle_pressorio"] == "descontrolado"]

        n_filtrado = len(df_pac)
        if n_filtrado < n_total:
            st.markdown(
                f"**{n_filtrado:,} pacientes** exibidos "
                f"<span style='color:{T.TEXT_MUTED};font-size:0.9em'>"
                f"(de {n_total:,} carregados)</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**{n_filtrado:,} pacientes** exibidos")

        # ── Anonimização (ativa via MODO_ANONIMO=true) ───────
        if MODO_ANONIMO:
            df_pac['nome']    = df_pac.apply(
                lambda r: anonimizar_nome(r.get('cpf') or r['nome'], r.get('genero')), axis=1
            )
            df_pac['ap']      = df_pac['ap'].apply(lambda v: anonimizar_ap(v))
            df_pac['clinica'] = df_pac['clinica'].apply(lambda v: anonimizar_clinica(v))
            df_pac['esf']     = df_pac['esf'].apply(lambda v: anonimizar_esf(v))

        # Formatar e exibir tabela
        df_exib = df_pac.copy()
        df_exib['pressao'] = df_exib.apply(
            lambda r: f"{int(r['pressao_sistolica'])}/{int(r['pressao_diastolica'])} mmHg"
            if pd.notna(r['pressao_sistolica']) and pd.notna(r['pressao_diastolica']) else "—",
            axis=1
        )
        df_exib['data_ultima_pa'] = pd.to_datetime(
            df_exib['data_ultima_pa'], errors='coerce'
        ).dt.strftime('%d/%m/%Y')
        df_exib['dias_desde_ultima_medica'] = df_exib['dias_desde_ultima_medica'].apply(
            lambda v: f"{int(v)}d" if pd.notna(v) else "—"
        )

        RENAME = {
            'nome':                    'Paciente',
            'idade':                   'Idade',
            'ap':                      'AP',
            'clinica':                 'Clínica',
            'esf':                     'ESF',
            'carga_morbidade':         'Carga de Morbidade',
            'cid_status':              'CID',
            'pressao':                 'PA',
            'data_ultima_pa':          'Data PA',
            'dias_desde_ultima_pa':    'Dias sem PA',
            'status_controle_pressorio': 'Controle PA',
            'tendencia_pa':            'Tendência',
            'risco_cv':                'Risco CV',
            'dias_desde_ultima_medica': 'Dias s/ médico',
            'consultas_medicas_365d':  'Consultas/ano',
            'total_morbidades':        'N° Morbidades',
            'morbidades_lista':        'Morbidades',
            'n_lacunas':               'N° Lacunas',
            'lacunas_ativas':          'Lacunas',
            'total_medicamentos_cronicos': 'N° Medicamentos',
            'medicamentos':            'Medicamentos',
        }
        cols_show = [c for c in RENAME if c in df_exib.columns]
        df_show = df_exib[cols_show].rename(columns=RENAME)

        st.dataframe(
            df_show,
            hide_index=True,
            use_container_width=True,
            height=520,
            column_config={
                'PA':              st.column_config.TextColumn('PA',           width='small'),
                'CID':             st.column_config.TextColumn('CID',          width='small'),
                'Dias sem PA':     st.column_config.NumberColumn('Dias sem PA', format='%d d'),
                'N° Morbidades':   st.column_config.NumberColumn('N° Morb.',   width='small'),
                'N° Lacunas':      st.column_config.NumberColumn('N° Lacunas', width='small'),
                'N° Medicamentos': st.column_config.NumberColumn('N° Meds',    width='small'),
                'Morbidades':      st.column_config.TextColumn('Morbidades',   width='large'),
                'Lacunas':         st.column_config.TextColumn('Lacunas',      width='large'),
                'Medicamentos':    st.column_config.TextColumn('Medicamentos', width='large'),
                'Clínica':         st.column_config.TextColumn('Clínica',      width='medium'),
            }
        )

        csv = df_pac.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            "⬇️ Baixar lista (.csv)", csv,
            "pacientes_hipertensao.csv", "text/csv",
        )


# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ · Navegador Clínico · Hipertensão Arterial Sistêmica")