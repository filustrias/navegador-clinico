"""
Página: Polifarmácia e Carga Anticolinérgica
Análise de polifarmácia, carga de morbidade e escore ACB por território
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter
from components.filtros import filtros_territoriais
from utils.bigquery_client import get_bigquery_client
import config
import math

# ═══════════════════════════════════════════════════════════════
# ANONIMIZAÇÃO
# ═══════════════════════════════════════════════════════════════
def anonimizar_ap(x): return str(x) if x else x
def anonimizar_clinica(x): return str(x) if x else x
def anonimizar_esf(x): return str(x) if x else x
def anonimizar_nome(nome, genero=''):
    import random
    nomes_m = ['A.S.', 'J.R.', 'M.F.', 'C.O.', 'P.L.']
    nomes_f = ['M.S.', 'A.R.', 'F.O.', 'C.L.', 'P.M.']
    return random.choice(nomes_f if str(genero).lower() in ['f','feminino'] else nomes_m)
MODO_ANONIMO = False

from utils.auth import exibir_usuario_logado

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']
if isinstance(usuario_logado, dict):
    nome     = usuario_logado.get('nome_completo', 'Usuário')
    esf_usr  = usuario_logado.get('esf') or 'N/A'
    clinica_usr = usuario_logado.get('clinica') or 'N/A'
    ap_usr   = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf_usr = clinica_usr = ap_usr = 'N/A'

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO
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
    if esf_usr != 'N/A':  info_lines.append(f"ESF: {esf_usr}")
    if clinica_usr != 'N/A': info_lines.append(f"Clínica: {clinica_usr}")
    if ap_usr != 'N/A':   info_lines.append(f"AP: {ap_usr}")
    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: #FAFAFA; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Polifarmácia"
ROTAS = {
    "Home":           "Home.py",
    "População":      "pages/Minha_Populacao.py",
    "Pacientes":      "pages/Meus_Pacientes.py",
    "Lacunas":        "pages/Lacunas_de_Cuidado.py",
    "Continuidade":   "pages/Acesso_Continuidade.py",
    "Polifarmácia":   "pages/Polifarmacia_ACB.py",
}
ICONES = [
    "house-fill", "people-fill", "person-lines-fill",
    "exclamation-triangle-fill", "arrow-repeat", "capsule"
]
selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0!important",
            "background-color": "#0E1117",
        },
        "icon": {
            "font-size": "22px",
            "color": "#FAFAFA",
            "display": "block",
            "margin-bottom": "4px",
        },
        "nav-link": {
            "font-size": "11px",
            "text-align": "center",
            "margin": "0px",
            "padding": "10px 18px",
            "color": "#AAAAAA",
            "background-color": "#262730",
            "--hover-color": "#353540",
            "display": "flex",
            "flex-direction": "column",
            "align-items": "center",
            "line-height": "1.2",
            "white-space": "nowrap",
        },
        "nav-link-selected": {
            "background-color": "#404040",
            "color": "#FFFFFF",
            "font-weight": "600",
        },
    }
)
if selected != PAGINA_ATUAL:
    st.switch_page(ROTAS[selected])

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# BIGQUERY
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=900, show_spinner=False)
def run_query(query: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(query).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro ao executar query: {e}")
        return pd.DataFrame()

def _fqn(tabela: str) -> str:
    return f"`{config.PROJECT_ID}.{config.DATASET_ID}.{tabela}`"

def _where(ap=None, clinica=None, esf=None, extra=None) -> str:
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if extra:   clauses.extend(extra)
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""

# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def carregar_piramide_meds(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Dados para pirâmide etária de medicamentos.
    
    Sem filtro → usa MM_piramides_populacionais (rápido, pré-agregado).
    Com filtro  → calcula direto da tabela fato (garante dados para qualquer recorte).
    """
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    # ── Sem filtro: usa tabela pré-agregada ──────────────────
    if not clauses:
        sql = f"""
        SELECT
            faixa_etaria, genero,
            SUM(total_pacientes)              AS total_pacientes,
            SUM(n_nenhum_medicamento)         AS n_nenhum_medicamento,
            SUM(n_um_e_dois_medicamentos)     AS n_um_e_dois_medicamentos,
            SUM(n_tres_e_quatro_medicamentos) AS n_tres_e_quatro_medicamentos,
            SUM(n_polifarmacia)               AS n_polifarmacia,
            SUM(n_hiperpolifarmacia)          AS n_hiperpolifarmacia
        FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
        GROUP BY faixa_etaria, genero
        """
        return run_query(sql)

    # ── Com filtro: calcula da tabela fato ───────────────────
    sql = f"""
    SELECT
        CASE
            WHEN idade BETWEEN 0  AND 4  THEN '0-4'
            WHEN idade BETWEEN 5  AND 9  THEN '5-9'
            WHEN idade BETWEEN 10 AND 14 THEN '10-14'
            WHEN idade BETWEEN 15 AND 19 THEN '15-19'
            WHEN idade BETWEEN 20 AND 24 THEN '20-24'
            WHEN idade BETWEEN 25 AND 29 THEN '25-29'
            WHEN idade BETWEEN 30 AND 34 THEN '30-34'
            WHEN idade BETWEEN 35 AND 39 THEN '35-39'
            WHEN idade BETWEEN 40 AND 44 THEN '40-44'
            WHEN idade BETWEEN 45 AND 49 THEN '45-49'
            WHEN idade BETWEEN 50 AND 54 THEN '50-54'
            WHEN idade BETWEEN 55 AND 59 THEN '55-59'
            WHEN idade BETWEEN 60 AND 64 THEN '60-64'
            WHEN idade BETWEEN 65 AND 69 THEN '65-69'
            WHEN idade BETWEEN 70 AND 74 THEN '70-74'
            WHEN idade BETWEEN 75 AND 79 THEN '75-79'
            WHEN idade BETWEEN 80 AND 84 THEN '80-84'
            WHEN idade BETWEEN 85 AND 89 THEN '85-89'
            ELSE '90+'
        END AS faixa_etaria,
        CASE
            WHEN LOWER(genero) IN ('masculino', 'm') THEN 'masculino'
            ELSE 'feminino'
        END AS genero,
        COUNT(*)                                                        AS total_pacientes,
        COUNTIF(COALESCE(total_medicamentos_cronicos, 0) = 0)           AS n_nenhum_medicamento,
        COUNTIF(total_medicamentos_cronicos BETWEEN 1 AND 2)            AS n_um_e_dois_medicamentos,
        COUNTIF(total_medicamentos_cronicos BETWEEN 3 AND 4)            AS n_tres_e_quatro_medicamentos,
        COUNTIF(total_medicamentos_cronicos BETWEEN 5 AND 9)            AS n_polifarmacia,
        COUNTIF(total_medicamentos_cronicos >= 10)                      AS n_hiperpolifarmacia
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    GROUP BY faixa_etaria, genero
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_cards(ap=None, clinica=None, esf=None) -> dict:
    """Cards de resumo: totais de polifarmácia, hiperpolifarmácia, ACB."""
    where = _where(ap, clinica, esf)
    sql = f"""
    SELECT
        COUNT(*)                                              AS total_pacientes,
        COUNTIF(idade >= 65)                                  AS n_idosos,
        COUNTIF(polifarmacia = TRUE)                          AS n_polifarmacia,
        COUNTIF(hiperpolifarmacia = TRUE)                     AS n_hiperpolifarmacia,
        COUNTIF(COALESCE(acb_score_total, 0) >= 3)            AS n_acb_relevante,
        COUNTIF(alerta_acb_idoso = TRUE)                      AS n_acb_idoso,
        COUNTIF(COALESCE(acb_score_total, 0) >= 3
                AND polifarmacia = TRUE)                      AS n_acb_e_poli,
        ROUND(AVG(COALESCE(acb_score_total, 0)), 2)           AS media_acb,
        ROUND(AVG(total_medicamentos_cronicos), 1)            AS media_meds,
        MAX(COALESCE(acb_score_total, 0))                     AS max_acb,
        COUNTIF(total_morbidades >= 2)                        AS n_multimorbidos,
        COUNTIF(total_morbidades >= 2 AND idade >= 65)        AS n_multimorbidos_idosos
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    """
    df = run_query(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=900, show_spinner=False)
def carregar_polifarmacia_por_charlson(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Distribuição de faixas de medicamentos por categoria Charlson."""
    where = _where(ap, clinica, esf, extra=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        COUNTIF(total_medicamentos_cronicos = 0)                AS n_zero,
        COUNTIF(total_medicamentos_cronicos BETWEEN 1 AND 4)    AS n_1a4,
        COUNTIF(total_medicamentos_cronicos BETWEEN 5 AND 9)    AS n_poli,
        COUNTIF(total_medicamentos_cronicos >= 10)              AS n_hiperpoli,
        COUNT(*)                                                AS total
    FROM {_fqn(config.TABELA_FATO)}
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


@st.cache_data(ttl=900, show_spinner=False)
def carregar_acb_por_charlson(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """ACB score total por categoria Charlson (para violin)."""
    where = _where(ap, clinica, esf, extra=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'",
        "acb_score_total IS NOT NULL"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        COALESCE(acb_score_total, 0) AS acb_score_total
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_top_medicamentos_acb(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Top medicamentos anticolinérgicos prescritos, com seus scores."""
    where = _where(ap, clinica, esf, extra=[
        "medicamentos_acb_positivos IS NOT NULL",
        "medicamentos_acb_positivos != ''"
    ])
    sql = f"""
    SELECT medicamentos_acb_positivos
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    LIMIT 50000
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_lista_pacientes(ap=None, clinica=None, esf=None,
                              apenas_alerta_idoso=False) -> pd.DataFrame:
    """Lista nominal ordenada por ACB decrescente."""
    extra = ["f.acb_score_total IS NOT NULL"]
    if apenas_alerta_idoso:
        extra.append("f.alerta_acb_idoso = TRUE")
    # Monta WHERE com alias f. para evitar ambiguidade no JOIN
    clauses = []
    if ap:      clauses.append(f"f.area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"f.nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"f.nome_esf_cadastro = '{esf}'")
    clauses.extend(extra)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        f.nome, f.idade, f.genero,
        f.nome_esf_cadastro,
        f.nome_clinica_cadastro,
        -- Morbidades como string agrupada
        ARRAY_TO_STRING(
            ARRAY(SELECT m FROM UNNEST([
                IF(f.HAS IS NOT NULL,       'HAS', NULL),
                IF(f.DM IS NOT NULL,        'DM', NULL),
                IF(f.pre_DM IS NOT NULL,    'Pré-DM', NULL),
                IF(f.CI IS NOT NULL,        'CI', NULL),
                IF(f.ICC IS NOT NULL,       'ICC', NULL),
                IF(f.stroke IS NOT NULL,    'AVC', NULL),
                IF(f.IRC IS NOT NULL,       'IRC', NULL),
                IF(f.COPD IS NOT NULL,      'DPOC', NULL),
                IF(f.arritmia IS NOT NULL,  'Arritmia', NULL),
                IF(f.dementia IS NOT NULL,  'Demência', NULL),
                IF(f.HIV IS NOT NULL,       'HIV', NULL),
                IF(f.psicoses IS NOT NULL,  'Psicose', NULL),
                IF(f.depre_ansiedade IS NOT NULL, 'Depressão/Ans.', NULL),
                IF(f.obesidade_consolidada IS NOT NULL, 'Obesidade', NULL),
                IF(f.tireoide IS NOT NULL,  'Tireoide', NULL),
                IF(f.reumato IS NOT NULL,   'Reumato', NULL),
                IF(f.epilepsy IS NOT NULL,  'Epilepsia', NULL),
                IF(f.parkinsonism IS NOT NULL, 'Parkinson', NULL),
                IF(f.alcool IS NOT NULL,    'Álcool', NULL),
                IF(f.tabaco IS NOT NULL,    'Tabagismo', NULL),
                IF(f.liver IS NOT NULL,     'Hepatopatia', NULL),
                IF(f.neoplasia_mama IS NOT NULL
                   OR f.neoplasia_colo_uterino IS NOT NULL
                   OR f.neoplasia_feminina_estrita IS NOT NULL
                   OR f.neoplasia_masculina_estrita IS NOT NULL
                   OR f.neoplasia_ambos_os_sexos IS NOT NULL
                   OR f.leukemia IS NOT NULL
                   OR f.lymphoma IS NOT NULL
                   OR f.metastasis IS NOT NULL, 'Neoplasia', NULL)
            ]) AS m WHERE m IS NOT NULL),
        ', ') AS morbidades_lista,
        f.charlson_categoria,
        f.charlson_score,
        f.total_medicamentos_cronicos,
        f.polifarmacia,
        f.hiperpolifarmacia,
        f.acb_score_total,
        f.acb_score_cronicos,
        f.n_meds_acb_alto,
        f.medicamentos_acb_positivos,
        f.categoria_acb,
        f.alerta_acb_idoso,
        f.nucleo_cronico_atual,
        -- Critérios STOPP/START (vem de MM_stopp_start via JOIN)
        COALESCE(ss.total_criterios_stopp, 0)  AS total_stopp,
        COALESCE(ss.total_criterios_start, 0)  AS total_start,
        ss.alerta_prescricao_idoso_ativo,
        -- Flags individuais STOPP para montar string descritiva
        ss.stopp_snc_001_365d AS fl_benzo,
        ss.stopp_snc_002_365d AS fl_hipnotico_z,
        ss.stopp_snc_003_365d AS fl_tca,
        ss.stopp_snc_004_365d AS fl_tca_demencia,
        ss.stopp_snc_005_365d AS fl_paroxetina,
        ss.stopp_snc_006_365d AS fl_antipsic_tipico,
        ss.stopp_snc_007_365d AS fl_antipsic_park,
        ss.stopp_snc_008_365d AS fl_metoclopramida,
        ss.stopp_snc_009_365d AS fl_cascata_biperideno,
        ss.stopp_cv_001_365d  AS fl_anti_hipert_central,
        ss.stopp_cv_003_365d  AS fl_nifedipina,
        ss.stopp_cv_005_365d  AS fl_bcc_icc,
        ss.stopp_cv_006_365d  AS fl_diur_has,
        ss.stopp_cv_007_365d  AS fl_dronedarona,
        ss.stopp_end_001_365d AS fl_sulfonilureia,
        ss.stopp_end_002_365d AS fl_pioglitazona,
        ss.stopp_end_003_365d AS fl_metformina_irc,
        ss.stopp_end_004_365d AS fl_insulina_escala,
        ss.stopp_mus_001_365d AS fl_aine_irc,
        ss.stopp_mus_002_365d AS fl_aine_icc,
        ss.stopp_mus_003_365d AS fl_aine_has,
        ss.stopp_mus_004_365d AS fl_aine_anticoag,
        ss.stopp_mus_005_365d AS fl_cortic_ar,
        ss.stopp_mus_006_365d AS fl_relaxante,
        ss.stopp_acb_001_365d AS fl_acb4,
        ss.stopp_acb_002_365d AS fl_anti_hist,
        ss.stopp_acb_003_365d AS fl_anticolinerg_bexiga,
        ss.stopp_ren_001_365d AS fl_gabapentin_egfr,
        ss.stopp_ren_002_365d AS fl_espiro_egfr,
        ss.stopp_ren_003_365d AS fl_tramadol_egfr,
        ss.beers_004_365d     AS fl_aas_primaria,
        ss.beers_006_365d     AS fl_opioide_benzo,
        ss.beers_007_365d     AS fl_isrs_tramadol,
        -- Flags individuais START
        ss.start_cv_001_365d   AS fl_has_sem_tto,
        ss.start_cv_002_365d   AS fl_ci_sem_estatina,
        ss.start_cv_003_365d   AS fl_dcv_sem_antiplatelet,
        ss.start_cv_004_365d   AS fl_icc_sem_ieca,
        ss.start_cv_005_365d   AS fl_fa_sem_anticoag,
        ss.start_cv_006_365d   AS fl_dm_irc_sem_ieca,
        ss.start_snc_001_365d  AS fl_parkinson_sem_levo,
        ss.start_snc_002_365d  AS fl_depressao_sem_ad,
        ss.start_snc_003_365d  AS fl_demencia_sem_icolin,
        ss.start_resp_001_365d AS fl_dpoc_sem_bronco,
        -- Todos os medicamentos prescritos (crônicos + agudos) com posologia
        med.medicamentos_completos      AS todos_medicamentos,
        -- Total real (crônicos + agudos) para exibição
        COALESCE(med.qtd_agudos, 0)     AS qtd_agudos_med,
        -- Dicionário ACB: usado para enriquecer a lista
        med.medicamentos_acb_positivos  AS acb_positivos_ref
    FROM {_fqn(config.TABELA_FATO)} f
    LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_mantidos_alterados_ultimas` med
        ON f.cpf = med.cpf
    LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_stopp_start` ss
        ON f.cpf = ss.cpf
    {where}
    ORDER BY f.acb_score_total DESC, f.charlson_score DESC
    LIMIT 5000
    """
    return run_query(sql)




@st.cache_data(ttl=900, show_spinner=False)
def carregar_stopp_resumo(ap=None, clinica=None, esf=None) -> dict:
    """Cards e totais STOPP/START por território.
    
    Faz JOIN entre tabela fato (filtros territoriais) e MM_stopp_start (flags).
    """
    clauses = []
    if ap:      clauses.append(f"f.area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"f.nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"f.nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        COUNTIF(f.idade >= 65)                                              AS n_idosos,
        COUNTIF(f.idade >= 65 AND COALESCE(ss.total_criterios_stopp,0) > 0) AS n_stopp_ativo,
        COUNTIF(f.idade >= 65 AND COALESCE(ss.total_criterios_start,0) > 0) AS n_start_ativo,
        COUNTIF(ss.alerta_prescricao_idoso_ativo = TRUE)                    AS n_prioritario,
        -- STOPP individuais (365d = prescricao ativa)
        COUNTIF(ss.stopp_snc_001_365d = TRUE)  AS stopp_benzo,
        COUNTIF(ss.stopp_end_001_365d = TRUE)  AS stopp_sulfonilureia,
        COUNTIF(ss.stopp_acb_001_365d = TRUE)  AS stopp_acb4,
        COUNTIF(ss.stopp_snc_003_365d = TRUE)  AS stopp_tca,
        COUNTIF(ss.stopp_snc_006_365d = TRUE)  AS stopp_antipsic,
        COUNTIF(ss.stopp_snc_007_365d = TRUE)  AS stopp_antipsic_park,
        COUNTIF(ss.stopp_cv_001_365d  = TRUE)  AS stopp_anti_hipert,
        COUNTIF(ss.stopp_cv_003_365d  = TRUE)  AS stopp_nifedipina,
        COUNTIF(ss.stopp_mus_001_365d = TRUE)  AS stopp_aine_irc,
        COUNTIF(ss.stopp_mus_002_365d = TRUE)  AS stopp_aine_icc,
        COUNTIF(ss.stopp_mus_006_365d = TRUE)  AS stopp_relaxante,
        COUNTIF(ss.stopp_acb_002_365d = TRUE)  AS stopp_anti_hist,
        COUNTIF(ss.stopp_end_003_365d = TRUE)  AS stopp_metformina,
        COUNTIF(ss.stopp_end_004_365d = TRUE)  AS stopp_insulina_escala,
        COUNTIF(ss.stopp_snc_008_365d = TRUE)  AS stopp_metoclopramida,
        COUNTIF(ss.stopp_snc_009_365d = TRUE)  AS stopp_cascata_biperideno,
        -- START individuais
        COUNTIF(ss.start_cv_004_365d  = TRUE)  AS start_icc_sem_ieca,
        COUNTIF(ss.start_cv_005_365d  = TRUE)  AS start_fa_sem_anticoag,
        COUNTIF(ss.start_snc_003_365d = TRUE)  AS start_demencia,
        COUNTIF(ss.start_cv_002_365d  = TRUE)  AS start_ci_sem_estatina,
        COUNTIF(ss.start_cv_003_365d  = TRUE)  AS start_dcv_sem_antiplatelet,
        COUNTIF(ss.start_snc_001_365d = TRUE)  AS start_parkinson,
        COUNTIF(ss.start_snc_002_365d = TRUE)  AS start_depressao,
        COUNTIF(ss.start_resp_001_365d = TRUE) AS start_dpoc_sem_bronco,
        -- Beers exclusivos
        COUNTIF(ss.beers_004_365d = TRUE)      AS beers_aas_primaria,
        COUNTIF(ss.beers_006_365d = TRUE)      AS beers_opioide_benzo,
        COUNTIF(ss.beers_007_365d = TRUE)      AS beers_isrs_tramadol
    FROM `rj-sms-sandbox.sub_pav_us.{config.TABELA_FATO}` f
    LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_stopp_start` ss
        ON f.cpf = ss.cpf
    {where}
    """
    df = run_query(sql)
    return df.iloc[0].to_dict() if not df.empty else {}

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — FILTROS
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo = lambda: None
territorio = filtros_territoriais(
    key_prefix="poli",
    obrigatorio_esf=False,
    mostrar_todas_opcoes=True
)

# Persistência de aba
if 'aba_poli' not in st.session_state:
    st.session_state['aba_poli'] = 0

st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
NOMES_ABAS_POLI = [
    "👥 Panorama",
    "📊 Polifarmácia × Morbidade",
    "🔴 Carga Anticolinérgica",
    "⚠️ STOPP / START",
    "📋 Lista de Pacientes",
    "📖 Referência",
]
aba_sel = st.sidebar.radio(
    "", options=range(len(NOMES_ABAS_POLI)),
    format_func=lambda i: NOMES_ABAS_POLI[i],
    index=st.session_state['aba_poli'],
    key="nav_aba_poli",
    label_visibility="collapsed"
)
st.session_state['aba_poli'] = aba_sel

# ═══════════════════════════════════════════════════════════════
# TÍTULO
# ═══════════════════════════════════════════════════════════════
st.title("💊 Polifarmácia e Carga Anticolinérgica")
st.markdown(
    "Análise da carga medicamentosa, polifarmácia e escore ACB "
    "(*Anticholinergic Cognitive Burden*) por território e complexidade clínica."
)
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(NOMES_ABAS_POLI)

ap      = territorio.get('ap')
clinica = territorio.get('clinica')
esf     = territorio.get('esf')

# ──────────────────────────────────────────────────────────────
# ABA 1 — PANORAMA
# ──────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### 👥 Panorama da Carga Medicamentosa")

    with st.spinner("Carregando dados..."):
        cards   = carregar_cards(ap, clinica, esf)
        df_pir  = carregar_piramide_meds(ap, clinica, esf)

    if not cards:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        total   = int(cards.get('total_pacientes', 0)) or 1
        n_poli  = int(cards.get('n_polifarmacia', 0))
        n_hiper = int(cards.get('n_hiperpolifarmacia', 0))
        n_acb   = int(cards.get('n_acb_relevante', 0))
        n_acbi  = int(cards.get('n_acb_idoso', 0))
        media_acb  = round(float(cards.get('media_acb', 0)), 2)
        media_meds = round(float(cards.get('media_meds', 0)), 1)
        n_multi     = int(cards.get('n_multimorbidos', 0))
        n_multi_id  = int(cards.get('n_multimorbidos_idosos', 0))

        # ── Cards de alerta ────────────────────────────────────
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("👥 Pacientes",       f"{total:,}")
        c2.metric("💊 Média de meds",   f"{media_meds}",
                  help="Média de medicamentos crônicos por paciente")
        c3.metric("⚠️ Polifarmácia",
                  f"{n_poli:,}",
                  delta=f"{n_poli/total*100:.1f}%",
                  delta_color="inverse",
                  help="5–9 medicamentos crônicos simultâneos")
        c4.metric("🚨 Hiperpolifarmácia",
                  f"{n_hiper:,}",
                  delta=f"{n_hiper/total*100:.1f}%",
                  delta_color="inverse",
                  help="≥ 10 medicamentos crônicos simultâneos")
        c5.metric("🔴 ACB ≥ 3",
                  f"{n_acb:,}",
                  delta=f"{n_acb/total*100:.1f}%",
                  delta_color="inverse",
                  help="Carga anticolinérgica clinicamente relevante (Boustani 2008)")
        c6.metric("🧠 ACB ≥ 3 em ≥65a",
                  f"{n_acbi:,}",
                  delta=f"{n_acbi/total*100:.1f}%",
                  delta_color="inverse",
                  help="Risco aumentado de demência e quedas em idosos")

        st.markdown("---")
        # ── Segunda linha: multimorbidade + STOPP/START (6 cards) ─

        with st.spinner(""):
            dados_ss_pan = carregar_stopp_resumo(ap, clinica, esf)

        if dados_ss_pan:
            n_id_pan    = int(dados_ss_pan.get("n_idosos",      0)) or 1
            n_stopp_pan = int(dados_ss_pan.get("n_stopp_ativo", 0))
            n_start_pan = int(dados_ss_pan.get("n_start_ativo", 0))
            n_prio_pan  = int(dados_ss_pan.get("n_prioritario", 0))

            r1, r2, r3, r4, r5, r6 = st.columns(6)
            r1.metric("🦠 Multimórbidos",
                      f"{n_multi:,}",
                      delta=f"{n_multi/total*100:.1f}%",
                      help="Pacientes com 2 ou mais morbidades crônicas registradas")
            r2.metric("🧓 Multimórb. ≥65a",
                      f"{n_multi_id:,}",
                      delta=f"{n_multi_id/total*100:.1f}%",
                      help="Multimórbidos com 65 anos ou mais — população de maior risco")
            r3.metric("🧓 Idosos (≥65a)",   f"{n_id_pan:,}")
            r4.metric("🚫 Com STOPP ativo",
                      f"{n_stopp_pan:,}",
                      delta=f"{n_stopp_pan/n_id_pan*100:.1f}%",
                      delta_color="inverse",
                      help="Pelo menos 1 medicamento inapropriado prescrito nos últimos 365 dias (STOPP v.2 + Beers 2023)")
            r5.metric("❌ Com omissão START",
                      f"{n_start_pan:,}",
                      delta=f"{n_start_pan/n_id_pan*100:.1f}%",
                      delta_color="inverse",
                      help="Pelo menos 1 medicamento indicado ausente na prescrição (START v.2)")
            r6.metric("🚨 Alerta prioritário",
                      f"{n_prio_pan:,}",
                      delta=f"{n_prio_pan/n_id_pan*100:.1f}%",
                      delta_color="inverse",
                      help="Critério STOPP grave ativo + paciente em acompanhamento nos últimos 365 dias")

        st.markdown("---")

        # ── Pirâmide ───────────────────────────────────────────
        st.subheader("🔺 Pirâmide Etária por Carga Medicamentosa")
        st.caption(
            "Cada barra representa uma faixa etária estratificada pela quantidade "
            "de medicamentos crônicos em uso. "
            "Masculino à esquerda, Feminino à direita."
        )

        if df_pir.empty:
            st.warning("Dados de pirâmide não disponíveis.")
        else:
            ordem_faixas = [
                '0-4','5-9','10-14','15-19','20-24','25-29','30-34',
                '35-39','40-44','45-49','50-54','55-59','60-64',
                '65-69','70-74','75-79','80-84','85-89','90+'
            ]
            df_pir['faixa_etaria'] = pd.Categorical(
                df_pir['faixa_etaria'], categories=ordem_faixas, ordered=True
            )
            df_pir = df_pir.sort_values('faixa_etaria')

            generos = df_pir['genero'].unique()
            col_m = 'masculino' if 'masculino' in generos else 'M'
            col_f = 'feminino'  if 'feminino'  in generos else 'F'
            df_m = df_pir[df_pir['genero'] == col_m].copy()
            df_f = df_pir[df_pir['genero'] == col_f].copy()

            cores_meds = ['#4A90D9', '#5BA85A', '#E8A838', '#D95F5F', '#9B59B6']
            estratos = [
                ('n_hiperpolifarmacia',          'Hiperpolifarmácia (≥10)',  cores_meds[4]),
                ('n_polifarmacia',               'Polifarmácia (5–9)',       cores_meds[3]),
                ('n_tres_e_quatro_medicamentos', '3–4 medicamentos',         cores_meds[2]),
                ('n_um_e_dois_medicamentos',     '1–2 medicamentos',         cores_meds[1]),
                ('n_nenhum_medicamento',         '0 medicamentos',           cores_meds[0]),
            ]

            fig_pir = go.Figure()
            for campo, label, cor in estratos:
                if campo in df_m.columns:
                    fig_pir.add_trace(go.Bar(
                        y=df_m['faixa_etaria'], x=-df_m[campo],
                        name=label, orientation='h',
                        marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                        legendgroup=label, showlegend=True,
                        hovertemplate='<b>%{y} — Homens</b><br>' + label + ': %{text:,}<extra></extra>',
                        text=df_m[campo]
                    ))
            for campo, label, cor in estratos:
                if campo in df_f.columns:
                    fig_pir.add_trace(go.Bar(
                        y=df_f['faixa_etaria'], x=df_f[campo],
                        name=label, orientation='h',
                        marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                        legendgroup=label, showlegend=False,
                        hovertemplate='<b>%{y} — Mulheres</b><br>' + label + ': %{x:,}<extra></extra>',
                    ))

            cols_sum = [c for c, *_ in estratos if c in df_m.columns]
            max_val = max(
                df_m[cols_sum].sum(axis=1).max() if cols_sum else 0,
                df_f[cols_sum].sum(axis=1).max() if cols_sum else 0
            )
            step = max(100, int(max_val / 5 / 100) * 100)
            ticks = list(range(0, int(max_val * 1.15), step))
            tick_vals  = [-t for t in ticks] + ticks
            tick_texts = [str(t) for t in ticks] + [str(t) for t in ticks]

            fig_pir.update_layout(
                barmode='relative',
                height=650,
                xaxis=dict(tickvals=tick_vals, ticktext=tick_texts,
                           title="Número de Pacientes",
                           gridcolor='rgba(255,255,255,0.08)'),
                yaxis=dict(title="Faixa Etária"),
                legend=dict(orientation='h', yanchor='bottom', y=1.02,
                            xanchor='right', x=1),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=60, r=40, t=60, b=60),
                annotations=[
                    dict(x=-max_val*0.5, y=1.02, xref='x', yref='paper',
                         text='◀ Masculino', showarrow=False,
                         font=dict(size=13, color='#AAAAAA')),
                    dict(x=max_val*0.5, y=1.02, xref='x', yref='paper',
                         text='Feminino ▶', showarrow=False,
                         font=dict(size=13, color='#AAAAAA')),
                ]
            )
            st.plotly_chart(fig_pir, use_container_width=True)
            st.caption(
                "⚠️ A concentração de polifarmácia e hiperpolifarmácia nas faixas etárias mais "
                "avançadas é esperada clinicamente, mas exige atenção especial ao risco de "
                "interações medicamentosas e carga anticolinérgica acumulada."
            )


# ──────────────────────────────────────────────────────────────
# ABA 2 — POLIFARMÁCIA × MORBIDADE
# ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown("""
    ### 📊 Polifarmácia por Categoria de Carga de Morbidade (Charlson)

    Pacientes com maior carga de morbidade naturalmente tendem a usar mais medicamentos.
    O gráfico abaixo verifica se esse padrão se sustenta na população — e identifica
    grupos onde a prescrição pode estar aquém ou além do esperado.
    """)

    with st.spinner("Carregando dados..."):
        df_ch = carregar_polifarmacia_por_charlson(ap, clinica, esf)

    if df_ch.empty:
        st.warning("Nenhum dado encontrado.")
    else:
        # ── Barras 100% empilhadas ─────────────────────────────
        df_pct = df_ch.copy()
        for col in ['n_zero', 'n_1a4', 'n_poli', 'n_hiperpoli']:
            df_pct[col + '_pct'] = (df_pct[col] / df_pct['total'] * 100).round(1)

        cores_faixas = {
            '0 meds':             '#4A90D9',
            '1–4 meds':           '#5BA85A',
            'Polifarmácia (5–9)': '#E8A838',
            'Hiperpolifarmácia (≥10)': '#D95F5F',
        }

        fig_bar = go.Figure()
        dados_barras = [
            ('n_zero_pct',     'n_zero',     '0 meds',                  '#4A90D9'),
            ('n_1a4_pct',      'n_1a4',      '1–4 meds',                '#5BA85A'),
            ('n_poli_pct',     'n_poli',      'Polifarmácia (5–9)',      '#E8A838'),
            ('n_hiperpoli_pct','n_hiperpoli', 'Hiperpolifarmácia (≥10)', '#D95F5F'),
        ]
        for col_pct, col_n, label, cor in dados_barras:
            fig_bar.add_trace(go.Bar(
                name=label,
                x=df_pct['charlson_categoria'],
                y=df_pct[col_pct],
                marker_color=cor,
                text=df_pct.apply(
                    lambda r: f"{r[col_pct]:.1f}%<br>({int(r[col_n]):,})", axis=1
                ),
                textposition='inside',
                insidetextanchor='middle',
                textfont=dict(size=11),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{label}: %{{y:.1f}}%<br>"
                    "N: %{customdata:,}<extra></extra>"
                ),
                customdata=df_pct[col_n]
            ))

        fig_bar.update_layout(
            barmode='stack',
            xaxis=dict(title="Carga de Morbidade",
                       categoryorder='array',
                       categoryarray=['Muito Alto', 'Alto', 'Moderado', 'Baixo']),
            yaxis=dict(title="% de Pacientes", range=[0, 100]),
            legend=dict(orientation='h', yanchor='bottom', y=1.02,
                        xanchor='right', x=1),
            height=460,
            margin=dict(t=80, b=60),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.caption(
            "Cada barra soma 100%. Quanto maior a fatia laranja + vermelha em categorias "
            "de alto risco, maior a sobreposição entre complexidade clínica e polifarmácia — "
            "um sinal de alerta para revisão de prescrições."
        )

        st.markdown("---")

        # ── Tabela resumo ──────────────────────────────────────
        st.subheader("📋 Resumo por Carga de Morbidade")
        df_exib = df_ch[['charlson_categoria','total','n_zero','n_1a4','n_poli','n_hiperpoli']].copy()
        df_exib['% Polifarm.']  = (df_exib['n_poli']      / df_exib['total'] * 100).round(1)
        df_exib['% Hiperp.']    = (df_exib['n_hiperpoli'] / df_exib['total'] * 100).round(1)
        df_exib.columns = [
            'Carga de Morbidade', 'Total', '0 meds', '1–4 meds',
            'Polifarm. (5–9)', 'Hiperp. (≥10)',
            '% Polifarm.', '% Hiperp.'
        ]
        st.dataframe(
            df_exib,
            hide_index=True,
            use_container_width=False,
            width=820,
            column_config={
                'Carga de Morbidade': st.column_config.TextColumn(width=170),
                'Total':              st.column_config.NumberColumn(width=80),
                '0 meds':             st.column_config.NumberColumn(width=80),
                '1–4 meds':           st.column_config.NumberColumn(width=90),
                'Polifarm. (5–9)':    st.column_config.NumberColumn(width=110),
                'Hiperp. (≥10)':      st.column_config.NumberColumn(width=100),
                '% Polifarm.':        st.column_config.NumberColumn(width=100, format="%.1f%%"),
                '% Hiperp.':          st.column_config.NumberColumn(width=90,  format="%.1f%%"),
            }
        )


# ──────────────────────────────────────────────────────────────
# ABA 3 — CARGA ANTICOLINÉRGICA (ACB)
# ──────────────────────────────────────────────────────────────
with tab3:
    st.markdown("""
    ### 🔴 Carga Anticolinérgica (ACB — *Anticholinergic Cognitive Burden*)

    A escala ACB pontua medicamentos de acordo com seu potencial anticolinérgico:
    **score 1** = efeito possível; **score 2** = efeito estabelecido;
    **score 3** = efeito clinicamente relevante.
    O **score total ≥ 3** indica carga clinicamente significativa associada a
    comprometimento cognitivo e aumento de mortalidade
    *(Boustani et al., Aging Health 2008)*.
    """)

    with st.spinner("Carregando dados de ACB..."):
        df_acb_ch  = carregar_acb_por_charlson(ap, clinica, esf)
        df_meds_acb = carregar_top_medicamentos_acb(ap, clinica, esf)

    col_v, col_t = st.columns([1, 1])

    # ── Esquerda: violin ACB × Charlson ───────────────────────
    with col_v:
        st.subheader("Distribuição ACB por Complexidade Clínica")
        if df_acb_ch.empty:
            st.warning("Sem dados.")
        else:
            ordem_cat = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
            fig_viol = px.violin(
                df_acb_ch,
                x='charlson_categoria',
                y='acb_score_total',
                color='charlson_categoria',
                category_orders={'charlson_categoria': ordem_cat},
                labels={
                    'acb_score_total': 'ACB Score Total',
                    'charlson_categoria': 'Categoria Charlson'
                },
                box=True,
                points=False,
                height=480,
            )
            fig_viol.update_traces(
                meanline_visible=True,
                spanmode='hard',
            )
            # Linha de referência ACB = 3
            fig_viol.add_hline(
                y=3, line_dash='dash', line_color='#FF4444', line_width=2,
                annotation_text='Limiar clínico (ACB = 3)',
                annotation_position='top right',
                annotation_font_color='#FF4444'
            )
            fig_viol.update_layout(
                showlegend=False,
                xaxis=dict(title="Carga de Morbidade"),
                yaxis=dict(title="ACB Score Total", zeroline=False),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=60, b=60),
            )
            st.plotly_chart(fig_viol, use_container_width=True)
            st.caption(
                "A linha vermelha tracejada marca o limiar clínico (ACB ≥ 3). "
                "Pacientes acima dela têm risco aumentado de efeitos cognitivos adversos."
            )

    # ── Direita: top medicamentos ACB ─────────────────────────
    with col_t:
        st.subheader("Top Medicamentos Anticolinérgicos Prescritos")
        if df_meds_acb.empty:
            st.warning("Sem dados.")
        else:
            # Parsear string "Medicamento(score); Medicamento(score)"
            contagens = Counter()
            scores_map = {}
            for row in df_meds_acb['medicamentos_acb_positivos'].dropna():
                for item in str(row).split(';'):
                    item = item.strip()
                    if not item:
                        continue
                    import re
                    m = re.match(r'^(.+)\((\d)\)$', item)
                    if m:
                        nome_med = m.group(1).strip()
                        score    = int(m.group(2))
                        contagens[nome_med] += 1
                        scores_map[nome_med] = score

            if not contagens:
                st.warning("Nenhum medicamento anticolinérgico identificado.")
            else:
                top_n = 15
                top_meds = contagens.most_common(top_n)
                nomes  = [m for m, _ in top_meds]
                counts = [c for _, c in top_meds]
                scores = [scores_map.get(m, 1) for m in nomes]

                cor_score = {1: '#F4D03F', 2: '#E67E22', 3: '#E74C3C'}
                cores_barras = [cor_score.get(s, '#888') for s in scores]

                fig_top = go.Figure(go.Bar(
                    y=nomes[::-1],
                    x=counts[::-1],
                    orientation='h',
                    marker=dict(
                        color=cores_barras[::-1],
                        line=dict(color='rgba(0,0,0,0.3)', width=0.5)
                    ),
                    text=[f"Score {s}" for s in scores[::-1]],
                    textposition='inside',
                    insidetextanchor='middle',
                    textfont=dict(size=10, color='white'),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Pacientes: %{x:,}<extra></extra>"
                    )
                ))
                fig_top.update_layout(
                    xaxis=dict(title="Número de Pacientes"),
                    yaxis=dict(title=""),
                    height=480,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=160, r=40, t=20, b=60),
                )
                st.plotly_chart(fig_top, use_container_width=True)
                st.caption(
                    "🟡 Score 1 = possível efeito &nbsp;|&nbsp; "
                    "🟠 Score 2 = efeito estabelecido &nbsp;|&nbsp; "
                    "🔴 Score 3 = clinicamente relevante"
                )

    st.markdown("---")

    # ── Distribuição de categorias ACB ────────────────────────
    st.subheader("📊 Distribuição por Categoria ACB na População")
    cards2 = carregar_cards(ap, clinica, esf)
    if cards2:
        total2 = int(cards2.get('total_pacientes', 1))
        n_acb2 = int(cards2.get('n_acb_relevante', 0))
        n_acbi2 = int(cards2.get('n_acb_idoso', 0))
        st.info(
            f"**{n_acb2:,} pacientes ({n_acb2/total2*100:.1f}%)** têm ACB ≥ 3 "
            f"(carga clinicamente relevante). "
            f"Desses, **{n_acbi2:,} têm 65 anos ou mais**, com risco aumentado "
            f"de comprometimento cognitivo e quedas."
        )


# ──────────────────────────────────────────────────────────────
# ABA 4 — STOPP / START / BEERS
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### ⚠️ Prescrição Potencialmente Inapropriada — STOPP / START / Beers 2023")
    st.caption(
        "Critérios aplicados apenas a pacientes **≥ 65 anos**. "
        "Flags _365d indicam prescrição ativa nos últimos 12 meses. "
        "Ref: STOPP/START v.2 (O\'Mahony 2015) · AGS Beers Criteria 2023."
    )

    with st.spinner("Carregando dados STOPP/START..."):
        dados_ss = carregar_stopp_resumo(ap, clinica, esf)

    if not dados_ss:
        st.warning("Nenhum dado encontrado.")
    else:
        n_id    = int(dados_ss.get("n_idosos", 0)) or 1
        n_stopp = int(dados_ss.get("n_stopp_ativo", 0))
        n_start = int(dados_ss.get("n_start_ativo", 0))
        n_prio  = int(dados_ss.get("n_prioritario", 0))

        # ── Cards de resumo ──────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🧓 Idosos (≥65a)",          f"{n_id:,}")
        c2.metric("🚫 Com critério STOPP",
                  f"{n_stopp:,}",
                  delta=f"{n_stopp/n_id*100:.1f}%",
                  delta_color="inverse",
                  help="Pelo menos 1 medicamento inapropriado prescrito nos últimos 365 dias")
        c3.metric("❌ Com omissão START",
                  f"{n_start:,}",
                  delta=f"{n_start/n_id*100:.1f}%",
                  delta_color="inverse",
                  help="Pelo menos 1 medicamento indicado ausente na prescrição")
        c4.metric("🚨 Alerta prioritário",
                  f"{n_prio:,}",
                  delta=f"{n_prio/n_id*100:.1f}%",
                  delta_color="inverse",
                  help="Critério grave ativo + paciente em acompanhamento nos últimos 365 dias")

        st.markdown("---")

        col_stopp, col_start = st.columns([1, 1])

        # ── Ranking STOPP ─────────────────────────────────────
        with col_stopp:
            st.subheader("🚫 Critérios STOPP ativos (últimos 365 dias)")
            stopp_dados = [
                ("Benzodiazepínico",           dados_ss.get("stopp_benzo", 0)),
                ("Sulfonilureia longa ação",    dados_ss.get("stopp_sulfonilureia", 0)),
                ("ACB ≥ 4",                    dados_ss.get("stopp_acb4", 0)),
                ("Antidepressivo tricíclico",   dados_ss.get("stopp_tca", 0)),
                ("Antipsicótico típico",        dados_ss.get("stopp_antipsic", 0)),
                ("Antipsicót. + Parkinson/dem.",dados_ss.get("stopp_antipsic_park", 0)),
                ("Anti-hipert. central",        dados_ss.get("stopp_anti_hipert", 0)),
                ("Anti-histam. 1ª geração",     dados_ss.get("stopp_anti_hist", 0)),
                ("Nifedipina imediata",         dados_ss.get("stopp_nifedipina", 0)),
                ("Relaxante muscular",          dados_ss.get("stopp_relaxante", 0)),
                ("Metoclopramida + Parkinson",  dados_ss.get("stopp_metoclopramida", 0)),
                ("Metformina eGFR < 30",        dados_ss.get("stopp_metformina", 0)),
                ("Insulina escala móvel",       dados_ss.get("stopp_insulina_escala", 0)),
                ("AINE + ICC",                  dados_ss.get("stopp_aine_icc", 0)),
                ("AINE + IRC eGFR < 50",        dados_ss.get("stopp_aine_irc", 0)),
                ("Cascata biperideno",          dados_ss.get("stopp_cascata_biperideno", 0)),
            ]
            stopp_dados = [(l, v) for l, v in stopp_dados if v > 0]
            stopp_dados.sort(key=lambda x: x[1], reverse=True)

            if stopp_dados:
                import plotly.graph_objects as go
                labels_s = [l for l, _ in stopp_dados]
                values_s = [v for _, v in stopp_dados]
                fig_stopp = go.Figure(go.Bar(
                    y=labels_s[::-1], x=values_s[::-1],
                    orientation="h",
                    marker_color="#E24B4A",
                    text=[f"{v:,}" for v in values_s[::-1]],
                    textposition="outside",
                    textfont=dict(size=11),
                    hovertemplate="<b>%{y}</b><br>Pacientes: %{x:,}<extra></extra>"
                ))
                fig_stopp.update_layout(
                    height=max(350, len(stopp_dados) * 38),
                    xaxis=dict(title="Pacientes idosos afetados"),
                    yaxis=dict(title=""),
                    margin=dict(l=10, r=80, t=20, b=40),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_stopp, use_container_width=True)
                st.caption("Medicamentos potencialmente inapropriados — prescrição ativa nos últimos 12 meses.")
            else:
                st.info("Nenhum critério STOPP ativo encontrado para este território.")

        # ── Ranking START + Beers ─────────────────────────────
        with col_start:
            st.subheader("❌ Omissões terapêuticas START")
            start_dados = [
                ("FA sem anticoagulação",       dados_ss.get("start_fa_sem_anticoag", 0)),
                ("Demência sem icolinesterase",  dados_ss.get("start_demencia", 0)),
                ("ICC sem IECA/BRA",             dados_ss.get("start_icc_sem_ieca", 0)),
                ("CI sem estatina",              dados_ss.get("start_ci_sem_estatina", 0)),
                ("DCV sem antiplaquetário",      dados_ss.get("start_dcv_sem_antiplatelet", 0)),
                ("Depressão sem antidepress.",   dados_ss.get("start_depressao", 0)),
                ("Parkinson sem levodopa",       dados_ss.get("start_parkinson", 0)),
                ("DPOC/Asma sem broncodilatador",dados_ss.get("start_dpoc_sem_bronco", 0)),
            ]
            start_dados = [(l, v) for l, v in start_dados if v > 0]
            start_dados.sort(key=lambda x: x[1], reverse=True)

            if start_dados:
                labels_t = [l for l, _ in start_dados]
                values_t = [v for _, v in start_dados]
                fig_start = go.Figure(go.Bar(
                    y=labels_t[::-1], x=values_t[::-1],
                    orientation="h",
                    marker_color="#1D9E75",
                    text=[f"{v:,}" for v in values_t[::-1]],
                    textposition="outside",
                    textfont=dict(size=11),
                    hovertemplate="<b>%{y}</b><br>Pacientes: %{x:,}<extra></extra>"
                ))
                fig_start.update_layout(
                    height=max(300, len(start_dados) * 38),
                    xaxis=dict(title="Pacientes idosos afetados"),
                    yaxis=dict(title=""),
                    margin=dict(l=10, r=80, t=20, b=40),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_start, use_container_width=True)
                st.caption("Medicamentos indicados ausentes na prescrição — oportunidades de melhoria.")
            else:
                st.info("Nenhuma omissão START identificada para este território.")

            st.markdown("---")
            st.subheader("🔵 Beers 2023")
            st.caption(
                "Critérios americanos que complementam o STOPP, com foco em situações "
                "específicas de risco em idosos. **AAS em prevenção primária** foi movido "
                "de 'usar com cautela' para 'evitar' na versão 2023, alinhado com a USPSTF. "
                "**Opioide + benzodiazepínico** é a combinação com maior risco de depressão "
                "respiratória e overdose — especialmente perigosa em idosos. "
                "**ISRS + Tramadol** pode desencadear síndrome serotonérgica."
            )
            b1, b2, b3 = st.columns(3)
            b1.metric("AAS prevenção primária ≥60a",
                      f"{int(dados_ss.get('beers_aas_primaria', 0)):,}",
                      help="AAS prescrito sem DCV estabelecida — Beers 2023 recomenda evitar")
            b2.metric("Opioide + Benzodiazepínico",
                      f"{int(dados_ss.get('beers_opioide_benzo', 0)):,}",
                      help="Combinação associada a depressão respiratória e overdose")
            b3.metric("ISRS + Tramadol",
                      f"{int(dados_ss.get('beers_isrs_tramadol', 0)):,}",
                      help="Risco de síndrome serotonérgica")

# ──────────────────────────────────────────────────────────────
# ABA 5 — LISTA DE PACIENTES
# ──────────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 📋 Lista Nominal — Ordenada por Carga Anticolinérgica")

    # ── Cards de resumo (respondem aos filtros de território) ──
    with st.spinner("Carregando resumo..."):
        cards4 = carregar_cards(ap, clinica, esf)

    if cards4:
        total4  = int(cards4.get('total_pacientes', 0)) or 1
        n_id4   = int(cards4.get('n_idosos', 0))
        n_po4   = int(cards4.get('n_polifarmacia', 0))
        n_hi4   = int(cards4.get('n_hiperpolifarmacia', 0))
        n_acb4  = int(cards4.get('n_acb_relevante', 0))
        n_acbi4 = int(cards4.get('n_acb_idoso', 0))
        n_both4 = int(cards4.get('n_acb_e_poli', 0))
        m_acb4  = float(cards4.get('media_acb', 0))
        m_med4  = float(cards4.get('media_meds', 0))
        max_acb4= int(cards4.get('max_acb', 0))

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("👥 Total de pacientes",    f"{total4:,}")
        r1c2.metric("🧓 Idosos (≥65 anos)",     f"{n_id4:,}",
                    delta=f"{n_id4/total4*100:.1f}%")
        r1c3.metric("💊 Média de meds crônicos", f"{m_med4}")
        r1c4.metric("📈 ACB médio / máximo",    f"{m_acb4} / {max_acb4}")

        st.markdown("")
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        r2c1.metric("⚠️ Polifarmácia (5–9)",
                    f"{n_po4:,}",
                    delta=f"{n_po4/total4*100:.1f}%",
                    delta_color="inverse")
        r2c2.metric("🚨 Hiperpolifarmácia (≥10)",
                    f"{n_hi4:,}",
                    delta=f"{n_hi4/total4*100:.1f}%",
                    delta_color="inverse")
        r2c3.metric("🔴 ACB ≥ 3 (carga relevante)",
                    f"{n_acb4:,}",
                    delta=f"{n_acb4/total4*100:.1f}%",
                    delta_color="inverse",
                    help="Ponto de corte clínico — Boustani et al., 2008")
        r2c4.metric("🧠 ACB ≥ 3 em idosos ≥65a",
                    f"{n_acbi4:,}",
                    delta=f"{n_acbi4/total4*100:.1f}%",
                    delta_color="inverse",
                    help="Risco aumentado de demência e quedas")

        if n_both4 > 0:
            st.caption(
                f"ℹ️ **{n_both4:,} pacientes ({n_both4/total4*100:.1f}%)** "
                f"têm simultaneamente polifarmácia E carga anticolinérgica ≥ 3 — "
                f"o grupo de maior risco para revisão de prescrições."
            )

    st.markdown("---")

    # ── Filtros da lista ───────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        apenas_idosos = st.toggle(
            "🧠 Mostrar apenas idosos com alerta ACB (≥65 anos, ACB ≥ 3)",
            value=False, key="poli_apenas_idosos"
        )
    with col_f2:
        cat_filtro = st.multiselect(
            "Filtrar por Categoria ACB",
            options=['MUITO_ALTO', 'ALTO', 'MODERADO', 'BAIXO'],
            default=['MUITO_ALTO', 'ALTO'],
            key="poli_cat_acb"
        )
    with col_f3:
        apenas_stopp = st.toggle(
            "⚠️ Mostrar apenas com critério STOPP ou START ativo",
            value=False, key="poli_apenas_stopp"
        )

    with st.spinner("Carregando lista de pacientes..."):
        df_lista = carregar_lista_pacientes(
            ap, clinica, esf, apenas_alerta_idoso=apenas_idosos
        )

    if df_lista.empty:
        st.warning("Nenhum paciente encontrado.")
    else:
        if cat_filtro:
            df_lista = df_lista[df_lista['categoria_acb'].isin(cat_filtro)]
        if apenas_stopp:
            df_lista = df_lista[
                (df_lista['total_stopp'] > 0) | (df_lista['total_start'] > 0)
            ]

        if df_lista.empty:
            st.warning("Nenhum paciente nas categorias selecionadas.")
        else:
            st.caption(f"**{len(df_lista):,} pacientes** exibidos na lista.")

            df_exib = df_lista.copy()

            if MODO_ANONIMO:
                df_exib['nome'] = df_exib.apply(
                    lambda r: anonimizar_nome(r['nome'], r.get('genero','')), axis=1
                )
                df_exib['nome_esf_cadastro']     = df_exib['nome_esf_cadastro'].apply(anonimizar_esf)
                df_exib['nome_clinica_cadastro']  = df_exib['nome_clinica_cadastro'].apply(anonimizar_clinica)

            df_exib['alerta_acb_idoso'] = df_exib['alerta_acb_idoso'].map({True: '🧠 Alerta', False: '—'})
            df_exib['alerta_prescricao_idoso_ativo'] = df_exib['alerta_prescricao_idoso_ativo'].map(
                {True: '🚨 Alta', False: '—'}
            )

            # ── Montar strings descritivas STOPP e START ──────────
            LABELS_STOPP = {
                'fl_benzo':             'Benzodiazepínico',
                'fl_hipnotico_z':       'Hipnótico Z',
                'fl_tca':               'TCA (tricíclico)',
                'fl_tca_demencia':      'TCA + demência',
                'fl_paroxetina':        'Paroxetina',
                'fl_antipsic_tipico':   'Antipsicótico típico',
                'fl_antipsic_park':     'Antipsicót. + Parkinson',
                'fl_metoclopramida':    'Metoclopramida + Parkinson',
                'fl_cascata_biperideno':'Cascata biperideno',
                'fl_anti_hipert_central':'Anti-hipert. central',
                'fl_nifedipina':        'Nifedipina imediata',
                'fl_bcc_icc':           'BCC não-DHP + ICC',
                'fl_diur_has':          'Diurético alça p/ HAS',
                'fl_dronedarona':       'Dronedarona + ICC',
                'fl_sulfonilureia':     'Sulfonilureia longa ação',
                'fl_pioglitazona':      'Pioglitazona + ICC',
                'fl_metformina_irc':    'Metformina eGFR<30',
                'fl_insulina_escala':   'Insulina escala móvel',
                'fl_aine_irc':          'AINE + IRC',
                'fl_aine_icc':          'AINE + ICC',
                'fl_aine_has':          'AINE + HAS descontr.',
                'fl_aine_anticoag':     'AINE + anticoagulante',
                'fl_cortic_ar':         'Corticoide + AR',
                'fl_relaxante':         'Relaxante muscular',
                'fl_acb4':              'Carga anticolinérg. elevada (ACB>=4)',
                'fl_anti_hist':         'Anti-histam. 1ª geração',
                'fl_anticolinerg_bexiga':'Anticolinérg. bexiga',
                'fl_gabapentin_egfr':   'Gabapentin. eGFR<60',
                'fl_espiro_egfr':       'Espironolact. eGFR<30',
                'fl_tramadol_egfr':     'Tramadol eGFR<30',
                'fl_aas_primaria':      'AAS prev. primária (Beers)',
                'fl_opioide_benzo':     'Opioide + BZD (Beers)',
                'fl_isrs_tramadol':     'ISRS + Tramadol (Beers)',
            }
            LABELS_START = {
                'fl_has_sem_tto':         'HAS descontr. sem tto.',
                'fl_ci_sem_estatina':     'CI sem estatina',
                'fl_dcv_sem_antiplatelet':'DCV sem antiplaquetário',
                'fl_icc_sem_ieca':        'ICC sem IECA/BRA',
                'fl_fa_sem_anticoag':     'FA sem anticoagulação',
                'fl_dm_irc_sem_ieca':     'DM+IRC sem IECA/BRA',
                'fl_parkinson_sem_levo':  'Parkinson sem levodopa',
                'fl_depressao_sem_ad':    'Depressão sem antidepress.',
                'fl_demencia_sem_icolin': 'Demência sem icolinesterase',
                'fl_dpoc_sem_bronco':     'DPOC sem broncodilatador',
            }

            def _montar_string(row, labels):
                ativos = [label for col, label in labels.items()
                          if col in row.index and row[col] is True]
                if not ativos:
                    return '—'
                return f"{len(ativos)} — " + '; '.join(ativos)

            df_exib['stopp_str'] = df_exib.apply(
                lambda r: _montar_string(r, LABELS_STOPP), axis=1
            )
            df_exib['start_str'] = df_exib.apply(
                lambda r: _montar_string(r, LABELS_START), axis=1
            )

            # ── 1. Coluna unificada: meds + flag de polifarmácia ──────────
            def fmt_meds(row):
                cronicos = row.get('total_medicamentos_cronicos', 0) or 0
                agudos   = row.get('qtd_agudos_med', 0) or 0
                total    = cronicos + agudos
                if cronicos >= 10:
                    return f"{total} (hiperpolifarmácia)"
                elif cronicos >= 5:
                    return f"{total} (polifarmácia)"
                return str(total)
            df_exib['meds_fmt'] = df_exib.apply(fmt_meds, axis=1)

            # ── Enriquecer lista completa de meds com scores ACB ──────────
            import re as _re

            def _parse_acb_dict(acb_str):
                """Monta dict {nome_upper: score} a partir de 'Nome(score); Nome(score)'."""
                d = {}
                if not acb_str or str(acb_str) == 'nan':
                    return d
                for item in str(acb_str).split(';'):
                    item = item.strip()
                    m = _re.match(r'^(.+)\((\d)\)$', item)
                    if m:
                        d[m.group(1).strip().upper()] = int(m.group(2))
                return d

            def _enrich_meds(row):
                """
                Pega medicamentos_completos (todos os meds com posologia) e,
                para cada medicamento que tem ACB > 0, acrescenta (score) ao nome.
                Formato entrada: 'Amitriptilina 25mg - 1X/DIA; Losartana 50mg - 1X/DIA'
                Formato saída:   'Amitriptilina 25mg(3) - 1X/DIA; Losartana 50mg - 1X/DIA'
                """
                todos = row.get('todos_medicamentos', '')
                if not todos or str(todos) == 'nan':
                    # Fallback: usa nucleo_cronico_atual se disponível
                    todos = row.get('nucleo_cronico_atual', '') or ''
                if not todos:
                    return '—'

                acb_dict = _parse_acb_dict(row.get('acb_positivos_ref', ''))
                if not acb_dict:
                    return str(todos)

                partes = []
                for item in str(todos).split(';'):
                    item = item.strip()
                    if not item:
                        continue
                    # Separar nome do medicamento da posologia
                    if ' - ' in item:
                        nome_med, posologia = item.split(' - ', 1)
                    else:
                        nome_med, posologia = item, ''

                    # Verificar se alguma palavra-chave do dict ACB está no nome
                    nome_upper = nome_med.strip().upper()
                    score_encontrado = None
                    for nome_acb, score in acb_dict.items():
                        # Match pela primeira palavra do nome ACB contra o nome do med
                        primeira = nome_acb.split()[0] if nome_acb.split() else nome_acb
                        if primeira in nome_upper:
                            score_encontrado = score
                            break

                    if score_encontrado:
                        parte = f"{nome_med.strip()}({score_encontrado})"
                    else:
                        parte = nome_med.strip()

                    if posologia:
                        parte += f" - {posologia}"
                    partes.append(parte)

                return '; '.join(partes)

            df_exib['lista_meds_enriquecida'] = df_exib.apply(_enrich_meds, axis=1)

            # ── 2. Coluna unificada: ACB score + categoria ────────────────
            cat_abrev = {
                'MUITO_ALTO': 'Muito alto',
                'ALTO':       'Alto',
                'MODERADO':   'Moderado',
                'BAIXO':      'Baixo',
            }
            def fmt_acb(row):
                score = row.get('acb_score_total', 0) or 0
                cat   = cat_abrev.get(row.get('categoria_acb', ''), row.get('categoria_acb', ''))
                return f"{score} ({cat})"
            df_exib['acb_fmt'] = df_exib.apply(fmt_acb, axis=1)

            colunas = {
                'nome':                      'Paciente',
                'idade':                     'Idade',
                'nome_esf_cadastro':         'ESF',
                'morbidades_lista':          'Morbidades',
                'charlson_categoria':        'Morbidade',
                'meds_fmt':                  'Meds Crôn.',
                'acb_fmt':                   'ACB',
                'n_meds_acb_alto':           'ACB alto',
                'alerta_acb_idoso':          'Alerta ACB',
                'alerta_prescricao_idoso_ativo': 'Prioridade',
                'stopp_str':                 'STOPP — prescr. inapropriada',
                'start_str':                 'START — omissão terap.',
                'lista_meds_enriquecida':    'Prescrições',
            }
            cols_ok = {k: v for k, v in colunas.items() if k in df_exib.columns}
            st.dataframe(
                df_exib[list(cols_ok.keys())].rename(columns=cols_ok),
                hide_index=True,
                use_container_width=True,
                height=500,
                column_config={
                    'Morbidades': st.column_config.TextColumn(
                        width='medium',
                        help="Lista de condições crônicas ativas do paciente."
                    ),
                    'Morbidade': st.column_config.TextColumn(
                        help="Categoria de carga de morbidade pelo índice de Charlson modificado: Baixo / Moderado / Alto / Muito Alto."
                    ),
                    'Meds Crôn.': st.column_config.TextColumn(
                        help=(
                            "Total de medicamentos crônicos em uso contínuo. "
                            "Polifarmácia: 5–9 medicamentos. "
                            "Hiperpolifarmácia: ≥ 10 medicamentos."
                        )
                    ),
                    'ACB': st.column_config.TextColumn(
                        help=(
                            "Score ACB total (soma dos scores de todos os medicamentos) "
                            "e categoria de risco: Baixo (0) | Moderado (1–2) | "
                            "Alto (3–5) | Muito alto (≥6). "
                            "Ponto de corte clínico: ACB ≥ 3 (Boustani et al., 2008)."
                        )
                    ),
                    'ACB alto': st.column_config.NumberColumn(
                        help=(
                            "Número de medicamentos com score ACB = 3 — "
                            "carga anticolinérgica clinicamente relevante. "
                            "Ex: Amitriptilina, Quetiapina, Olanzapina, "
                            "Oxibutinina, Prometazina, Difenidramina."
                        )
                    ),
                    'Alerta': st.column_config.TextColumn(
                        help="Paciente com ≥ 65 anos e ACB ≥ 3 — risco aumentado de comprometimento cognitivo e quedas."
                    ),
                    'Prioridade': st.column_config.TextColumn(
                        help="🚨 Alta = critério grave ativo + paciente em acompanhamento nos últimos 365 dias."
                    ),
                    'STOPP — prescr. inapropriada': st.column_config.TextColumn(
                        width='large',
                        help=(
                            "Medicamentos potencialmente inapropriados identificados (STOPP v.2 + Beers 2023). "
                            "Critérios com prescrição ativa nos últimos 365 dias."
                        )
                    ),
                    'START — omissão terap.': st.column_config.TextColumn(
                        width='large',
                        help=(
                            "Medicamentos indicados ausentes na prescrição (START v.2). "
                            "Oportunidades de melhoria terapêutica."
                        )
                    ),
                    'Prescrições': st.column_config.TextColumn(
                        width='large',
                        help=(
                            "Todos os medicamentos prescritos (crônicos e agudos) com posologia. "
                            "Score ACB entre parênteses após o nome quando > 0: "
                            "1 = possível efeito | 2 = efeito estabelecido | "
                            "3 = clinicamente relevante."
                        )
                    ),
                }
            )

            # CSV inclui colunas originais + lista enriquecida
            cols_csv = list(cols_ok.keys())
            csv = df_exib[cols_csv].rename(columns=cols_ok).to_csv(
                index=False, sep=';', encoding='utf-8-sig'
            )
            st.download_button(
                "⬇️ Baixar lista (.csv)", csv,
                "lista_polifarmacia_acb.csv", "text/csv"
            )

# ──────────────────────────────────────────────────────────────
# ABA 6 — REFERÊNCIA CLÍNICA
# ──────────────────────────────────────────────────────────────
with tab6:
    st.markdown("""
    ### 📖 Referência dos Critérios de Prescrição em Idosos

    Esta aba reúne os critérios utilizados para identificar prescrições potencialmente
    inapropriadas (**STOPP**), omissões terapêuticas (**START**) e alertas adicionais
    (**Beers 2023**) em pacientes com 65 anos ou mais.

    > Todos os critérios são aplicados sobre dados de prescrição crônica dos últimos 365 dias.
    > O flag **_365d** confirma prescrição ativa recente.
    """)

    ref_tab1, ref_tab2, ref_tab3 = st.tabs([
        "🚫 STOPP — Evitar", "❌ START — Iniciar", "🔵 Beers 2023"
    ])

    # ── STOPP ──────────────────────────────────────────────────
    with ref_tab1:
        st.caption(
            "**STOPP** (*Screening Tool of Older Persons' Prescriptions*) — "
            "identifica medicamentos que devem ser **evitados** em idosos ≥65 anos, "
            "pois os riscos superam os benefícios na maioria dos casos. "
            "Ref: O'Mahony D et al., *Age Ageing* 2015;44(2):213-218."
        )
        import pandas as pd
        stopp_ref = pd.DataFrame([
            # Cardiovascular
            ("stopp_cv_001", "Cardiovascular", "Clonidina, Metildopa, Moxonidina",
             "HAS em idoso", "Risco de hipotensão ortostática, bradicardia e efeitos no SNC. Alternativas mais seguras disponíveis.", "Média"),
            ("stopp_cv_002", "Cardiovascular", "Doxazosina, Prazosina, Terazosina",
             "HAS em idoso", "Risco de hipotensão ortostática e síncope. Evitar como anti-hipertensivo.", "Média"),
            ("stopp_cv_003", "Cardiovascular", "Nifedipina liberação imediata",
             "HAS ou CI", "Risco de hipotensão reflexa e isquemia coronariana. Usar formulações de liberação lenta.", "Alta"),
            ("stopp_cv_004", "Cardiovascular", "Amiodarona como 1ª linha",
             "FA sem ICC", "Maior risco de efeitos adversos que BB, digoxina ou BCC não-DHP. Reservar para refratários.", "Média"),
            ("stopp_cv_005", "Cardiovascular", "Verapamil, Diltiazem",
             "ICC sistólica", "Efeito inotrópico negativo — pode descompensar ICC. Contraindicado.", "Alta"),
            ("stopp_cv_006", "Cardiovascular", "Furosemida",
             "HAS sem ICC ou IRC", "Alternativas mais seguras disponíveis para HAS. Diurético de alça não é 1ª linha.", "Baixa"),
            ("stopp_cv_007", "Cardiovascular", "Dronedarona",
             "ICC", "Associada a aumento de mortalidade em ICC. Contraindicada.", "Alta"),
            ("stopp_cv_008", "Cardiovascular", "Digoxina",
             "eGFR < 30 ml/min", "Risco de toxicidade digitálica por acúmulo. Reduzir dose ou suspender.", "Alta"),
            ("stopp_cv_009", "Cardiovascular", "Dabigatrana",
             "eGFR < 30 ml/min", "Acúmulo renal com risco de sangramento grave. Usar alternativa.", "Alta"),
            ("stopp_cv_010", "Cardiovascular", "Rivaroxabana, Apixabana",
             "eGFR < 15 ml/min", "Risco de sangramento por acúmulo. Contraindicado.", "Alta"),
            # SNC
            ("stopp_snc_001", "SNC", "Benzodiazepínicos (todos)",
             "Idoso ≥65 anos", "Risco de sedação, quedas, fraturas, acidentes e dependência. Evitar independente da indicação.", "Alta"),
            ("stopp_snc_002", "SNC", "Zolpidem, Zopiclona, Zaleplon",
             "Idoso ≥65 anos", "Mesmos riscos dos benzodiazepínicos para quedas e sedação prolongada.", "Alta"),
            ("stopp_snc_003", "SNC", "Amitriptilina, Nortriptilina, Imipramina",
             "Idoso ≥65 anos", "Efeitos anticolinérgicos, cardiotóxicos e sedativos. Risco de arritmia, hipotensão e queda.", "Alta"),
            ("stopp_snc_004", "SNC", "Tricíclicos (TCA)",
             "Com demência", "Piora do comprometimento cognitivo. Risco de delirium.", "Alta"),
            ("stopp_snc_005", "SNC", "Paroxetina",
             "Idoso ≥65 anos", "ISRS com maior carga anticolinérgica. Alternativas menos anticolinérgicas disponíveis.", "Média"),
            ("stopp_snc_006", "SNC", "Haloperidol, Clorpromazina, Levomepromazina",
             "Idoso ≥65 anos", "Risco de síndrome extrapiramidal, hipotensão e quedas.", "Alta"),
            ("stopp_snc_007", "SNC", "Antipsicóticos (típicos e atípicos)",
             "Parkinson ou demência", "Piora de sintomas extrapiramidais e aumento do risco de AVC em demência.", "Alta"),
            ("stopp_snc_008", "SNC", "Metoclopramida",
             "Parkinson", "Antagonista dopaminérgico — piora diretamente os sintomas parkinsonianos.", "Alta"),
            ("stopp_snc_009", "SNC", "Biperideno, Benzatropina",
             "Em uso de antipsicótico", "Cascata prescritiva: antipsicótico causa EPE → biperideno trata EPE. Rever antipsicótico.", "Média"),
            ("stopp_snc_010", "SNC", "Levodopa, agonistas dopaminérgicos",
             "Sem diagnóstico de Parkinson", "Uso inadequado sem indicação estabelecida.", "Baixa"),
            ("stopp_snc_011", "SNC", "Morfina, Oxicodona, Fentanil",
             "Sem indicação de dor severa", "Opioides fortes como 1ª linha em dor leve-moderada. Escalonamento inadequado (WHO).", "Média"),
            # Endócrino
            ("stopp_end_001", "Endócrino", "Glibenclamida, Glimepiride, Clorpropamida",
             "DM + idoso ≥65", "Hipoglicemia prolongada e grave — meia-vida longa. Usar agentes de ação curta.", "Alta"),
            ("stopp_end_002", "Endócrino", "Pioglitazona",
             "ICC + DM", "Retenção hídrica exacerba ICC. Contraindicado.", "Alta"),
            ("stopp_end_003", "Endócrino", "Metformina",
             "eGFR < 30 ml/min", "Risco de acidose lática por acúmulo. Suspender.", "Alta"),
            ("stopp_end_004", "Endócrino", "Insulina regular (sem basal)",
             "DM + idoso", "Escala móvel isolada — sem cobertura basal — aumenta risco de hipoglicemia.", "Alta"),
            # Musculoesquelético
            ("stopp_mus_001", "Musculoesquelético", "AINEs (todos)",
             "IRC eGFR < 50", "Piora da função renal. Contraindicado ou usar com monitoramento rigoroso.", "Alta"),
            ("stopp_mus_002", "Musculoesquelético", "AINEs (todos)",
             "ICC", "Retenção hídrica e piora da ICC. Evitar.", "Alta"),
            ("stopp_mus_003", "Musculoesquelético", "AINEs (todos)",
             "HAS não controlada", "Antagoniza efeito anti-hipertensivo e eleva PA.", "Alta"),
            ("stopp_mus_004", "Musculoesquelético", "AINE + Anticoagulante",
             "Uso concomitante", "Risco de sangramento gastrintestinal maior. Combinação a evitar.", "Alta"),
            ("stopp_mus_005", "Musculoesquelético", "Corticoide oral crônico",
             "Artrite reumatoide (M05/M06)", "DMARDs são preferíveis. Corticoide crônico causa osteoporose, infecção e DM.", "Alta"),
            ("stopp_mus_006", "Musculoesquelético", "Ciclobenzaprina, Carisoprodol, Baclofeno",
             "Idoso ≥65 anos", "Efeitos sedativos e anticolinérgicos. Risco de queda.", "Alta"),
            # ACB
            ("stopp_acb_001", "Anticolinérgico", "≥2 medicamentos com ACB > 0",
             "ACB total ≥ 4", "Carga anticolinérgica cumulativa — dois ou mais meds com efeito anticolinérgico somam risco de confusão, delirium, quedas e comprometimento cognitivo.", "Alta"),
            ("stopp_acb_002", "Anticolinérgico", "Difenidramina, Prometazina, Hidroxizina",
             "Idoso ≥65 anos", "Anti-histamínicos 1ª geração com alta atividade anticolinérgica central.", "Alta"),
            ("stopp_acb_003", "Anticolinérgico", "Oxibutinina, Tolterodina, Solifenacina",
             "Idoso ≥65 anos", "Anticolinérgicos urinários — risco de retenção urinária, confusão e piora cognitiva.", "Alta"),
            # Renal
            ("stopp_ren_001", "Renal", "Gabapentina, Pregabalina",
             "eGFR < 60 ml/min", "Dose precisa ser ajustada à função renal. Acúmulo causa sedação e quedas.", "Alta"),
            ("stopp_ren_002", "Renal", "Espironolactona",
             "eGFR < 30 ml/min", "Risco de hipercalemia grave.", "Alta"),
            ("stopp_ren_003", "Renal", "Tramadol",
             "eGFR < 30 ml/min", "Acúmulo de metabólitos — risco de convulsão e sedação.", "Alta"),
        ], columns=["Código", "Categoria", "Medicamento(s)", "Condição", "Justificativa clínica", "Severidade"])

        st.dataframe(
            stopp_ref,
            hide_index=True,
            use_container_width=True,
            height=520,
            column_config={
                "Código":            st.column_config.TextColumn(width=130),
                "Categoria":         st.column_config.TextColumn(width=130),
                "Medicamento(s)":    st.column_config.TextColumn(width=220),
                "Condição":          st.column_config.TextColumn(width=160),
                "Justificativa clínica": st.column_config.TextColumn(width=360),
                "Severidade":        st.column_config.TextColumn(width=90),
            }
        )

    # ── START ──────────────────────────────────────────────────
    with ref_tab2:
        st.caption(
            "**START** (*Screening Tool to Alert to Right Treatment*) — "
            "identifica medicamentos que **deveriam ser prescritos** mas estão ausentes, "
            "dado o diagnóstico do paciente. São oportunidades de melhoria terapêutica. "
            "Ref: O'Mahony D et al., *Age Ageing* 2015;44(2):213-218."
        )
        start_ref = pd.DataFrame([
            ("start_cv_001", "Cardiovascular", "Anti-hipertensivo (qualquer classe)",
             "HAS descontrolada PAS ≥160 sem tto.", "Hipertensão não tratada — principal causa evitável de AVC e IAM."),
            ("start_cv_002", "Cardiovascular", "Estatina",
             "Cardiopatia isquêmica (CI)",          "Redução de mortalidade cardiovascular comprovada em DCV estabelecida."),
            ("start_cv_003", "Cardiovascular", "AAS ou Clopidogrel",
             "DCV estabelecida (CI/AVC/DAP)",        "Antiplaquetário reduz eventos isquêmicos recorrentes em DCV estabelecida."),
            ("start_cv_004", "Cardiovascular", "IECA ou BRA",
             "ICC sistólica",                        "Reduz mortalidade e hospitalizações em ICC. Pilar do tratamento."),
            ("start_cv_005", "Cardiovascular", "Anticoagulante (warfarina ou DOAC)",
             "Fibrilação atrial",                   "Prevenção de AVC cardioembólico — risco elevado sem anticoagulação."),
            ("start_cv_006", "Cardiovascular", "IECA ou BRA",
             "DM + IRC (nefroproteção)",             "Retarda progressão da doença renal diabética. Indicado independente da PA."),
            ("start_snc_001", "SNC", "Levodopa ou agonista dopaminérgico",
             "Parkinson com incapacidade funcional", "Tratamento de primeira linha — melhora qualidade de vida e função motora."),
            ("start_snc_002", "SNC", "ISRS ou IRSN (não TCA)",
             "Depressão/ansiedade moderada-grave",   "Antidepressivos não-tricíclicos são mais seguros em idosos. TCA deve ser evitado."),
            ("start_snc_003", "SNC", "Donepezila, Rivastigmina, Galantamina",
             "Demência leve-moderada",               "Inibidores da colinesterase — modesta melhora cognitiva e funcional. Padrão de cuidado."),
            ("start_resp_001", "Respiratório", "Broncodilatador inalatório",
             "DPOC ou asma",                        "Alívio sintomático e prevenção de exacerbações. Indicado em qualquer grau."),
        ], columns=["Código", "Categoria", "Medicamento indicado", "Condição", "Justificativa clínica"])

        st.dataframe(
            start_ref,
            hide_index=True,
            use_container_width=True,
            height=420,
            column_config={
                "Código":               st.column_config.TextColumn(width=130),
                "Categoria":            st.column_config.TextColumn(width=130),
                "Medicamento indicado": st.column_config.TextColumn(width=230),
                "Condição":             st.column_config.TextColumn(width=220),
                "Justificativa clínica":st.column_config.TextColumn(width=360),
            }
        )

    # ── BEERS ──────────────────────────────────────────────────
    with ref_tab3:
        st.caption(
            "**AGS Beers Criteria® 2023** — critérios americanos complementares ao STOPP, "
            "com foco em situações específicas de risco. Os itens abaixo são os critérios "
            "**exclusivos** dos Beers, não cobertos pelo STOPP. "
            "Ref: AGS Beers Criteria® Update Expert Panel, *J Am Geriatr Soc* 2023;71(7):2052-2081."
        )
        beers_ref = pd.DataFrame([
            ("beers_001", "Tabela 2", "Sulfonilureias (todas)",
             "DM + idoso ≥65",
             "Beers 2023 expande além das de longa ação — inclui gliclazida e glipizida. "
             "Toda a classe aumenta risco de hipoglicemia em idosos."),
            ("beers_002", "Box 1", "Warfarina",
             "FA — sem tentativa prévia de DOAC",
             "Beers 2023 recomenda DOACs como 1ª escolha em FA. Warfarina tem janela terapêutica estreita "
             "e maior risco de sangramento. Nota: no SUS, DOACs não estão disponíveis na farmácia popular."),
            ("beers_003", "Box 1", "Rivaroxabana",
             "FA de longa duração",
             "Beers 2023 recomenda apixabana em detrimento de rivaroxabana, por perfil de segurança superior "
             "especialmente em pacientes com função renal reduzida."),
            ("beers_004", "Tabela 2", "AAS",
             "Prevenção primária ≥60 anos (sem DCV)",
             "Novo em 2023: movido de 'cautela' para 'evitar'. Alinhado com USPSTF — risco de sangramento "
             "supera benefício em prevenção primária em idosos. Manter apenas se DCV estabelecida."),
            ("beers_005", "Tabela 3", "Antipsicóticos atípicos (clozapina, olanzapina)",
             "Epilepsia",
             "Reduzem limiar convulsivo. Usar com extrema cautela ou evitar em pacientes com epilepsia."),
            ("beers_006", "Tabela 5", "Opioide + Benzodiazepínico",
             "Uso concomitante",
             "Combinação sinérgica de depressão do SNC — risco de depressão respiratória, "
             "sedação grave e overdose. Evitar em todas as faixas etárias, especialmente em idosos."),
            ("beers_007", "Tabela 5", "ISRS + Tramadol",
             "Uso concomitante",
             "Risco de síndrome serotonérgica (agitação, tremor, hipertermia, rigidez). "
             "Tramadol também inibe recaptação de serotonina."),
        ], columns=["Código", "Tabela Beers", "Medicamento(s)", "Condição", "Justificativa / Nota clínica"])

        st.dataframe(
            beers_ref,
            hide_index=True,
            use_container_width=True,
            height=360,
            column_config={
                "Código":          st.column_config.TextColumn(width=100),
                "Tabela Beers":    st.column_config.TextColumn(width=100),
                "Medicamento(s)":  st.column_config.TextColumn(width=200),
                "Condição":        st.column_config.TextColumn(width=200),
                "Justificativa / Nota clínica": st.column_config.TextColumn(width=420),
            }
        )

        st.info(
            "💡 **Como usar esta referência:** ao identificar um critério STOPP ou START "
            "na lista de pacientes, consulte esta aba para entender a justificativa clínica "
            "e orientar a revisão da prescrição junto ao paciente."
        )


# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "SMS-RJ | Navegador Clínico | Polifarmácia e Carga Anticolinérgica  |  "
    "Referência ACB: Boustani et al., *Aging Health* 2008;4(3):311–320"
)