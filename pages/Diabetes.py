"""
Page: Diabetes Mellitus
Prevalência, controle glicêmico, tendência, comorbidades, lacunas e lista nominal.
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
    page_title="Diabetes · Navegador Clínico",
    page_icon="🩸",
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

# ctx para filtros
ctx = {
    'ap':      None if ap      == 'N/A' else ap,
    'clinica': None if clinica == 'N/A' else clinica,
    'esf':     None if esf     == 'N/A' else esf,
}

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO CONSISTENTE
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

PAGINA_ATUAL = "Diabetes"
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
ICONES = [
    "house-fill", "people-fill", "person-lines-fill",
    "exclamation-triangle-fill", "arrow-repeat", "capsule",
    "droplet-fill", "heart-pulse-fill", "heart-fill",
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
def _where(ap, clinica, esf, extra=None):
    c = []
    if ap:      c.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: c.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     c.append(f"nome_esf_cadastro = '{esf}'")
    if extra:   c.extend(extra)
    return ("WHERE " + " AND ".join(c)) if c else ""

@st.cache_data(show_spinner=False, ttl=900)
def carregar_sumario_dm(ap, clinica, esf):
    where = _where(ap, clinica, esf)
    sql = f"""
    SELECT
        COUNT(*) AS total_pop,
        COUNTIF(DM IS NOT NULL)                                          AS n_DM,
        COUNTIF(dm_por_cid IS NOT NULL)                                  AS n_DM_por_cid,
        COUNTIF(dm_por_exames IS NOT NULL)                               AS n_DM_por_exames,
        COUNTIF(dm_por_progressao_pre_dm IS NOT NULL)                    AS n_DM_por_progressao,
        COUNTIF(dm_por_medicamento_forte IS NOT NULL)                    AS n_DM_por_medicamento,
        COUNTIF(DM_sem_CID = TRUE)                                       AS n_DM_sem_cid,
        COUNTIF(provavel_dm1 = TRUE)                                     AS n_DM1_provavel,
        COUNTIF(pre_DM IS NOT NULL)                                      AS n_pre_DM,
        COUNTIF(DM IS NOT NULL AND DM_controlado = TRUE)                 AS n_DM_controlado,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_descontrolado = TRUE)       AS n_DM_descontrolado,
        COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)                 AS n_DM_melhorando,
        COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)                   AS n_DM_piorando,
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN pct_dias_dm_controlado_365d END), 1) AS media_pct_dm_ctrl,
        COUNTIF(DM IS NOT NULL AND hba1c_atual IS NOT NULL)              AS n_DM_com_hba1c,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_sem_HbA1c_recente = TRUE)   AS n_DM_sem_hba1c,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_hba1c_nao_solicitado = TRUE) AS n_DM_hba1c_nao_sol,
        COUNTIF(DM IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)      AS n_lac_dm_creatinina,
        COUNTIF(DM IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)      AS n_lac_dm_colesterol,
        COUNTIF(DM IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)             AS n_lac_dm_eas,
        COUNTIF(DM IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)             AS n_lac_dm_ecg,
        COUNTIF(DM IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)             AS n_lac_dm_imc,
        COUNTIF(DM IS NOT NULL AND lacuna_IRC_sem_SGLT2 = TRUE)          AS n_lac_dm_irc_sglt2,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_complicado_sem_SGLT2 = TRUE) AS n_lac_dm_comp_sglt2,
        COUNTIF(DM IS NOT NULL AND IRC IS NOT NULL)                       AS n_dm_com_irc,
        COUNTIF(DM IS NOT NULL AND (ICC IS NOT NULL OR IRC IS NOT NULL OR CI IS NOT NULL)) AS n_dm_complicado_total,
        COUNTIF(DM IS NOT NULL AND IRC IS NOT NULL AND COALESCE(lacuna_IRC_sem_SGLT2, FALSE) = FALSE)  AS n_dm_irc_com_sglt2,
        COUNTIF(DM IS NOT NULL AND (ICC IS NOT NULL OR IRC IS NOT NULL OR CI IS NOT NULL)
                AND COALESCE(lacuna_DM_complicado_sem_SGLT2, FALSE) = FALSE) AS n_dm_comp_com_sglt2,
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN hba1c_atual END), 2)     AS media_hba1c,
        COUNTIF(lacuna_DM_microalbuminuria_nao_solicitado = TRUE)         AS n_lac_microalb,
        COUNTIF(lacuna_rastreio_DM_hipertenso = TRUE)                     AS n_lac_rastreio_dm_has,
        COUNTIF(lacuna_rastreio_DM_45mais = TRUE)                         AS n_lac_rastreio_dm_45,
        COUNTIF(lacuna_DM_sem_exame_pe_365d = TRUE)                       AS n_lac_pe_365d,
        COUNTIF(lacuna_DM_sem_exame_pe_180d = TRUE)                       AS n_lac_pe_180d,
        COUNTIF(lacuna_DM_nunca_teve_exame_pe = TRUE)                     AS n_lac_pe_nunca,
        -- Complicações do DM
        COUNTIF(DM IS NOT NULL AND dm_com_complicacao = TRUE)             AS n_dm_com_complicacao,
        COUNTIF(DM IS NOT NULL AND dm_retinopatia IS NOT NULL)            AS n_dm_retinopatia,
        COUNTIF(DM IS NOT NULL AND dm_catarata IS NOT NULL)               AS n_dm_catarata,
        COUNTIF(DM IS NOT NULL AND dm_nefropatia IS NOT NULL)             AS n_dm_nefropatia,
        COUNTIF(DM IS NOT NULL AND dm_neuropatia IS NOT NULL)             AS n_dm_neuropatia,
        COUNTIF(DM IS NOT NULL AND dm_pe_diabetico_cid IS NOT NULL)       AS n_dm_pe_diabetico,
        COUNTIF(DM IS NOT NULL AND dm_complicacao_cv IS NOT NULL)         AS n_dm_complicacao_cv,
        -- Prescrições de antidiabéticos
        COUNTIF(DM IS NOT NULL AND principio_BIGUANIDA IS NOT NULL)               AS n_rx_biguanida,
        COUNTIF(DM IS NOT NULL AND principio_SULFONILUREIA IS NOT NULL)            AS n_rx_sulfonilureia,
        COUNTIF(DM IS NOT NULL AND principio_iSGLT2 IS NOT NULL)                  AS n_rx_isglt2,
        COUNTIF(DM IS NOT NULL AND principio_iDPP4 IS NOT NULL)                   AS n_rx_idpp4,
        COUNTIF(DM IS NOT NULL AND principio_GLP1 IS NOT NULL)                    AS n_rx_glp1,
        COUNTIF(DM IS NOT NULL AND principio_TIAZOLIDINEDIONA IS NOT NULL)        AS n_rx_tiazolidinediona,
        COUNTIF(DM IS NOT NULL AND principio_GLINIDA IS NOT NULL)                 AS n_rx_glinida,
        COUNTIF(DM IS NOT NULL AND principio_ACARBOSE IS NOT NULL)                AS n_rx_acarbose,
        COUNTIF(DM IS NOT NULL AND principio_INSULINA_BASAL_HUMANA IS NOT NULL)   AS n_rx_ins_basal_humana,
        COUNTIF(DM IS NOT NULL AND principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL) AS n_rx_ins_prandial_humana,
        COUNTIF(DM IS NOT NULL AND principio_INSULINA_BASAL_ANALOGICA IS NOT NULL) AS n_rx_ins_basal_analogica,
        COUNTIF(DM IS NOT NULL AND principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL) AS n_rx_ins_prandial_analogica,
        COUNTIF(DM IS NOT NULL AND principio_INSULINA_MISTA IS NOT NULL)          AS n_rx_ins_mista,
        -- Metformina > 2000mg
        COUNTIF(DM IS NOT NULL AND principio_BIGUANIDA IS NOT NULL
                AND dose_BIGUANIDA_mg_dia > 2000)                                AS n_rx_metformina_alta,
        -- Sulfonilureia como único antidiabético (sem metformina, sem outros orais, sem insulina)
        COUNTIF(DM IS NOT NULL AND principio_SULFONILUREIA IS NOT NULL
                AND principio_BIGUANIDA IS NULL
                AND principio_iSGLT2 IS NULL
                AND principio_iDPP4 IS NULL
                AND principio_GLP1 IS NULL
                AND principio_TIAZOLIDINEDIONA IS NULL
                AND principio_GLINIDA IS NULL
                AND principio_ACARBOSE IS NULL
                AND principio_INSULINA_BASAL_HUMANA IS NULL
                AND principio_INSULINA_PRANDIAL_HUMANA IS NULL
                AND principio_INSULINA_BASAL_ANALOGICA IS NULL
                AND principio_INSULINA_PRANDIAL_ANALOGICA IS NULL
                AND principio_INSULINA_MISTA IS NULL)                             AS n_rx_sulfo_monoterapia
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}

@st.cache_data(show_spinner=False, ttl=900)
def carregar_resumo_hba1c(ap, clinica, esf):
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where_fato = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    WITH
    cpfs_todos AS (
        SELECT cpf FROM `{_fqn(config.TABELA_FATO)}` {where_fato}
    ),
    mais_recente AS (
        SELECT g.cpf, g.tem_dm, g.tem_pre_dm, g.tem_has, g.tem_dm_complicado,
               g.tem_ci, g.tem_icc, g.tem_stroke, g.tem_irc,
               g.valor, g.data_exame, g.dias_desde_exame, g.recencia,
               g.interpretacao_hba1c, g.hba1c_em_nao_diabetico, g.meta_hba1c
        FROM `rj-sms-sandbox.sub_pav_us.MM_glicemia_hba1c_historico` g
        INNER JOIN cpfs_todos ct ON g.cpf = ct.cpf
        WHERE g.tipo_exame = 'hba1c'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY g.cpf ORDER BY g.data_exame DESC) = 1
    ),
    diabeticos_sem_hba1c AS (
        SELECT c.cpf
        FROM cpfs_todos c
        INNER JOIN `{_fqn(config.TABELA_FATO)}` f ON c.cpf = f.cpf
        WHERE f.DM IS NOT NULL
          AND c.cpf NOT IN (SELECT cpf FROM mais_recente)
    )
    SELECT
        COUNTIF(tem_dm AND recencia = 'ate_180d')                    AS n_dm_hba1c_180d,
        COUNTIF(tem_dm AND recencia = 'ate_365d')                    AS n_dm_hba1c_365d,
        COUNTIF(tem_dm AND recencia = 'mais_de_365d')                AS n_dm_hba1c_antiga,
        (SELECT COUNT(*) FROM diabeticos_sem_hba1c)                  AS n_dm_nunca_hba1c,
        COUNTIF(tem_dm AND recencia = 'ate_180d'
                AND interpretacao_hba1c = 'dm_controlado')           AS n_ctrl,
        COUNTIF(tem_dm AND recencia = 'ate_180d'
                AND interpretacao_hba1c = 'dm_nao_controlado')       AS n_nao_ctrl,
        ROUND(AVG(CASE WHEN tem_dm AND recencia = 'ate_180d' THEN valor END), 2) AS media_hba1c_dm_recente,
        COUNTIF(hba1c_em_nao_diabetico = TRUE)                       AS n_rastreio_incorreto,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_normal')       AS n_rastreio_normal,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_pre_diabetes') AS n_rastreio_pre_dm,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_provavel_dm')  AS n_rastreio_provavel_dm,
        COUNTIF(tem_dm_complicado = TRUE)                             AS n_dm_complicado,
        COUNTIF(tem_dm AND tem_has)   AS n_dm_has,
        COUNTIF(tem_dm AND tem_irc)   AS n_dm_irc,
        COUNTIF(tem_dm AND tem_ci)    AS n_dm_ci,
        COUNTIF(tem_dm AND tem_icc)   AS n_dm_icc,
        COUNTIF(tem_dm AND tem_stroke) AS n_dm_avc,
        COUNTIF(tem_dm AND tem_has AND tem_irc)   AS n_dm_has_irc,
        COUNTIF(tem_dm AND tem_has AND tem_ci)    AS n_dm_has_ci,
        COUNTIF(tem_dm AND tem_has AND tem_icc)   AS n_dm_has_icc,
        COUNTIF(tem_dm AND tem_has AND tem_stroke) AS n_dm_has_avc,
        COUNTIF(tem_dm AND tem_irc AND tem_ci)    AS n_dm_irc_ci,
        COUNTIF(tem_dm AND tem_irc AND tem_icc)   AS n_dm_irc_icc,
        COUNTIF(tem_dm AND tem_irc AND tem_stroke) AS n_dm_irc_avc,
        COUNTIF(tem_dm AND tem_ci  AND tem_icc)   AS n_dm_ci_icc,
        COUNTIF(tem_dm AND tem_ci  AND tem_stroke) AS n_dm_ci_avc,
        COUNTIF(tem_dm AND tem_icc AND tem_stroke) AS n_dm_icc_avc,
        COUNTIF(tem_dm AND tem_has AND tem_irc AND tem_ci AND tem_icc AND tem_stroke) AS n_dm_todas5
    FROM mais_recente
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}

@st.cache_data(show_spinner=False, ttl=900)
def carregar_nph_ui_kg(ap, clinica, esf):
    """Retorna UI/kg de NPH por paciente (para histograma). Exclui doses absurdas."""
    clauses = [
        "DM IS NOT NULL",
        "dose_NPH_ui_kg IS NOT NULL",
        "dose_NPH_ui_kg > 0",
        "COALESCE(alerta_dose_NPH_absurda, FALSE) = FALSE",
    ]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = "WHERE " + " AND ".join(clauses)
    sql = f"""
    SELECT dose_NPH_ui_kg AS ui_kg
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_territorio_dm(ap, clinica, esf):
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
        ROUND(COUNTIF(DM IS NOT NULL AND DM_controlado = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)  AS pct_dm_ctrl,
        ROUND(COUNTIF(DM IS NOT NULL AND lacuna_DM_descontrolado = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)  AS pct_dm_desctrl,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)  AS pct_dm_mel,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)  AS pct_dm_pio,
        ROUND(COUNTIF(DM IS NOT NULL AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c <= 180)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_hba1c_180d_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c BETWEEN 181 AND 365)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_hba1c_365d_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c > 365)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_hba1c_ant_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND dias_desde_ultima_hba1c IS NULL)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_hba1c_nunca_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_mel_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND COALESCE(DM_melhorando, FALSE) = FALSE
                      AND COALESCE(DM_piorando, FALSE) = FALSE)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_est_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)
              * 100.0 / COUNT(*), 1)                             AS pct_dm_pio_pop
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY {grupo_col}
    ORDER BY {grupo_col}
    """
    df = bq(sql)
    df['label_col'] = label_col
    return df

@st.cache_data(show_spinner=False, ttl=900)
def carregar_pacientes_dm(ap, clinica, esf, limite=500,
                          filtro_carga=None, nunca_hba1c=False):
    """Lista nominal — filtros de carga e nunca_hba1c vão para o SQL (correto com LIMIT).
    Ordenação e demais filtros são feitos no Python após o retorno.
    """
    clauses = ["DM IS NOT NULL"]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    # Filtro de carga no SQL — garante que o LIMIT incide sobre o universo correto
    if filtro_carga:
        cats = ", ".join(f"'{c}'" for c in filtro_carga)
        clauses.append(f"charlson_categoria IN ({cats})")
    # Nunca fez HbA1c — também vai para o SQL pelo mesmo motivo
    if nunca_hba1c:
        clauses.append("hba1c_atual IS NULL")
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
        hba1c_atual,
        data_hba1c_atual,
        dias_desde_ultima_hba1c,
        status_controle_glicemico,
        tendencia_hba1c,
        meta_hba1c,
        pressao_sistolica,
        pressao_diastolica,
        dias_desde_ultima_medica,
        consultas_medicas_365d,
        meses_com_consulta_12m,

        CASE
            WHEN provavel_dm1 = TRUE THEN 'Possível DM1'
            ELSE 'DM2'
        END AS tipo_dm,

        CASE WHEN DM_sem_CID = TRUE THEN '⚠️ Sem CID' ELSE '✅ Com CID' END AS cid_status,

        -- Morbidades presentes
        ARRAY_TO_STRING(ARRAY(SELECT m FROM UNNEST([
            IF(HAS IS NOT NULL,              'HAS',                 NULL),
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
            -- IF(tireoide IS NOT NULL,         'Tireoide',            NULL),
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
            IF(lacuna_DM_sem_HbA1c_recente = TRUE,              'Sem HbA1c recente',        NULL),
            IF(lacuna_DM_descontrolado = TRUE,                   'DM não controlado',        NULL),
            IF(lacuna_DM_sem_exame_pe_365d = TRUE,               'Sem exame do pé',          NULL),
            IF(lacuna_creatinina_HAS_DM = TRUE,                  'Sem creatinina',           NULL),
            IF(lacuna_colesterol_HAS_DM = TRUE,                  'Sem colesterol',           NULL),
            IF(lacuna_DM_microalbuminuria_nao_solicitado = TRUE, 'Sem microalbuminúria',     NULL),
            IF(lacuna_IRC_sem_SGLT2 = TRUE,                      'IRC sem SGLT-2',           NULL),
            IF(lacuna_DM_complicado_sem_SGLT2 = TRUE,            'DM complicado sem SGLT-2', NULL),
            IF(lacuna_HAS_descontrolado_menor80 = TRUE
               OR lacuna_HAS_descontrolado_80mais = TRUE,        'HAS não controlada',       NULL)
        ]) AS l WHERE l IS NOT NULL), ' · ') AS lacunas_ativas,

        (IF(lacuna_DM_sem_HbA1c_recente = TRUE, 1, 0)
         + IF(lacuna_DM_descontrolado = TRUE, 1, 0)
         + IF(lacuna_DM_sem_exame_pe_365d = TRUE, 1, 0)
         + IF(lacuna_creatinina_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_colesterol_HAS_DM = TRUE, 1, 0)
         + IF(lacuna_DM_microalbuminuria_nao_solicitado = TRUE, 1, 0)
         + IF(lacuna_IRC_sem_SGLT2 = TRUE, 1, 0)
         + IF(lacuna_DM_complicado_sem_SGLT2 = TRUE, 1, 0)) AS n_lacunas,

        total_medicamentos_cronicos,
        COALESCE(nucleo_cronico_atual, '—') AS medicamentos,

        -- Medicamentos DM
        ARRAY_TO_STRING(ARRAY(SELECT m FROM UNNEST([
            IF(principio_BIGUANIDA IS NOT NULL,                principio_BIGUANIDA, NULL),
            IF(principio_SULFONILUREIA IS NOT NULL,            principio_SULFONILUREIA, NULL),
            IF(principio_iSGLT2 IS NOT NULL,                  principio_iSGLT2, NULL),
            IF(principio_iDPP4 IS NOT NULL,                   principio_iDPP4, NULL),
            IF(principio_GLP1 IS NOT NULL,                    principio_GLP1, NULL),
            IF(principio_TIAZOLIDINEDIONA IS NOT NULL,        principio_TIAZOLIDINEDIONA, NULL),
            IF(principio_GLINIDA IS NOT NULL,                 principio_GLINIDA, NULL),
            IF(principio_ACARBOSE IS NOT NULL,                principio_ACARBOSE, NULL),
            IF(principio_INSULINA_BASAL_HUMANA IS NOT NULL,   'NPH', NULL),
            IF(principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL,'Regular', NULL),
            IF(principio_INSULINA_BASAL_ANALOGICA IS NOT NULL, principio_INSULINA_BASAL_ANALOGICA, NULL),
            IF(principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL, principio_INSULINA_PRANDIAL_ANALOGICA, NULL),
            IF(principio_INSULINA_MISTA IS NOT NULL,          principio_INSULINA_MISTA, NULL)
        ]) AS m WHERE m IS NOT NULL), ' · ') AS meds_dm,

        dose_BIGUANIDA_mg_dia,
        dose_NPH_ui_kg,
        n_classes_antidiabeticos,
        intensidade_tratamento_dm

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    LIMIT {limite}
    """
    return bq(sql)


def _ordenar_df(df: pd.DataFrame, ordem: str) -> pd.DataFrame:
    """Ordena o dataframe localmente — 100% Python, sem depender do BigQuery."""
    if df.empty:
        return df

    CONFIG = {
        # (coluna, crescente, na_position)
        'charlson_desc': ('charlson_score',           False, 'last'),
        'morbidades_desc': ('total_morbidades',       False, 'last'),
        'idade_desc':    ('idade',                    False, 'last'),
        'sem_medico':    ('dias_desde_ultima_medica', False, 'first'),
        'hba1c_desc':    ('hba1c_atual',              False, 'last'),
    }
    if ordem not in CONFIG:
        return df
    col, asc, na_pos = CONFIG[ordem]
    if col not in df.columns:
        return df
    return df.sort_values(col, ascending=asc, na_position=na_pos)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — FILTROS
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo()
st.sidebar.title("Filtros")

_opcoes = carregar_opcoes_filtros()
_areas  = _opcoes.get('areas', [])

def _dm_reset_cli_esf():
    st.session_state['dm_cli'] = None
    st.session_state['dm_esf'] = None

def _dm_reset_esf():
    st.session_state['dm_esf'] = None

if 'dm_ap'  not in st.session_state: st.session_state['dm_ap']  = ctx.get('ap')
if 'dm_cli' not in st.session_state: st.session_state['dm_cli'] = ctx.get('clinica')
if 'dm_esf' not in st.session_state: st.session_state['dm_esf'] = ctx.get('esf')

ap_sel = st.sidebar.selectbox(
    "Área Programática",
    options=[None] + _areas,
    format_func=lambda x: "Todas" if x is None else anonimizar_ap(str(x)),
    key="dm_ap", on_change=_dm_reset_cli_esf,
)
_clinicas = sorted(_opcoes['clinicas'].get(ap_sel, [])) if ap_sel else []
if st.session_state.get('dm_cli') not in _clinicas:
    st.session_state['dm_cli'] = None

cli_sel = st.sidebar.selectbox(
    "Clínica da Família",
    options=[None] + _clinicas,
    format_func=lambda x: "Todas" if x is None else anonimizar_clinica(x),
    key="dm_cli", disabled=not ap_sel, on_change=_dm_reset_esf,
)
_esfs = sorted(_opcoes['esf'].get(cli_sel, [])) if cli_sel else []
if st.session_state.get('dm_esf') not in _esfs:
    st.session_state['dm_esf'] = None

esf_sel = st.sidebar.selectbox(
    "Equipe ESF",
    options=[None] + _esfs,
    format_func=lambda x: "Todas" if x is None else anonimizar_esf(x),
    key="dm_esf", disabled=not cli_sel,
)

# Navegação
st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
NOMES_ABAS = [
    "1️⃣ Diagnóstico e Prevalência",
    "2️⃣ Controle Glicêmico",
    "3️⃣ Medicamentos Prescritos",
    "4️⃣ Comorbidades",
    "5️⃣ Lacunas de Cuidado",
    "👤 Lista de Pacientes",
]
if 'dm_aba' not in st.session_state:
    st.session_state['dm_aba'] = 0
aba_sel = st.sidebar.radio(
    "", options=range(len(NOMES_ABAS)),
    format_func=lambda i: NOMES_ABAS[i],
    index=st.session_state['dm_aba'],
    key="dm_nav", label_visibility="collapsed",
)
st.session_state['dm_aba'] = aba_sel

# ═══════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
with st.spinner("Carregando dados de diabetes..."):
    sumario   = carregar_sumario_dm(ap_sel, cli_sel, esf_sel)
    rh        = carregar_resumo_hba1c(ap_sel, cli_sel, esf_sel)
    df_terr   = carregar_territorio_dm(ap_sel, cli_sel, esf_sel)
    # Anonimizar eixo X dos gráficos de território
    if MODO_ANONIMO and not df_terr.empty and 'territorio' in df_terr.columns:
        if cli_sel:
            df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_esf)
        elif ap_sel:
            df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_clinica)
        else:
            df_terr['territorio'] = df_terr['territorio'].apply(lambda x: anonimizar_ap(str(x)))

if not sumario:
    st.error("❌ Não foi possível carregar os dados.")
    st.stop()

n_dm  = int(sumario.get('n_DM', 0) or 1)
tot   = int(sumario.get('total_pop', 0) or 1)
lbl   = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'

# ═══════════════════════════════════════════════════════════════
# TÍTULO E MÉTRICAS TOPO
# ═══════════════════════════════════════════════════════════════
st.title("🩸 Diabetes Mellitus")
st.markdown("Panorama do diabetes no território — do diagnóstico ao controle glicêmico.")
st.caption("Fonte: tabela fato — dados individuais agregados por território.")
st.markdown("---")

m1, m2, m3, m4 = st.columns(4)
m1.metric("🩸 Diabéticos", f"{n_dm:,}", f"{_p(n_dm, tot):.1f}% da população")
m2.metric("✅ Controlados (HbA1c ≤180d)", f"{int(rh.get('n_ctrl', 0) or 0):,}",
          f"{_p(rh.get('n_ctrl', 0), n_dm):.1f}% dos diabéticos")
m3.metric("⚠️ Não controlados", f"{int(rh.get('n_nao_ctrl', 0) or 0):,}",
          f"{_p(rh.get('n_nao_ctrl', 0), n_dm):.1f}% dos diabéticos",
          delta_color="inverse")
m4.metric("🟡 Pré-Diabetes", f"{int(sumario.get('n_pre_DM', 0) or 0):,}",
          f"{_p(sumario.get('n_pre_DM', 0), tot):.1f}% da população")
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
        margin=dict(l=10, r=160, t=50, b=60 if len(terrs) <= 12 else 130),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        title=dict(text=titulo, font=dict(color=T.TEXT, size=13)),
        xaxis=dict(type='category', categoryorder='array', categoryarray=terrs,
                   tickfont=dict(color=T.TEXT, size=10),
                   tickangle=-35),
        yaxis=dict(title='% da população total', tickfont=dict(color=T.TEXT_MUTED, size=10),
                   gridcolor=T.GRID, range=[0, 25]),
        legend=dict(orientation='v', xanchor='left', x=1.01, yanchor='middle', y=0.5,
                    font=dict(color=T.TEXT, size=11),
                    bgcolor=T.LEGEND_BG, bordercolor=T.LEGEND_BORDER, borderwidth=1),
    )
    st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab_meds, tab3, tab4, tab5 = st.tabs(NOMES_ABAS)


# ──────────────────────────────────────────────────────────────
# ABA 1 — DIAGNÓSTICO E PREVALÊNCIA
# ──────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### 1️⃣ Prevalência, complicações e como foram identificados")
    n_sem_cid_dm  = int(sumario.get('n_DM_sem_cid', 0) or 0)
    n_pre_dm      = int(sumario.get('n_pre_DM', 0) or 0)
    n_dm1         = int(sumario.get('n_DM1_provavel', 0) or 0)
    pct_sem_cid   = _p(n_sem_cid_dm, n_dm)

    col_dm1, col_dm2, col_dm3, col_dm4 = st.columns(4)
    with col_dm1:
        with st.container(border=True):
            st.metric("🩸 Diabéticos identificados", f"{n_dm:,}",
                      f"{_p(n_dm, tot):.1f}% da população",
                      help="Total identificados por qualquer critério.")
    with col_dm2:
        with st.container(border=True):
            st.metric("🟡 Pré-Diabetes", f"{n_pre_dm:,}",
                      f"{_p(n_pre_dm, tot):.1f}% da população",
                      help="Glicemia 100–125 mg/dL ou HbA1c 5,7–6,4%.")
    with col_dm3:
        with st.container(border=True):
            st.metric("💉 Provável DM tipo 1", f"{n_dm1:,}",
                      f"{_p(n_dm1, n_dm):.1f}% dos diabéticos",
                      help="Pacientes jovens, e/ou que nunca receberam hipoglicemiantes orais, e/ou com prescrição de insulina de ação rápida.")
    with col_dm4:
        with st.container(border=True):
            st.metric("⚠️ Sem CID registrado", f"{n_sem_cid_dm:,}",
                      f"{pct_sem_cid:.1f}% dos diabéticos",
                      delta_color="inverse",
                      help="Diabéticos sem CID E10–E14.")

    if pct_sem_cid > 20:
        st.warning(f"⚠️ **Alerta de subnotificação:** {pct_sem_cid:.1f}% dos diabéticos ({n_sem_cid_dm:,}) "
                   "não têm CID registrado. Subnotificação compromete a qualidade do cuidado prestado.")

    st.markdown("##### Como estes pacientes foram identificados")
    st.caption("Um mesmo paciente pode ser identificado por mais de um critério.")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**📋 Por CID registrado (E10–E14)**")
            st.metric("Pacientes", f"{sumario.get('n_DM_por_cid', 0):,}",
                      f"{_p(sumario.get('n_DM_por_cid', 0), n_dm):.0f}% dos diabéticos")
            st.caption("Forma mais robusta. Essencial para listas e indicadores de qualidade.")
    with c2:
        with st.container(border=True):
            st.markdown("**🩸 Por exames laboratoriais**")
            st.metric("Pacientes", f"{sumario.get('n_DM_por_exames', 0):,}",
                      f"{_p(sumario.get('n_DM_por_exames', 0), n_dm):.0f}% dos diabéticos")
            st.caption("Glicemia ≥126 mg/dL ou HbA1c ≥6,5%. Devem ter CID registrado.")

    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            st.markdown("**📈 Por progressão do pré-DM**")
            st.metric("Pacientes", f"{sumario.get('n_DM_por_progressao', 0):,}",
                      f"{_p(sumario.get('n_DM_por_progressao', 0), n_dm):.0f}% dos diabéticos")
            st.caption("Pré-DM que atingiu critérios em exame subsequente.")
    with c4:
        with st.container(border=True):
            st.markdown("**💊 Por prescrição de insulina ou similares**")
            st.metric("Pacientes", f"{sumario.get('n_DM_por_medicamento', 0):,}",
                      f"{_p(sumario.get('n_DM_por_medicamento', 0), n_dm):.0f}% dos diabéticos")
            st.caption("Diagnóstico implícito pelo tratamento — oportunidade de codificação formal.")

    # ── Complicações do diabetes ─────────────────────────────
    st.markdown("---")
    st.markdown("##### CIDs codificados de complicações do diabetes")
    st.caption("Pacientes diabéticos com complicações micro e macrovasculares registradas por CID.")

    n_comp_total = int(sumario.get('n_dm_com_complicacao', 0) or 0)
    n_retino     = int(sumario.get('n_dm_retinopatia', 0) or 0)
    n_catarata   = int(sumario.get('n_dm_catarata', 0) or 0)
    n_nefro      = int(sumario.get('n_dm_nefropatia', 0) or 0)
    n_neuro      = int(sumario.get('n_dm_neuropatia', 0) or 0)
    n_pe         = int(sumario.get('n_dm_pe_diabetico', 0) or 0)
    n_irc        = int(sumario.get('n_dm_com_irc', 0) or 0)

    st.metric("🚨 Diabéticos com pelo menos 1 complicação", f"{n_comp_total:,}",
              f"{_p(n_comp_total, n_dm):.1f}% dos diabéticos")

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        with st.container(border=True):
            st.markdown("**👁️ Retinopatia**")
            st.metric("Pacientes", f"{n_retino:,}",
                      f"{_p(n_retino, n_dm):.1f}% dos diabéticos")
        with st.container(border=True):
            st.markdown("**👁️ Catarata**")
            st.metric("Pacientes", f"{n_catarata:,}",
                      f"{_p(n_catarata, n_dm):.1f}% dos diabéticos")
    with cc2:
        with st.container(border=True):
            st.markdown(f"**🫘 Nefropatia** ({n_irc:,} com IRC)")
            st.metric("Pacientes", f"{n_nefro:,}",
                      f"{_p(n_nefro, n_dm):.1f}% dos diabéticos")
        with st.container(border=True):
            st.markdown("**🦶 Pé diabético**")
            st.metric("Pacientes", f"{n_pe:,}",
                      f"{_p(n_pe, n_dm):.1f}% dos diabéticos")
    with cc3:
        with st.container(border=True):
            st.markdown("**🧠 Neuropatia**")
            st.metric("Pacientes", f"{n_neuro:,}",
                      f"{_p(n_neuro, n_dm):.1f}% dos diabéticos")


# ──────────────────────────────────────────────────────────────
# ABA 2 — CONTROLE GLICÊMICO
# ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 2️⃣ Controle glicêmico — situação atual")
    st.caption("HbA1c mais recente por paciente diabético.")

    n_hba1c_180  = int(rh.get('n_dm_hba1c_180d', 0) or 0)
    n_hba1c_365  = int(rh.get('n_dm_hba1c_365d', 0) or 0)
    n_hba1c_ant  = int(rh.get('n_dm_hba1c_antiga', 0) or 0)
    n_nunca      = int(rh.get('n_dm_nunca_hba1c', 0) or 0)
    n_ctrl_dm    = int(rh.get('n_ctrl', 0) or 0)
    n_nctrl_dm   = int(rh.get('n_nao_ctrl', 0) or 0)
    media_hba1c  = rh.get('media_hba1c_dm_recente') or 0
    n_rastreio   = int(rh.get('n_rastreio_incorreto', 0) or 0)
    n_rast_norm  = int(rh.get('n_rastreio_normal', 0) or 0)
    n_rast_pre   = int(rh.get('n_rastreio_pre_dm', 0) or 0)
    n_rast_dm    = int(rh.get('n_rastreio_provavel_dm', 0) or 0)

    m1c, m2c, m3c, m4c = st.columns(4)
    m1c.metric("✅ Controlados (HbA1c ≤180d)", f"{n_ctrl_dm:,}",
               f"{_p(n_ctrl_dm, n_dm):.1f}% dos diabéticos")
    m2c.metric("⚠️ Não controlados", f"{n_nctrl_dm:,}",
               f"{_p(n_nctrl_dm, n_dm):.1f}% dos diabéticos", delta_color="inverse")
    m3c.metric("🩸 HbA1c média (≤180d)",
               f"{media_hba1c:.1f}%" if media_hba1c else "—")
    m4c.metric("📊 % médio tempo controlado",
               f"{sumario.get('media_pct_dm_ctrl', 0):.1f}%")

    st.markdown("**🗓️ Recência da última HbA1c**")
    rc1, rc2, rc3, rc4 = st.columns(4)
    for col, emoji, label, n, caption in [
        (rc1, "🟢", "HbA1c ≤ 180 dias",       n_hba1c_180, "Monitoramento em dia."),
        (rc2, "🟡", "HbA1c 181–365 dias",      n_hba1c_365, "Monitoramento anual mínimo atendido."),
        (rc3, "🟠", "HbA1c há mais de 365 dias", n_hba1c_ant, "Exame desatualizado."),
        (rc4, "🔴", "Nunca realizou HbA1c",    n_nunca,     "Prioridade máxima de solicitação."),
    ]:
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{label}**")
                st.markdown(f"## {_p(n, n_dm):.1f}%")
                st.metric("Diabéticos", f"{n:,}")
                st.caption(caption)

    if n_rastreio > 0:
        st.warning(
            f"⚠️ **{n_rastreio:,} pacientes sem diabetes fizeram HbA1c** — uso inadequado. "
            f"Resultado: {n_rast_norm:,} normais, {n_rast_pre:,} pré-DM, {n_rast_dm:,} provável DM."
        )
        if n_rast_dm > 0:
            st.error(f"🚨 **{n_rast_dm:,} pacientes com HbA1c ≥6,5% sem diagnóstico de DM** — revisar.")

    _stacked_bar(df_terr,
        cols_pop=['pct_dm_hba1c_180d_pop','pct_dm_hba1c_365d_pop','pct_dm_hba1c_ant_pop','pct_dm_hba1c_nunca_pop'],
        labels=['HbA1c ≤180d','HbA1c 181–365d','HbA1c >365d','Nunca realizou'],
        cores=['#2ECC71','#F4D03F','#E67E22','#777777'],
        titulo=f'Janelas temporais para o resultado de HbA1c pela prevalência de diabetes na população por {lbl}',
    )

    st.markdown("---")
    st.markdown("#### Tendência glicêmica")
    st.caption("Comparação entre a última e a penúltima HbA1c registrada (intervalo ≥90 dias).")

    n_mel_dm = int(sumario.get('n_DM_melhorando', 0) or 0)
    n_pio_dm = int(sumario.get('n_DM_piorando', 0) or 0)
    n_est_dm = max(0, n_dm - n_mel_dm - n_pio_dm)

    td1, td2, td3 = st.columns(3)
    td1.metric("📈 Melhorando", f"{n_mel_dm:,}", f"{_p(n_mel_dm, n_dm):.1f}%",
               help="HbA1c caiu >0,5% em relação à anterior.")
    td2.metric("➡️ Estável", f"{n_est_dm:,}", f"{_p(n_est_dm, n_dm):.1f}%", delta_color="off")
    td3.metric("📉 Piorando", f"{n_pio_dm:,}", f"{_p(n_pio_dm, n_dm):.1f}%", delta_color="inverse",
               help="HbA1c subiu >0,5% em relação à anterior.")

    _stacked_bar(df_terr,
        cols_pop=['pct_dm_mel_pop','pct_dm_est_pop','pct_dm_pio_pop'],
        labels=['Melhorando','Estável/sem info','Piorando'],
        cores=['#2ECC71','#F4D03F','#E74C3C'],
        titulo=f'Tendência de controle glicêmico na população por {lbl}',
    )


# ──────────────────────────────────────────────────────────────
# ABA 3 — MEDICAMENTOS PRESCRITOS
# ──────────────────────────────────────────────────────────────
with tab_meds:
    st.markdown("### 3️⃣ Medicamentos prescritos")
    st.caption("Prevalência de cada classe farmacológica entre os pacientes diabéticos. Um paciente pode receber mais de uma classe.")

    # Antidiabéticos orais
    orais = [
        ('Biguanida (Metformina)',            'n_rx_biguanida'),
        ('Sulfonilureia',                     'n_rx_sulfonilureia'),
        ('iSGLT2 (Gliflozina)',              'n_rx_isglt2'),
        ('iDPP4 (Gliptina)',                 'n_rx_idpp4'),
        ('Agonista GLP-1',                   'n_rx_glp1'),
        ('Tiazolidinediona (glitazonas)',     'n_rx_tiazolidinediona'),
        ('Glinidas',                          'n_rx_glinida'),
        ('Acarbose',                          'n_rx_acarbose'),
    ]
    insulinas = [
        ('Insulina basal humana (NPH)',                                           'n_rx_ins_basal_humana'),
        ('Insulina prandial humana (Regular)',                                     'n_rx_ins_prandial_humana'),
        ('Insulina basal analógica (Glargina, Detemir, Degludeca)',               'n_rx_ins_basal_analogica'),
        ('Insulina prandial analógica (Lispro, Asparte, Glulisina, Fiasp)',       'n_rx_ins_prandial_analogica'),
        ('Insulina pré-misturada',                                                'n_rx_ins_mista'),
    ]

    st.markdown("**💊 Antidiabéticos orais**")
    ro1, ro2, ro3, ro4 = st.columns(4)
    for i, (label, key) in enumerate(orais):
        n = int(sumario.get(key, 0) or 0)
        col = [ro1, ro2, ro3, ro4][i % 4]
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.metric("Pacientes", f"{n:,}",
                          f"{_p(n, n_dm):.0f}% dos diabéticos")

    # Alertas em caixinhas
    n_sulfo_total = int(sumario.get('n_rx_sulfonilureia', 0) or 0)
    n_sulfo_mono  = int(sumario.get('n_rx_sulfo_monoterapia', 0) or 0)
    n_metf_alta   = int(sumario.get('n_rx_metformina_alta', 0) or 0)
    n_metf_total  = int(sumario.get('n_rx_biguanida', 0) or 0)

    al1, al2 = st.columns(2)
    with al1:
        with st.container(border=True):
            if n_sulfo_total > 0 and n_sulfo_mono > 0:
                st.warning(
                    f"⚠️ **Sulfonilureia como único antidiabético** (sem metformina, sem outros orais, sem insulina): "
                    f"**{n_sulfo_mono:,}** pacientes "
                    f"({_p(n_sulfo_mono, n_sulfo_total):.0f}% dos que usam sulfonilureia). "
                    f"Sulfonilureia isolada não é primeira linha — metformina deve ser o tratamento inicial na maioria dos casos."
                )
            else:
                st.success("✅ Nenhum paciente em monoterapia com sulfonilureia.")
    with al2:
        with st.container(border=True):
            if n_metf_total > 0 and n_metf_alta > 0:
                st.warning(
                    f"⚠️ **Metformina > 2.000 mg/dia:** "
                    f"**{n_metf_alta:,}** pacientes "
                    f"({_p(n_metf_alta, n_metf_total):.0f}% dos que usam metformina). "
                    f"Doses acima de 2.000 mg/dia aumentam efeitos gastrointestinais "
                    f"sem ganho proporcional de eficácia."
                )
            else:
                st.success("✅ Nenhum paciente com metformina acima de 2.000 mg/dia.")

    st.markdown("---")
    st.markdown("**💉 Insulinas**")
    ri1, ri2, ri3 = st.columns(3)
    for i, (label, key) in enumerate(insulinas):
        n = int(sumario.get(key, 0) or 0)
        col = [ri1, ri2, ri3][i % 3]
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.metric("Pacientes", f"{n:,}",
                          f"{_p(n, n_dm):.0f}% dos diabéticos")

    # Histograma de UI/kg de NPH
    st.markdown("---")
    st.markdown("**📊 Distribuição da dose de insulina NPH (UI/kg)**")
    st.caption(
        "Dose diária de NPH dividida pelo peso do paciente. "
        "Referência: 0,1–0,2 UI/kg para início; 0,3–0,5 UI/kg habitual; "
        ">1,0 UI/kg sugere resistência insulínica importante. "
        "Este gráfico exclui pacientes sem peso registrado ou com doses = 0 "
        "ou ainda doses acima de 1,5 UI/kg, consideradas erros de digitação."
    )

    df_nph = carregar_nph_ui_kg(ap_sel, cli_sel, esf_sel)
    if df_nph.empty or 'ui_kg' not in df_nph.columns:
        st.info("Sem dados de dose NPH + peso para os filtros selecionados.")
    else:
        df_nph = df_nph.dropna(subset=['ui_kg'])
        df_nph = df_nph[df_nph['ui_kg'] > 0]
        if df_nph.empty:
            st.info("Sem dados válidos de UI/kg.")
        else:
            media_ui = df_nph['ui_kg'].mean()
            mediana_ui = df_nph['ui_kg'].median()
            n_acima_1 = (df_nph['ui_kg'] > 1.0).sum()

            mi1, mi2, mi3, mi4 = st.columns(4)
            mi1.metric("Pacientes com dose calculável", f"{len(df_nph):,}")
            mi2.metric("Média UI/kg", f"{media_ui:.2f}")
            mi3.metric("Mediana UI/kg", f"{mediana_ui:.2f}")
            mi4.metric(">1,0 UI/kg (resistência)", f"{n_acima_1:,}",
                       f"{_p(n_acima_1, len(df_nph)):.0f}%", delta_color="inverse")

            n_bins = 150  # bins de ~0.01 UI/kg no range 0–1.5
            fig_nph = px.histogram(
                df_nph, x='ui_kg', nbins=n_bins,
                labels={'ui_kg': 'UI/kg/dia', 'count': 'Pacientes'},
                title='Distribuição da dose de NPH (UI/kg/dia)',
                color_discrete_sequence=['#3498DB'],
            )
            fig_nph.update_traces(
                marker_line_color='#1a5276',
                marker_line_width=0.8,
            )
            fig_nph.add_vline(x=0.5, line_dash="dash", line_color="#2ECC71",
                              annotation_text="0,5 UI/kg (habitual)")
            fig_nph.add_vline(x=1.0, line_dash="dash", line_color="#E74C3C",
                              annotation_text="1,0 UI/kg (resistência)")
            fig_nph.update_layout(
                height=420,
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
                font=dict(color=T.TEXT),
                margin=dict(l=60, r=20, t=50, b=60),
            )
            fig_nph.update_xaxes(range=[0, 1.5], title='UI/kg/dia')
            fig_nph.update_yaxes(title='Pacientes', gridcolor=T.GRID)
            st.plotly_chart(fig_nph, use_container_width=True)


# ──────────────────────────────────────────────────────────────
# ABA 4 — COMORBIDADES
# ──────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 4️⃣ Comorbidades associadas ao DM")
    st.caption("Sobreposição entre diabetes e comorbidades cardiovasculares e renais.")

    n_dm_has = int(rh.get('n_dm_has', 0) or 0)
    n_dm_irc = int(rh.get('n_dm_irc', 0) or 0)
    n_dm_ci  = int(rh.get('n_dm_ci',  0) or 0)
    n_dm_icc = int(rh.get('n_dm_icc', 0) or 0)
    n_dm_avc = int(rh.get('n_dm_avc', 0) or 0)

    dmc1, dmc2, dmc3, dmc4, dmc5 = st.columns(5)
    for col, val, label, emoji, cor_c, ajuda in [
        (dmc1, n_dm_has, 'HAS', '🩸', '#3498DB', 'DM+HAS: meta PA <130/80 mmHg. IECA/BRA como 1ª linha.'),
        (dmc2, n_dm_irc, 'IRC', '🫘', '#9B59B6', 'DM+IRC: IECA/BRA + SGLT-2 para nefroproteção.'),
        (dmc3, n_dm_ci,  'CI',  '💔', '#E74C3C', 'DM+CI: SGLT-2 + estatina alta intensidade + AAS.'),
        (dmc4, n_dm_icc, 'ICC', '🫀', '#E67E22', 'DM+ICC: SGLT-2 + IECA/BRA/INRA + BB + ARM.'),
        (dmc5, n_dm_avc, 'AVC', '🧠', '#1ABC9C', 'DM+AVC: risco muito alto. Controle rigoroso.'),
    ]:
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{label}**")
                st.markdown(f"## {val:,}")
                st.caption(f"{_p(val, n_dm):.1f}% dos diabéticos")
                st.caption(ajuda)

    # Heatmap
    grupos_dm  = ['HAS', 'IRC', 'CI', 'ICC', 'AVC']
    totais_dm  = [n_dm_has, n_dm_irc, n_dm_ci, n_dm_icc, n_dm_avc]
    cores_dm   = ['#3498DB', '#9B59B6', '#E74C3C', '#E67E22', '#1ABC9C']
    pares_dm   = {
        ('HAS','IRC'): int(rh.get('n_dm_has_irc',0) or 0),
        ('HAS','CI'):  int(rh.get('n_dm_has_ci', 0) or 0),
        ('HAS','ICC'): int(rh.get('n_dm_has_icc',0) or 0),
        ('HAS','AVC'): int(rh.get('n_dm_has_avc',0) or 0),
        ('IRC','CI'):  int(rh.get('n_dm_irc_ci', 0) or 0),
        ('IRC','ICC'): int(rh.get('n_dm_irc_icc',0) or 0),
        ('IRC','AVC'): int(rh.get('n_dm_irc_avc',0) or 0),
        ('CI', 'ICC'): int(rh.get('n_dm_ci_icc', 0) or 0),
        ('CI', 'AVC'): int(rh.get('n_dm_ci_avc', 0) or 0),
        ('ICC','AVC'): int(rh.get('n_dm_icc_avc',0) or 0),
    }
    nd = len(grupos_dm)
    mat_z   = np.zeros((nd, nd))
    mat_txt = [['']*nd for _ in range(nd)]
    for i in range(nd):
        for j in range(nd):
            val = totais_dm[i] if i == j else pares_dm.get((grupos_dm[min(i,j)], grupos_dm[max(i,j)]), 0)
            mat_z[i][j]   = val
            pct = _p(val, n_dm)
            mat_txt[i][j] = f"<b>{val:,}</b><br>{pct:.1f}%" if i==j else f"{val:,}<br>{pct:.1f}%"

    col_hm, col_leg = st.columns([3, 2])
    with col_hm:
        def _hex_rgba(h, a=0.13):
            h = h.lstrip('#')
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"
        fig_hm = go.Figure(data=go.Heatmap(
            z=mat_z.tolist(), x=grupos_dm, y=grupos_dm,
            text=mat_txt, texttemplate="%{text}",
            textfont=dict(size=12, color=T.TEXT),
            colorscale=T.HEATMAP_COLORSCALE, showscale=True,
            colorbar=dict(title=dict(text='Pacientes', font=dict(color=T.TEXT_SECONDARY, size=11)),
                          tickfont=dict(color=T.TEXT_SECONDARY, size=9), thickness=14, len=0.85,
                          bgcolor=T.PAPER_BG, bordercolor=T.PAPER_BG),
            hovertemplate="<b>DM + %{y} + %{x}</b><br>Pacientes: <b>%{z:,}</b><extra></extra>",
        ))
        for i, (nome, cor) in enumerate(zip(grupos_dm, cores_dm)):
            fig_hm.add_shape(type='rect', xref='x', yref='y',
                             x0=i-0.5, y0=i-0.5, x1=i+0.5, y1=i+0.5,
                             fillcolor=_hex_rgba(cor), line=dict(color=cor, width=3))
        fig_hm.update_layout(
            title=dict(text=f"Comorbidades em diabéticos<br>"
                            f"<sup style='color:{T.TEXT_MUTED}'>Total: {n_dm:,} · Diagonal = DM+comorbidade · Off-diagonal = interseção</sup>",
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
            for nome, val, cor in zip(grupos_dm, totais_dm, cores_dm):
                pct_g = _p(val, n_dm)
                bar_w = max(4, int(pct_g * 1.5))
                st.markdown(
                    f"<div style='margin-bottom:10px'>"
                    f"<span style='color:{cor};font-size:15px'>⬤</span> "
                    f"<span style='font-weight:700;color:{T.TEXT}'>{nome}</span><br>"
                    f"<span style='font-size:13px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_g:.1f}%</span><br>"
                    f"<div style='background:{cor};height:4px;width:{bar_w}%;border-radius:2px;opacity:0.7'></div>"
                    f"</div>", unsafe_allow_html=True
                )
        with sp:
            st.markdown(f"<p style='font-size:13px;font-weight:700;color:{T.TEXT_SECONDARY};margin-bottom:8px'>🔗 Sobreposições</p>", unsafe_allow_html=True)
            for (g1,g2), val in sorted(pares_dm.items(), key=lambda x: -x[1]):
                if val > 0:
                    c1 = cores_dm[grupos_dm.index(g1)]
                    c2 = cores_dm[grupos_dm.index(g2)]
                    st.markdown(
                        f"<div style='margin-bottom:8px'>"
                        f"<span style='color:{c1}'>⬤</span><span style='color:{c2}'>⬤</span> "
                        f"<span style='font-size:12px;color:{T.TEXT}'><b>{g1}+{g2}</b></span><br>"
                        f"<span style='font-size:12px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                        f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{_p(val,n_dm):.1f}%</span>"
                        f"</div>", unsafe_allow_html=True
                    )


# ──────────────────────────────────────────────────────────────
# ABA 4 — LACUNAS
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### 4️⃣ Lacunas de cuidado no DM")

    def _card(col, emoji, titulo, val, denom, denom_label, caption_txt):
        with col:
            with st.container(border=True):
                st.markdown(f"{emoji} **{titulo}**")
                st.markdown(f"## {_p(val, denom):.1f}%")
                st.metric("Pacientes", f"{val:,}", f"de {denom:,} ({denom_label})",
                          delta_color="inverse")
                st.caption(caption_txt)

    # Controle glicêmico
    st.markdown("**🩸 Controle Glicêmico**")
    g_ctrl = st.columns(4)
    _card(g_ctrl[0], "🔴", "DM não controlado",
          int(sumario.get('n_DM_descontrolado', 0) or 0), n_dm, "dos diabéticos",
          "HbA1c acima da meta nos últimos 180 dias.")
    _card(g_ctrl[1], "🟠", "Sem HbA1c recente (>180 dias)",
          int(sumario.get('n_DM_sem_hba1c', 0) or 0), n_dm, "dos diabéticos",
          "Sem exame de HbA1c nos últimos 6 meses.")
    _card(g_ctrl[2], "⛔", "HbA1c nunca solicitada",
          int(sumario.get('n_DM_hba1c_nao_sol', 0) or 0), n_dm, "dos diabéticos",
          "Sem nenhuma solicitação de HbA1c no histórico.")
    _card(g_ctrl[3], "🔵", "DM+HAS com PA não controlada",
          int(sumario.get('n_lac_dm_has_pa_desctrl', sumario.get('n_lac_dm_creatinina', 0)) or 0),
          n_dm, "dos diabéticos",
          "DM+HAS com PA >135/80 mmHg — meta mais restrita para diabéticos.")

    st.markdown("---")
    # Rastreio
    st.markdown("**🔍 Rastreio de Diabetes na População**")
    g_rastr = st.columns(2)
    _card(g_rastr[0], "🟣", "Hipertensos sem rastreio de DM",
          int(sumario.get('n_lac_rastreio_dm_has', 0) or 0), tot, "da população total",
          "Hipertensos sem glicemia ou HbA1c nos últimos 12 meses. Rastreio anual recomendado.")
    _card(g_rastr[1], "🟣", "Adultos ≥45 anos sem rastreio de DM",
          int(sumario.get('n_lac_rastreio_dm_45', 0) or 0), tot, "da população total",
          "A partir dos 45 anos, rastreio ao menos a cada 3 anos em assintomáticos.")

    st.markdown("---")
    # Exames
    st.markdown("**🔬 Exames Laboratoriais Mínimos para Diabéticos**")
    g_lab = st.columns(5)
    for col, emoji, titulo, chave, caption in [
        (g_lab[0], "🧪", "Sem creatinina no último ano",   'n_lac_dm_creatinina',
         "Essencial para estadiamento de DRC e ajuste de dose de metformina."),
        (g_lab[1], "🧪", "Sem colesterol no último ano",   'n_lac_dm_colesterol',
         "Perfil lipídico anual orienta terapia com estatinas."),
        (g_lab[2], "🧪", "Sem EAS no último ano",          'n_lac_dm_eas',
         "EAS identifica proteinúria — triagem de nefropatia diabética."),
        (g_lab[3], "🧫", "Sem microalbuminúria no último ano", 'n_lac_microalb',
         "Marcador mais precoce de nefropatia diabética. Detecta lesão renal reversível."),
        (g_lab[4], "⚖️", "Sem IMC calculável",             'n_lac_dm_imc',
         "Peso e altura não registrados. IMC guia metas e elegibilidade cirúrgica."),
    ]:
        _card(col, emoji, titulo, int(sumario.get(chave, 0) or 0), n_dm, "dos diabéticos", caption)

    st.markdown("---")
    # Pé diabético
    st.markdown("**🦶 Prevenção de Pé Diabético**")
    g_pe = st.columns(3)
    _card(g_pe[0], "🟠", "Sem exame do pé nos últimos 365 dias",
          int(sumario.get('n_lac_pe_365d', 0) or 0), n_dm, "dos diabéticos",
          "Meta mínima: ao menos 1 exame dos pés por ano.")
    _card(g_pe[1], "🟡", "Sem exame do pé nos últimos 180 dias",
          int(sumario.get('n_lac_pe_180d', 0) or 0), n_dm, "dos diabéticos",
          "Para diabéticos de maior risco, exame semestral recomendado.")
    _card(g_pe[2], "⛔", "Nunca teve exame do pé registrado",
          int(sumario.get('n_lac_pe_nunca', 0) or 0), n_dm, "dos diabéticos",
          "Prioridade máxima — risco elevado de úlcera e amputação não detectado.")

    st.markdown("---")
    # SGLT-2
    n_irc_sglt2  = int(sumario.get('n_lac_dm_irc_sglt2', 0) or 0)
    n_comp_sglt2 = int(sumario.get('n_lac_dm_comp_sglt2', 0) or 0)
    n_dm_irc_t   = int(sumario.get('n_dm_com_irc', 0) or 0)
    n_dm_comp_t  = int(sumario.get('n_dm_complicado_total', 0) or 0)
    n_irc_com    = int(sumario.get('n_dm_irc_com_sglt2', 0) or 0)
    n_comp_com   = int(sumario.get('n_dm_comp_com_sglt2', 0) or 0)

    if n_irc_sglt2 > 0 or n_comp_sglt2 > 0:
        st.markdown("**💊 Oportunidades de Proteção Orgânica — Inibidores SGLT-2**")
        g_sglt = st.columns(2)
        with g_sglt[0]:
            with st.container(border=True):
                st.markdown("💊 **DM+IRC sem SGLT-2**")
                st.markdown(f"**{n_dm_irc_t:,}** pacientes com DM+IRC — {n_irc_com:,} ({_p(n_irc_com, n_dm_irc_t):.1f}%) já têm SGLT-2.")
                st.markdown(f"## {_p(n_irc_sglt2, n_dm_irc_t):.1f}%")
                st.metric("Sem SGLT-2", f"{n_irc_sglt2:,}", f"dos {n_dm_irc_t:,} elegíveis", delta_color="inverse")
                st.caption("SGLT-2 reduz progressão de DRC, hospitalizações por ICC e eventos CV.")
        with g_sglt[1]:
            with st.container(border=True):
                st.markdown("💊 **DM complicado sem SGLT-2**")
                st.markdown(f"**{n_dm_comp_t:,}** pacientes com DM+CI/ICC/IRC — {n_comp_com:,} ({_p(n_comp_com, n_dm_comp_t):.1f}%) já têm SGLT-2.")
                st.markdown(f"## {_p(n_comp_sglt2, n_dm_comp_t):.1f}%")
                st.metric("Sem SGLT-2", f"{n_comp_sglt2:,}", f"dos {n_dm_comp_t:,} elegíveis", delta_color="inverse")
                st.caption("Indicação com grau de evidência A nas diretrizes internacionais.")

    st.caption("Lacunas calculadas sobre o denominador indicado em cada card.")


# ──────────────────────────────────────────────────────────────
# ABA 5 — LISTA NOMINAL
# ──────────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 👤 Lista Nominal de Pacientes com DM")
    st.caption(
        "Filtros de carga e HbA1c são enviados ao banco — o limite respeita o universo filtrado. "
        "Ordenação e demais filtros são aplicados localmente."
    )

    # ── Linha 1: Filtros que vão para o SQL ──────────────────
    sf1, sf2, sf3 = st.columns(3)
    with sf1:
        filtro_carga = st.multiselect(
            "Carga de Morbidade",
            options=["Muito Alto", "Alto", "Moderado", "Baixo"],
            default=[],
            placeholder="Todas",
            key="dm_lista_carga",
            help="Vazio = todas as categorias.",
        )
    with sf2:
        nunca_hba1c = st.toggle(
            "Nunca fez HbA1c",
            value=False, key="dm_lista_nunca_hba1c",
            help="Apenas pacientes sem nenhuma HbA1c registrada.",
        )
    with sf3:
        n_exibir = st.selectbox(
            "Exibir até",
            options=[50, 100, 250, 500, 1000],
            index=1, key="dm_lista_n",
        )

    # ── Linha 2: Ordenação + filtros locais ──────────────────
    lf1, lf2, lf3 = st.columns(3)
    with lf1:
        ORDEM_MAP = {
            "⚠️ Carga de morbidade (mais grave primeiro)":   "charlson_desc",
            "🔢 Número de morbidades (maior primeiro)":       "morbidades_desc",
            "👴 Idade (mais velhos primeiro)":                "idade_desc",
            "⏳ Mais tempo sem consulta médica":              "sem_medico",
            "🩸 HbA1c mais alta (não controlados primeiro)": "hba1c_desc",
        }
        ordem = st.selectbox(
            "Ordenar por",
            options=list(ORDEM_MAP.keys()),
            key="dm_lista_ordem",
        )
        ordem_key = ORDEM_MAP[ordem]
    with lf2:
        TEND_LABEL = {
            "piorando":              "📉 Piorando",
            "estavel":               "➡️ Estável",
            "melhorando":            "📈 Melhorando",
            "sem_referencia_previa": "❓ Apenas 1 HbA1c (sem tendência)",
        }
        filtro_tendencia = st.multiselect(
            "Filtrar por Tendência",
            options=list(TEND_LABEL.keys()),
            default=[],
            placeholder="Todas",
            format_func=lambda v: TEND_LABEL.get(v, v),
            key="dm_lista_tendencia",
            help="Quem não tem HbA1c é sempre incluído.",
        )
    with lf3:
        apenas_nao_ctrl = st.toggle(
            "Apenas não controlados",
            value=False, key="dm_lista_nao_ctrl",
            help="HbA1c acima da meta nos últimos 180 dias.",
        )
        sem_hba1c_recente = st.toggle(
            "Sem HbA1c recente (>180 dias)",
            value=False, key="dm_lista_sem_hba1c",
            help="Inclui quem nunca fez e quem tem exame desatualizado.",
        )

    # ── Carregar ─────────────────────────────────────────────
    with st.spinner("Carregando lista de pacientes..."):
        df_pac = carregar_pacientes_dm(
            ap_sel, cli_sel, esf_sel,
            limite=n_exibir,
            filtro_carga=filtro_carga if filtro_carga else None,
            nunca_hba1c=nunca_hba1c,
        )

    if df_pac.empty:
        st.info("Nenhum paciente encontrado para os critérios selecionados.")
    else:
        # Ordenação local
        df_pac = _ordenar_df(df_pac, ordem_key)
        n_total = len(df_pac)

        # Filtros locais — não afetam o LIMIT pois são pós-carregamento
        if filtro_tendencia:
            tem = df_pac["tendencia_hba1c"].notna()
            df_pac = df_pac[~tem | df_pac["tendencia_hba1c"].isin(filtro_tendencia)]

        if apenas_nao_ctrl:
            df_pac = df_pac[df_pac["status_controle_glicemico"] == "fora_da_meta"]

        if sem_hba1c_recente:
            df_pac = df_pac[
                df_pac["hba1c_atual"].isna() |
                (df_pac["dias_desde_ultima_hba1c"].notna() &
                 (df_pac["dias_desde_ultima_hba1c"] > 180))
            ]

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

        # ── Formatar e exibir tabela ──────────────────────────
        df_exib = df_pac.copy()
        df_exib['hba1c_atual'] = df_exib['hba1c_atual'].apply(
            lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
        )
        df_exib['data_hba1c_atual'] = pd.to_datetime(
            df_exib['data_hba1c_atual'], errors='coerce'
        ).dt.strftime('%d/%m/%Y')
        df_exib['dias_desde_ultima_medica'] = df_exib['dias_desde_ultima_medica'].apply(
            lambda v: f"{int(v)}d" if pd.notna(v) else "—"
        )
        df_exib['dose_NPH_ui_kg'] = df_exib['dose_NPH_ui_kg'].apply(
            lambda v: f"{v:.2f}" if pd.notna(v) and v > 0 else "—"
        )
        df_exib['dose_BIGUANIDA_mg_dia'] = df_exib['dose_BIGUANIDA_mg_dia'].apply(
            lambda v: f"{int(v)}" if pd.notna(v) and v > 0 else "—"
        )

        RENAME = {
            'nome':                      'Paciente',
            'idade':                     'Idade',
            'ap':                        'AP',
            'clinica':                   'Clínica',
            'esf':                       'ESF',
            'tipo_dm':                   'Tipo',
            'carga_morbidade':           'Carga de Morbidade',
            'cid_status':                'CID',
            'hba1c_atual':               'HbA1c',
            'data_hba1c_atual':          'Data HbA1c',
            'dias_desde_ultima_hba1c':   'Dias sem HbA1c',
            'status_controle_glicemico': 'Controle Glicêmico',
            'tendencia_hba1c':           'Tendência',
            'dias_desde_ultima_medica':  'Dias s/ médico',
            'consultas_medicas_365d':    'Consultas/ano',
            'total_morbidades':          'N° Morbidades',
            'morbidades_lista':          'Morbidades',
            'n_lacunas':                 'N° Lacunas',
            'lacunas_ativas':            'Lacunas',
            'total_medicamentos_cronicos': 'N° Medicamentos',
            'medicamentos':              'Medicamentos',
            'meds_dm':                   'Antidiabéticos',
            'dose_BIGUANIDA_mg_dia':     'Metformina (mg)',
            'dose_NPH_ui_kg':           'NPH (UI/kg)',
            'n_classes_antidiabeticos':  'N° Classes DM',
            'intensidade_tratamento_dm': 'Intensidade DM',
        }
        cols_show = [c for c in RENAME if c in df_exib.columns]
        df_show = df_exib[cols_show].rename(columns=RENAME)

        st.dataframe(
            df_show,
            hide_index=True,
            use_container_width=True,
            height=520,
            column_config={
                'HbA1c':               st.column_config.TextColumn('HbA1c',        width='small'),
                'Tipo':                st.column_config.TextColumn('Tipo',          width='small'),
                'CID':                 st.column_config.TextColumn('CID',           width='small'),
                'N° Morbidades':       st.column_config.NumberColumn('N° Morb.',    width='small'),
                'N° Lacunas':          st.column_config.NumberColumn('N° Lacunas',  width='small'),
                'N° Medicamentos':     st.column_config.NumberColumn('N° Meds',     width='small'),
                'Dias sem HbA1c':      st.column_config.NumberColumn('Dias sem HbA1c', format='%d d'),
                'Morbidades':          st.column_config.TextColumn('Morbidades',    width='large'),
                'Lacunas':             st.column_config.TextColumn('Lacunas',       width='large'),
                'Medicamentos':        st.column_config.TextColumn('Medicamentos',  width='large'),
                'Antidiabéticos':      st.column_config.TextColumn('Antidiabéticos', width='large'),
                'Clínica':             st.column_config.TextColumn('Clínica',       width='medium'),
                'Metformina (mg)':     st.column_config.TextColumn('Metformina (mg)', width='small'),
                'NPH (UI/kg)':         st.column_config.TextColumn('NPH (UI/kg)',  width='small'),
                'N° Classes DM':       st.column_config.NumberColumn('N° Classes DM', width='small'),
                'Intensidade DM':      st.column_config.TextColumn('Intensidade DM', width='medium'),
            }
        )

        csv = df_pac.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            "⬇️ Baixar lista (.csv)", csv,
            "pacientes_diabetes.csv", "text/csv",
        )

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ · Navegador Clínico · Diabetes Mellitus")