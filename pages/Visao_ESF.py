"""
Page: Visão ESF
Hub operacional para a equipe de Saúde da Família — KPIs da equipe,
top-N pacientes mais críticos via IPC, e análise de colinearidade
entre as dimensões do índice.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from utils.bigquery_client import get_bigquery_client
from utils import theme as T
from components.cabecalho import renderizar_cabecalho
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf, anonimizar_nome,
    mostrar_badge_anonimo, MODO_ANONIMO
)
from utils.ipc import (
    calcular_ipc, gerar_sql_total_lacunas, explicar_ipc_paciente,
    PESOS_DEFAULT, BONUS_DCV_SEM_PREV, CORES_IPC,
)
from utils.morbidades import gerar_sql_morbidades_lista
from utils.lacunas_config import LACUNAS, GRUPOS_LACUNAS
from utils.criterios_idoso import (
    CRITERIOS_STOPP, CRITERIOS_START, CRITERIOS_BEERS,
    todos_codigos_stopp, todos_codigos_start, todos_codigos_beers,
    coluna_para_codigo, descricao_curta, justificativa, categoria, tipo,
)
import config

st.set_page_config(
    page_title="Visão ESF · Navegador Clínico",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

renderizar_cabecalho("Visão ESF")

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name):
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"


@st.cache_data(show_spinner=False, ttl=900)
def bq(sql: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro na query: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=900)
def carregar_territorios() -> pd.DataFrame:
    """Tuplas únicas (AP, clínica, ESF) para alimentar os selectboxes."""
    sql = f"""
    SELECT DISTINCT
        area_programatica_cadastro,
        nome_clinica_cadastro,
        nome_esf_cadastro
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro IS NOT NULL
      AND nome_clinica_cadastro IS NOT NULL
      AND nome_esf_cadastro IS NOT NULL
    ORDER BY area_programatica_cadastro, nome_clinica_cadastro, nome_esf_cadastro
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_pacientes_ipc(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """Carrega colunas necessárias para o IPC + identificação do paciente."""
    sql_total_lac   = gerar_sql_total_lacunas("total_lacunas")
    sql_morb_lista  = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    WITH stopp AS (
        SELECT cpf, COALESCE(total_criterios_stopp, 0) AS total_criterios_stopp
        FROM `rj-sms-sandbox.sub_pav_us.MM_stopp_start`
    )
    SELECT
        f.cpf, f.nome, f.idade, f.genero,
        f.area_programatica_cadastro,
        f.nome_clinica_cadastro AS clinica,
        f.nome_esf_cadastro     AS esf,
        f.charlson_score,
        f.charlson_categoria,
        f.acb_score_total,
        f.categoria_acb,
        f.dias_desde_ultima_medica,
        f.consultas_medicas_365d,
        f.total_morbidades,
        f.polifarmacia,
        f.hiperpolifarmacia,
        f.nucleo_cronico_atual         AS medicamentos_lista,
        f.dose_NPH_ui_kg,
        -- DCV estabelecida
        f.CI, f.stroke, f.vascular_periferica,
        -- Lacunas individuais usadas no bônus
        f.lacuna_CI_sem_AAS,
        f.lacuna_CI_sem_estatina_qualquer,
        -- Total de lacunas (soma dos 41 booleanos)
        {sql_total_lac},
        -- Lista textual de morbidades ativas
        {sql_morb_lista},
        -- Total de critérios STOPP (JOIN com MM_stopp_start)
        COALESCE(s.total_criterios_stopp, 0) AS total_criterios_stopp
    FROM `{_fqn(config.TABELA_FATO)}` AS f
    LEFT JOIN stopp s ON f.cpf = s.cpf
    WHERE f.area_programatica_cadastro = '{ap}'
      AND f.nome_clinica_cadastro     = '{clinica}'
      AND f.nome_esf_cadastro         = '{esf}'
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_lacunas_agregado(ap: str = None, clinica: str = None,
                              esf: str = None) -> pd.DataFrame:
    """
    Para um escopo (equipe = AP+clínica+ESF, ou município = sem filtro),
    devolve um DataFrame com uma linha por lacuna contendo:
      lacuna, grupo, numerador, denominador, pct
    A fórmula segue exatamente o denominador_sql definido em
    utils/lacunas_config.py (população elegível para a lacuna).
    """
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro     = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro         = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    selects = []
    for nome, info in LACUNAS.items():
        col   = info['coluna_fato']
        den   = info['denominador_sql']
        alias_n = "n_num__" + info['alias_pct'][len('pct_'):]
        alias_d = "n_den__" + info['alias_pct'][len('pct_'):]
        selects.append(f"COUNTIF({col} = TRUE) AS {alias_n}")
        selects.append(f"{den}                AS {alias_d}")

    sql = f"""
    SELECT
        {', '.join(selects)}
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    if df.empty:
        return pd.DataFrame(columns=['lacuna', 'grupo', 'numerador',
                                     'denominador', 'pct'])

    row = df.iloc[0]
    linhas = []
    for nome, info in LACUNAS.items():
        sufixo = info['alias_pct'][len('pct_'):]
        num = row.get(f"n_num__{sufixo}")
        den = row.get(f"n_den__{sufixo}")
        try:
            num_f = float(num) if pd.notna(num) else 0.0
            den_f = float(den) if pd.notna(den) and den else 0.0
        except (TypeError, ValueError):
            num_f, den_f = 0.0, 0.0
        pct = (num_f / den_f * 100.0) if den_f > 0 else None
        grupo = info['grupo']
        if isinstance(grupo, list):
            grupo = grupo[0]
        linhas.append({
            'lacuna':      nome,
            'grupo':       grupo,
            'numerador':   int(num_f),
            'denominador': int(den_f),
            'pct':         round(pct, 1) if pct is not None else None,
        })
    return pd.DataFrame(linhas)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_criterios_idoso_agregado(ap: str, clinica: str, esf: str) -> dict:
    """
    Para a equipe selecionada, devolve dict com:
      - 'totais_por_criterio': DataFrame (codigo, n_pacientes, pct)
      - 'distribuicao_stopp', 'distribuicao_start', 'distribuicao_beers':
        DataFrames (n_criterios, n_pacientes) — quantos pacientes têm
        0, 1, 2, 3, ≥4 critérios de cada tipo
      - 'n_pacientes_equipe', 'n_com_stopp', 'n_com_start', 'n_com_beers'
    """
    todos_codigos = (todos_codigos_stopp() + todos_codigos_start()
                     + todos_codigos_beers())
    countifs = ",\n        ".join(
        f"COUNTIF(s.{coluna_para_codigo(c)} = TRUE) AS {c}"
        for c in todos_codigos
    )

    sql = f"""
    WITH ss AS (
        SELECT s.*
        FROM `{_fqn(config.TABELA_FATO)}` f
        LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_stopp_start` s
               ON f.cpf = s.cpf
        WHERE f.area_programatica_cadastro = '{ap}'
          AND f.nome_clinica_cadastro     = '{clinica}'
          AND f.nome_esf_cadastro         = '{esf}'
    )
    SELECT
        COUNT(*) AS n_pacientes_equipe,
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) > 0)  AS n_com_stopp,
        COUNTIF(COALESCE(s.total_criterios_start, 0) > 0)  AS n_com_start,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) > 0)  AS n_com_beers,
        -- Distribuição por nº de critérios (cap em 4+)
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) = 0)  AS stopp_eq_0,
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) = 1)  AS stopp_eq_1,
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) = 2)  AS stopp_eq_2,
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) = 3)  AS stopp_eq_3,
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) >= 4) AS stopp_ge_4,
        COUNTIF(COALESCE(s.total_criterios_start, 0) = 0)  AS start_eq_0,
        COUNTIF(COALESCE(s.total_criterios_start, 0) = 1)  AS start_eq_1,
        COUNTIF(COALESCE(s.total_criterios_start, 0) = 2)  AS start_eq_2,
        COUNTIF(COALESCE(s.total_criterios_start, 0) = 3)  AS start_eq_3,
        COUNTIF(COALESCE(s.total_criterios_start, 0) >= 4) AS start_ge_4,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) = 0)  AS beers_eq_0,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) = 1)  AS beers_eq_1,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) = 2)  AS beers_eq_2,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) = 3)  AS beers_eq_3,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) >= 4) AS beers_ge_4,
        -- COUNTIF de cada critério individual
        {countifs}
    FROM ss s
    """
    df = bq(sql)
    if df.empty:
        return {
            'n_pacientes_equipe': 0, 'n_com_stopp': 0,
            'n_com_start': 0, 'n_com_beers': 0,
            'totais_por_criterio': pd.DataFrame(),
            'distribuicao_stopp':  pd.DataFrame(),
            'distribuicao_start':  pd.DataFrame(),
            'distribuicao_beers':  pd.DataFrame(),
        }
    row = df.iloc[0]
    n_total = int(row['n_pacientes_equipe'] or 0) or 1

    totais = []
    for c in todos_codigos:
        n = int(row.get(c, 0) or 0)
        totais.append({
            'codigo':  c,
            'tipo':    tipo(c),
            'categoria': categoria(c),
            'descricao': descricao_curta(c),
            'justificativa': justificativa(c),
            'n_pacientes': n,
            'pct':         round(n / n_total * 100, 1) if n_total else 0.0,
        })
    df_tot = pd.DataFrame(totais)

    def _dist(prefix):
        return pd.DataFrame([
            {'n_criterios': '0',  'n_pacientes': int(row[f'{prefix}_eq_0'] or 0)},
            {'n_criterios': '1',  'n_pacientes': int(row[f'{prefix}_eq_1'] or 0)},
            {'n_criterios': '2',  'n_pacientes': int(row[f'{prefix}_eq_2'] or 0)},
            {'n_criterios': '3',  'n_pacientes': int(row[f'{prefix}_eq_3'] or 0)},
            {'n_criterios': '≥4', 'n_pacientes': int(row[f'{prefix}_ge_4'] or 0)},
        ])

    return {
        'n_pacientes_equipe': int(row['n_pacientes_equipe'] or 0),
        'n_com_stopp':        int(row['n_com_stopp']        or 0),
        'n_com_start':        int(row['n_com_start']        or 0),
        'n_com_beers':        int(row['n_com_beers']        or 0),
        'totais_por_criterio': df_tot,
        'distribuicao_stopp':  _dist('stopp'),
        'distribuicao_start':  _dist('start'),
        'distribuicao_beers':  _dist('beers'),
    }


@st.cache_data(show_spinner=False, ttl=900)
def carregar_criterios_idoso_nominal(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """
    Devolve DataFrame paciente-a-paciente apenas com quem tem
    ≥1 critério positivo, com colunas individuais de cada critério.
    """
    todos_codigos = (todos_codigos_stopp() + todos_codigos_start()
                     + todos_codigos_beers())
    flags = ",\n        ".join(
        f"s.{coluna_para_codigo(c)} AS {c}"
        for c in todos_codigos
    )
    sql_morb_lista = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    SELECT
        f.cpf, f.nome, f.idade, f.genero,
        f.acb_score_total,
        f.nucleo_cronico_atual AS medicamentos_lista,
        {sql_morb_lista},
        COALESCE(s.total_criterios_stopp, 0) AS total_stopp,
        COALESCE(s.total_criterios_start, 0) AS total_start,
        COALESCE(s.total_criterios_beers, 0) AS total_beers,
        {flags}
    FROM `{_fqn(config.TABELA_FATO)}` f
    LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_stopp_start` s
           ON f.cpf = s.cpf
    WHERE f.area_programatica_cadastro = '{ap}'
      AND f.nome_clinica_cadastro     = '{clinica}'
      AND f.nome_esf_cadastro         = '{esf}'
      AND (COALESCE(s.total_criterios_stopp, 0) > 0
           OR COALESCE(s.total_criterios_start, 0) > 0
           OR COALESCE(s.total_criterios_beers, 0) > 0
           OR COALESCE(f.acb_score_total, 0) >= 3)
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_continuidade_agregado(ap: str, clinica: str, esf: str) -> dict:
    """Estatísticas de continuidade do cuidado para a equipe."""
    sql = f"""
    SELECT
        COUNT(*) AS n_total,
        COUNTIF(dias_desde_ultima_medica > 180)                     AS n_sem_medico_180d,
        COUNTIF(consultas_365d = 0)                                  AS n_sem_consulta_365d,
        COUNTIF(regularidade_acompanhamento = 'regular')             AS n_regular,
        COUNTIF(regularidade_acompanhamento = 'irregular')           AS n_irregular,
        COUNTIF(regularidade_acompanhamento = 'esporadico')          AS n_esporadico,
        COUNTIF(regularidade_acompanhamento = 'sem_acompanhamento')  AS n_sem_acomp,
        COUNTIF(baixa_longitudinalidade   = TRUE)                   AS n_baixa_long,
        COUNTIF(usuario_frequente_urgencia = TRUE)                   AS n_freq_urg,
        COUNTIF(alto_risco_baixo_acesso    = TRUE)                   AS n_alto_baixo_acesso,
        COUNTIF(alto_risco_intervalo_longo = TRUE)                   AS n_alto_intv_longo,
        ROUND(AVG(consultas_365d), 1)                                AS media_consultas_total,
        ROUND(AVG(consultas_medicas_365d), 1)                        AS media_consultas_med,
        ROUND(AVG(consultas_enfermagem_365d), 1)                     AS media_consultas_enf,
        ROUND(AVG(consultas_tecnico_enfermagem_365d), 1)             AS media_consultas_tec,
        ROUND(AVG(intervalo_mediano_dias), 1)                        AS media_intv_mediano,
        ROUND(AVG(pct_consultas_medicas_na_unidade_365d), 1)         AS media_pct_na_unidade,
        ROUND(AVG(pct_consultas_medicas_fora_365d), 1)               AS media_pct_fora
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_continuidade_nominal(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """
    Lista paciente-a-paciente para a aba de continuidade. Inclui
    morbidades, prescrição crônica e indicadores de acesso.
    """
    sql_morb_lista = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    SELECT
        cpf, nome, idade, genero,
        charlson_score,
        charlson_categoria,
        nucleo_cronico_atual                  AS medicamentos_lista,
        {sql_morb_lista},
        consultas_365d,
        consultas_medicas_365d,
        consultas_enfermagem_365d,
        consultas_tecnico_enfermagem_365d,
        pct_consultas_medicas_na_unidade_365d,
        pct_consultas_medicas_fora_365d,
        dias_desde_ultima_medica,
        dias_desde_ultima_enfermagem,
        intervalo_mediano_dias,
        meses_com_consulta_12m,
        regularidade_acompanhamento,
        baixa_longitudinalidade,
        usuario_frequente_urgencia,
        alto_risco_baixo_acesso,
        alto_risco_intervalo_longo,
        perfil_cuidado_365d
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_hipertensao_agregado(ap: str, clinica: str, esf: str) -> dict:
    """Indicadores resumidos de HAS para a equipe."""
    sql = f"""
    SELECT
        COUNT(*)                                                       AS n_total,
        COUNTIF(HAS IS NOT NULL)                                       AS n_has,
        COUNTIF(HAS_sem_CID = TRUE)                                    AS n_sem_cid,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')    AS n_ctrl,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado') AS n_desc,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL) AS n_sem_info,
        COUNTIF(HAS IS NOT NULL AND lacuna_PA_hipertenso_180d = TRUE)  AS n_sem_pa_180d,
        COUNTIF(HAS IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)   AS n_sem_creat,
        COUNTIF(HAS IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)   AS n_sem_col,
        COUNTIF(HAS IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)          AS n_sem_eas,
        COUNTIF(HAS IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)          AS n_sem_ecg,
        COUNTIF(HAS IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)          AS n_sem_imc,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pressao_sistolica END), 0)  AS media_pas,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pressao_diastolica END), 0) AS media_pad,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pct_dias_has_controlado_365d END), 1)
                                                                        AS media_pct_ctrl
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_hipertensao_nominal(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """Lista nominal — só pacientes com HAS."""
    sql_morb_lista = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    SELECT
        cpf, nome, idade, genero,
        charlson_categoria,
        nucleo_cronico_atual                  AS medicamentos_lista,
        {sql_morb_lista},
        pressao_sistolica,
        pressao_diastolica,
        dias_desde_ultima_pa,
        dias_desde_ultima_medica,
        status_controle_pressorio,
        pct_dias_has_controlado_365d,
        meta_pas,
        HAS_sem_CID,
        DM, IRC, ICC, CI,
        lacuna_PA_hipertenso_180d,
        lacuna_HAS_descontrolado_menor80,
        lacuna_HAS_descontrolado_80mais,
        lacuna_DM_HAS_PA_descontrolada,
        lacuna_creatinina_HAS_DM,
        lacuna_colesterol_HAS_DM,
        lacuna_eas_HAS_DM,
        lacuna_ecg_HAS_DM,
        lacuna_IMC_HAS_DM
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
      AND HAS IS NOT NULL
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_diabetes_agregado(ap: str, clinica: str, esf: str) -> dict:
    """Indicadores resumidos de DM para a equipe."""
    sql = f"""
    SELECT
        COUNT(*)                                                       AS n_total,
        COUNTIF(DM IS NOT NULL)                                        AS n_dm,
        COUNTIF(DM_sem_CID = TRUE)                                     AS n_sem_cid,
        -- Controle glicêmico calculado pela meta etária (HbA1c recente ≤180d)
        COUNTIF(DM IS NOT NULL
                AND hba1c_atual IS NOT NULL
                AND dias_desde_ultima_hba1c <= 180
                AND hba1c_atual <= meta_hba1c)                          AS n_ctrl,
        COUNTIF(DM IS NOT NULL
                AND hba1c_atual IS NOT NULL
                AND dias_desde_ultima_hba1c <= 180
                AND hba1c_atual >  meta_hba1c)                          AS n_desc,
        COUNTIF(DM IS NOT NULL AND hba1c_atual IS NULL)                AS n_nunca_a1c,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_sem_HbA1c_recente = TRUE) AS n_sem_a1c_180d,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_descontrolado = TRUE)     AS n_lac_desc,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_sem_exame_pe_365d = TRUE) AS n_sem_pe,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_microalbuminuria_nao_solicitado = TRUE)
                                                                        AS n_sem_micro,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_complicado_sem_SGLT2 = TRUE)
                                                                        AS n_complic_sem_sglt2,
        COUNTIF(DM IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)    AS n_sem_creat,
        COUNTIF(DM IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)    AS n_sem_col,
        COUNTIF(DM IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)           AS n_sem_ecg,
        COUNTIF(DM IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)           AS n_sem_imc,
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN hba1c_atual END), 2)   AS media_a1c
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_diabetes_nominal(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """Lista nominal — só pacientes com DM."""
    sql_morb_lista = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    SELECT
        cpf, nome, idade, genero,
        charlson_categoria,
        nucleo_cronico_atual                  AS medicamentos_lista,
        {sql_morb_lista},
        hba1c_atual,
        dias_desde_ultima_hba1c,
        dias_desde_ultima_medica,
        status_controle_glicemico,
        meta_hba1c,
        DM_sem_CID,
        provavel_dm1,
        HAS, IRC, ICC, CI,
        lacuna_DM_sem_HbA1c_recente,
        lacuna_DM_descontrolado,
        lacuna_DM_sem_exame_pe_365d,
        lacuna_DM_sem_exame_pe_180d,
        lacuna_DM_nunca_teve_exame_pe,
        lacuna_DM_microalbuminuria_nao_solicitado,
        lacuna_DM_complicado_sem_SGLT2,
        lacuna_DM_hba1c_nao_solicitado,
        lacuna_creatinina_HAS_DM,
        lacuna_colesterol_HAS_DM,
        lacuna_eas_HAS_DM,
        lacuna_ecg_HAS_DM,
        lacuna_IMC_HAS_DM
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
      AND DM IS NOT NULL
    """
    return bq(sql)


def _kpi(col, label, valor, delta=None, ajuda=None):
    with col:
        with st.container(border=True):
            st.metric(label, valor, delta, help=ajuda)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — SELEÇÃO OBRIGATÓRIA AP / CLÍNICA / ESF
# ═══════════════════════════════════════════════════════════════
st.sidebar.header("🎯 Equipe selecionada")
mostrar_badge_anonimo()
st.sidebar.info("⚠️ Selecione AP, Clínica e ESF para carregar a visão da equipe.")

df_opts = carregar_territorios()
if df_opts.empty:
    st.sidebar.error("Sem opções de filtro disponíveis.")
    st.stop()

aps = sorted(df_opts['area_programatica_cadastro'].dropna().unique().tolist())
ap_sel = st.sidebar.selectbox(
    "Área Programática: *",
    options=[None] + aps,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_ap(str(x)),
    key="ve_ap",
)

if ap_sel:
    clinicas = sorted(df_opts[df_opts['area_programatica_cadastro'] == ap_sel]
                      ['nome_clinica_cadastro'].dropna().unique().tolist())
else:
    clinicas = []

cli_sel = st.sidebar.selectbox(
    "Clínica da Família: *",
    options=[None] + clinicas,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_clinica(x),
    disabled=not ap_sel, key="ve_cli",
)

if ap_sel and cli_sel:
    esfs = sorted(df_opts[(df_opts['area_programatica_cadastro'] == ap_sel)
                          & (df_opts['nome_clinica_cadastro'] == cli_sel)]
                  ['nome_esf_cadastro'].dropna().unique().tolist())
else:
    esfs = []

esf_sel = st.sidebar.selectbox(
    "ESF: *",
    options=[None] + esfs,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_esf(x),
    disabled=not cli_sel, key="ve_esf",
)

# Bloqueia até que a equipe esteja selecionada
if not ap_sel:
    st.warning("⚠️ Selecione uma Área Programática na barra lateral.")
    st.stop()
if not cli_sel:
    st.warning("⚠️ Selecione uma Clínica da Família na barra lateral.")
    st.stop()
if not esf_sel:
    st.warning("⚠️ Selecione uma ESF na barra lateral.")
    st.stop()

# ═══════════════════════════════════════════════════════════════
# TÍTULO + EXPLICAÇÃO DO IPC
# ═══════════════════════════════════════════════════════════════
st.title("📋 Visão da ESF")
st.caption(
    f"AP **{anonimizar_ap(ap_sel)}** · Clínica **{anonimizar_clinica(cli_sel)}** "
    f"· ESF **{anonimizar_esf(esf_sel)}**"
)

# ═══════════════════════════════════════════════════════════════
# CARREGAMENTO DE DADOS
# ═══════════════════════════════════════════════════════════════
with st.spinner("Carregando pacientes da equipe..."):
    df_raw = carregar_pacientes_ipc(ap_sel, cli_sel, esf_sel)

if df_raw.empty:
    st.warning("⚠️ Nenhum paciente encontrado para a equipe selecionada.")
    st.stop()

df = calcular_ipc(df_raw)

# Anonimização para exibição
if MODO_ANONIMO:
    df['nome_exib'] = df.apply(
        lambda r: anonimizar_nome(str(r.get('cpf') or r.get('nome', '')),
                                  r.get('genero', '')),
        axis=1,
    )
else:
    df['nome_exib'] = df['nome']

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
(tab_resumo, tab_lacunas, tab_cont, tab_polif, tab_has, tab_dm,
 tab_analise) = st.tabs([
    "📊 Resumo da equipe",
    "⚠️ Lacunas",
    "🔄 Continuidade",
    "💊 Polifarmácia",
    "🩺 Hipertensão",
    "🩸 Diabetes",
    "🔬 Análise do IPC",
])

# ─────────────────────────────────────────────────────────────
# ABA 1 — RESUMO DA EQUIPE
# ─────────────────────────────────────────────────────────────
with tab_resumo:
    n_total = len(df)

    # ─────────────────────────────────────────────────────────
    # 3️⃣ Top-10 mais críticos (PRIMEIRA INFORMAÇÃO)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 1️⃣ Aqui estão os 10 pacientes mais críticos da sua equipe (pacientes com maior IPC)")
    st.caption(
        "Ranking pelo IPC. Empates são desempatados pela Carga de "
        "Morbidade. Use como ponto de partida para discussão "
        "clínica em equipe."
    )
    top = df.sort_values(['ipc', 'charlson_score'],
                        ascending=[False, False]).head(10).copy()

    if top.empty:
        st.info("Sem pacientes para listar.")
    else:
        def _fmt_int_or_dash(v):
            return f"{int(v)}" if pd.notna(v) else "—"

        def _fmt_nph(v):
            if pd.isna(v) or v is None or v == 0:
                return "—"
            return f"{float(v):.2f}"

        top_show = pd.DataFrame({
            '#': range(1, len(top) + 1),
            'Paciente': top['nome_exib'].values,
            'Idade': top['idade'].astype('Int64').values,
            'IPC': top['ipc'].round(2).values,
            'Categoria': top['ipc_categoria'].values,
            'Carga de Morbidade': top['charlson_score'].astype('Int64').values,
            'Morbidades': top['morbidades_lista'].fillna('—').values,
            'ACB': top['acb_score_total'].astype('Int64').values,
            'STOPP': top['total_criterios_stopp'].astype('Int64').values,
            'Dias s/ médico': top['dias_desde_ultima_medica'].apply(
                _fmt_int_or_dash
            ).values,
            'Lacunas': top['total_lacunas'].astype('Int64').values,
            'Medicamentos (última prescrição)': top['medicamentos_lista'].fillna('—').values,
            'NPH (UI/kg)': top['dose_NPH_ui_kg'].apply(_fmt_nph).values,
            'DCV s/ prev': top['ipc_dcv_sem_prev'].apply(
                lambda v: '⚠️' if v else ''
            ).values,
        })
        st.dataframe(
            top_show, hide_index=True, use_container_width=True,
            column_config={
                'Morbidades':   st.column_config.TextColumn('Morbidades',   width='large'),
                'Medicamentos (última prescrição)':
                    st.column_config.TextColumn('Medicamentos (última prescrição)',
                                                width='large'),
                'IPC':          st.column_config.NumberColumn('IPC', format='%.2f'),
                'Carga de Morbidade':
                    st.column_config.NumberColumn('Carga de Morbidade', width='small'),
                'ACB':          st.column_config.NumberColumn('ACB',     width='small'),
                'STOPP':        st.column_config.NumberColumn('STOPP',   width='small'),
                'Lacunas':      st.column_config.NumberColumn('Lacunas', width='small'),
                'Dias s/ médico': st.column_config.TextColumn('Dias s/ médico', width='small'),
                'NPH (UI/kg)':  st.column_config.TextColumn('NPH (UI/kg)', width='small'),
                'DCV s/ prev':  st.column_config.TextColumn('DCV s/ prev', width='small'),
            },
        )

        # Detalhe expandido por paciente
        with st.expander("Ver decomposição do IPC por paciente"):
            for _, row in top.iterrows():
                cor = CORES_IPC.get(row['ipc_categoria'], '#999')
                st.markdown(
                    f"<div style='border-left:4px solid {cor}; padding:6px 12px; "
                    f"margin:4px 0; background:{cor}10; border-radius:4px;'>"
                    f"<strong>{row['nome_exib']}</strong> — IPC {row['ipc']:.2f} "
                    f"(<span style='color:{cor};'>{row['ipc_categoria']}</span>)<br>"
                    f"<span style='color:{T.TEXT_MUTED}; font-size:0.88em;'>"
                    f"{explicar_ipc_paciente(row)}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ─────────────────────────────────────────────────────────
    # Sobre o IPC — sem sanfona, sem "Diferença para o ICA"
    # ─────────────────────────────────────────────────────────
    st.markdown("### ℹ️ Sobre o IPC — Índice de Priorização de Cuidado")
    st.markdown(f"""
**O IPC é um índice composto que ordena pacientes por necessidade de
atenção da equipe.** Combina cinco dimensões clínicas em uma única
escala de 0 a 1, com bandas absolutas (independentes da amostra),
permitindo comparar pacientes entre ESFs, clínicas e APs.

#### Dimensões e pesos

| Dimensão | Peso | Bandas |
|---|---|---|
| 🦠 **Carga de Morbidade** (Charlson) | {PESOS_DEFAULT['charlson']:.0%} | 0–3 → 0 · 4–6 → 0,33 · 7–9 → 0,67 · ≥10 → 1 |
| ⚠️ **Total de lacunas de cuidado** | {PESOS_DEFAULT['lacunas']:.0%} | 0 → 0 · 1–3 → 0,33 · 4–7 → 0,67 · ≥8 → 1 |
| ⏳ **Dias sem consulta médica** | {PESOS_DEFAULT['acesso']:.0%} | 0–180 → 0 · 181–365 → 0,5 · 366–730 → 0,85 · >730 ou nunca → 1 |
| 💊 **ACB** (carga anticolinérgica) | {PESOS_DEFAULT['acb']:.0%} | 0 → 0 · 1 → 0,33 · 2 → 0,67 · ≥3 → 1 |
| 🚫 **STOPP** (prescrições inapropriadas) | {PESOS_DEFAULT['stopp']:.0%} | 0 → 0 · 1 → 0,33 · 2 → 0,67 · ≥3 → 1 |

**Bônus de +{BONUS_DCV_SEM_PREV:.2f}** quando o paciente tem DCV estabelecida
(CI, AVC ou doença arterial periférica) **e** mantém lacunas de prevenção
secundária pendentes (sem AAS ou sem estatina). O resultado final é
cortado em 1,0.

#### Como interpretar

| Faixa de IPC | Categoria |
|---|---|
| ≥ 0,75 | 🔴 Crítico |
| 0,50 – 0,74 | 🟠 Alto |
| 0,25 – 0,49 | 🟡 Moderado |
| < 0,25 | 🟢 Baixo |
""")

    st.markdown("---")

    # ─────────────────────────────────────────────────────────
    # 1️⃣ Indicadores da equipe (KPIs)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 2️⃣ Indicadores da equipe")
    k1, k2, k3, k4 = st.columns(4)
    n_multi = int((df['total_morbidades'] >= 2).sum()) if 'total_morbidades' in df.columns else 0
    n_poli  = int(df['polifarmacia'].fillna(False).astype(bool).sum()) if 'polifarmacia' in df.columns else 0
    n_dcv   = int(((df['CI'].notna()) | (df['stroke'].notna())
                   | (df['vascular_periferica'].notna())).sum())
    _kpi(k1, "👥 Pacientes da equipe", f"{n_total:,}")
    _kpi(k2, "🦠 Multimórbidos (≥2)", f"{n_multi:,}",
         f"{n_multi/n_total*100:.0f}%" if n_total else None)
    _kpi(k3, "💊 Em polifarmácia", f"{n_poli:,}",
         f"{n_poli/n_total*100:.0f}%" if n_total else None)
    _kpi(k4, "❤️ DCV estabelecida", f"{n_dcv:,}",
         f"{n_dcv/n_total*100:.0f}%" if n_total else None)

    # ─────────────────────────────────────────────────────────
    # 2️⃣ Distribuição do IPC — caixas alinhadas com o histograma
    # (Baixo → Crítico, ordem visual da esquerda para a direita)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 3️⃣ Distribuição do IPC (Índice de Priorização de Cuidado)")
    dist = df['ipc_categoria'].value_counts().reindex(
        ['Baixo', 'Moderado', 'Alto', 'Crítico']
    ).fillna(0).astype(int)

    cd1, cd2, cd3, cd4 = st.columns(4)
    for col_w, cat in zip([cd1, cd2, cd3, cd4], ['Baixo', 'Moderado', 'Alto', 'Crítico']):
        n = int(dist.get(cat, 0))
        cor = CORES_IPC[cat]
        with col_w:
            st.markdown(
                f"<div style='background:{cor}20; border-left:6px solid {cor}; "
                f"padding:14px 16px; border-radius:8px;'>"
                f"<div style='color:{cor}; font-weight:600; font-size:0.9em;'>{cat}</div>"
                f"<div style='font-size:1.8em; font-weight:600; color:{T.TEXT};'>{n:,}</div>"
                f"<div style='color:{T.TEXT_MUTED}; font-size:0.85em;'>"
                f"{n/n_total*100:.1f}% da equipe</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Histograma do IPC — bins curtos coloridos pela faixa de IPC
    st.markdown("##### Histograma do IPC (Índice de Priorização de Cuidado)")
    n_bins = 80
    bins = np.linspace(0, 1.0, n_bins + 1)
    counts, edges = np.histogram(df['ipc'].clip(0, 1.0), bins=bins)
    centros = (edges[:-1] + edges[1:]) / 2

    def _cor_para_centro(c):
        if c >= 0.75: return CORES_IPC['Crítico']
        if c >= 0.50: return CORES_IPC['Alto']
        if c >= 0.25: return CORES_IPC['Moderado']
        return CORES_IPC['Baixo']

    cores_bins = [_cor_para_centro(c) for c in centros]

    fig_hist = go.Figure(
        go.Bar(
            x=centros, y=counts,
            marker=dict(color=cores_bins, line=dict(width=0)),
            width=(1.0 / n_bins) * 0.95,
            hovertemplate='IPC %{x:.2f}<br>%{y} pacientes<extra></extra>',
        )
    )
    for limiar in (0.25, 0.50, 0.75):
        fig_hist.add_vline(x=limiar, line_dash='dash', line_color='#888888')
    fig_hist.update_layout(
        height=320, bargap=0.0,
        margin=dict(l=10, r=10, t=20, b=40),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        xaxis=dict(range=[0, 1.05], title='IPC',
                   tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
        yaxis=dict(title='Pacientes',
                   tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# ─────────────────────────────────────────────────────────────
# ABA 2 — LACUNAS DA EQUIPE × MUNICÍPIO
# ─────────────────────────────────────────────────────────────
with tab_lacunas:
    st.markdown(
        "#### Lacunas de cuidado da sua equipe — comparado ao município"
    )
    st.caption(
        "Cada lacuna é calculada apenas sobre a população elegível "
        "(ex.: 'CI sem AAS' usa pacientes com CI como denominador). "
        "Município = todos os pacientes da base. Lacunas ordenadas "
        "da mais prevalente à menos prevalente na sua equipe."
    )

    with st.spinner("Calculando lacunas da equipe e do município..."):
        df_eq  = carregar_lacunas_agregado(ap_sel, cli_sel, esf_sel)
        df_mun = carregar_lacunas_agregado(None, None, None)

    if df_eq.empty:
        st.warning("Sem dados de lacunas para a equipe selecionada.")
    else:
        df_lac = df_eq.merge(
            df_mun[['lacuna', 'numerador', 'denominador', 'pct']]
                .rename(columns={'numerador':   'numerador_mun',
                                 'denominador': 'denominador_mun',
                                 'pct':         'pct_mun'}),
            on='lacuna', how='left',
        )
        df_lac['delta'] = df_lac['pct'] - df_lac['pct_mun']
        df_lac = df_lac.sort_values('pct', ascending=False, na_position='last')

        # ── Tabela com gradiente de cor + setas ─────────────────
        df_tab = pd.DataFrame({
            'Grupo':       df_lac['grupo'].values,
            'Lacuna':      df_lac['lacuna'].values,
            'n / N':       df_lac.apply(
                lambda r: f"{int(r['numerador'])} / {int(r['denominador'])}"
                          if r['denominador'] else "—",
                axis=1,
            ).values,
            '% Equipe':    df_lac['pct'].astype(float).values,
            '% Município': df_lac['pct_mun'].astype(float).values,
            'Variação':    df_lac['delta'].astype(float).values,
        })

        def _fmt_variacao(v):
            if pd.isna(v):
                return '—'
            if v > 0:
                return f'↑ +{v:.1f}%'   # equipe pior que município
            if v < 0:
                return f'↓ {v:.1f}%'    # equipe melhor (v já negativo)
            return '↔ 0,0%'

        def _cor_variacao(v):
            if pd.isna(v):
                return ''
            if v > 0:
                return 'color: #C0392B; font-weight: 600;'   # vermelho
            if v < 0:
                return 'color: #27AE60; font-weight: 600;'   # verde
            return 'color: #6B7280;'

        # Gradiente manual verde→amarelo→vermelho (sem matplotlib)
        def _gradiente_pct(v, vmin=0.0, vmax=100.0):
            if pd.isna(v):
                return ''
            norm = max(0.0, min(1.0, (float(v) - vmin) / (vmax - vmin)))
            if norm <= 0.5:                       # verde → amarelo
                t = norm * 2
                r = int(round(76  + (255 - 76)  * t))
                g = int(round(175 + (235 - 175) * t))
                b = int(round( 80 + ( 59 -  80) * t))
            else:                                  # amarelo → vermelho
                t = (norm - 0.5) * 2
                r = int(round(255 + (231 - 255) * t))
                g = int(round(235 + ( 76 - 235) * t))
                b = int(round( 59 + ( 60 -  59) * t))
            return f'background-color: rgba({r},{g},{b},0.55);'

        styled = (
            df_tab.style
            .applymap(_gradiente_pct, subset=['% Equipe', '% Município'])
            .format({
                '% Equipe':    lambda v: f'{v:.1f}%' if pd.notna(v) else '—',
                '% Município': lambda v: f'{v:.1f}%' if pd.notna(v) else '—',
                'Variação':    _fmt_variacao,
            })
            .applymap(_cor_variacao, subset=['Variação'])
            .set_properties(
                subset=['Grupo', 'Lacuna'],
                **{'text-align': 'left'},
            )
            .set_properties(
                subset=['n / N', '% Equipe', '% Município', 'Variação'],
                **{'text-align': 'center'},
            )
            .set_table_styles([
                {'selector': 'th.col_heading.level0',
                 'props': [('text-align', 'center')]},
                {'selector': 'th.col_heading.level0:nth-child(1), '
                             'th.col_heading.level0:nth-child(2)',
                 'props': [('text-align', 'left')]},
            ])
        )

        st.dataframe(
            styled, hide_index=True, use_container_width=True, height=560,
        )

        st.markdown("---")

        # ── Gráfico vertical filtrado por grupo ─────────────────
        st.markdown("##### Comparação visual por grupo: equipe × município")

        grupos_disponiveis = (df_lac.dropna(subset=['grupo'])
                                    ['grupo'].unique().tolist())
        # Ordenar pela ordem canônica de GRUPOS_LACUNAS
        grupos_disponiveis = [g for g in GRUPOS_LACUNAS.keys()
                              if g in grupos_disponiveis]

        grupo_sel = st.selectbox(
            "Filtrar por grupo",
            options=grupos_disponiveis,
            index=0 if grupos_disponiveis else None,
            key="lac_grupo_filter",
        )

        df_plot = df_lac[(df_lac['grupo'] == grupo_sel)
                         & (df_lac['denominador'] > 0)].copy()
        df_plot = df_plot.sort_values('pct', ascending=False)

        if df_plot.empty:
            st.info(f"Sem lacunas com pacientes elegíveis no grupo "
                   f"**{grupo_sel}** para esta equipe.")
        else:
            # Cor da barra da equipe baseada em comparação com município:
            # acima do município (pior) → vermelho; abaixo (melhor) → verde.
            def _cor_barra_equipe(d):
                if pd.isna(d):
                    return '#9CA3AF'
                if d > 0.5:  return '#E74C3C'
                if d < -0.5: return '#27AE60'
                return '#F59E0B'  # próximo ao município

            cores_equipe = [_cor_barra_equipe(d) for d in df_plot['delta']]

            fig = go.Figure()
            # Barra do município (cinza, atrás)
            fig.add_trace(go.Bar(
                x=df_plot['lacuna'], y=df_plot['pct_mun'],
                name='Município',
                marker=dict(color='#D1D5DB'),
                text=[f'{v:.0f}%' for v in df_plot['pct_mun']],
                textposition='outside',
                textfont=dict(color=T.TEXT_MUTED, size=14),
                hovertemplate='<b>%{x}</b><br>Município: %{y:.1f}%<extra></extra>',
            ))
            # Barra da equipe (cor varia por delta)
            fig.add_trace(go.Bar(
                x=df_plot['lacuna'], y=df_plot['pct'],
                name='Equipe',
                marker=dict(color=cores_equipe),
                text=[f'{v:.0f}%' for v in df_plot['pct']],
                textposition='outside',
                textfont=dict(color=T.TEXT, size=15, family='Arial Black'),
                hovertemplate='<b>%{x}</b><br>Equipe: %{y:.1f}%<extra></extra>',
            ))
            fig.update_layout(
                barmode='group',
                height=520,
                margin=dict(l=10, r=10, t=40, b=160),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    tickangle=-25,
                    tickfont=dict(color=T.TEXT, size=14),
                    automargin=True,
                ),
                yaxis=dict(
                    title=dict(
                        text='% da população elegível',
                        font=dict(color=T.TEXT, size=14),
                    ),
                    tickfont=dict(color=T.TEXT_MUTED, size=13),
                    gridcolor=T.GRID,
                    rangemode='tozero',
                ),
                legend=dict(
                    orientation='h', x=0.5, xanchor='center',
                    y=1.08, yanchor='bottom',
                    font=dict(color=T.TEXT, size=14),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "🟥 acima do município (≥ +0,5 pp) · "
                "🟧 próximo ao município · "
                "🟩 abaixo do município (≤ −0,5 pp)"
            )

# ─────────────────────────────────────────────────────────────
# ABA 3 — CONTINUIDADE DO CUIDADO
# ─────────────────────────────────────────────────────────────
with tab_cont:
    st.markdown("#### Continuidade do cuidado — panorama da equipe")
    st.caption(
        "Indicadores de acesso, regularidade e fragmentação do cuidado, "
        "com base nas consultas dos últimos 365 dias. Pacientes com "
        "maior carga de morbidade deveriam ter intervalos menores e "
        "maior regularidade — quando isso não acontece, há iniquidade "
        "no cuidado."
    )

    with st.spinner("Carregando indicadores de continuidade..."):
        cont = carregar_continuidade_agregado(ap_sel, cli_sel, esf_sel)

    n_total_c = int(cont.get('n_total', 0) or 0) or 1

    def _pct_int(num):
        return f"{int(num or 0)/n_total_c*100:.0f}%" if n_total_c else "0%"

    # ─── Bloco 1: KPIs panorâmicos (inspirado em INDICADORES_VIOLIN) ───
    st.markdown("##### Indicadores populacionais")
    c1, c2, c3, c4 = st.columns(4)
    _kpi(c1, "👥 Pacientes da equipe", f"{int(cont.get('n_total', 0) or 0):,}")
    _kpi(c2, "🩺 Sem médico há >180d",
         f"{int(cont.get('n_sem_medico_180d', 0) or 0):,}",
         _pct_int(cont.get('n_sem_medico_180d')))
    _kpi(c3, "📅 Regulares (≥6m com consulta)",
         f"{int(cont.get('n_regular', 0) or 0):,}",
         _pct_int(cont.get('n_regular')))
    _kpi(c4, "🚫 Sem nenhuma consulta no ano",
         f"{int(cont.get('n_sem_consulta_365d', 0) or 0):,}",
         _pct_int(cont.get('n_sem_consulta_365d')))

    c5, c6, c7, c8 = st.columns(4)
    _kpi(c5, "🧩 Fragmentação (>50% das consultas fora da clínica)",
         f"{int(cont.get('n_baixa_long', 0) or 0):,}",
         _pct_int(cont.get('n_baixa_long')))
    _kpi(c6, "⚠️ Alto risco + baixo acesso",
         f"{int(cont.get('n_alto_baixo_acesso', 0) or 0):,}",
         _pct_int(cont.get('n_alto_baixo_acesso')))
    _kpi(c7, "⏱️ Alto risco + intervalo longo",
         f"{int(cont.get('n_alto_intv_longo', 0) or 0):,}",
         _pct_int(cont.get('n_alto_intv_longo')))
    _kpi(c8, "🚑 Uso frequente de urgência",
         f"{int(cont.get('n_freq_urg', 0) or 0):,}",
         _pct_int(cont.get('n_freq_urg')))

    # Médias de consultas
    st.markdown("##### Médias por paciente (últimos 365 dias)")
    m1, m2, m3, m4 = st.columns(4)
    def _f(v):
        return f"{float(v or 0):.1f}" if v is not None else "—"
    _kpi(m1, "Consultas no total", _f(cont.get('media_consultas_total')))
    _kpi(m2, "Consultas médicas",  _f(cont.get('media_consultas_med')))
    _kpi(m3, "Consultas de enfermagem", _f(cont.get('media_consultas_enf')))
    _kpi(m4, "Consultas de técnico de enfermagem",
         _f(cont.get('media_consultas_tec')))

    m5, m6, m7, _m8 = st.columns(4)
    _kpi(m5, "Intervalo mediano entre consultas",
         f"{_f(cont.get('media_intv_mediano'))} dias")
    _kpi(m6, "% médicas na unidade",
         f"{_f(cont.get('media_pct_na_unidade'))}%")
    _kpi(m7, "% médicas fora da unidade",
         f"{_f(cont.get('media_pct_fora'))}%")

    st.markdown("---")

    # ─── Bloco 2: lista nominal ───
    st.markdown("##### Lista nominal de pacientes — continuidade do cuidado")

    with st.spinner("Carregando lista de pacientes..."):
        df_c = carregar_continuidade_nominal(ap_sel, cli_sel, esf_sel)

    if df_c.empty:
        st.warning("Sem pacientes para a equipe selecionada.")
    else:
        # Filtros — multiselect OR
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            sinalizadores = st.multiselect(
                "Mostrar pacientes com:",
                options=[
                    'Sem médico há >180d',
                    'Sem consulta no ano',
                    'Fragmentação (>50% das consultas fora da clínica)',
                    'Alto risco + baixo acesso',
                    'Alto risco + intervalo longo',
                    'Uso frequente de urgência',
                ],
                default=[],
                placeholder="Todos os pacientes (default)",
                help="Sem filtro: mostra todos. Selecione um ou mais para "
                     "restringir — lógica OR (paciente aparece se atender "
                     "a qualquer um dos sinalizadores marcados).",
                key="cont_filtro_sinaliz",
            )
        with col_f2:
            cargas_disp = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
            carga_sel = st.multiselect(
                "Carga de morbidade",
                options=cargas_disp,
                default=[],
                placeholder="Todas",
                key="cont_filtro_carga",
            )

        df_v = df_c.copy()
        if carga_sel:
            df_v = df_v[df_v['charlson_categoria'].isin(carga_sel)]

        if sinalizadores:
            mask = pd.Series(False, index=df_v.index)
            if 'Sem médico há >180d' in sinalizadores:
                mask |= (df_v['dias_desde_ultima_medica'].fillna(99999) > 180)
            if 'Sem consulta no ano' in sinalizadores:
                mask |= (df_v['consultas_365d'].fillna(0) == 0)
            if 'Fragmentação (>50% das consultas fora da clínica)' in sinalizadores:
                mask |= df_v['baixa_longitudinalidade'].fillna(False).astype(bool)
            if 'Alto risco + baixo acesso' in sinalizadores:
                mask |= df_v['alto_risco_baixo_acesso'].fillna(False).astype(bool)
            if 'Alto risco + intervalo longo' in sinalizadores:
                mask |= df_v['alto_risco_intervalo_longo'].fillna(False).astype(bool)
            if 'Uso frequente de urgência' in sinalizadores:
                mask |= df_v['usuario_frequente_urgencia'].fillna(False).astype(bool)
            df_v = df_v[mask]

        st.caption(
            f"**{len(df_v):,} pacientes** sendo apresentados "
            f"(de {len(df_c):,} pacientes da equipe)."
        )

        if df_v.empty:
            st.info("Nenhum paciente bate com a combinação de filtros selecionada.")
        else:
            df_r = df_v.copy()

            if MODO_ANONIMO:
                df_r['nome_exib'] = df_r.apply(
                    lambda r: anonimizar_nome(
                        str(r.get('cpf') or r.get('nome', '')),
                        r.get('genero', '')),
                    axis=1,
                )
            else:
                df_r['nome_exib'] = df_r['nome']

            # Calcular consultas médicas FORA da unidade (n_int)
            def _fora(row):
                med = row.get('consultas_medicas_365d')
                pct = row.get('pct_consultas_medicas_fora_365d')
                if pd.isna(med) or pd.isna(pct):
                    return None
                return int(round(float(med) * float(pct) / 100.0))
            df_r['n_med_fora'] = df_r.apply(_fora, axis=1)

            def _fmt_dias(v):
                return f"{int(v)}" if pd.notna(v) else "—"

            def _fmt_reg(v):
                if pd.isna(v) or v is None:
                    return '—'
                v = str(v).lower()
                return {
                    'regular':            '🟢 Regular',
                    'irregular':          '🟡 Irregular',
                    'esporadico':         '🟠 Esporádico',
                    'sem_acompanhamento': '🔴 Sem acompanhamento',
                }.get(v, v)

            def _fmt_alerta(*flags):
                """Concatena ⚠️ por flag positiva."""
                txt = []
                if flags[0]: txt.append('Fragmentação')
                if flags[1]: txt.append('Risco↑/Acesso↓')
                if flags[2]: txt.append('Risco↑/Intervalo')
                if flags[3]: txt.append('Urgência freq.')
                return ' · '.join(txt) if txt else '—'

            def _truthy(v):
                """Robusto a pd.NA / None / NaN."""
                if v is None:
                    return False
                try:
                    if pd.isna(v):
                        return False
                except (TypeError, ValueError):
                    pass
                return bool(v)

            df_r['alertas'] = df_r.apply(
                lambda r: _fmt_alerta(
                    _truthy(r.get('baixa_longitudinalidade')),
                    _truthy(r.get('alto_risco_baixo_acesso')),
                    _truthy(r.get('alto_risco_intervalo_longo')),
                    _truthy(r.get('usuario_frequente_urgencia')),
                ),
                axis=1,
            )

            df_r = df_r.sort_values(
                ['alto_risco_baixo_acesso', 'dias_desde_ultima_medica'],
                ascending=[False, False], na_position='last',
            )

            st.dataframe(
                pd.DataFrame({
                    'Paciente':   df_r['nome_exib'].values,
                    'Idade':      df_r['idade'].astype('Int64').values,
                    'Morbidades': df_r['morbidades_lista'].fillna('—').values,
                    'Última prescrição crônica':
                        df_r['medicamentos_lista'].fillna('—').values,
                    'Carga de Morbidade':
                        df_r['charlson_categoria'].fillna('—').values,
                    'Consultas/ano':
                        df_r['consultas_365d'].astype('Int64').values,
                    'Médicas/ano':
                        df_r['consultas_medicas_365d'].astype('Int64').values,
                    'Enfermagem/ano':
                        df_r['consultas_enfermagem_365d'].astype('Int64').values,
                    'Técnico/ano':
                        df_r['consultas_tecnico_enfermagem_365d'].astype('Int64').values,
                    'Médicas fora':
                        df_r['n_med_fora'].astype('Int64').values,
                    '% fora':
                        df_r['pct_consultas_medicas_fora_365d'].astype(float).values,
                    'Dias s/ médico':
                        df_r['dias_desde_ultima_medica'].apply(_fmt_dias).values,
                    'Dias s/ enfermagem':
                        df_r['dias_desde_ultima_enfermagem'].apply(_fmt_dias).values,
                    'Intervalo mediano':
                        df_r['intervalo_mediano_dias'].apply(_fmt_dias).values,
                    'Regularidade':
                        df_r['regularidade_acompanhamento'].apply(_fmt_reg).values,
                    'Sinalizadores':
                        df_r['alertas'].values,
                }),
                hide_index=True, use_container_width=True, height=540,
                column_config={
                    'Paciente':   st.column_config.TextColumn('Paciente', width='medium'),
                    'Idade':      st.column_config.NumberColumn('Idade', width='small'),
                    'Morbidades': st.column_config.TextColumn('Morbidades', width='large'),
                    'Última prescrição crônica':
                        st.column_config.TextColumn('Última prescrição crônica',
                                                    width='large'),
                    'Carga de Morbidade':
                        st.column_config.TextColumn('Carga de Morbidade', width='small'),
                    'Consultas/ano':
                        st.column_config.NumberColumn('Consultas/ano', width='small'),
                    'Médicas/ano':
                        st.column_config.NumberColumn('Médicas/ano', width='small'),
                    'Enfermagem/ano':
                        st.column_config.NumberColumn('Enfermagem/ano', width='small'),
                    'Técnico/ano':
                        st.column_config.NumberColumn('Técnico/ano', width='small'),
                    'Médicas fora':
                        st.column_config.NumberColumn('Médicas fora', width='small'),
                    '% fora':
                        st.column_config.NumberColumn('% fora', format='%.0f%%',
                                                      width='small'),
                    'Dias s/ médico':
                        st.column_config.TextColumn('Dias s/ médico', width='small'),
                    'Dias s/ enfermagem':
                        st.column_config.TextColumn('Dias s/ enfermagem', width='small'),
                    'Intervalo mediano':
                        st.column_config.TextColumn('Intervalo mediano (d)',
                                                    width='small'),
                    'Regularidade':
                        st.column_config.TextColumn('Regularidade', width='small'),
                    'Sinalizadores':
                        st.column_config.TextColumn('Sinalizadores', width='medium'),
                },
            )

            with st.expander("ℹ️ O que significa cada coluna"):
                st.markdown("""
- **Paciente** — nome (anonimizado quando o modo está ativo).
- **Idade** — em anos.
- **Morbidades** — diagnósticos crônicos ativos no prontuário.
- **Última prescrição crônica** — medicamentos da prescrição mais recente.
- **Carga de Morbidade** — categoria do escore de Charlson
  (Baixo / Moderado / Alto / Muito Alto).
- **Consultas/ano** — total de consultas do paciente nos últimos
  365 dias (todas as categorias profissionais somadas).
- **Médicas/ano**, **Enfermagem/ano**, **Técnico/ano** — número de
  consultas em cada categoria nos últimos 365 dias.
- **Médicas fora** — número de consultas médicas realizadas em
  unidade diferente da de cadastro.
- **% fora** — proporção das consultas médicas do paciente que
  ocorreram fora da unidade de cadastro.
- **Dias s/ médico** / **Dias s/ enfermagem** — dias decorridos
  desde a última consulta de cada profissional.
- **Intervalo mediano (d)** — mediana dos intervalos entre
  consultas consecutivas. Reflete o ritmo habitual de acesso.
- **Regularidade** — 🟢 Regular (≥6 meses com consulta), 🟡
  Irregular, 🟠 Esporádico, 🔴 Sem acompanhamento.
- **Sinalizadores** — alertas combinados:
  *Fragmentação* = >50% das consultas fora da unidade;
  *Risco↑/Acesso↓* = carga muito alta (≥7) com consultas abaixo
  do P25 dos pares (iniquidade);
  *Risco↑/Intervalo* = carga alta com intervalo entre consultas
  acima do esperado;
  *Urgência freq.* = ≥3 atendimentos em UPA/CER/hospital de
  urgência nos últimos 365 dias.
""")

# ─────────────────────────────────────────────────────────────
# ABA 4 — POLIFARMÁCIA (STOPP/START/Beers)
# ─────────────────────────────────────────────────────────────
with tab_polif:
    st.markdown("#### Critérios de prescrição em idosos — STOPP, START, Beers e escore ACB")
    st.caption(
        "STOPP = medicamentos potencialmente inapropriados que devem ser "
        "evitados/revistos. START = medicamentos indicados ausentes da "
        "prescrição. Beers = critérios complementares (AGS 2023). "
        "ACB = Anticholinergic Cognitive Burden score, soma da carga "
        "anticolinérgica dos medicamentos em uso. "
        "Cada paciente pode somar múltiplos critérios; um critério é "
        "contado uma única vez por paciente, independente de quantos "
        "medicamentos da classe estejam prescritos."
    )

    with st.spinner("Calculando critérios da equipe..."):
        agg = carregar_criterios_idoso_agregado(ap_sel, cli_sel, esf_sel)

    n_total_pol = agg.get('n_pacientes_equipe', 0) or 1

    # ─── Cards de totais por tipo ───
    p1, p2, p3, p4 = st.columns(4)
    _kpi(p1, "👥 Pacientes da equipe", f"{agg.get('n_pacientes_equipe', 0):,}")
    _kpi(p2, "🚫 Com STOPP", f"{agg.get('n_com_stopp', 0):,}",
         f"{agg.get('n_com_stopp', 0)/n_total_pol*100:.0f}%")
    _kpi(p3, "💡 Com START", f"{agg.get('n_com_start', 0):,}",
         f"{agg.get('n_com_start', 0)/n_total_pol*100:.0f}%")
    _kpi(p4, "🇺🇸 Com Beers", f"{agg.get('n_com_beers', 0):,}",
         f"{agg.get('n_com_beers', 0)/n_total_pol*100:.0f}%")

    # ─── Distribuição: gráfico de barras ───
    st.markdown("##### Distribuição de critérios por paciente")
    st.caption(
        "Quantos pacientes têm 0, 1, 2, 3 ou ≥4 critérios de cada tipo."
    )
    df_d_stopp = agg.get('distribuicao_stopp', pd.DataFrame())
    df_d_start = agg.get('distribuicao_start', pd.DataFrame())
    df_d_beers = agg.get('distribuicao_beers', pd.DataFrame())

    if not df_d_stopp.empty:
        fig_d = go.Figure()
        ordem = ['0', '1', '2', '3', '≥4']
        fig_d.add_trace(go.Bar(
            x=ordem, y=df_d_stopp.set_index('n_criterios')
                                  .reindex(ordem)['n_pacientes'].values,
            name='STOPP',
            marker=dict(color='#C0392B'),
            text=df_d_stopp.set_index('n_criterios')
                            .reindex(ordem)['n_pacientes'].values,
            textposition='outside',
            textfont=dict(size=14, color=T.TEXT),
        ))
        fig_d.add_trace(go.Bar(
            x=ordem, y=df_d_start.set_index('n_criterios')
                                  .reindex(ordem)['n_pacientes'].values,
            name='START',
            marker=dict(color='#27AE60'),
            text=df_d_start.set_index('n_criterios')
                            .reindex(ordem)['n_pacientes'].values,
            textposition='outside',
            textfont=dict(size=14, color=T.TEXT),
        ))
        fig_d.add_trace(go.Bar(
            x=ordem, y=df_d_beers.set_index('n_criterios')
                                  .reindex(ordem)['n_pacientes'].values,
            name='Beers',
            marker=dict(color='#4f8ef7'),
            text=df_d_beers.set_index('n_criterios')
                            .reindex(ordem)['n_pacientes'].values,
            textposition='outside',
            textfont=dict(size=14, color=T.TEXT),
        ))
        fig_d.update_layout(
            barmode='group',
            height=380,
            margin=dict(l=10, r=10, t=20, b=40),
            paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
            xaxis=dict(
                title=dict(text='Nº de critérios por paciente',
                           font=dict(color=T.TEXT, size=14)),
                tickfont=dict(color=T.TEXT, size=14),
            ),
            yaxis=dict(
                title=dict(text='Pacientes',
                           font=dict(color=T.TEXT, size=14)),
                tickfont=dict(color=T.TEXT_MUTED, size=13),
                gridcolor=T.GRID,
                rangemode='tozero',
            ),
            legend=dict(orientation='h', x=0.5, xanchor='center',
                        y=1.10, yanchor='bottom',
                        font=dict(color=T.TEXT, size=14)),
        )
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")

    # ─── Tabela detalhada de cada critério ───
    df_tot = agg.get('totais_por_criterio', pd.DataFrame())
    if not df_tot.empty:
        st.markdown("##### Detalhe por critério")

        tipo_sel = st.radio(
            "Tipo de critério",
            options=['STOPP', 'START', 'Beers', 'Todos'],
            index=0, horizontal=True, key="pol_tipo_filtro",
        )

        df_show = df_tot.copy()
        if tipo_sel != 'Todos':
            df_show = df_show[df_show['tipo'] == tipo_sel]
        df_show = df_show.sort_values('n_pacientes', ascending=False)

        st.dataframe(
            pd.DataFrame({
                'Tipo':         df_show['tipo'].values,
                'Categoria':    df_show['categoria'].values,
                'Critério':     df_show['descricao'].values,
                'Pacientes':    df_show['n_pacientes'].values,
                '% Equipe':     df_show['pct'].values,
                'Justificativa clínica': df_show['justificativa'].values,
            }),
            hide_index=True, use_container_width=True, height=520,
            column_config={
                'Tipo':       st.column_config.TextColumn('Tipo', width='small'),
                'Categoria':  st.column_config.TextColumn('Categoria', width='small'),
                'Critério':   st.column_config.TextColumn('Critério', width='medium'),
                'Pacientes':  st.column_config.NumberColumn('Pacientes', width='small'),
                '% Equipe':   st.column_config.NumberColumn('% Equipe', format='%.1f%%',
                                                            width='small'),
                'Justificativa clínica':
                    st.column_config.TextColumn('Justificativa clínica', width='large'),
            },
        )

    st.markdown("---")

    # ─── Lista nominal dos pacientes com ≥1 critério ───
    st.markdown("##### Lista de pacientes com critérios positivos")

    with st.spinner("Carregando lista nominal..."):
        df_nom = carregar_criterios_idoso_nominal(ap_sel, cli_sel, esf_sel)

    if df_nom.empty:
        st.success("✅ Nenhum paciente da equipe tem critério STOPP/START/Beers/ACB ativo.")
    else:
        # Filtro: mostrar pacientes com critérios específicos
        filtros_sel = st.multiselect(
            "Mostrar pacientes com:",
            options=['STOPP', 'START', 'Beers', 'ACB ≥ 3'],
            default=[],
            placeholder="Todos os critérios (default)",
            help="Sem filtro: mostra todos com pelo menos um critério "
                 "positivo. Selecione um ou mais para restringir — a "
                 "lógica é OR (paciente aparece se atender a qualquer "
                 "um dos critérios marcados).",
            key="pol_filtro_criterios",
        )

        df_nom_filt = df_nom.copy()
        if filtros_sel:
            mask = pd.Series(False, index=df_nom_filt.index)
            if 'STOPP'   in filtros_sel: mask |= (df_nom_filt['total_stopp'] > 0)
            if 'START'   in filtros_sel: mask |= (df_nom_filt['total_start'] > 0)
            if 'Beers'   in filtros_sel: mask |= (df_nom_filt['total_beers'] > 0)
            if 'ACB ≥ 3' in filtros_sel:
                mask |= (df_nom_filt['acb_score_total'].fillna(0) >= 3)
            df_nom_filt = df_nom_filt[mask]

        st.caption(
            f"**{len(df_nom_filt):,} pacientes** sendo apresentados "
            f"(de {len(df_nom):,} da equipe com pelo menos um critério "
            f"STOPP/START/Beers ou ACB ≥ 3)."
        )

        if df_nom_filt.empty:
            st.info("Nenhum paciente bate com a combinação de filtros selecionada.")
        else:
            df_render = df_nom_filt.copy()
            todos_codigos = (todos_codigos_stopp() + todos_codigos_start()
                             + todos_codigos_beers())

            def _linhas_paciente(row):
                """Lista descrições dos critérios STOPP/START/Beers ativos,
                separadas por vírgula e sem códigos."""
                ativos = []
                for c in todos_codigos:
                    v = row.get(c)
                    if v in [True, 1, '1', 'True', 'true', 'TRUE']:
                        ativos.append(descricao_curta(c))
                return ", ".join(ativos) if ativos else "—"

            df_render['criterios_ativos'] = df_render.apply(_linhas_paciente, axis=1)

            if MODO_ANONIMO:
                df_render['nome_exib'] = df_render.apply(
                    lambda r: anonimizar_nome(
                        str(r.get('cpf') or r.get('nome', '')),
                        r.get('genero', '')),
                    axis=1,
                )
            else:
                df_render['nome_exib'] = df_render['nome']

            df_render['total_critérios'] = (
                df_render['total_stopp']
                + df_render['total_start']
                + df_render['total_beers']
            )
            df_render = df_render.sort_values('total_critérios', ascending=False)

            st.dataframe(
                pd.DataFrame({
                    'Paciente':   df_render['nome_exib'].values,
                    'Idade':      df_render['idade'].astype('Int64').values,
                    'Morbidades': df_render['morbidades_lista'].fillna('—').values,
                    'Última prescrição crônica':
                        df_render['medicamentos_lista'].fillna('—').values,
                    'ACB':        df_render['acb_score_total'].astype('Int64').values,
                    'STOPP':      df_render['total_stopp'].astype('Int64').values,
                    'START':      df_render['total_start'].astype('Int64').values,
                    'Beers':      df_render['total_beers'].astype('Int64').values,
                    'Total':      df_render['total_critérios'].astype('Int64').values,
                    'Critérios ativos': df_render['criterios_ativos'].values,
                }),
                hide_index=True, use_container_width=True, height=520,
                column_config={
                    'Paciente':   st.column_config.TextColumn('Paciente', width='medium'),
                    'Idade':      st.column_config.NumberColumn('Idade', width='small'),
                    'Morbidades': st.column_config.TextColumn('Morbidades', width='large'),
                    'Última prescrição crônica':
                        st.column_config.TextColumn('Última prescrição crônica',
                                                    width='large'),
                    'ACB':        st.column_config.NumberColumn('ACB', width='small'),
                    'STOPP':      st.column_config.NumberColumn('STOPP', width='small'),
                    'START':      st.column_config.NumberColumn('START', width='small'),
                    'Beers':      st.column_config.NumberColumn('Beers', width='small'),
                    'Total':      st.column_config.NumberColumn('Total', width='small'),
                    'Critérios ativos':
                        st.column_config.TextColumn('Critérios ativos', width='large'),
                },
            )

            # Legenda das colunas
            with st.expander("ℹ️ O que significa cada coluna"):
                st.markdown("""
- **Paciente** — nome (anonimizado quando o modo está ativo).
- **Idade** — em anos.
- **Morbidades** — diagnósticos crônicos ativos no prontuário.
- **Última prescrição crônica** — medicamentos da prescrição mais recente.
- **ACB** — *Anticholinergic Cognitive Burden* score, soma da carga
  anticolinérgica dos medicamentos em uso. **ACB ≥ 3** indica risco
  clinicamente relevante de confusão, delirium e quedas.
- **STOPP** — nº de critérios STOPP positivos (medicamentos
  potencialmente inapropriados que devem ser evitados ou revistos).
- **START** — nº de critérios START positivos (medicamentos
  indicados para a condição mas ausentes da prescrição).
- **Beers** — nº de critérios Beers (AGS 2023) positivos —
  complementares ao STOPP, focados em situações específicas de risco.
- **Total** — soma de STOPP + START + Beers.
- **Critérios ativos** — descrição clínica dos critérios sinalizados.
  Consulte a tabela **'Detalhe por critério'** acima para a
  justificativa clínica completa de cada um.
""")


# ─────────────────────────────────────────────────────────────
# ABA 5 — HIPERTENSÃO (HAS)
# ─────────────────────────────────────────────────────────────
with tab_has:
    st.markdown("#### Hipertensão arterial — controle e lacunas da equipe")
    st.caption(
        "Apenas pacientes com diagnóstico ativo de HAS. Status do "
        "controle pressórico vem da fato (status_controle_pressorio) "
        "e considera as últimas aferições registradas."
    )

    with st.spinner("Carregando indicadores de HAS..."):
        ag_h = carregar_hipertensao_agregado(ap_sel, cli_sel, esf_sel)

    n_has = int(ag_h.get('n_has', 0) or 0) or 1

    def _pct_h(num):
        return f"{int(num or 0)/n_has*100:.0f}%" if n_has else "0%"

    # KPIs
    st.markdown("##### Indicadores populacionais (denominador = hipertensos)")
    h1, h2, h3, h4 = st.columns(4)
    _kpi(h1, "🩺 Hipertensos na equipe",
         f"{int(ag_h.get('n_has', 0) or 0):,}",
         f"{int(ag_h.get('n_has', 0) or 0)/(int(ag_h.get('n_total', 0) or 1))*100:.0f}% da equipe")
    _kpi(h2, "✅ PA controlada",
         f"{int(ag_h.get('n_ctrl', 0) or 0):,}",
         _pct_h(ag_h.get('n_ctrl')))
    _kpi(h3, "❌ PA descontrolada",
         f"{int(ag_h.get('n_desc', 0) or 0):,}",
         _pct_h(ag_h.get('n_desc')))
    _kpi(h4, "⚠️ HAS sem CID",
         f"{int(ag_h.get('n_sem_cid', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_cid')))

    h5, h6, h7, h8 = st.columns(4)
    _kpi(h5, "📉 Sem aferição PA >180d",
         f"{int(ag_h.get('n_sem_pa_180d', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_pa_180d')))
    _kpi(h6, "🧪 Sem creatinina (365d)",
         f"{int(ag_h.get('n_sem_creat', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_creat')))
    _kpi(h7, "🧪 Sem colesterol (365d)",
         f"{int(ag_h.get('n_sem_col', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_col')))
    _kpi(h8, "🫀 Sem ECG (365d)",
         f"{int(ag_h.get('n_sem_ecg', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_ecg')))

    h9, h10, h11, _h12 = st.columns(4)
    _kpi(h9, "💉 Sem EAS (365d)",
         f"{int(ag_h.get('n_sem_eas', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_eas')))
    _kpi(h10, "⚖️ Sem IMC calculável",
         f"{int(ag_h.get('n_sem_imc', 0) or 0):,}",
         _pct_h(ag_h.get('n_sem_imc')))
    _kpi(h11, "PAS / PAD média",
         f"{int(ag_h.get('media_pas') or 0)} / {int(ag_h.get('media_pad') or 0)}")

    st.markdown("---")
    st.markdown("##### Lista nominal de hipertensos")

    with st.spinner("Carregando lista de hipertensos..."):
        df_h = carregar_hipertensao_nominal(ap_sel, cli_sel, esf_sel)

    if df_h.empty:
        st.info("Sem pacientes com HAS na equipe.")
    else:
        col_fh1, col_fh2 = st.columns([2, 1])
        with col_fh1:
            sin_h = st.multiselect(
                "Mostrar pacientes com:",
                options=[
                    'PA descontrolada',
                    'Sem aferição PA >180d',
                    'Sem médico há >180d',
                    'Sem CID',
                    'Sem creatinina',
                    'Sem colesterol',
                    'Sem EAS',
                    'Sem ECG',
                    'Sem IMC calculável',
                    'DM + HAS com PA >135/80',
                    'HAS + IRC',
                    'HAS + ICC',
                    'HAS + CI',
                    'HAS + DM',
                ],
                default=[],
                placeholder="Todos os hipertensos (default)",
                help="Lógica OR — paciente aparece se atender a qualquer "
                     "um dos sinalizadores marcados.",
                key="has_filtro_sin",
            )
        with col_fh2:
            cargas_disp_h = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
            carga_h = st.multiselect(
                "Carga de morbidade",
                options=cargas_disp_h, default=[], placeholder="Todas",
                key="has_filtro_carga",
            )

        col_fh3, _ = st.columns([2, 2])
        with col_fh3:
            faixa_h = st.multiselect(
                "Faixa etária",
                options=['<60a', '60–79a', '≥80a'],
                default=[], placeholder="Todas",
                key="has_filtro_faixa",
            )

        df_hv = df_h.copy()
        if carga_h:
            df_hv = df_hv[df_hv['charlson_categoria'].isin(carga_h)]
        if faixa_h:
            mfx = pd.Series(False, index=df_hv.index)
            if '<60a'   in faixa_h: mfx |= (df_hv['idade'] < 60)
            if '60–79a' in faixa_h: mfx |= ((df_hv['idade'] >= 60) & (df_hv['idade'] < 80))
            if '≥80a'   in faixa_h: mfx |= (df_hv['idade'] >= 80)
            df_hv = df_hv[mfx]
        if sin_h:
            mask = pd.Series(False, index=df_hv.index)
            if 'PA descontrolada'  in sin_h:
                mask |= (df_hv['status_controle_pressorio'] == 'descontrolado')
            if 'Sem aferição PA >180d' in sin_h:
                mask |= df_hv['lacuna_PA_hipertenso_180d'].fillna(False).astype(bool)
            if 'Sem médico há >180d' in sin_h:
                mask |= (df_hv['dias_desde_ultima_medica'].fillna(99999) > 180)
            if 'Sem CID'           in sin_h:
                mask |= df_hv['HAS_sem_CID'].fillna(False).astype(bool)
            if 'Sem creatinina'    in sin_h:
                mask |= df_hv['lacuna_creatinina_HAS_DM'].fillna(False).astype(bool)
            if 'Sem colesterol'    in sin_h:
                mask |= df_hv['lacuna_colesterol_HAS_DM'].fillna(False).astype(bool)
            if 'Sem EAS'           in sin_h:
                mask |= df_hv['lacuna_eas_HAS_DM'].fillna(False).astype(bool)
            if 'Sem ECG'           in sin_h:
                mask |= df_hv['lacuna_ecg_HAS_DM'].fillna(False).astype(bool)
            if 'Sem IMC calculável' in sin_h:
                mask |= df_hv['lacuna_IMC_HAS_DM'].fillna(False).astype(bool)
            if 'DM + HAS com PA >135/80' in sin_h:
                mask |= df_hv['lacuna_DM_HAS_PA_descontrolada'].fillna(False).astype(bool)
            if 'HAS + IRC' in sin_h:
                mask |= df_hv['IRC'].notna()
            if 'HAS + ICC' in sin_h:
                mask |= df_hv['ICC'].notna()
            if 'HAS + CI'  in sin_h:
                mask |= df_hv['CI'].notna()
            if 'HAS + DM'  in sin_h:
                mask |= df_hv['DM'].notna()
            df_hv = df_hv[mask]

        st.caption(
            f"**{len(df_hv):,} hipertensos** sendo apresentados "
            f"(de {len(df_h):,} hipertensos da equipe)."
        )

        if df_hv.empty:
            st.info("Nenhum paciente bate com a combinação de filtros selecionada.")
        else:
            df_hr = df_hv.copy()

            if MODO_ANONIMO:
                df_hr['nome_exib'] = df_hr.apply(
                    lambda r: anonimizar_nome(
                        str(r.get('cpf') or r.get('nome', '')),
                        r.get('genero', '')),
                    axis=1,
                )
            else:
                df_hr['nome_exib'] = df_hr['nome']

            def _truthy_h(v):
                if v is None: return False
                try:
                    if pd.isna(v): return False
                except (TypeError, ValueError):
                    pass
                return bool(v)

            def _lacunas_has(r):
                ats = []
                pares = [
                    ('lacuna_PA_hipertenso_180d',          'Sem PA (>180d)'),
                    ('lacuna_HAS_descontrolado_menor80',   'PA descontrolada (<80a)'),
                    ('lacuna_HAS_descontrolado_80mais',    'PA descontrolada (≥80a)'),
                    ('lacuna_DM_HAS_PA_descontrolada',     'DM+HAS PA >135/80'),
                    ('lacuna_creatinina_HAS_DM',           'Sem creatinina'),
                    ('lacuna_colesterol_HAS_DM',           'Sem colesterol'),
                    ('lacuna_eas_HAS_DM',                  'Sem EAS'),
                    ('lacuna_ecg_HAS_DM',                  'Sem ECG'),
                    ('lacuna_IMC_HAS_DM',                  'Sem IMC'),
                ]
                for col, txt in pares:
                    if _truthy_h(r.get(col)):
                        ats.append(txt)
                if _truthy_h(r.get('HAS_sem_CID')):
                    ats.append('Sem CID')
                return ", ".join(ats) if ats else "—"

            df_hr['lacunas_has'] = df_hr.apply(_lacunas_has, axis=1)

            def _pa_str(r):
                pas = r.get('pressao_sistolica')
                pad = r.get('pressao_diastolica')
                if pd.isna(pas) or pd.isna(pad):
                    return "—"
                return f"{int(pas)}/{int(pad)}"

            df_hr['pa_atual'] = df_hr.apply(_pa_str, axis=1)

            def _ctrl_str(v):
                v = str(v or '').lower()
                return {'controlado':    '🟢 Controlado',
                        'descontrolado': '🔴 Descontrolado'}.get(v, '— sem dados')

            df_hr['ctrl_str'] = df_hr['status_controle_pressorio'].apply(_ctrl_str)

            def _fmt_dias(v):
                return f"{int(v)}" if pd.notna(v) else "—"

            df_hr = df_hr.sort_values(
                ['status_controle_pressorio', 'dias_desde_ultima_pa'],
                ascending=[True, False], na_position='last',
            )

            st.dataframe(
                pd.DataFrame({
                    'Paciente':   df_hr['nome_exib'].values,
                    'Idade':      df_hr['idade'].astype('Int64').values,
                    'Morbidades': df_hr['morbidades_lista'].fillna('—').values,
                    'Última prescrição crônica':
                        df_hr['medicamentos_lista'].fillna('—').values,
                    'Carga de Morbidade':
                        df_hr['charlson_categoria'].fillna('—').values,
                    'PA atual (mmHg)':  df_hr['pa_atual'].values,
                    'Dias s/ PA':       df_hr['dias_desde_ultima_pa'].apply(_fmt_dias).values,
                    'Controle':         df_hr['ctrl_str'].values,
                    '% dias controlado (365d)':
                        df_hr['pct_dias_has_controlado_365d'].astype(float).values,
                    'Meta PAS':         df_hr['meta_pas'].astype('Int64').values,
                    'Lacunas de HAS':   df_hr['lacunas_has'].values,
                }),
                hide_index=True, use_container_width=True, height=540,
                column_config={
                    'Paciente':   st.column_config.TextColumn('Paciente', width='medium'),
                    'Idade':      st.column_config.NumberColumn('Idade', width='small'),
                    'Morbidades': st.column_config.TextColumn('Morbidades', width='large'),
                    'Última prescrição crônica':
                        st.column_config.TextColumn('Última prescrição crônica',
                                                    width='large'),
                    'Carga de Morbidade':
                        st.column_config.TextColumn('Carga de Morbidade', width='small'),
                    'PA atual (mmHg)':
                        st.column_config.TextColumn('PA atual (mmHg)', width='small'),
                    'Dias s/ PA':
                        st.column_config.TextColumn('Dias s/ PA', width='small'),
                    'Controle':
                        st.column_config.TextColumn('Controle', width='small'),
                    '% dias controlado (365d)':
                        st.column_config.NumberColumn('% dias controlado',
                                                       format='%.0f%%', width='small'),
                    'Meta PAS':
                        st.column_config.NumberColumn('Meta PAS', width='small'),
                    'Lacunas de HAS':
                        st.column_config.TextColumn('Lacunas de HAS', width='large'),
                },
            )

            with st.expander("ℹ️ O que significa cada coluna"):
                st.markdown("""
- **Paciente** — nome (anonimizado quando o modo está ativo).
- **Idade** — anos.
- **Morbidades** — diagnósticos crônicos ativos.
- **Última prescrição crônica** — medicamentos da prescrição mais recente.
- **Carga de Morbidade** — categoria do escore de Charlson.
- **PA atual (mmHg)** — última aferição registrada (PAS/PAD).
- **Dias s/ PA** — dias desde a última aferição.
- **Controle** — 🟢 Controlado / 🔴 Descontrolado / — sem dados,
  conforme `status_controle_pressorio`.
- **% dias controlado (365d)** — proporção dos dias do último ano
  em que o paciente esteve com PA dentro da meta.
- **Meta PAS** — meta sistólica para o paciente (varia conforme
  idade, comorbidades — DM/IRC têm meta mais restrita).
- **Lacunas de HAS** — checagens em aberto: sem PA recente, PA
  descontrolada por faixa etária, exames laboratoriais ausentes,
  IMC não calculável, ou diagnóstico sem CID.
""")

# ─────────────────────────────────────────────────────────────
# ABA 6 — DIABETES MELLITUS (DM)
# ─────────────────────────────────────────────────────────────
with tab_dm:
    st.markdown("#### Diabetes mellitus — controle e lacunas da equipe")
    st.caption(
        "Apenas pacientes com diagnóstico ativo de DM. Status do "
        "controle glicêmico considera HbA1c recente vs meta etária "
        "(<60a → 7,0%; 60–69a → 7,5%; ≥70a → 8,0%)."
    )

    with st.spinner("Carregando indicadores de DM..."):
        ag_d = carregar_diabetes_agregado(ap_sel, cli_sel, esf_sel)

    n_dm = int(ag_d.get('n_dm', 0) or 0) or 1

    def _pct_d(num):
        return f"{int(num or 0)/n_dm*100:.0f}%" if n_dm else "0%"

    st.markdown("##### Indicadores populacionais (denominador = diabéticos)")
    d1, d2, d3, d4 = st.columns(4)
    _kpi(d1, "🩸 Diabéticos na equipe",
         f"{int(ag_d.get('n_dm', 0) or 0):,}",
         f"{int(ag_d.get('n_dm', 0) or 0)/(int(ag_d.get('n_total', 0) or 1))*100:.0f}% da equipe")
    _kpi(d2, "✅ Glicemia controlada",
         f"{int(ag_d.get('n_ctrl', 0) or 0):,}",
         _pct_d(ag_d.get('n_ctrl')))
    _kpi(d3, "❌ HbA1c acima da meta",
         f"{int(ag_d.get('n_lac_desc', 0) or 0):,}",
         _pct_d(ag_d.get('n_lac_desc')))
    _kpi(d4, "⚠️ DM sem CID",
         f"{int(ag_d.get('n_sem_cid', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_cid')))

    d5, d6, d7, d8 = st.columns(4)
    _kpi(d5, "📉 Sem HbA1c (>180d)",
         f"{int(ag_d.get('n_sem_a1c_180d', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_a1c_180d')))
    _kpi(d6, "🚫 Nunca fez HbA1c",
         f"{int(ag_d.get('n_nunca_a1c', 0) or 0):,}",
         _pct_d(ag_d.get('n_nunca_a1c')))
    _kpi(d7, "🦶 Sem exame do pé (365d)",
         f"{int(ag_d.get('n_sem_pe', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_pe')))
    _kpi(d8, "🧪 Sem microalbuminúria",
         f"{int(ag_d.get('n_sem_micro', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_micro')))

    d9, d10, d11, d12 = st.columns(4)
    _kpi(d9, "💊 DM complicado sem SGLT-2",
         f"{int(ag_d.get('n_complic_sem_sglt2', 0) or 0):,}",
         _pct_d(ag_d.get('n_complic_sem_sglt2')))
    _kpi(d10, "🧪 Sem creatinina",
         f"{int(ag_d.get('n_sem_creat', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_creat')))
    _kpi(d11, "🧪 Sem colesterol",
         f"{int(ag_d.get('n_sem_col', 0) or 0):,}",
         _pct_d(ag_d.get('n_sem_col')))
    _kpi(d12, "HbA1c média",
         f"{float(ag_d.get('media_a1c') or 0):.1f}%" if ag_d.get('media_a1c') else "—")

    st.markdown("---")
    st.markdown("##### Lista nominal de diabéticos")

    with st.spinner("Carregando lista de diabéticos..."):
        df_d = carregar_diabetes_nominal(ap_sel, cli_sel, esf_sel)

    if df_d.empty:
        st.info("Sem pacientes com DM na equipe.")
    else:
        col_fd1, col_fd2 = st.columns([2, 1])
        with col_fd1:
            sin_d = st.multiselect(
                "Mostrar pacientes com:",
                options=[
                    'HbA1c acima da meta',
                    'HbA1c severamente alta (≥9%)',
                    'Sem HbA1c recente (>180d)',
                    'Nunca fez HbA1c',
                    'Sem médico há >180d',
                    'Sem exame do pé (365d)',
                    'Sem microalbuminúria',
                    'DM complicado sem SGLT-2',
                    'DM tipo 1 provável',
                    'DM + IRC',
                    'DM + ICC',
                    'DM + CI',
                    'DM + HAS',
                    'Sem CID',
                    'Sem creatinina',
                    'Sem colesterol',
                    'Sem ECG',
                ],
                default=[],
                placeholder="Todos os diabéticos (default)",
                help="Lógica OR — paciente aparece se atender a qualquer "
                     "um dos sinalizadores marcados.",
                key="dm_filtro_sin",
            )
        with col_fd2:
            cargas_disp_d = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
            carga_d = st.multiselect(
                "Carga de morbidade",
                options=cargas_disp_d, default=[], placeholder="Todas",
                key="dm_filtro_carga",
            )

        col_fd3, _ = st.columns([2, 2])
        with col_fd3:
            faixa_d = st.multiselect(
                "Faixa etária",
                options=['<60a', '60–79a', '≥80a'],
                default=[], placeholder="Todas",
                key="dm_filtro_faixa",
            )

        df_dv = df_d.copy()
        if carga_d:
            df_dv = df_dv[df_dv['charlson_categoria'].isin(carga_d)]
        if faixa_d:
            mfx = pd.Series(False, index=df_dv.index)
            if '<60a'   in faixa_d: mfx |= (df_dv['idade'] < 60)
            if '60–79a' in faixa_d: mfx |= ((df_dv['idade'] >= 60) & (df_dv['idade'] < 80))
            if '≥80a'   in faixa_d: mfx |= (df_dv['idade'] >= 80)
            df_dv = df_dv[mfx]
        if sin_d:
            mask = pd.Series(False, index=df_dv.index)
            if 'HbA1c acima da meta' in sin_d:
                mask |= df_dv['lacuna_DM_descontrolado'].fillna(False).astype(bool)
            if 'HbA1c severamente alta (≥9%)' in sin_d:
                mask |= (df_dv['hba1c_atual'].fillna(0) >= 9)
            if 'Sem HbA1c recente (>180d)' in sin_d:
                mask |= df_dv['lacuna_DM_sem_HbA1c_recente'].fillna(False).astype(bool)
            if 'Nunca fez HbA1c' in sin_d:
                mask |= df_dv['hba1c_atual'].isna()
            if 'Sem médico há >180d' in sin_d:
                mask |= (df_dv['dias_desde_ultima_medica'].fillna(99999) > 180)
            if 'Sem exame do pé (365d)' in sin_d:
                mask |= df_dv['lacuna_DM_sem_exame_pe_365d'].fillna(False).astype(bool)
            if 'Sem microalbuminúria' in sin_d:
                mask |= df_dv['lacuna_DM_microalbuminuria_nao_solicitado'].fillna(False).astype(bool)
            if 'DM complicado sem SGLT-2' in sin_d:
                mask |= df_dv['lacuna_DM_complicado_sem_SGLT2'].fillna(False).astype(bool)
            if 'DM tipo 1 provável' in sin_d:
                mask |= df_dv['provavel_dm1'].fillna(False).astype(bool)
            if 'DM + IRC' in sin_d:
                mask |= df_dv['IRC'].notna()
            if 'DM + ICC' in sin_d:
                mask |= df_dv['ICC'].notna()
            if 'DM + CI'  in sin_d:
                mask |= df_dv['CI'].notna()
            if 'DM + HAS' in sin_d:
                mask |= df_dv['HAS'].notna()
            if 'Sem CID' in sin_d:
                mask |= df_dv['DM_sem_CID'].fillna(False).astype(bool)
            if 'Sem creatinina' in sin_d:
                mask |= df_dv['lacuna_creatinina_HAS_DM'].fillna(False).astype(bool)
            if 'Sem colesterol' in sin_d:
                mask |= df_dv['lacuna_colesterol_HAS_DM'].fillna(False).astype(bool)
            if 'Sem ECG' in sin_d:
                mask |= df_dv['lacuna_ecg_HAS_DM'].fillna(False).astype(bool)
            df_dv = df_dv[mask]

        st.caption(
            f"**{len(df_dv):,} diabéticos** sendo apresentados "
            f"(de {len(df_d):,} diabéticos da equipe)."
        )

        if df_dv.empty:
            st.info("Nenhum paciente bate com a combinação de filtros selecionada.")
        else:
            df_dr = df_dv.copy()

            if MODO_ANONIMO:
                df_dr['nome_exib'] = df_dr.apply(
                    lambda r: anonimizar_nome(
                        str(r.get('cpf') or r.get('nome', '')),
                        r.get('genero', '')),
                    axis=1,
                )
            else:
                df_dr['nome_exib'] = df_dr['nome']

            def _truthy_d(v):
                if v is None: return False
                try:
                    if pd.isna(v): return False
                except (TypeError, ValueError):
                    pass
                return bool(v)

            def _tipo_dm(v):
                return 'DM1?' if _truthy_d(v) else 'DM2'

            def _lacunas_dm(r):
                ats = []
                pares = [
                    ('lacuna_DM_descontrolado',                  'HbA1c > meta'),
                    ('lacuna_DM_sem_HbA1c_recente',              'Sem HbA1c (>180d)'),
                    ('lacuna_DM_hba1c_nao_solicitado',           'A1c não solicitada'),
                    ('lacuna_DM_sem_exame_pe_365d',              'Sem exame do pé (>365d)'),
                    ('lacuna_DM_sem_exame_pe_180d',              'Sem exame do pé (>180d)'),
                    ('lacuna_DM_nunca_teve_exame_pe',            'Nunca exame do pé'),
                    ('lacuna_DM_microalbuminuria_nao_solicitado','Sem microalbuminúria'),
                    ('lacuna_DM_complicado_sem_SGLT2',           'DM complicado sem SGLT-2'),
                    ('lacuna_creatinina_HAS_DM',                 'Sem creatinina'),
                    ('lacuna_colesterol_HAS_DM',                 'Sem colesterol'),
                    ('lacuna_eas_HAS_DM',                        'Sem EAS'),
                    ('lacuna_ecg_HAS_DM',                        'Sem ECG'),
                    ('lacuna_IMC_HAS_DM',                        'Sem IMC'),
                ]
                for col, txt in pares:
                    if _truthy_d(r.get(col)):
                        ats.append(txt)
                if _truthy_d(r.get('DM_sem_CID')):
                    ats.append('Sem CID')
                return ", ".join(ats) if ats else "—"

            df_dr['lacunas_dm'] = df_dr.apply(_lacunas_dm, axis=1)
            df_dr['tipo_dm']    = df_dr['provavel_dm1'].apply(_tipo_dm)

            def _ctrl_dm_str(v):
                v = str(v or '').lower()
                return {'controlado':    '🟢 Controlado',
                        'descontrolado': '🔴 Descontrolado'}.get(v, '— sem dados')

            df_dr['ctrl_str'] = df_dr['status_controle_glicemico'].apply(_ctrl_dm_str)

            def _fmt_dias(v):
                return f"{int(v)}" if pd.notna(v) else "—"

            def _fmt_a1c(v):
                return f"{float(v):.1f}%" if pd.notna(v) else "—"

            df_dr = df_dr.sort_values(
                ['status_controle_glicemico', 'dias_desde_ultima_hba1c'],
                ascending=[True, False], na_position='last',
            )

            st.dataframe(
                pd.DataFrame({
                    'Paciente':   df_dr['nome_exib'].values,
                    'Idade':      df_dr['idade'].astype('Int64').values,
                    'Morbidades': df_dr['morbidades_lista'].fillna('—').values,
                    'Última prescrição crônica':
                        df_dr['medicamentos_lista'].fillna('—').values,
                    'Carga de Morbidade':
                        df_dr['charlson_categoria'].fillna('—').values,
                    'Tipo':       df_dr['tipo_dm'].values,
                    'HbA1c atual': df_dr['hba1c_atual'].apply(_fmt_a1c).values,
                    'Meta HbA1c': df_dr['meta_hba1c'].apply(_fmt_a1c).values,
                    'Dias s/ HbA1c':
                        df_dr['dias_desde_ultima_hba1c'].apply(_fmt_dias).values,
                    'Controle':   df_dr['ctrl_str'].values,
                    'Lacunas de DM': df_dr['lacunas_dm'].values,
                }),
                hide_index=True, use_container_width=True, height=540,
                column_config={
                    'Paciente':   st.column_config.TextColumn('Paciente', width='medium'),
                    'Idade':      st.column_config.NumberColumn('Idade', width='small'),
                    'Morbidades': st.column_config.TextColumn('Morbidades', width='large'),
                    'Última prescrição crônica':
                        st.column_config.TextColumn('Última prescrição crônica',
                                                    width='large'),
                    'Carga de Morbidade':
                        st.column_config.TextColumn('Carga de Morbidade', width='small'),
                    'Tipo':         st.column_config.TextColumn('Tipo', width='small'),
                    'HbA1c atual':  st.column_config.TextColumn('HbA1c atual', width='small'),
                    'Meta HbA1c':   st.column_config.TextColumn('Meta HbA1c', width='small'),
                    'Dias s/ HbA1c':st.column_config.TextColumn('Dias s/ HbA1c', width='small'),
                    'Controle':     st.column_config.TextColumn('Controle', width='small'),
                    'Lacunas de DM':st.column_config.TextColumn('Lacunas de DM', width='large'),
                },
            )

            with st.expander("ℹ️ O que significa cada coluna"):
                st.markdown("""
- **Paciente** — nome (anonimizado quando o modo está ativo).
- **Idade** — anos.
- **Morbidades** — diagnósticos crônicos ativos.
- **Última prescrição crônica** — medicamentos da prescrição mais recente.
- **Carga de Morbidade** — categoria do escore de Charlson.
- **Tipo** — DM1? (provável tipo 1 por sinais clínicos) ou DM2.
- **HbA1c atual** — último resultado disponível.
- **Meta HbA1c** — meta etária do paciente
  (<60a → 7,0%; 60–69a → 7,5%; ≥70a → 8,0%).
- **Dias s/ HbA1c** — dias desde o último resultado registrado.
- **Controle** — 🟢 Controlado / 🔴 Descontrolado / — sem dados,
  conforme `status_controle_glicemico`.
- **Lacunas de DM** — checagens em aberto: HbA1c acima da meta,
  HbA1c não solicitada/ausente, exame do pé ausente,
  microalbuminúria ausente, DM complicado sem SGLT-2, exames
  laboratoriais e cardiológicos ausentes, ou diagnóstico sem CID.
""")

# ─────────────────────────────────────────────────────────────
# ABA 7 — ANÁLISE DO IPC
# ─────────────────────────────────────────────────────────────
with tab_analise:
    st.markdown(
        "Esta aba investiga **colinearidade entre as dimensões do IPC** "
        "e a forma da distribuição de cada uma na equipe selecionada. "
        "É esperada alguma correlação positiva entre Carga de Morbidade e total "
        "de lacunas (mais morbidades → mais oportunidades para lacunas), "
        "mas dimensões muito redundantes empobrecem o índice."
    )

    cols_dim = {
        'charlson_score':           'Carga de Morbidade',
        'acb_score_total':          'ACB',
        'total_criterios_stopp':    'STOPP',
        'dias_desde_ultima_medica': 'Dias s/ médico',
        'total_lacunas':            'N° lacunas',
        'ipc':                      'IPC final',
    }

    df_corr_src = df[list(cols_dim.keys())].copy()
    df_corr_src.columns = list(cols_dim.values())
    # Garante dtype float — colunas Int64 (nullable) não aceitam fillna
    # com mediana fracionária. Pearson precisa de float de qualquer modo.
    df_corr_src = df_corr_src.apply(pd.to_numeric, errors='coerce').astype(float)
    # Tratamento de NaN: paciente sem consulta (NaN) é o caso mais crítico
    # — substituir por valor alto (ex.: 9999) distorceria. Usar mediana.
    df_corr_src = df_corr_src.fillna(df_corr_src.median(numeric_only=True))

    # Matriz de correlação
    st.markdown("#### Matriz de correlação (Pearson)")
    corr = df_corr_src.corr(method='pearson').round(2)
    fig_corr = px.imshow(
        corr,
        text_auto=True,
        color_continuous_scale='RdBu_r',
        zmin=-1, zmax=1,
        aspect='auto',
    )
    fig_corr.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        xaxis=dict(side='bottom', tickfont=dict(color=T.TEXT)),
        yaxis=dict(tickfont=dict(color=T.TEXT)),
        coloraxis_colorbar=dict(title='r'),
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    st.caption(
        "Leitura prática: |r| < 0,3 = baixa correlação (dimensões "
        "razoavelmente independentes); 0,3 ≤ |r| < 0,6 = moderada; "
        "|r| ≥ 0,6 = alta (redundância — pode justificar reformular pesos)."
    )

    # Distribuição de cada dimensão (banda)
    st.markdown("#### Distribuição de cada dimensão (após mapeamento em banda)")
    bandas_cols = {
        'ipc_charlson_band': '🦠 Carga de Morbidade',
        'ipc_lacunas_band':  '⚠️ Lacunas',
        'ipc_acesso_band':   '⏳ Dias s/ médico',
        'ipc_acb_band':      '💊 ACB',
        'ipc_stopp_band':    '🚫 STOPP',
    }
    cb_cols = st.columns(2)
    for i, (col_band, label) in enumerate(bandas_cols.items()):
        target = cb_cols[i % 2]
        with target:
            counts = df[col_band].value_counts().sort_index()
            fig_b = go.Figure(go.Bar(
                x=[f"{v:.2f}" for v in counts.index],
                y=counts.values,
                marker_color='#4f8ef7',
            ))
            fig_b.update_layout(
                title=dict(text=label, font=dict(color=T.TEXT, size=13)),
                height=240, bargap=0.4,
                margin=dict(l=10, r=10, t=40, b=20),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(title='Banda', tickfont=dict(color=T.TEXT_MUTED)),
                yaxis=dict(title='Pacientes', tickfont=dict(color=T.TEXT_MUTED),
                           gridcolor=T.GRID),
            )
            st.plotly_chart(fig_b, use_container_width=True)

    # Tabela de pares com a maior correlação (ranking)
    st.markdown("#### Pares com correlação mais forte")
    pairs = []
    nomes = [v for k, v in cols_dim.items() if k != 'ipc']  # excluir IPC final
    sub = corr.loc[nomes, nomes]
    for i, a in enumerate(nomes):
        for b in nomes[i+1:]:
            pairs.append({'Par': f"{a} × {b}", 'r': sub.loc[a, b]})
    pares_df = pd.DataFrame(pairs).sort_values('r', key=lambda s: s.abs(),
                                               ascending=False)
    pares_df['r'] = pares_df['r'].round(2)
    pares_df['Magnitude'] = pares_df['r'].abs().apply(
        lambda v: 'Alta (≥0.6)' if v >= 0.6
                  else ('Moderada (0.3-0.6)' if v >= 0.3
                        else 'Baixa (<0.3)')
    )
    st.dataframe(pares_df, hide_index=True, use_container_width=True)
