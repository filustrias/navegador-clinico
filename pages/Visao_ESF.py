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
from utils.lacunas_config import LACUNAS
from utils.criterios_idoso import (
    CRITERIOS_STOPP, CRITERIOS_START, CRITERIOS_BEERS,
    todos_codigos_stopp, todos_codigos_start, todos_codigos_beers,
    coluna_para_codigo, descricao_curta, justificativa, categoria, tipo,
)
from utils.auth import (
    requer_login, get_perfil, get_contexto_territorial, logout,
)
import config

st.set_page_config(
    page_title="Visão ESF · Navegador Clínico",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Login obrigatório (redireciona para Home se não houver sessão)
_usuario = requer_login()
_perfil  = get_perfil()

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
def carregar_polifarm_resumo(ap: str = None, clinica: str = None,
                             esf: str = None) -> dict:
    """Resumo de Carga farmacológica para um escopo (equipe ou
    município). Cobre as três dimensões:
      - quantitativa:   polifarmácia, hiperpolifarmácia, média de meds
      - qualitativa:    pacientes com ≥1 STOPP, START, Beers
      - exposição funcional (anticolinérgica): ACB ≥1 e ≥3

    Aceita None nos filtros para escopo do município (sem WHERE).
    Função leve — não lista critérios individuais."""
    clauses = []
    if ap:      clauses.append(f"f.area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"f.nome_clinica_cadastro     = '{clinica}'")
    if esf:     clauses.append(f"f.nome_esf_cadastro         = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
    SELECT
        COUNT(*)                                                   AS n_total,
        COUNTIF(f.idade >= 65)                                     AS n_idosos,
        -- ── Dimensão quantitativa ──
        COUNTIF(f.polifarmacia = TRUE)                             AS n_polifarm,
        COUNTIF(f.hiperpolifarmacia = TRUE)                        AS n_hiperpoli,
        COUNTIF(f.idade >= 65 AND f.polifarmacia = TRUE)           AS n_polifarm_idosos,
        COUNTIF(f.idade >= 65 AND f.hiperpolifarmacia = TRUE)      AS n_hiperpoli_idosos,
        ROUND(AVG(f.total_medicamentos_cronicos), 1)               AS media_meds,
        ROUND(AVG(IF(f.idade >= 65,
                     f.total_medicamentos_cronicos, NULL)), 1)     AS media_meds_idosos,
        -- ── Dimensão de exposição funcional (ACB) ──
        COUNTIF(f.acb_score_total >= 1)                            AS n_acb_ge1,
        COUNTIF(f.acb_score_total >= 3)                            AS n_acb_ge3,
        COUNTIF(f.acb_score_total >= 1 AND f.idade >= 65)          AS n_acb_ge1_idosos,
        COUNTIF(f.acb_score_total >= 3 AND f.idade >= 65)          AS n_acb_ge3_idosos,
        -- ── Dimensão qualitativa (STOPP/START/Beers) ──
        COUNTIF(COALESCE(s.total_criterios_stopp, 0) > 0)          AS n_com_stopp,
        COUNTIF(COALESCE(s.total_criterios_start, 0) > 0)          AS n_com_start,
        COUNTIF(COALESCE(s.total_criterios_beers, 0) > 0)          AS n_com_beers,
        COUNTIF(f.idade >= 65
                AND COALESCE(s.total_criterios_stopp, 0) > 0)      AS n_com_stopp_idosos,
        COUNTIF(f.idade >= 65
                AND COALESCE(s.total_criterios_start, 0) > 0)      AS n_com_start_idosos,
        COUNTIF(f.idade >= 65
                AND COALESCE(s.total_criterios_beers, 0) > 0)      AS n_com_beers_idosos
    FROM `{_fqn(config.TABELA_FATO)}` f
    LEFT JOIN `rj-sms-sandbox.sub_pav_us.MM_stopp_start` s
           ON f.cpf = s.cpf
    {where}
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_continuidade_agregado(ap: str = None, clinica: str = None,
                                   esf: str = None) -> dict:
    """Estatísticas de continuidade do cuidado.
    - Aceita None nos filtros para escopo do município (sem WHERE).
    - Inclui contagens estratificadas por charlson_categoria
      ('Baixo'/'Moderado'/'Alto'/'Muito Alto') para os 4 indicadores
      estruturais e as 6 médias de consultas/intervalo/% na unidade
      (12 meses)."""
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro     = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro         = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
    SELECT
        COUNT(*) AS n_total,
        -- Denominadores por carga (Charlson)
        COUNTIF(charlson_categoria = 'Baixo')      AS n_carga_baixo,
        COUNTIF(charlson_categoria = 'Moderado')   AS n_carga_mod,
        COUNTIF(charlson_categoria = 'Alto')       AS n_carga_alto,
        COUNTIF(charlson_categoria = 'Muito Alto') AS n_carga_ma,
        -- KPIs totais (originais)
        COUNTIF(dias_desde_ultima_medica > 180)                      AS n_sem_medico_180d,
        COUNTIF(consultas_365d = 0)                                  AS n_sem_consulta_365d,
        COUNTIF(regularidade_acompanhamento = 'regular')             AS n_regular,
        COUNTIF(regularidade_acompanhamento = 'irregular')           AS n_irregular,
        COUNTIF(regularidade_acompanhamento = 'esporadico')          AS n_esporadico,
        COUNTIF(regularidade_acompanhamento = 'sem_acompanhamento')  AS n_sem_acomp,
        COUNTIF(baixa_longitudinalidade   = TRUE)                    AS n_baixa_long,
        COUNTIF(usuario_frequente_urgencia = TRUE)                   AS n_freq_urg,
        -- Uso frequente de urgência restrito a Alto/Muito Alto risco
        COUNTIF(usuario_frequente_urgencia = TRUE
                AND charlson_categoria IN ('Alto', 'Muito Alto'))    AS n_freq_urg_alto_ma,
        COUNTIF(alto_risco_baixo_acesso    = TRUE)                   AS n_alto_baixo_acesso,
        COUNTIF(alto_risco_intervalo_longo = TRUE)                   AS n_alto_intv_longo,
        ROUND(AVG(consultas_365d), 1)                                AS media_consultas_total,
        ROUND(AVG(consultas_medicas_365d), 1)                        AS media_consultas_med,
        ROUND(AVG(consultas_enfermagem_365d), 1)                     AS media_consultas_enf,
        ROUND(AVG(consultas_tecnico_enfermagem_365d), 1)             AS media_consultas_tec,
        ROUND(AVG(intervalo_mediano_dias), 1)                        AS media_intv_mediano,
        ROUND(AVG(pct_consultas_medicas_na_unidade_365d), 1)         AS media_pct_na_unidade,
        ROUND(AVG(pct_consultas_medicas_fora_365d), 1)               AS media_pct_fora,
        -- ── Estratificação por carga: indicadores estruturais ──
        -- Sem médico há >180 dias
        COUNTIF(dias_desde_ultima_medica > 180 AND charlson_categoria = 'Baixo')      AS n_sm180_baixo,
        COUNTIF(dias_desde_ultima_medica > 180 AND charlson_categoria = 'Moderado')   AS n_sm180_mod,
        COUNTIF(dias_desde_ultima_medica > 180 AND charlson_categoria = 'Alto')       AS n_sm180_alto,
        COUNTIF(dias_desde_ultima_medica > 180 AND charlson_categoria = 'Muito Alto') AS n_sm180_ma,
        -- Acompanhamento regular
        COUNTIF(regularidade_acompanhamento = 'regular' AND charlson_categoria = 'Baixo')      AS n_reg_baixo,
        COUNTIF(regularidade_acompanhamento = 'regular' AND charlson_categoria = 'Moderado')   AS n_reg_mod,
        COUNTIF(regularidade_acompanhamento = 'regular' AND charlson_categoria = 'Alto')       AS n_reg_alto,
        COUNTIF(regularidade_acompanhamento = 'regular' AND charlson_categoria = 'Muito Alto') AS n_reg_ma,
        -- Sem nenhuma consulta no ano
        COUNTIF(consultas_365d = 0 AND charlson_categoria = 'Baixo')      AS n_sc_baixo,
        COUNTIF(consultas_365d = 0 AND charlson_categoria = 'Moderado')   AS n_sc_mod,
        COUNTIF(consultas_365d = 0 AND charlson_categoria = 'Alto')       AS n_sc_alto,
        COUNTIF(consultas_365d = 0 AND charlson_categoria = 'Muito Alto') AS n_sc_ma,
        -- Fragmentação (>50% das consultas fora da clínica)
        COUNTIF(baixa_longitudinalidade = TRUE AND charlson_categoria = 'Baixo')      AS n_bl_baixo,
        COUNTIF(baixa_longitudinalidade = TRUE AND charlson_categoria = 'Moderado')   AS n_bl_mod,
        COUNTIF(baixa_longitudinalidade = TRUE AND charlson_categoria = 'Alto')       AS n_bl_alto,
        COUNTIF(baixa_longitudinalidade = TRUE AND charlson_categoria = 'Muito Alto') AS n_bl_ma,
        -- ── Médias de consultas (12 meses) por carga ──
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      consultas_365d, NULL)), 1) AS m_ct_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   consultas_365d, NULL)), 1) AS m_ct_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       consultas_365d, NULL)), 1) AS m_ct_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', consultas_365d, NULL)), 1) AS m_ct_ma,
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      consultas_medicas_365d, NULL)), 1) AS m_med_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   consultas_medicas_365d, NULL)), 1) AS m_med_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       consultas_medicas_365d, NULL)), 1) AS m_med_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', consultas_medicas_365d, NULL)), 1) AS m_med_ma,
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      consultas_enfermagem_365d, NULL)), 1) AS m_enf_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   consultas_enfermagem_365d, NULL)), 1) AS m_enf_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       consultas_enfermagem_365d, NULL)), 1) AS m_enf_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', consultas_enfermagem_365d, NULL)), 1) AS m_enf_ma,
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      consultas_tecnico_enfermagem_365d, NULL)), 1) AS m_tec_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   consultas_tecnico_enfermagem_365d, NULL)), 1) AS m_tec_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       consultas_tecnico_enfermagem_365d, NULL)), 1) AS m_tec_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', consultas_tecnico_enfermagem_365d, NULL)), 1) AS m_tec_ma,
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      intervalo_mediano_dias, NULL)), 1) AS m_iv_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   intervalo_mediano_dias, NULL)), 1) AS m_iv_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       intervalo_mediano_dias, NULL)), 1) AS m_iv_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', intervalo_mediano_dias, NULL)), 1) AS m_iv_ma,
        ROUND(AVG(IF(charlson_categoria = 'Baixo',      pct_consultas_medicas_na_unidade_365d, NULL)), 1) AS m_pu_baixo,
        ROUND(AVG(IF(charlson_categoria = 'Moderado',   pct_consultas_medicas_na_unidade_365d, NULL)), 1) AS m_pu_mod,
        ROUND(AVG(IF(charlson_categoria = 'Alto',       pct_consultas_medicas_na_unidade_365d, NULL)), 1) AS m_pu_alto,
        ROUND(AVG(IF(charlson_categoria = 'Muito Alto', pct_consultas_medicas_na_unidade_365d, NULL)), 1) AS m_pu_ma
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


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
def carregar_hipertensao_narrativa_agregado(ap: str, clinica: str, esf: str) -> dict:
    """Indicadores ampliados de HAS para a aba narrativa — inclui
    medicamentos, combinações, intensidade do tratamento, recência da
    PA, tendência, risco CV e comorbidades. Espelha os campos da page
    Hipertensão (abas 2 'Controle pressórico', 3 'Medicamentos
    prescritos' e 5 'Lacunas')."""
    sql = f"""
    SELECT
        COUNT(*)                                                       AS n_total,
        COUNTIF(HAS IS NOT NULL)                                       AS n_has,
        COUNTIF(HAS_sem_CID = TRUE)                                    AS n_sem_cid,
        COUNTIF(has_por_cid IS NOT NULL)                               AS n_por_cid,
        COUNTIF(has_por_medida_critica IS NOT NULL)                    AS n_por_medida_critica,
        COUNTIF(has_por_medidas_repetidas IS NOT NULL)                 AS n_por_medidas_rep,
        COUNTIF(has_por_medicamento IS NOT NULL)                       AS n_por_medicamento,
        -- Controle pressórico
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')    AS n_ctrl,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado') AS n_desc,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL)           AS n_sem_info,
        -- Faixa etária
        COUNTIF(HAS IS NOT NULL AND idade < 80)                        AS n_menor80,
        COUNTIF(HAS IS NOT NULL AND idade < 80
                AND status_controle_pressorio = 'controlado')          AS n_ctrl_menor80,
        COUNTIF(HAS IS NOT NULL AND idade >= 80)                       AS n_80mais,
        COUNTIF(HAS IS NOT NULL AND idade >= 80
                AND status_controle_pressorio = 'controlado')          AS n_ctrl_80mais,
        -- Recência da PA
        COUNTIF(HAS IS NOT NULL AND dias_desde_ultima_pa <= 90)        AS n_pa_90d,
        COUNTIF(HAS IS NOT NULL AND dias_desde_ultima_pa BETWEEN 91 AND 180)
                                                                        AS n_pa_91_180,
        COUNTIF(HAS IS NOT NULL AND dias_desde_ultima_pa BETWEEN 181 AND 365)
                                                                        AS n_pa_181_365,
        COUNTIF(HAS IS NOT NULL AND
                (dias_desde_ultima_pa > 365 OR dias_desde_ultima_pa IS NULL))
                                                                        AS n_pa_365mais,
        -- Tendência
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')       AS n_melhorando,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')          AS n_estavel,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')         AS n_piorando,
        -- Médias
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pressao_sistolica END), 0)  AS media_pas,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pressao_diastolica END), 0) AS media_pad,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pct_dias_has_controlado_365d END), 1)
                                                                        AS media_pct_ctrl,
        -- Lacunas
        COUNTIF(HAS IS NOT NULL AND lacuna_PA_hipertenso_180d = TRUE)  AS n_sem_pa_180d,
        COUNTIF(HAS IS NOT NULL AND lacuna_DM_HAS_PA_descontrolada = TRUE)
                                                                        AS n_dm_has_pa,
        COUNTIF(HAS IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)   AS n_sem_creat,
        COUNTIF(HAS IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)   AS n_sem_col,
        COUNTIF(HAS IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)          AS n_sem_eas,
        COUNTIF(HAS IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)          AS n_sem_ecg,
        COUNTIF(HAS IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)          AS n_sem_imc,
        -- Comorbidades em hipertensos
        COUNTIF(HAS IS NOT NULL AND DM IS NOT NULL)                    AS n_has_dm,
        COUNTIF(HAS IS NOT NULL AND IRC IS NOT NULL)                   AS n_has_irc,
        COUNTIF(HAS IS NOT NULL AND CI IS NOT NULL)                    AS n_has_ci,
        COUNTIF(HAS IS NOT NULL AND ICC IS NOT NULL)                   AS n_has_icc,
        COUNTIF(HAS IS NOT NULL AND stroke IS NOT NULL)                AS n_has_avc,
        -- Risco cardiovascular (HEARTS / OMS / OPAS — who_categoria_risco_simplificada)
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada = 'Crítico')    AS n_who_critico,
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada = 'Muito alto') AS n_who_muito_alto,
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada = 'Alto')       AS n_who_alto,
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada = 'Moderado')   AS n_who_moderado,
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada = 'Baixo')      AS n_who_baixo,
        COUNTIF(HAS IS NOT NULL AND who_categoria_risco_simplificada IS NULL)        AS n_who_nao_calc,
        -- Prescrições por classe de anti-hipertensivo
        COUNTIF(HAS IS NOT NULL AND principio_IECA IS NOT NULL)          AS n_rx_ieca,
        COUNTIF(HAS IS NOT NULL AND principio_BRA IS NOT NULL)           AS n_rx_bra,
        COUNTIF(HAS IS NOT NULL AND principio_BCC_DHP IS NOT NULL)       AS n_rx_bcc_dhp,
        COUNTIF(HAS IS NOT NULL AND principio_BCC_NAO_DHP IS NOT NULL)   AS n_rx_bcc_nao_dhp,
        COUNTIF(HAS IS NOT NULL AND principio_TIAZIDICO IS NOT NULL)     AS n_rx_tiazidico,
        COUNTIF(HAS IS NOT NULL AND principio_DIURETICO_ALCA IS NOT NULL) AS n_rx_diur_alca,
        COUNTIF(HAS IS NOT NULL AND principio_POUPADOR_K IS NOT NULL)    AS n_rx_poupador_k,
        COUNTIF(HAS IS NOT NULL AND principio_BETABLOQUEADOR IS NOT NULL) AS n_rx_betabloq,
        COUNTIF(HAS IS NOT NULL AND principio_SIMPATICOLITICO IS NOT NULL) AS n_rx_simpaticol,
        COUNTIF(HAS IS NOT NULL AND principio_ALFABLOQUEADOR IS NOT NULL) AS n_rx_alfabloq,
        COUNTIF(HAS IS NOT NULL AND principio_VASODILATADOR IS NOT NULL) AS n_rx_vasodilat,
        COUNTIF(HAS IS NOT NULL AND principio_NITRATO IS NOT NULL)       AS n_rx_nitrato,
        -- Combinações e contexto clínico
        COUNTIF(HAS IS NOT NULL AND principio_IECA IS NOT NULL
                AND principio_BRA IS NOT NULL)                          AS n_rx_ieca_bra,
        COUNTIF(HAS IS NOT NULL AND principio_DIURETICO_ALCA IS NOT NULL
                AND ICC IS NOT NULL)                                    AS n_rx_diur_alca_icc,
        COUNTIF(HAS IS NOT NULL AND principio_DIURETICO_ALCA IS NOT NULL
                AND ICC IS NULL)                                        AS n_rx_diur_alca_sem_icc,
        COUNTIF(HAS IS NOT NULL AND principio_POUPADOR_K IS NOT NULL
                AND ICC IS NOT NULL)                                    AS n_rx_poupador_k_icc,
        COUNTIF(HAS IS NOT NULL AND principio_NITRATO IS NOT NULL
                AND CI IS NOT NULL)                                     AS n_rx_nitrato_ci,
        COUNTIF(HAS IS NOT NULL AND principio_NITRATO IS NOT NULL
                AND CI IS NULL)                                         AS n_rx_nitrato_sem_ci,
        -- Intensidade do tratamento
        COUNTIF(HAS IS NOT NULL AND intensidade_tratamento_has = 'MONOTERAPIA')        AS n_int_mono,
        COUNTIF(HAS IS NOT NULL AND intensidade_tratamento_has = 'DUPLA_TERAPIA')      AS n_int_dupla,
        COUNTIF(HAS IS NOT NULL AND intensidade_tratamento_has = 'TRIPLA_TERAPIA')     AS n_int_tripla,
        COUNTIF(HAS IS NOT NULL AND intensidade_tratamento_has = 'QUADRUPLA_TERAPIA')  AS n_int_quadrupla,
        COUNTIF(HAS IS NOT NULL AND intensidade_tratamento_has IS NULL)                AS n_int_sem_med,
        -- Complexidade clínica e farmacológica
        COUNTIF(HAS IS NOT NULL AND charlson_categoria = 'Baixo')        AS n_charl_baixo,
        COUNTIF(HAS IS NOT NULL AND charlson_categoria = 'Moderado')     AS n_charl_moderado,
        COUNTIF(HAS IS NOT NULL AND charlson_categoria = 'Alto')         AS n_charl_alto,
        COUNTIF(HAS IS NOT NULL AND charlson_categoria = 'Muito Alto')   AS n_charl_muito_alto,
        COUNTIF(HAS IS NOT NULL AND total_morbidades >= 2)               AS n_multimorb,
        COUNTIF(HAS IS NOT NULL AND polifarmacia = TRUE)                 AS n_polifarm,
        COUNTIF(HAS IS NOT NULL AND hiperpolifarmacia = TRUE)            AS n_hiperpoli,
        COUNTIF(HAS IS NOT NULL AND acb_score_total >= 3)                AS n_acb_alto
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


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
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN hba1c_atual END), 2)   AS media_a1c,
        -- Pré-diabetes e complicações detectadas
        COUNTIF(pre_DM IS NOT NULL)                                    AS n_pre_dm,
        COUNTIF(DM IS NOT NULL AND dm_retinopatia    IS NOT NULL)      AS n_dm_retino,
        COUNTIF(DM IS NOT NULL AND dm_nefropatia     IS NOT NULL)      AS n_dm_nefro,
        COUNTIF(DM IS NOT NULL AND dm_neuropatia     IS NOT NULL)      AS n_dm_neuro,
        COUNTIF(DM IS NOT NULL AND dm_pe_diabetico_cid IS NOT NULL)    AS n_dm_pe,
        COUNTIF(DM IS NOT NULL AND dm_complicacao_cv IS NOT NULL)      AS n_dm_complic_cv,
        -- Insulina e doses farmacológicas críticas — KPIs populacionais.
        -- Aqui usamos as flags estruturais principio_INSULINA_* para
        -- bater com a page Diabetes (mesma janela do pipeline).
        -- Os filtros e a coluna NPH (UI/kg) na lista nominal usam um
        -- critério mais estrito (nucleo_cronico_atual = última
        -- prescrição), que é o que importa para ação caso a caso.
        COUNTIF(DM IS NOT NULL AND (
            principio_INSULINA_BASAL_HUMANA   IS NOT NULL OR
            principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL OR
            principio_INSULINA_BASAL_ANALOGICA IS NOT NULL OR
            principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL OR
            principio_INSULINA_MISTA          IS NOT NULL
        ))                                                               AS n_em_insulina,
        COUNTIF(DM IS NOT NULL AND dose_NPH_ui_kg > 0.85)                AS n_nph_alta,
        COUNTIF(DM IS NOT NULL AND alerta_dose_maxima_biguanida    = TRUE)
                                                                          AS n_metf_total_alta,
        COUNTIF(DM IS NOT NULL AND alerta_dose_maxima_biguanida_xr = TRUE)
                                                                          AS n_metf_xr_alta,
        COUNTIF(DM IS NOT NULL
                AND principio_SULFONILUREIA          IS NOT NULL
                AND principio_BIGUANIDA              IS NULL
                AND principio_BIGUANIDA_XR           IS NULL
                AND principio_iSGLT2                 IS NULL
                AND principio_iDPP4                  IS NULL
                AND principio_GLP1                   IS NULL
                AND principio_TIAZOLIDINEDIONA       IS NULL
                AND principio_GLINIDA                IS NULL
                AND principio_ACARBOSE               IS NULL
                AND principio_INSULINA_BASAL_HUMANA  IS NULL
                AND principio_INSULINA_PRANDIAL_HUMANA IS NULL
                AND principio_INSULINA_BASAL_ANALOGICA IS NULL
                AND principio_INSULINA_PRANDIAL_ANALOGICA IS NULL
                AND principio_INSULINA_MISTA         IS NULL)            AS n_sulfo_mono,
        -- Complexidade clínica e farmacológica (denominador = diabéticos)
        COUNTIF(DM IS NOT NULL AND charlson_categoria = 'Baixo')         AS n_charl_baixo,
        COUNTIF(DM IS NOT NULL AND charlson_categoria = 'Moderado')      AS n_charl_moderado,
        COUNTIF(DM IS NOT NULL AND charlson_categoria = 'Alto')          AS n_charl_alto,
        COUNTIF(DM IS NOT NULL AND charlson_categoria = 'Muito Alto')    AS n_charl_muito_alto,
        COUNTIF(DM IS NOT NULL AND total_morbidades >= 2)                AS n_multimorb,
        COUNTIF(DM IS NOT NULL AND polifarmacia = TRUE)                  AS n_polifarm,
        COUNTIF(DM IS NOT NULL AND hiperpolifarmacia = TRUE)             AS n_hiperpoli,
        COUNTIF(DM IS NOT NULL AND acb_score_total >= 3)                 AS n_acb_alto
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
        dose_NPH_ui_kg,
        DM_sem_CID,
        provavel_dm1,
        HAS, IRC, ICC, CI,
        (principio_INSULINA_BASAL_HUMANA   IS NOT NULL OR
         principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL OR
         principio_INSULINA_BASAL_ANALOGICA IS NOT NULL OR
         principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL OR
         principio_INSULINA_MISTA          IS NOT NULL) AS usa_insulina,
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


@st.cache_data(show_spinner=False, ttl=900)
def carregar_inercia_agregado(ap: str, clinica: str, esf: str) -> dict:
    """Indicadores de inércia terapêutica e tratamento estagnado da
    equipe (grão sexo × faixa × AP × clínica × ESF, agregado por equipe).

    Lê de MM_consultas_agregado, que já é pré-agregada por essas
    dimensões. Inclui denominadores, distribuição dos 8 status atuais
    e dos 6 padrões de manejo 365d, tanto para HAS quanto para DM.
    """
    sql = f"""
    SELECT
        -- HAS — denominadores
        SUM(n_pacientes_HAS)            AS n_pacientes_HAS,
        SUM(n_HAS_tratados)             AS n_HAS_tratados,
        -- HAS — status atual (8 categorias mutuamente exclusivas)
        SUM(n_em_inercia_HAS)           AS n_em_inercia_HAS,
        SUM(n_estagnado_HAS)            AS n_estagnado_HAS,
        SUM(n_manejo_apropriado_HAS)    AS n_manejo_apropriado_HAS,
        SUM(n_controlado_HAS)           AS n_controlado_HAS,
        SUM(n_controlado_lacuna_HAS)    AS n_controlado_lacuna_HAS,
        SUM(n_descontrole_sem_comp_HAS) AS n_descontrole_sem_comp_HAS,
        SUM(n_sem_afericao_HAS)         AS n_sem_afericao_HAS,
        SUM(n_sem_prescricao_HAS)       AS n_sem_prescricao_HAS,
        -- HAS — padrão de manejo 365d (6 categorias)
        SUM(n_padrao_proativo_HAS)            AS n_padrao_proativo_HAS,
        SUM(n_padrao_inerte_HAS)              AS n_padrao_inerte_HAS,
        SUM(n_padrao_estagnado_HAS)           AS n_padrao_estagnado_HAS,
        SUM(n_padrao_controlado_HAS)          AS n_padrao_controlado_HAS,
        SUM(n_padrao_misto_HAS)               AS n_padrao_misto_HAS,
        SUM(n_padrao_menos_2_consultas_HAS)   AS n_padrao_menos_2_consultas_HAS,
        -- DM — denominadores
        SUM(n_pacientes_DM)             AS n_pacientes_DM,
        SUM(n_DM_tratados)              AS n_DM_tratados,
        -- DM — status atual (8 categorias)
        SUM(n_em_inercia_DM)            AS n_em_inercia_DM,
        SUM(n_estagnado_DM)             AS n_estagnado_DM,
        SUM(n_manejo_apropriado_DM)     AS n_manejo_apropriado_DM,
        SUM(n_controlado_DM)            AS n_controlado_DM,
        SUM(n_controlado_lacuna_DM)     AS n_controlado_lacuna_DM,
        SUM(n_descontrole_sem_comp_DM)  AS n_descontrole_sem_comp_DM,
        SUM(n_sem_afericao_DM)          AS n_sem_afericao_DM,
        SUM(n_sem_prescricao_DM)        AS n_sem_prescricao_DM,
        -- DM — padrão de manejo 365d
        SUM(n_padrao_proativo_DM)            AS n_padrao_proativo_DM,
        SUM(n_padrao_inerte_DM)              AS n_padrao_inerte_DM,
        SUM(n_padrao_estagnado_DM)           AS n_padrao_estagnado_DM,
        SUM(n_padrao_controlado_DM)          AS n_padrao_controlado_DM,
        SUM(n_padrao_misto_DM)               AS n_padrao_misto_DM,
        SUM(n_padrao_menos_2_consultas_DM)   AS n_padrao_menos_2_consultas_DM
    FROM `{_fqn('MM_consultas_agregado')}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=3600)
def carregar_inercia_benchmarks(ap: str) -> dict:
    """Medianas de % de inércia e % de estagnação entre clínicas — no
    município e na AP da equipe — para benchmark contextual.

    Cada clínica é uma observação (soma das células sexo × faixa × ESF
    da clínica). Filtro de n_tratados ≥ 50 evita ruído de clínicas com
    poucos pacientes, conforme recomendação do dicionário de inércia.
    """
    sql = f"""
    WITH por_clinica AS (
      SELECT
        area_programatica_cadastro AS ap,
        nome_clinica_cadastro      AS clinica,
        SUM(n_HAS_tratados)        AS n_HAS_t,
        SUM(n_em_inercia_HAS)      AS n_in_HAS,
        SUM(n_estagnado_HAS)       AS n_est_HAS,
        SUM(n_controlado_HAS)      AS n_ctrl_HAS,
        SUM(n_DM_tratados)         AS n_DM_t,
        SUM(n_em_inercia_DM)       AS n_in_DM,
        SUM(n_estagnado_DM)        AS n_est_DM,
        SUM(n_controlado_DM)       AS n_ctrl_DM
      FROM `{_fqn('MM_consultas_agregado')}`
      GROUP BY ap, clinica
    )
    SELECT
      -- Município
      APPROX_QUANTILES(
        IF(n_HAS_t >= 50, SAFE_DIVIDE(n_in_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_in_HAS,
      APPROX_QUANTILES(
        IF(n_HAS_t >= 50, SAFE_DIVIDE(n_est_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_est_HAS,
      APPROX_QUANTILES(
        IF(n_HAS_t >= 50, SAFE_DIVIDE(n_ctrl_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_ctrl_HAS,
      APPROX_QUANTILES(
        IF(n_DM_t >= 50, SAFE_DIVIDE(n_in_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_in_DM,
      APPROX_QUANTILES(
        IF(n_DM_t >= 50, SAFE_DIVIDE(n_est_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_est_DM,
      APPROX_QUANTILES(
        IF(n_DM_t >= 50, SAFE_DIVIDE(n_ctrl_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS mun_ctrl_DM,
      -- AP
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_HAS_t >= 50,
           SAFE_DIVIDE(n_in_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_in_HAS,
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_HAS_t >= 50,
           SAFE_DIVIDE(n_est_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_est_HAS,
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_HAS_t >= 50,
           SAFE_DIVIDE(n_ctrl_HAS, n_HAS_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_ctrl_HAS,
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_DM_t >= 50,
           SAFE_DIVIDE(n_in_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_in_DM,
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_DM_t >= 50,
           SAFE_DIVIDE(n_est_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_est_DM,
      APPROX_QUANTILES(
        IF(ap = '{ap}' AND n_DM_t >= 50,
           SAFE_DIVIDE(n_ctrl_DM, n_DM_t)*100, NULL),
        100 IGNORE NULLS)[OFFSET(50)] AS ap_ctrl_DM
    FROM por_clinica
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


def _kpi(col, label, valor, delta=None, ajuda=None):
    """Card KPI com label que quebra linha (não trunca como st.metric)."""
    with col:
        delta_html = ""
        if delta:
            delta_html = (
                f"<div style='color:#09ab3b; font-size:0.85em; "
                f"margin-top:4px;'>↑ {delta}</div>"
            )
        ajuda_attr = f' title="{ajuda}"' if ajuda else ""
        st.markdown(
            f"<div{ajuda_attr} style='border:1px solid {T.BORDER}; "
            f"border-radius:8px; padding:12px 14px; height:100%; "
            f"box-sizing:border-box; background:{T.CARD_BG};'>"
            f"<div style='color:{T.TEXT_SECONDARY}; font-size:0.85em; "
            f"line-height:1.25; word-wrap:break-word;'>{label}</div>"
            f"<div style='font-size:1.8em; font-weight:600; "
            f"line-height:1.2; margin-top:6px; color:{T.TEXT};'>{valor}</div>"
            f"{delta_html}"
            f"</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════
# HELPERS — CARD DE LACUNA (aba "Lacunas" narrativa)
# ═══════════════════════════════════════════════════════════════
def _gradiente_bg_pct(v, alpha=0.25):
    """Gradiente verde→amarelo→vermelho conforme % (0–100)."""
    if pd.isna(v):
        return f"rgba(229,231,235,{alpha})"
    norm = max(0.0, min(1.0, float(v) / 100.0))
    if norm <= 0.5:
        t = norm * 2
        r = int(round(76  + (255 - 76)  * t))
        g = int(round(175 + (235 - 175) * t))
        b = int(round( 80 + ( 59 -  80) * t))
    else:
        t = (norm - 0.5) * 2
        r = int(round(255 + (231 - 255) * t))
        g = int(round(235 + ( 76 - 235) * t))
        b = int(round( 59 + ( 60 -  59) * t))
    return f"rgba({r},{g},{b},{alpha})"


def _cor_borda_delta(delta):
    """Cor da borda do card de lacuna conforme comparação com município.
    Vermelho = pior; verde = melhor; cinza = ~similar."""
    if delta is None or pd.isna(delta):
        return "#9CA3AF"
    if delta > 0.5:
        return "#C0392B"
    if delta < -0.5:
        return "#27AE60"
    return "#9CA3AF"


def _card_lacuna(col, row):
    """Card de uma lacuna: número absoluto + n/N (%) + delta vs município.
    Fundo com gradiente pela %; borda esquerda colorida pelo delta."""
    nome    = row['lacuna']
    num     = int(row['numerador']) if pd.notna(row.get('numerador')) else 0
    den     = int(row['denominador']) if pd.notna(row.get('denominador')) else 0
    pct     = float(row['pct']) if pd.notna(row.get('pct')) else 0.0
    pct_mun = row.get('pct_mun')
    delta   = row.get('delta')

    bg     = _gradiente_bg_pct(pct, alpha=0.20)
    border = _cor_borda_delta(delta)

    if pct_mun is None or pd.isna(pct_mun):
        delta_txt = ("<span style='color:#6B7280;'>"
                     "vs município —</span>")
    elif delta is None or pd.isna(delta):
        delta_txt = ("<span style='color:#6B7280;'>"
                     "vs município —</span>")
    elif delta > 0.5:
        delta_txt = (f"<span style='color:#C0392B; font-weight:600;'>"
                     f"↑ +{delta:.1f} pp vs município "
                     f"({float(pct_mun):.0f}%)</span>")
    elif delta < -0.5:
        delta_txt = (f"<span style='color:#27AE60; font-weight:600;'>"
                     f"↓ {delta:.1f} pp vs município "
                     f"({float(pct_mun):.0f}%)</span>")
    else:
        delta_txt = (f"<span style='color:#6B7280;'>"
                     f"≈ vs município ({float(pct_mun):.0f}%)</span>")

    with col:
        st.markdown(
            f"<div style='border:1px solid {T.BORDER}; "
            f"border-left:5px solid {border}; border-radius:8px; "
            f"padding:10px 12px; height:100%; box-sizing:border-box; "
            f"background:{bg};'>"
            f"<div style='color:{T.TEXT_SECONDARY}; font-size:0.82em; "
            f"line-height:1.3; min-height:34px; word-wrap:break-word;'>"
            f"{nome}</div>"
            f"<div style='font-size:1.5em; font-weight:600; "
            f"color:{T.TEXT}; line-height:1.2; margin-top:6px;'>"
            f"{num:,} <span style='font-size:0.6em; "
            f"color:{T.TEXT_MUTED}; font-weight:500;'>/ {den:,} "
            f"({pct:.0f}%)</span></div>"
            f"<div style='font-size:0.78em; margin-top:4px;'>{delta_txt}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─── Card mini para indicadores estratificados por carga ──────
def _card_carga_strat(col, carga_label, emoji, n_eq, den_eq,
                      n_mun, den_mun, indicador_ruim_se_alto=True,
                      formato_valor='%'):
    """Mini-card por carga (Baixo/Moderado/Alto/Muito Alto) usado na
    aba 'Continuidade do cuidado'. Mostra valor da equipe + benchmark
    município + delta colorido.

    formato_valor:
      '%'   → exibe pct_eq como '12%' (n/N implícito); usa contagem
              estratificada (n_eq) sobre o denominador da carga (den_eq).
      'avg' → exibe média numérica direta (n_eq é a média já calculada,
              den_eq é ignorado).

    indicador_ruim_se_alto:
      True  → equipe acima do município = vermelho (ex.: sem médico,
              sem consulta, fragmentação).
      False → equipe acima do município = verde (ex.: regulares,
              consultas/ano, % na unidade).
    """
    if formato_valor == '%':
        pct_eq  = (n_eq / den_eq * 100) if den_eq else None
        pct_mun = (n_mun / den_mun * 100) if den_mun else None
        valor_eq_str  = f"{pct_eq:.0f}%"  if pct_eq  is not None else "—"
        valor_mun_str = f"{pct_mun:.0f}%" if pct_mun is not None else "—"
        delta = ((pct_eq - pct_mun)
                 if (pct_eq is not None and pct_mun is not None)
                 else None)
        unidade = "pp"
    else:  # 'avg'
        v_eq  = float(n_eq)  if pd.notna(n_eq)  else None
        v_mun = float(n_mun) if pd.notna(n_mun) else None
        valor_eq_str  = f"{v_eq:.1f}"  if v_eq  is not None else "—"
        valor_mun_str = f"{v_mun:.1f}" if v_mun is not None else "—"
        delta = (v_eq - v_mun) if (v_eq is not None and v_mun is not None) else None
        unidade = ""
        pct_eq = v_eq

    if delta is None or pd.isna(delta):
        delta_color = "#6B7280"
        delta_str   = "vs município —"
    elif abs(delta) < (0.5 if formato_valor == '%' else 0.1):
        delta_color = "#6B7280"
        delta_str   = f"≈ {valor_mun_str} no município"
    else:
        equipe_pior = (delta > 0) == indicador_ruim_se_alto
        delta_color = "#C0392B" if equipe_pior else "#27AE60"
        seta  = "↑" if delta > 0 else "↓"
        sinal = "+" if delta > 0 else ""
        if formato_valor == '%':
            delta_str = (f"{seta} {sinal}{delta:.1f} {unidade} "
                         f"vs {valor_mun_str} no município")
        else:
            delta_str = (f"{seta} {sinal}{delta:.1f} "
                         f"vs {valor_mun_str} no município")

    n_eq_int = int(n_eq) if (formato_valor == '%' and pd.notna(n_eq)) else None
    den_int  = int(den_eq) if (formato_valor == '%' and pd.notna(den_eq)) else None
    n_str = (f"<div style='font-size:0.7em; color:{T.TEXT_MUTED}; "
             f"margin-top:2px;'>n = {n_eq_int:,} de {den_int:,}</div>"
             if n_eq_int is not None and den_int is not None
             else "")

    with col:
        st.markdown(
            f"<div style='border:1px solid {T.BORDER}; "
            f"border-radius:8px; padding:10px 12px; height:100%; "
            f"box-sizing:border-box; background:{T.CARD_BG};'>"
            f"<div style='color:{T.TEXT_SECONDARY}; font-size:0.82em; "
            f"line-height:1.25;'>{emoji} {carga_label}</div>"
            f"<div style='font-size:1.55em; font-weight:600; "
            f"color:{T.TEXT}; line-height:1.2; margin-top:4px;'>"
            f"{valor_eq_str}</div>"
            f"<div style='font-size:0.78em; color:{delta_color}; "
            f"margin-top:4px; font-weight:500;'>{delta_str}</div>"
            f"{n_str}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _detecta_inversao_gradiente(valores, esperado_crescente):
    """Compara extremos (Baixo vs Muito Alto). Retorna mensagem se há
    inversão clara (≥5 pp ou unidades), None caso contrário.
    valores = [v_baixo, v_mod, v_alto, v_ma]
    esperado_crescente: True quando bom = crescer com a carga
                        (ex.: regulares, consultas/ano, % na unidade)."""
    v_bx, _, _, v_ma = valores
    if v_bx is None or v_ma is None:
        return None
    try:
        v_bx_f, v_ma_f = float(v_bx), float(v_ma)
    except (TypeError, ValueError):
        return None
    diff = v_ma_f - v_bx_f
    if esperado_crescente and diff <= -5:
        return ("⚠️ <b>Gradiente invertido</b>: pacientes Muito Alto "
                f"({v_ma_f:.0f}) estão <b>abaixo</b> dos Baixo "
                f"({v_bx_f:.0f}) — o esperado seria o oposto, dado "
                "que cargas mais altas demandam acompanhamento "
                "mais regular.")
    if (not esperado_crescente) and diff >= 5:
        return ("⚠️ <b>Gradiente invertido</b>: pacientes Muito Alto "
                f"({v_ma_f:.0f}) estão <b>acima</b> dos Baixo "
                f"({v_bx_f:.0f}) — o esperado seria o oposto, dado "
                "que cargas mais altas deveriam ter acesso e "
                "longitudinalidade melhores.")
    return None


def _render_ato_inercia(condicao: str, ag_in: dict, bm: dict,
                        n_cond_total: int):
    """Ato 2.5 — Resposta ao descontrole (inércia / tratamento
    estagnado) — para HAS ou DM. Espelha o estilo dos demais atos
    (texto à esquerda, KPIs à direita) e adiciona dois gráficos
    plotly (distribuição de status atual + padrão de manejo 365d)
    e cards de benchmark vs. AP e município.

    Recebe:
      condicao: 'HAS' ou 'DM'.
      ag_in:    dict retornado por carregar_inercia_agregado().
      bm:       dict retornado por carregar_inercia_benchmarks().
      n_cond_total: nº total da população com a condição na equipe.
    """
    nome   = 'Hipertensão' if condicao == 'HAS' else 'Diabetes'
    abrev  = condicao
    param  = 'PA'    if condicao == 'HAS' else 'HbA1c'

    def _v(k):
        v = ag_in.get(k)
        return int(v) if (v is not None and pd.notna(v)) else 0

    n_trat = _v(f'n_{abrev}_tratados')
    n_iner = _v(f'n_em_inercia_{abrev}')
    n_est  = _v(f'n_estagnado_{abrev}')
    n_mapr = _v(f'n_manejo_apropriado_{abrev}')
    n_ctrl = _v(f'n_controlado_{abrev}')
    n_clac = _v(f'n_controlado_lacuna_{abrev}')
    n_dsc  = _v(f'n_descontrole_sem_comp_{abrev}')
    n_safe = _v(f'n_sem_afericao_{abrev}')
    n_spr  = _v(f'n_sem_prescricao_{abrev}')

    n_p_pro  = _v(f'n_padrao_proativo_{abrev}')
    n_p_in   = _v(f'n_padrao_inerte_{abrev}')
    n_p_est  = _v(f'n_padrao_estagnado_{abrev}')
    n_p_ctrl = _v(f'n_padrao_controlado_{abrev}')
    n_p_mix  = _v(f'n_padrao_misto_{abrev}')
    n_p_lt2  = _v(f'n_padrao_menos_2_consultas_{abrev}')

    def _pct(num, den):
        return (100 * num / den) if den else 0

    pct_iner = _pct(n_iner, n_trat)
    pct_est  = _pct(n_est,  n_trat)
    pct_mapr = _pct(n_mapr, n_trat)
    pct_ctrl = _pct(n_ctrl, n_trat)

    def _b(v):     return f"<b>{v}</b>"
    def _br(v):    return f"<span style='color:#B71C1C; font-weight:700;'>{v}</span>"
    def _bg(v):    return f"<span style='color:#198754; font-weight:700;'>{v}</span>"

    ai_e, ai_d = st.columns([1, 1.1])
    with ai_e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Dos {_b(n_cond_total)} pacientes com {nome.lower()} "
            f"da equipe, {_b(n_trat)} têm <b>tratamento ativo</b> "
            f"(≥1 prescrição em 365 dias) — esse é o denominador "
            f"para avaliar a resposta do esquema ao controle de "
            f"{param}.<br><br>"
            f"<b>Inércia provável:</b> {_br(n_iner)} "
            f"({_b(f'{pct_iner:.1f}%')}) — paciente descontrolado e "
            f"esquema mantido na última consulta.<br>"
            f"<b>Tratamento estagnado:</b> {_br(n_est)} "
            f"({_b(f'{pct_est:.0f}%')}) — prescrição renovada sem "
            f"{param} aferida em 180 dias.<br>"
            f"<b>Manejo apropriado:</b> {_bg(n_mapr)} "
            f"({_b(f'{pct_mapr:.0f}%')}) — descontrolado, e a "
            f"equipe intensificou ou trocou o esquema.<br>"
            f"<b>Controlado:</b> {_bg(n_ctrl)} "
            f"({_b(f'{pct_ctrl:.0f}%')}).<br><br>"
            f"<i>No conjunto do município, a <b>estagnação</b> é "
            f"muito mais frequente que a inércia médica propriamente "
            f"dita — em geral, a maior alavanca não é mudar o "
            f"esquema dos descontrolados, e sim retomar aferições e "
            f"exames dos pacientes em renovação sem seguimento.</i>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with ai_d:
        c1, c2 = st.columns(2)
        _kpi(c1, f"⏱️ Em inércia {abrev}",
             f"{n_iner:,}", f"{pct_iner:.1f}% dos tratados")
        _kpi(c2, f"🚧 Tratamento estagnado {abrev}",
             f"{n_est:,}", f"{pct_est:.0f}% dos tratados")
        c3, c4 = st.columns(2)
        _kpi(c3, "✅ Manejo apropriado",
             f"{n_mapr:,}", f"{pct_mapr:.0f}% dos tratados")
        _kpi(c4, "🟢 Controlado",
             f"{n_ctrl:,}", f"{pct_ctrl:.0f}% dos tratados")
        c5, c6 = st.columns(2)
        _kpi(c5, "🟡 Controlado c/ lacuna de consulta",
             f"{n_clac:,}", f"{_pct(n_clac, n_trat):.0f}% dos tratados")
        _kpi(c6, "🔴 Sem aferição (180d)",
             f"{n_safe:,}", f"{_pct(n_safe, n_trat):.0f}% dos tratados")

    # ── Gráficos: distribuição de status (donut) + padrão manejo (bar)
    g1, g2 = st.columns(2)
    status_rows = [
        ('Inércia provável',                n_iner, '#B71C1C'),
        ('Tratamento estagnado',            n_est,  '#D32F2F'),
        ('Controlado c/ lacuna consulta',   n_clac, '#E53935'),
        ('Descontrole sem comparação',      n_dsc,  '#E69138'),
        ('Sem aferição',                    n_safe, '#F6B26B'),
        ('Sem prescrição recente',          n_spr,  '#9E9E9E'),
        ('Manejo apropriado',               n_mapr, '#43A047'),
        ('Controlado',                      n_ctrl, '#198754'),
    ]
    df_status = pd.DataFrame(
        [{'Status': lab, 'n': n, 'cor': c}
         for lab, n, c in status_rows if n > 0]
    )
    with g1:
        st.markdown("**Distribuição do status atual** "
                    "(snapshot da última consulta)")
        if not df_status.empty:
            cor_map = dict(zip(df_status['Status'], df_status['cor']))
            fig = px.pie(df_status, values='n', names='Status',
                         hole=0.45,
                         color='Status',
                         color_discrete_map=cor_map)
            fig.update_traces(textposition='inside', textinfo='percent',
                              hovertemplate='%{label}<br>%{value} pacientes (%{percent})<extra></extra>')
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10),
                              height=320, legend=dict(font=dict(size=11)))
            st.plotly_chart(fig, use_container_width=True,
                            key=f"inercia_status_{abrev}")
        else:
            st.info("Sem dados de status.")

    pad_rows = [
        ('Manejo proativo',        n_p_pro,  '#43A047'),
        ('Manejo inerte',          n_p_in,   '#B71C1C'),
        ('Manejo estagnado',       n_p_est,  '#D32F2F'),
        ('Controlado consistente', n_p_ctrl, '#198754'),
        ('Padrão misto',           n_p_mix,  '#FBC02D'),
        ('<2 consultas em 365d',   n_p_lt2,  '#9E9E9E'),
    ]
    df_pad = pd.DataFrame(
        [{'Padrão': lab, 'n': n, 'cor': c}
         for lab, n, c in pad_rows if n > 0]
    )
    with g2:
        st.markdown("**Padrão de manejo nos últimos 365 dias** "
                    "(trajetória, não snapshot)")
        if not df_pad.empty:
            df_pad_sorted = df_pad.sort_values('n', ascending=True)
            cor_map_p = dict(zip(df_pad_sorted['Padrão'],
                                 df_pad_sorted['cor']))
            fig2 = px.bar(df_pad_sorted, x='n', y='Padrão',
                          orientation='h', color='Padrão',
                          color_discrete_map=cor_map_p,
                          text='n')
            fig2.update_traces(textposition='outside')
            fig2.update_layout(
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=30),
                height=320,
                xaxis_title='Pacientes',
                yaxis_title='',
            )
            st.plotly_chart(fig2, use_container_width=True,
                            key=f"inercia_padrao_{abrev}")
        else:
            st.info("Sem dados de padrão de manejo.")

    # ── Benchmarks vs. AP e município ─────────────────────────────
    st.markdown(
        "**Comparação com a área programática e com o município** "
        "<span style='color:#777; font-size:0.85em;'>"
        "(mediana entre clínicas com n_tratados ≥ 50)</span>",
        unsafe_allow_html=True,
    )

    def _delta_chip(d, invertido=True):
        # invertido=True: positivo é ruim (inércia, estagnado)
        if d is None or pd.isna(d):
            return "<span style='color:#999;'>—</span>"
        sinal = '+' if d > 0 else ('' if d == 0 else '')
        if invertido:
            cor = '#B71C1C' if d > 0.5 else ('#198754' if d < -0.5 else '#666')
        else:
            cor = '#198754' if d > 0.5 else ('#B71C1C' if d < -0.5 else '#666')
        return (f"<span style='color:{cor}; font-weight:700;'>"
                f"{sinal}{d:+.1f} pp</span>".replace('++', '+'))

    def _bm_card(col, titulo, valor_equipe, valor_ap, valor_mun,
                 cor_destaque, invertido=True):
        with col:
            v = valor_equipe
            vap = valor_ap if valor_ap is not None else 0
            vmun = valor_mun if valor_mun is not None else 0
            d_ap = v - vap
            d_mun = v - vmun
            st.markdown(
                f"<div style='border:1px solid #E0E0E0; border-radius:6px; "
                f"padding:12px; background:#FAFAFA; height:100%;'>"
                f"<div style='font-size:0.85em; color:#555;'>{titulo}</div>"
                f"<div style='font-size:1.45em; font-weight:700; "
                f"color:{cor_destaque}; line-height:1.2;'>"
                f"Sua equipe: {v:.1f}%</div>"
                f"<div style='font-size:0.88em; color:#555; "
                f"margin-top:6px; line-height:1.5;'>"
                f"Mediana da AP: {vap:.1f}% &nbsp; "
                f"({_delta_chip(d_ap, invertido)})<br>"
                f"Mediana do município: {vmun:.1f}% &nbsp; "
                f"({_delta_chip(d_mun, invertido)})"
                f"</div></div>",
                unsafe_allow_html=True,
            )

    b1, b2, b3 = st.columns(3)
    _bm_card(b1, f"⏱️ % em inércia {abrev}",
             pct_iner, bm.get(f'ap_in_{abrev}'),
             bm.get(f'mun_in_{abrev}'),
             '#B71C1C', invertido=True)
    _bm_card(b2, f"🚧 % em tratamento estagnado {abrev}",
             pct_est, bm.get(f'ap_est_{abrev}'),
             bm.get(f'mun_est_{abrev}'),
             '#D32F2F', invertido=True)
    _bm_card(b3, f"🟢 % controlado {abrev}",
             pct_ctrl, bm.get(f'ap_ctrl_{abrev}'),
             bm.get(f'mun_ctrl_{abrev}'),
             '#198754', invertido=False)


# Ordem de exibição dos grupos de lacunas na aba narrativa. Difere
# da ordem canônica de GRUPOS_LACUNAS (que vive em
# utils/lacunas_config.py e é usada por outras telas). Chaves
# precisam bater literalmente com o que vem de df_lac['grupo'].
_ORDEM_GRUPOS_LACUNAS = [
    "Rastreio",
    "Hipertensão (HAS)",
    "Diabetes Mellitus (DM)",
    "Cardiopatia Isquêmica (CI)",
    "ICC e IRC (manejo clínico)",
    "Fibrilação Atrial (FA)",
    "Prescrições Inapropriadas",
]

# Renames apenas para exibição (chave do banco/config → label visível
# na aba). Não mexe no df_lac['grupo'] em si.
_LABEL_GRUPO_DISPLAY = {
    "Rastreio": "Rastreios",
    "ICC e IRC (manejo clínico)":
        "Insuficiência Cardíaca e Doença Renal Crônica",
}


# Texto contextual narrativo por grupo de lacunas. Mostrado à esquerda
# antes da listagem das lacunas piores/melhores em comparação com o
# município. Só descreve o RACIONAL CLÍNICO do grupo, deixando os
# números para os cards. Chaves devem bater literalmente com
# df_lac['grupo'] (proveniente de utils/lacunas_config.py).
NARRATIVA_GRUPO_LACUNAS = {
    "Cardiopatia Isquêmica (CI)":
        "Avalia se pacientes com CI estão em <b>prevenção secundária</b> "
        "adequada — antiagregação plaquetária, estatina de alta "
        "intensidade e betabloqueador quando apropriado. O efeito "
        "destas medidas sobre mortalidade e recorrência de eventos é "
        "maior que qualquer outra intervenção isolada.",
    "ICC e IRC (manejo clínico)":
        "Avalia se pacientes com <b>insuficiência cardíaca</b> ou "
        "<b>doença renal crônica</b> recebem o pacote farmacológico "
        "que reduz mortalidade e progressão da doença "
        "(IECA/BRA/INRA, betabloqueador, ARM, SGLT-2). Inclui também "
        "combinações inadequadas a evitar.",
    "Fibrilação Atrial (FA)":
        "Avalia <b>anticoagulação</b> e <b>controle da frequência "
        "cardíaca</b> em pacientes com FA. Estas são medidas "
        "terapêuticas em que o médico deverá avaliar segurança e "
        "adequação ao cenário do paciente para decidir, de forma "
        "compartilhada, se as utiliza ou não.",
    "Diabetes Mellitus (DM)":
        "Avalia <b>monitoramento glicêmico</b>, <b>rastreio de "
        "complicações</b> (pé, microalbuminúria) e adequação do "
        "<b>diagnóstico (CID)</b> — três pilares do cuidado "
        "longitudinal do paciente diabético.",
    "Hipertensão (HAS)":
        "Avalia <b>aferição regular da PA</b>, <b>controle pressórico</b> "
        "por faixa etária e adequação do <b>diagnóstico (CID)</b>. "
        "As metas pressóricas variam conforme idade e comorbidades.",
    "Prescrições Inapropriadas":
        "Combinações farmacológicas <b>contraindicadas</b> ou de "
        "<b>uso questionável</b> em determinadas populações. A "
        "deprescrição é tão importante quanto a prescrição correta.",
    "Rastreio":
        "Identificação <b>oportunística e ativa</b> de hipertensão e "
        "diabetes em populações elegíveis. Diagnóstico precoce muda "
        "a história natural dessas doenças.",
}


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — território da equipe
#
# Para o perfil 'equipe' (ESF), o território vem fixo do contexto
# territorial definido na tela de seleção do Home.py — a sidebar
# mostra apenas o resumo + botões de Trocar equipe / Sair.
#
# Para outros perfis (gerente / gestor / admin), continuam os
# selectboxes editáveis para navegar entre territórios.
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo()

if _perfil == 'equipe':
    _ctx = get_contexto_territorial()
    ap_sel  = _ctx.get('ap')
    cli_sel = _ctx.get('clinica')
    esf_sel = _ctx.get('esf')

    if not (ap_sel and cli_sel and esf_sel):
        # Contexto vazio — em vez de fazer st.switch_page automático
        # (que pode entrar em loop com st.navigation), mostra um link
        # clicável e para a renderização. Mais defensivo e visível
        # para o usuário do que um switch silencioso.
        st.error(
            "⚠️ Sua equipe não está selecionada. Volte para a tela "
            "inicial e escolha sua AP, Clínica e ESF."
        )
        st.page_link("Home.py", label="↩ Voltar para a tela inicial",
                      icon="🏠")
        st.stop()

    st.sidebar.header("🎯 Sua equipe")
    st.sidebar.markdown(
        f"**AP:** {anonimizar_ap(str(ap_sel))}  \n"
        f"**Clínica:** {anonimizar_clinica(cli_sel)}  \n"
        f"**ESF:** {anonimizar_esf(esf_sel)}"
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("🧑‍⚕️ Abrir Lista Nominal",
                          use_container_width=True,
                          type="primary", key="ve_abrir_lista"):
        st.switch_page("pages/Meus_Pacientes.py")
    if st.sidebar.button("🔄 Trocar equipe", use_container_width=True,
                          key="ve_trocar"):
        st.session_state['contexto_territorial'] = None
        st.switch_page("Home.py")
    if st.sidebar.button("🚪 Sair", use_container_width=True,
                          key="ve_sair"):
        logout()
else:
    st.sidebar.header("🎯 Equipe selecionada")
    st.sidebar.info(
        "⚠️ Selecione AP, Clínica e ESF para carregar a visão da equipe."
    )

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
(tab_resumo, tab_cont, tab_polif,
 tab_has, tab_dm, tab_lacunas) = st.tabs([
    "📊 Resumo da população",
    "🔄 Continuidade",
    "💊 Carga farmacológica",
    "🩺 Hipertensão",
    "🩸 Diabetes",
    "⚠️ Lacunas",
])

# ─────────────────────────────────────────────────────────────
# ABA 1 — RESUMO DA EQUIPE
# ─────────────────────────────────────────────────────────────
with tab_resumo:
    n_total = len(df)

    # ─────────────────────────────────────────────────────────
    # 1️⃣ Top-10 com maior prioridade de cuidado — cards expansíveis
    # ─────────────────────────────────────────────────────────
    st.markdown(
        "#### 1️⃣ 10 pacientes com maior prioridade de cuidado"
    )
    st.markdown(
        "Caros colegas, aqui estão os 10 pacientes com maior pontuação "
        "no **Índice de Priorização do Cuidado (IPC)**. Estes pacientes "
        "possuem uma combinação de critérios que consideramos "
        "importantes para qualificar o cuidado de pessoas com "
        "**multimorbidade** (2 ou mais condições crônicas em um mesmo "
        "paciente). Estes critérios são uma combinação de **carga de "
        "morbidade**, **carga farmacológica**, **tempo sem consulta "
        "médica** e **lacunas de cuidado**. Use esta lista como ponto "
        "de partida para discussão em equipe e planejamento do cuidado "
        "de pacientes com doenças crônicas."
    )

    top10_cpfs = (
        df.sort_values(['ipc', 'charlson_score'], ascending=[False, False])
          .head(10)['cpf'].astype(str).tolist()
    )

    if not top10_cpfs:
        st.info("Sem pacientes para listar.")
    else:
        from components.lista_pacientes import (
            load_patient_data_paginated, create_patient_card,
        )

        df_top10 = load_patient_data_paginated(
            cpfs=tuple(top10_cpfs),
            limit=len(top10_cpfs),
            offset=0,
        )

        if df_top10.empty:
            st.warning(
                "Não foi possível carregar os dados completos dos "
                "pacientes Top-10."
            )
        else:
            # SQL não ordena por IPC (calculado em Python). Reordena aqui.
            df_top10 = df_top10.sort_values(
                ['ipc', 'charlson_score'], ascending=[False, False]
            )
            for _, paciente in df_top10.iterrows():
                create_patient_card(paciente.to_dict(), key_prefix='resumo_')

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
| 🦠 **Carga de Morbidade** | {PESOS_DEFAULT['charlson']:.0%} | 0–3 → 0 · 4–6 → 0,33 · 7–9 → 0,67 · ≥10 → 1 |
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
# ABA 2 — CONTINUIDADE DO CUIDADO
# ─────────────────────────────────────────────────────────────
with tab_cont:
    st.markdown(
        "#### Continuidade do cuidado — narrativa por carga de morbidade"
    )
    st.caption(
        "Indicadores de acesso, regularidade e fragmentação dos últimos "
        "365 dias, comparados com a média do município. Pacientes com "
        "maior carga de morbidade deveriam ter mais consultas e "
        "intervalos menores — quando isso não acontece, há iniquidade "
        "no cuidado."
    )

    with st.spinner("Carregando indicadores de continuidade..."):
        cont     = carregar_continuidade_agregado(ap_sel, cli_sel, esf_sel)
        cont_mun = carregar_continuidade_agregado(None, None, None)

    n_total_c     = int(cont.get('n_total', 0) or 0) or 1
    n_total_c_mun = int(cont_mun.get('n_total', 0) or 0) or 1

    def _pct_int(num):
        return f"{int(num or 0)/n_total_c*100:.0f}%" if n_total_c else "0%"

    # ═════════════════════════════════════════════════════════════
    # 1. PACIENTES EM ALTO RISCO — pontos críticos
    # Denominador = pacientes de Alto + Muito Alto risco (não a equipe
    # toda). "De N pacientes de alto risco, X têm tal lacuna" é a
    # leitura correta para esses indicadores.
    # ═════════════════════════════════════════════════════════════
    n_alto_ma_eq  = (int(cont.get('n_carga_alto', 0) or 0)
                     + int(cont.get('n_carga_ma', 0) or 0)) or 1
    n_alto_ma_mun = (int(cont_mun.get('n_carga_alto', 0) or 0)
                     + int(cont_mun.get('n_carga_ma', 0) or 0)) or 1

    st.markdown("##### 1. Pacientes em alto risco — pontos críticos")
    e1, d1 = st.columns([1, 1.3])
    with e1:
        st.markdown(
            f"<div style='line-height:1.6; font-size:0.95em;'>"
            f"Estes três indicadores apontam pacientes que combinam "
            f"<b>alta carga de morbidade</b> com <b>acesso insuficiente</b>. "
            f"São prioridade absoluta para busca ativa e revisão do "
            f"plano de cuidado.<br><br>"
            f"O denominador aqui são os <b>{n_alto_ma_eq:,} pacientes "
            f"de Carga Alta ou Muito Alta</b> da sua equipe — não a "
            f"equipe toda. Assim, '5%' significa <i>5 em cada 100 "
            f"pacientes de alto risco</i> com aquela lacuna.<br><br>"
            f"A comparação com o município ajuda a calibrar a leitura: "
            f"equipes em territórios mais vulneráveis tendem a ter % "
            f"mais alto em todos os indicadores. O que importa é "
            f"identificar onde sua equipe está acima da média e "
            f"priorizar esses pacientes."
            f"</div>",
            unsafe_allow_html=True,
        )
    with d1:
        sub = st.columns(3)
        _card_carga_strat(
            sub[0], "Alto risco + baixo acesso", "⚠️",
            cont.get('n_alto_baixo_acesso'), n_alto_ma_eq,
            cont_mun.get('n_alto_baixo_acesso'), n_alto_ma_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            sub[1], "Alto risco + intervalo longo", "⏱️",
            cont.get('n_alto_intv_longo'), n_alto_ma_eq,
            cont_mun.get('n_alto_intv_longo'), n_alto_ma_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            sub[2], "Alto risco + uso frequente de urgência", "🚑",
            cont.get('n_freq_urg_alto_ma'), n_alto_ma_eq,
            cont_mun.get('n_freq_urg_alto_ma'), n_alto_ma_mun,
            indicador_ruim_se_alto=True,
        )

    # ═════════════════════════════════════════════════════════════
    # 2. ACESSO E REGULARIDADE — estratificado por carga
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(
        "##### 2. Acesso e regularidade — estratificado por Carga de Morbidade"
    )
    st.caption(
        "Para cada indicador, comparamos as 4 cargas (🟢 Baixa, 🟡 "
        "Moderada, 🟠 Alta, 🔴 Muito Alta) com a média do município "
        "naquela mesma carga. A leitura clínica esperada é descrita "
        "no texto à esquerda; quando o gradiente está invertido, há "
        "alerta automático."
    )

    # (chave_total, sufixo, label, emoji, ruim_se_alto, esperado_crescente,
    #  texto_esquerda)
    _SUB_ATOS = [
        (
            "n_sem_medico_180d", "sm180",
            "Sem médico há mais de 180 dias", "🩺",
            True, False,
            "Pacientes com maior carga de morbidade <b>deveriam estar "
            "entre os mais bem acompanhados</b>: o esperado é que o "
            "% sem médico recente diminua conforme a carga aumenta. "
            "Quando isso não acontece, é sinal de <b>iniquidade no "
            "acesso</b> — quem mais precisa, menos vê o médico.",
        ),
        (
            "n_regular", "reg",
            "Acompanhamento regular (seis ou mais meses do ano com "
            "consultas médicas)", "📅",
            False, True,
            "<b>Regularidade aumenta com a carga</b> é o gradiente "
            "esperado: pacientes mais complexos exigem retornos mais "
            "frequentes. Equipes maduras costumam ter Muito Alto e "
            "Alto bem acima de Baixo neste indicador.",
        ),
        (
            "n_sem_consulta_365d", "sc",
            "Sem nenhuma consulta no ano", "🚫",
            True, False,
            "Esperamos % cada vez <b>menor</b> conforme a carga "
            "aumenta. Pacientes Muito Alto sem nenhuma consulta no "
            "ano são <b>prioridade absoluta</b> para busca ativa — "
            "alto risco clínico desconhecido.",
        ),
        (
            "n_baixa_long", "bl",
            "Fragmentação (>50% das consultas fora da clínica)", "🧩",
            True, False,
            "Pacientes mais complexos <b>deveriam ter cuidado "
            "centrado na equipe de referência</b> — esperamos "
            "fragmentação cair com a carga. Alta fragmentação em "
            "Muito Alto sugere falha de vínculo: o paciente busca "
            "cuidado em outras unidades porque não encontra "
            "regularidade na sua.",
        ),
    ]

    for chave_total, suf, label, emoji, ruim_alto, cresc, texto in _SUB_ATOS:
        st.markdown(f"###### {emoji} {label}")
        e, d = st.columns([1, 1.3])
        with e:
            # Detecta inversão de gradiente
            pcts = []
            for suf_carga in ('baixo', 'mod', 'alto', 'ma'):
                n  = cont.get(f'n_{suf}_{suf_carga}', 0)
                dn = cont.get(f'n_carga_{suf_carga}', 0)
                pcts.append((n / dn * 100) if dn else None)
            inversao = _detecta_inversao_gradiente(pcts, cresc)

            html = (f"<div style='line-height:1.6; font-size:0.92em;'>"
                    f"{texto}</div>")
            if inversao:
                html += (
                    f"<div style='margin-top:10px; padding:8px 10px; "
                    f"border-left:3px solid #C0392B; "
                    f"background:rgba(192,57,43,0.08); border-radius:4px; "
                    f"font-size:0.88em;'>{inversao}</div>"
                )
            st.markdown(html, unsafe_allow_html=True)
        with d:
            sub = st.columns(4)
            for i, (carga_lbl, em, suf_carga) in enumerate([
                ("Baixa",      "🟢", "baixo"),
                ("Moderada",   "🟡", "mod"),
                ("Alta",       "🟠", "alto"),
                ("Muito Alta", "🔴", "ma"),
            ]):
                _card_carga_strat(
                    sub[i], carga_lbl, em,
                    cont.get(f'n_{suf}_{suf_carga}'),
                    cont.get(f'n_carga_{suf_carga}'),
                    cont_mun.get(f'n_{suf}_{suf_carga}'),
                    cont_mun.get(f'n_carga_{suf_carga}'),
                    indicador_ruim_se_alto=ruim_alto,
                )

    # ═════════════════════════════════════════════════════════════
    # 3. MÉDIAS DE CONSULTAS (12 meses) — estratificado por carga
    # Mesmo padrão narrativa-à-esquerda + cards-à-direita das
    # outras seções, agora com explicação por indicador.
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(
        "##### 3. Médias por paciente nos últimos 12 meses — por Carga"
    )
    st.caption(
        "Cada card mostra a média da equipe naquela carga e a "
        "comparação com a média do município (mesma carga). Em "
        "cargas altas, mais consultas e intervalos menores são bons "
        "sinais — inversões nesse padrão indicam iniquidade no ritmo "
        "do cuidado."
    )

    # (sufixo, label, emoji, ruim_se_alto, esperado_crescente, texto_esq)
    _MEDIAS_STRAT = [
        (
            "ct", "Consultas no total / ano", "👥", False, True,
            "Total de consultas com qualquer profissional da equipe "
            "(médico, enfermagem, técnico) por paciente em 12 meses. "
            "<b>Esperamos um gradiente claro</b>: pacientes Muito "
            "Alto costumam ter 3–4× mais consultas que Baixos. "
            "Quando a diferença é pequena, o cuidado pode estar "
            "padronizado demais — todos recebem o mesmo, "
            "independentemente da complexidade.",
        ),
        (
            "med", "Consultas médicas / ano", "🩺", False, True,
            "Consultas com médico (clínico geral, médico de família, "
            "geriatra etc.) por paciente em 12 meses. É o indicador "
            "<b>mais sensível à longitudinalidade do cuidado</b>: "
            "cargas altas precisam de consultas médicas frequentes "
            "para acompanhar morbidades, ajustar terapêutica e "
            "revisar exames complementares. O número médio na "
            "população geral fica entre 1 e 2/ano; em pacientes "
            "Muito Alto deveria passar de 5/ano.",
        ),
        (
            "enf", "Consultas de enfermagem / ano", "📋", False, True,
            "Consultas com enfermeiro(a) por paciente em 12 meses. "
            "A enfermagem complementa o cuidado médico em "
            "<b>hipertensão, diabetes, gestação e crônicos</b>, com "
            "consultas próprias de educação em saúde, monitoramento "
            "e revisão de plano. Bom cuidado tem ambos (médico e "
            "enfermagem) crescendo com a carga, não um substituindo "
            "o outro.",
        ),
        (
            "tec", "Consultas de técnico de enfermagem / ano",
            "💉", False, True,
            "Atendimentos com técnico de enfermagem por paciente em "
            "12 meses — incluindo <b>vacinas, curativos, aferições "
            "de PA, coleta de exames, glicemia capilar</b> etc. "
            "Esperamos números maiores em cargas altas (mais "
            "procedimentos), mas a relação com a complexidade "
            "clínica é mais fraca que na enfermagem.",
        ),
        (
            "iv", "Intervalo mediano entre consultas (dias)",
            "⏱️", True, False,
            "Mediana dos intervalos (em dias) entre consultas "
            "consecutivas do paciente. <b>Quanto menor, melhor</b> "
            "— principalmente em cargas altas. Pacientes Muito Alto "
            "deveriam ter intervalo bem menor que Baixos (idealmente "
            "&lt;30 dias contra &gt;60 dias). Quando o intervalo de "
            "Muito Alto é parecido com Baixo, há iniquidade no "
            "<b>ritmo</b> do cuidado: o paciente complexo demora "
            "tanto quanto o saudável para voltar.",
        ),
        (
            "pu", "% de consultas médicas na unidade", "🏥", False, True,
            "Proporção das consultas médicas que aconteceram na "
            "<b>própria unidade de cadastro</b> (vs UPA, hospital "
            "ou outras unidades). Cargas altas deveriam ter % maior "
            "— mais vínculo com a equipe de referência. Valores "
            "baixos sugerem fragmentação ou paciente buscando "
            "cuidado em outros pontos por falta de acesso na sua "
            "unidade.",
        ),
    ]

    for suf, label, emoji, ruim_alto, cresc, texto in _MEDIAS_STRAT:
        st.markdown(f"###### {emoji} {label}")
        e, d = st.columns([1, 1.3])
        with e:
            valores = [cont.get(f'm_{suf}_{c}')
                       for c in ('baixo', 'mod', 'alto', 'ma')]
            inversao = _detecta_inversao_gradiente(valores, cresc)
            html = (f"<div style='line-height:1.6; font-size:0.92em;'>"
                    f"{texto}</div>")
            if inversao:
                html += (
                    f"<div style='margin-top:10px; padding:8px 10px; "
                    f"border-left:3px solid #C0392B; "
                    f"background:rgba(192,57,43,0.08); border-radius:4px; "
                    f"font-size:0.88em;'>{inversao}</div>"
                )
            st.markdown(html, unsafe_allow_html=True)
        with d:
            sub = st.columns(4)
            for i, (carga_lbl, em, suf_carga) in enumerate([
                ("Baixa",      "🟢", "baixo"),
                ("Moderada",   "🟡", "mod"),
                ("Alta",       "🟠", "alto"),
                ("Muito Alta", "🔴", "ma"),
            ]):
                _card_carga_strat(
                    sub[i], carga_lbl, em,
                    cont.get(f'm_{suf}_{suf_carga}'), None,
                    cont_mun.get(f'm_{suf}_{suf_carga}'), None,
                    indicador_ruim_se_alto=ruim_alto,
                    formato_valor='avg',
                )

    # ═════════════════════════════════════════════════════════════
    # Final: nota remetendo a Meus Pacientes
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.info(
        "🧑‍⚕️ **Para abrir os pacientes individualmente**, vá para a "
        "aba **Meus Pacientes**. Lá é possível filtrar a lista "
        "nominal por **Carga de Morbidade** e por **sinalizadores de "
        "continuidade** (sem médico há >180d, alto risco com baixo "
        "acesso, alto risco com intervalo longo, uso frequente de "
        "urgência) e abrir o card completo de cada paciente."
    )

# ─────────────────────────────────────────────────────────────
# ABA 3 — CARGA FARMACOLÓGICA (Polifarmácia, STOPP, START, Beers, ACB)
# ─────────────────────────────────────────────────────────────
with tab_polif:
    st.markdown("#### Carga farmacológica")

    # Texto explicativo de abertura — três dimensões + ACB
    st.markdown("""
**Carga farmacológica** é o termo que usamos para descrever a
exposição cumulativa de um paciente a medicamentos e seus
potenciais efeitos adversos. Operacionalmente, costuma ser
decomposta em três dimensões.

**Dimensão quantitativa.** Polifarmácia (≥5 medicamentos crônicos)
e hiperpolifarmácia (≥10). São métricas simples, mas que se
correlacionam fortemente com eventos adversos, hospitalizações e
mortalidade em idosos.

**Dimensão qualitativa.** Avalia a adequação prescritiva paciente
a paciente. Fazem parte deste domínio os critérios STOPP/START, os
critérios de Beers e o MAI (*Medication Appropriateness Index*).

**Dimensão de exposição funcional.** Mensura o potencial impacto
funcional que o uso crônico de medicamentos pode ter sobre o
paciente. O Drug Burden Index (DBI) é um exemplo de escala neste
domínio: pondera a exposição diária a fármacos sedativos e
anticolinérgicos pela dose mínima eficaz, predizendo perda
funcional e cognitiva.

Dentro dessa dimensão, a **carga anticolinérgica** ocupa um lugar
de destaque e está aqui representada pelo **Escore ACB
(*Anticholinergic Cognitive Burden*)**. Refere-se ao efeito
cumulativo do bloqueio de receptores muscarínicos por um ou mais
medicamentos. Perifericamente, produz xerostomia, constipação,
retenção urinária, taquicardia e visão turva; centralmente, pode
causar sedação, confusão, delirium e — com exposição prolongada —
declínio cognitivo e maior incidência de demência. Os idosos são
especialmente vulneráveis pela menor reserva colinérgica central,
redução da barreira hematoencefálica e alterações
farmacocinéticas.

---

**No Navegador**, os três domínios estão representados
respectivamente por: (1) a contagem de medicamentos crônicos e a
identificação dos pacientes em polifarmácia ou hiperpolifarmácia;
(2) o painel de critérios STOPP, START e Beers; e (3) o Escore
ACB calculado individualmente para cada paciente.
""")

    with st.spinner("Calculando carga farmacológica da equipe e do município..."):
        pf_eq  = carregar_polifarm_resumo(ap_sel, cli_sel, esf_sel)
        pf_mun = carregar_polifarm_resumo(None, None, None)
        agg    = carregar_criterios_idoso_agregado(ap_sel, cli_sel, esf_sel)

    n_total_eq   = int(pf_eq.get('n_total', 0) or 0) or 1
    n_idosos_eq  = int(pf_eq.get('n_idosos', 0) or 0) or 1
    n_total_mun  = int(pf_mun.get('n_total', 0) or 0) or 1
    n_idosos_mun = int(pf_mun.get('n_idosos', 0) or 0) or 1

    def _top5_criterios(tipo: str, titulo: str):
        """Lista em bullets os 5 critérios mais prevalentes de um
        tipo (STOPP/START/Beers) na equipe, ocupando largura total
        abaixo dos cards da seção."""
        df_tot = agg.get('totais_por_criterio', pd.DataFrame())
        if df_tot.empty:
            return
        df_top5 = (df_tot[df_tot['tipo'] == tipo]
                   .sort_values('n_pacientes', ascending=False)
                   .head(5))
        df_top5 = df_top5[df_top5['n_pacientes'] > 0]
        if df_top5.empty:
            return
        bullets = ""
        for _, r in df_top5.iterrows():
            bullets += (
                f"<li style='margin-bottom:4px;'><b>"
                f"{int(r['n_pacientes'])} pacientes</b> — "
                f"{r['descricao']}</li>"
            )
        st.markdown(
            f"<div style='margin-top:14px; font-size:0.92em;'>"
            f"<b>{titulo}</b>"
            f"<ul style='margin:6px 0 0 0; padding-left:20px;'>"
            f"{bullets}</ul></div>",
            unsafe_allow_html=True,
        )

    # ═════════════════════════════════════════════════════════════
    # 1. DIMENSÃO QUANTITATIVA — polifarmácia e hiperpolifarmácia
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(
        "##### 1. Dimensão quantitativa — polifarmácia e "
        "hiperpolifarmácia"
    )
    e1, d1 = st.columns([1, 1.3])
    with e1:
        media_meds_eq        = pf_eq.get('media_meds') or 0
        media_meds_idosos_eq = pf_eq.get('media_meds_idosos') or 0
        st.markdown(
            f"<div style='line-height:1.6; font-size:0.95em;'>"
            f"Quantos medicamentos crônicos cada paciente tem em "
            f"prescrição? <b>Polifarmácia</b> sinaliza ≥5 e "
            f"<b>hiperpolifarmácia</b> ≥10 medicamentos crônicos "
            f"simultâneos.<br><br>"
            f"Na sua equipe, a média é <b>{float(media_meds_eq):.1f} "
            f"medicamentos crônicos por paciente</b> "
            f"(<b>{float(media_meds_idosos_eq):.1f}</b> nos pacientes "
            f"com 65 anos ou mais). Os cards à direita mostram a "
            f"prevalência de polifarmácia e hiperpolifarmácia "
            f"separadamente para a equipe inteira e para o "
            f"sub-conjunto de <b>idosos</b> — esse último é o "
            f"recorte que mais importa para o risco de eventos "
            f"adversos.<br><br>"
            f"A comparação com a média do município ajuda a calibrar "
            f"a leitura: equipes com perfil mais idoso ou mais "
            f"comórbido tendem a ter % maior, e isso não é "
            f"necessariamente \"problema\" — mas serve para "
            f"identificar pacientes-alvo de revisão de prescrição."
            f"</div>",
            unsafe_allow_html=True,
        )
    with d1:
        c1, c2 = st.columns(2)
        _card_carga_strat(
            c1, "Polifarmácia (≥5 meds crônicos)", "💊",
            pf_eq.get('n_polifarm'), n_total_eq,
            pf_mun.get('n_polifarm'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c2, "Hiperpolifarmácia (≥10 meds crônicos)", "💊💊",
            pf_eq.get('n_hiperpoli'), n_total_eq,
            pf_mun.get('n_hiperpoli'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        c3, c4 = st.columns(2)
        _card_carga_strat(
            c3, "Idosos (≥65a) em polifarmácia", "👴",
            pf_eq.get('n_polifarm_idosos'), n_idosos_eq,
            pf_mun.get('n_polifarm_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c4, "Idosos (≥65a) em hiperpolifarmácia", "👴",
            pf_eq.get('n_hiperpoli_idosos'), n_idosos_eq,
            pf_mun.get('n_hiperpoli_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )

    # ═════════════════════════════════════════════════════════════
    # 2. CRITÉRIOS STOPP
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("##### 2. Critérios STOPP")
    e2, d2 = st.columns([1, 1.3])
    with e2:
        st.markdown(
            "<div style='line-height:1.6; font-size:0.95em;'>"
            "<b>STOPP</b> é uma ferramenta de rastreio que sinaliza "
            "prescrições potencialmente inapropriadas em idosos, "
            "organizada por sistema/órgão. Destaca três cenários: "
            "medicamentos sem benefício comprovado nessa população, "
            "medicamentos mantidos por tempo superior ao recomendado "
            "e duplicações terapêuticas. Indica o que deve ser "
            "<b>reavaliado ou suspenso</b>.<br><br>"
            "Os cards à direita mostram quantos pacientes da equipe "
            "têm <b>pelo menos um critério STOPP positivo</b>, "
            "comparados com a média do município. A lista detalhada "
            "de quais critérios estão ativos aparece mais abaixo "
            "(<i>Detalhe por critério</i>) e a lista nominal de "
            "pacientes está no fim da aba."
            "</div>",
            unsafe_allow_html=True,
        )
    with d2:
        c1, c2 = st.columns(2)
        _card_carga_strat(
            c1, "Pacientes com ≥1 critério STOPP", "🚫",
            pf_eq.get('n_com_stopp'), n_total_eq,
            pf_mun.get('n_com_stopp'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c2, "Idosos (≥65a) com ≥1 critério STOPP", "👴",
            pf_eq.get('n_com_stopp_idosos'), n_idosos_eq,
            pf_mun.get('n_com_stopp_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )
    _top5_criterios(
        'STOPP',
        'Top-5 critérios STOPP mais prevalentes na sua equipe',
    )

    # ═════════════════════════════════════════════════════════════
    # 3. CRITÉRIOS START
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("##### 3. Critérios START")
    e3, d3 = st.columns([1, 1.3])
    with e3:
        st.markdown(
            "<div style='line-height:1.6; font-size:0.95em;'>"
            "<b>START</b> é a ferramenta complementar ao STOPP: em "
            "vez de apontar o que deve sair, sinaliza o que <b>"
            "deveria ter sido prescrito e não foi</b>. As "
            "recomendações são baseadas em condições clínicas — como "
            "antiplaquetário em doença vascular, ácido fólico com "
            "metotrexato, laxativos com opioides crônicos — e devem "
            "ser consideradas para a maioria dos idosos elegíveis, "
            "salvo contraindicação específica.<br><br>"
            "É importante lembrar que cada um destes apontamentos "
            "é uma <b>oportunidade de revisão</b>, não uma falha "
            "automática. A decisão de prescrever ou não envolve "
            "avaliação de segurança, contraindicações, expectativa "
            "de vida e preferência do paciente."
            "</div>",
            unsafe_allow_html=True,
        )
    with d3:
        c1, c2 = st.columns(2)
        _card_carga_strat(
            c1, "Pacientes com ≥1 critério START", "💡",
            pf_eq.get('n_com_start'), n_total_eq,
            pf_mun.get('n_com_start'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c2, "Idosos (≥65a) com ≥1 critério START", "👴",
            pf_eq.get('n_com_start_idosos'), n_idosos_eq,
            pf_mun.get('n_com_start_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )
    _top5_criterios(
        'START',
        'Top-5 critérios START mais prevalentes na sua equipe',
    )

    # ═════════════════════════════════════════════════════════════
    # 4. CRITÉRIOS BEERS
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("##### 4. Critérios de Beers")
    e4, d4 = st.columns([1, 1.3])
    with e4:
        st.markdown(
            "<div style='line-height:1.6; font-size:0.95em;'>"
            "<b>Beers (2023)</b> é um conjunto de critérios "
            "desenvolvido pela <i>American Geriatrics Society</i> "
            "para identificar medicamentos potencialmente "
            "inapropriados em pessoas com 65 anos ou mais fora de "
            "cuidados paliativos exclusivos. Cobrem precauções "
            "específicas, ajustes de dose e interações "
            "medicamentosas.<br><br>"
            "A versão de 2023 enfatiza a <b>carga anticolinérgica "
            "cumulativa</b> e atualiza recomendações sobre "
            "anticoagulação, antidiabéticos e prevenção "
            "cardiovascular primária. Por exemplo: evitar início de "
            "AAS para prevenção primária em idosos; cautela com "
            "rivaroxabana e dabigatrana em FA prolongada (frente à "
            "apixabana); evitar sulfonilureias pelo risco de "
            "hipoglicemia."
            "</div>",
            unsafe_allow_html=True,
        )
    with d4:
        c1, c2 = st.columns(2)
        _card_carga_strat(
            c1, "Pacientes com ≥1 critério Beers", "🇺🇸",
            pf_eq.get('n_com_beers'), n_total_eq,
            pf_mun.get('n_com_beers'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c2, "Idosos (≥65a) com ≥1 critério Beers", "👴",
            pf_eq.get('n_com_beers_idosos'), n_idosos_eq,
            pf_mun.get('n_com_beers_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )
    _top5_criterios(
        'Beers',
        'Top-5 critérios Beers mais prevalentes na sua equipe',
    )

    # ═════════════════════════════════════════════════════════════
    # 5. ESCORE ACB — carga anticolinérgica
    # ═════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("##### 5. Escore ACB — *Anticholinergic Cognitive Burden*")
    e5, d5 = st.columns([1, 1.3])
    with e5:
        st.markdown(
            "<div style='line-height:1.6; font-size:0.95em;'>"
            "O <b>Escore ACB</b> mede o efeito cumulativo do "
            "bloqueio de receptores muscarínicos pelos medicamentos "
            "em uso. Cada fármaco recebe um peso de 0 a 3; o escore "
            "do paciente é a soma dos pesos da lista atual de "
            "medicamentos.<br><br>"
            "<b>ACB ≥ 1</b> indica algum grau de exposição "
            "anticolinérgica; <b>ACB ≥ 3</b> é o ponto de corte "
            "associado a risco clinicamente relevante de confusão, "
            "delirium, quedas e — com exposição prolongada — "
            "declínio cognitivo.<br><br>"
            "Idosos são especialmente vulneráveis pela menor reserva "
            "colinérgica central, alterações farmacocinéticas e "
            "menor barreira hematoencefálica."
            "</div>",
            unsafe_allow_html=True,
        )
    with d5:
        c1, c2 = st.columns(2)
        _card_carga_strat(
            c1, "Pacientes com ACB ≥ 1", "🧠",
            pf_eq.get('n_acb_ge1'), n_total_eq,
            pf_mun.get('n_acb_ge1'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c2, "Pacientes com ACB ≥ 3 (risco relevante)", "🚨",
            pf_eq.get('n_acb_ge3'), n_total_eq,
            pf_mun.get('n_acb_ge3'), n_total_mun,
            indicador_ruim_se_alto=True,
        )
        c3, c4 = st.columns(2)
        _card_carga_strat(
            c3, "Idosos (≥65a) com ACB ≥ 1", "👴",
            pf_eq.get('n_acb_ge1_idosos'), n_idosos_eq,
            pf_mun.get('n_acb_ge1_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )
        _card_carga_strat(
            c4, "Idosos (≥65a) com ACB ≥ 3", "👴",
            pf_eq.get('n_acb_ge3_idosos'), n_idosos_eq,
            pf_mun.get('n_acb_ge3_idosos'), n_idosos_mun,
            indicador_ruim_se_alto=True,
        )

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

    # ─── Lista nominal removida — usuário deve usar a aba "Meus Pacientes" ───
    st.markdown("---")
    st.info(
        "🧑‍⚕️ **Para abrir os pacientes individualmente**, vá para a "
        "aba **Meus Pacientes**. Lá é possível filtrar a lista "
        "nominal por **Carga de Morbidade** e por **sinalizadores "
        "de carga farmacológica** (polifarmácia, hiperpolifarmácia, "
        "ACB ≥ 3, critérios STOPP/START/Beers ativos) e abrir o "
        "card completo de cada paciente."
    )


# ─────────────────────────────────────────────────────────────
# ABA 4 — HIPERTENSÃO
# Mesma base da aba "🩺 Hipertensão" + campos importados das abas
# 'Controle pressórico', 'Medicamentos prescritos' e 'Lacunas' da
# page Hipertensão. Layout em 2 colunas: à esquerda o texto
# narrativo, à direita os cards. Mantém a tabela nominal embaixo.
# ─────────────────────────────────────────────────────────────
with tab_has:
    st.markdown("#### Hipertensão arterial — narrativa da equipe")
    st.caption(
        "Mesma base da aba 🩺 Hipertensão, ampliada com medicamentos, "
        "combinações, intensidade do tratamento, recência da PA, "
        "tendência e risco cardiovascular — apresentada como história "
        "em 5 atos. Status do controle pressórico vem da fato "
        "(status_controle_pressorio) e considera as últimas aferições."
    )

    with st.spinner("Carregando indicadores de HAS..."):
        ag_hn = carregar_hipertensao_narrativa_agregado(
            ap_sel, cli_sel, esf_sel)

    n_has_n      = int(ag_hn.get('n_has', 0) or 0) or 1
    n_total_eq_h = int(ag_hn.get('n_total', 0) or 0) or 1

    def _vh(k):
        return int(ag_hn.get(k, 0) or 0)

    def _pct_hn(num):
        return f"{int(num or 0)/n_has_n*100:.0f}%"

    # Helpers de destaque inline
    def _bh(v):       return f"<b>{v}</b>"
    def _bh_red(v):   return f"<span style='color:#B71C1C; font-weight:700;'>{v}</span>"
    def _bh_green(v): return f"<span style='color:#198754; font-weight:700;'>{v}</span>"
    def _bh_orange(v):return f"<span style='color:#E69138; font-weight:700;'>{v}</span>"

    n_has_total      = _vh('n_has')
    n_sem_cid        = _vh('n_sem_cid')
    n_por_cid        = _vh('n_por_cid')
    n_por_critica    = _vh('n_por_medida_critica')
    n_por_repetidas  = _vh('n_por_medidas_rep')
    n_por_med        = _vh('n_por_medicamento')
    pct_eq_has       = (n_has_total / n_total_eq_h * 100) if n_total_eq_h else 0

    n_ctrl_h    = _vh('n_ctrl')
    n_desc_h    = _vh('n_desc')
    n_sem_info  = _vh('n_sem_info')
    n_menor80   = _vh('n_menor80')
    n_ctrl_m80  = _vh('n_ctrl_menor80')
    n_80mais    = _vh('n_80mais')
    n_ctrl_80   = _vh('n_ctrl_80mais')
    n_pa_90d    = _vh('n_pa_90d')
    n_pa_180    = _vh('n_pa_91_180')
    n_pa_365    = _vh('n_pa_181_365')
    n_pa_old    = _vh('n_pa_365mais')
    n_melh      = _vh('n_melhorando')
    n_est_h     = _vh('n_estavel')
    n_pio_h     = _vh('n_piorando')
    media_pas   = ag_hn.get('media_pas')
    media_pad   = ag_hn.get('media_pad')
    media_pct_c = ag_hn.get('media_pct_ctrl')

    n_sem_pa180 = _vh('n_sem_pa_180d')
    n_dm_has_pa = _vh('n_dm_has_pa')
    n_sem_creat = _vh('n_sem_creat')
    n_sem_col   = _vh('n_sem_col')
    n_sem_eas   = _vh('n_sem_eas')
    n_sem_ecg   = _vh('n_sem_ecg')
    n_sem_imc   = _vh('n_sem_imc')

    n_has_dm    = _vh('n_has_dm')
    n_has_irc   = _vh('n_has_irc')
    n_has_ci    = _vh('n_has_ci')
    n_has_icc   = _vh('n_has_icc')
    n_has_avc   = _vh('n_has_avc')
    n_who_crit  = _vh('n_who_critico')
    n_who_ma    = _vh('n_who_muito_alto')
    n_who_a     = _vh('n_who_alto')
    n_who_mod   = _vh('n_who_moderado')
    n_who_b     = _vh('n_who_baixo')
    n_who_nc    = _vh('n_who_nao_calc')

    n_ieca      = _vh('n_rx_ieca')
    n_bra       = _vh('n_rx_bra')
    n_bcc_dhp   = _vh('n_rx_bcc_dhp')
    n_bcc_ndhp  = _vh('n_rx_bcc_nao_dhp')
    n_tiazid    = _vh('n_rx_tiazidico')
    n_diur_alca = _vh('n_rx_diur_alca')
    n_poup_k    = _vh('n_rx_poupador_k')
    n_betabloq  = _vh('n_rx_betabloq')
    n_simpat    = _vh('n_rx_simpaticol')
    n_alfablo   = _vh('n_rx_alfabloq')
    n_vasod     = _vh('n_rx_vasodilat')
    n_nitrato   = _vh('n_rx_nitrato')

    n_ieca_bra       = _vh('n_rx_ieca_bra')
    n_alca_icc       = _vh('n_rx_diur_alca_icc')
    n_alca_sem_icc   = _vh('n_rx_diur_alca_sem_icc')
    n_poup_k_icc     = _vh('n_rx_poupador_k_icc')
    n_nit_ci         = _vh('n_rx_nitrato_ci')
    n_nit_sem_ci     = _vh('n_rx_nitrato_sem_ci')

    n_mono      = _vh('n_int_mono')
    n_dupla     = _vh('n_int_dupla')
    n_tripla    = _vh('n_int_tripla')
    n_quad      = _vh('n_int_quadrupla')
    n_sem_med   = _vh('n_int_sem_med')

    # ───────── ATO 1 — POPULAÇÃO E COMO FORAM IDENTIFICADOS ─────────
    st.markdown("---")
    st.markdown("##### 1. Como foram identificados os hipertensos da equipe?")
    a1e, a1d = st.columns([1, 1.1])
    with a1e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Sua equipe tem {_bh(n_has_total)} <b>hipertensos</b> "
            f"({_bh(f'{pct_eq_has:.0f}%')} da população cadastrada).<br><br>"
            f"<b>Como chegaram a esse diagnóstico?</b><br>"
            f"• {_bh(n_por_cid)} <b>por CID registrado</b> (I10–I16, "
            f"O10–O11);<br>"
            f"• {_bh(n_por_critica)} por <b>medida crítica</b> (≥180/110 "
            f"mmHg em uma única aferição);<br>"
            f"• {_bh(n_por_repetidas)} por <b>medidas repetidas</b> (≥140/90 "
            f"em datas distintas);<br>"
            f"• {_bh(n_por_med)} por <b>uso de anti-hipertensivo</b> sem CID "
            f"(diagnóstico implícito).<br><br>"
            f"Dentre o total, {_bh_red(n_sem_cid)} <b>ainda não têm CID "
            f"registrado</b> — primeira lacuna a fechar para que esses "
            f"pacientes apareçam nos relatórios oficiais."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a1d:
        c1, c2 = st.columns(2)
        _kpi(c1, "🩺 Hipertensos na equipe",
             f"{n_has_total:,}", f"{pct_eq_has:.0f}% da equipe")
        _kpi(c2, "⚠️ HAS sem CID",
             f"{n_sem_cid:,}", _pct_hn(n_sem_cid))
        c3, c4 = st.columns(2)
        _kpi(c3, "📋 Por CID registrado",
             f"{n_por_cid:,}", _pct_hn(n_por_cid))
        _kpi(c4, "📏 Por medida crítica (≥180/110)",
             f"{n_por_critica:,}", _pct_hn(n_por_critica))
        c5, c6 = st.columns(2)
        _kpi(c5, "📏 Por medidas repetidas (≥140/90)",
             f"{n_por_repetidas:,}", _pct_hn(n_por_repetidas))
        _kpi(c6, "💊 Por uso de anti-hipertensivo",
             f"{n_por_med:,}", _pct_hn(n_por_med))

    # ───────── ATO 2 — CONTROLE PRESSÓRICO ─────────
    st.markdown("---")
    st.markdown("##### 2. Controle pressórico")
    a2e, a2d = st.columns([1, 1.1])
    with a2e:
        media_pa_str = (f"{int(media_pas)}/{int(media_pad)} mmHg"
                        if media_pas and media_pad else "—")
        media_pct_str = (f"{float(media_pct_c):.0f}%"
                         if media_pct_c is not None else "—")
        pct_m80  = (n_ctrl_m80 / n_menor80 * 100) if n_menor80 else 0
        pct_80   = (n_ctrl_80  / n_80mais * 100)  if n_80mais  else 0
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Dos {_bh(n_has_total)} hipertensos, {_bh_green(n_ctrl_h)} "
            f"estão <b>controlados</b> (PA dentro da meta), "
            f"{_bh_red(n_desc_h)} <b>não-controlados</b> e "
            f"{_bh_orange(n_sem_info)} sem informação suficiente.<br><br>"
            f"<b>Por faixa etária:</b><br>"
            f"• Menores de 80a (meta &lt;140/90): {_bh_green(n_ctrl_m80)} "
            f"controlados de {_bh(n_menor80)} ({_bh(f'{pct_m80:.0f}%')});<br>"
            f"• 80a ou mais (meta &lt;150/90): {_bh_green(n_ctrl_80)} "
            f"controlados de {_bh(n_80mais)} ({_bh(f'{pct_80:.0f}%')}).<br><br>"
            f"<b>Recência da última aferição:</b> {_bh_green(n_pa_90d)} "
            f"≤90 dias, {_bh(n_pa_180)} entre 91–180d, "
            f"{_bh_orange(n_pa_365)} entre 181–365d, "
            f"{_bh_red(n_pa_old)} <b>há mais de 365 dias ou nunca</b>.<br><br>"
            f"<b>Tendência de controle da AP:</b> 📈 "
            f"{_bh_green(n_melh)} estão melhorando, ➡️ {_bh(n_est_h)} "
            f"estão estáveis, 📉 {_bh_red(n_pio_h)} estão piorando.<br><br>"
            f"O <b>valor médio de PA da equipe</b> é {_bh(media_pa_str)} "
            f"e seus pacientes têm passado, em média, "
            f"{_bh(media_pct_str)} dos dias do ano com a PA dentro dos "
            f"valores desejados."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a2d:
        c1, c2 = st.columns(2)
        _kpi(c1, "✅ PA controlada",
             f"{n_ctrl_h:,}", _pct_hn(n_ctrl_h))
        _kpi(c2, "❌ PA descontrolada",
             f"{n_desc_h:,}", _pct_hn(n_desc_h))
        c3, c4 = st.columns(2)
        _kpi(c3, "🧑 Controlados <80a",
             f"{n_ctrl_m80:,}/{n_menor80:,}",
             f"{(n_ctrl_m80/n_menor80*100 if n_menor80 else 0):.0f}% da faixa")
        _kpi(c4, "👴 Controlados ≥80a",
             f"{n_ctrl_80:,}/{n_80mais:,}",
             f"{(n_ctrl_80/n_80mais*100 if n_80mais else 0):.0f}% da faixa")
        c5, c6 = st.columns(2)
        _kpi(c5, "🟢 PA aferida ≤90d",
             f"{n_pa_90d:,}", _pct_hn(n_pa_90d))
        _kpi(c6, "🔴 PA >365d ou nunca",
             f"{n_pa_old:,}", _pct_hn(n_pa_old))
        c7, c8 = st.columns(2)
        _kpi(c7, "📈 Melhorando",
             f"{n_melh:,}", _pct_hn(n_melh))
        _kpi(c8, "📉 Piorando",
             f"{n_pio_h:,}", _pct_hn(n_pio_h))
        c9, _c10 = st.columns(2)
        _kpi(c9, "PAS / PAD média",
             f"{int(media_pas)}/{int(media_pad)}"
             if media_pas and media_pad else "—",
             f"{float(media_pct_c):.0f}% dias controlado (365d)"
             if media_pct_c is not None else None)

    # ───────── ATO 2.5 — RESPOSTA AO DESCONTROLE (INÉRCIA / ESTAGNADO) ─
    st.markdown("---")
    st.markdown("##### 2.5 Resposta ao descontrole — "
                "inércia e tratamento estagnado")
    st.caption(
        "Como o esquema terapêutico tem respondido ao controle "
        "pressórico, ao longo do último ano. Denominador são os "
        "hipertensos em tratamento ativo (≥1 prescrição em 365 "
        "dias); pacientes sem prescrição recente aparecem como "
        "categoria à parte."
    )
    with st.spinner("Carregando indicadores de inércia (HAS)..."):
        ag_in_has = carregar_inercia_agregado(ap_sel, cli_sel, esf_sel)
        bm_inercia = carregar_inercia_benchmarks(ap_sel)
    _render_ato_inercia('HAS', ag_in_has, bm_inercia, n_has_total)

    # ───────── ATO 3 — LACUNAS DE CUIDADO ─────────
    st.markdown("---")
    st.markdown("##### 3. Lacunas de cuidado")
    a3e, a3d = st.columns([1, 1.1])
    with a3e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Quanto às ações de cuidado e exames de rotina nos "
            f"{_bh(n_has_total)} hipertensos:<br><br>"
            f"• {_bh_red(n_sem_pa180)} <b>sem aferição de PA</b> nos "
            f"últimos 180 dias;<br>"
            f"• {_bh_red(n_dm_has_pa)} com <b>DM+HAS e PA &gt;135/80</b> "
            f"(meta restrita não atingida);<br>"
            f"• {_bh_red(n_sem_creat)} <b>sem creatinina</b>;<br>"
            f"• {_bh_red(n_sem_col)} <b>sem colesterol</b>;<br>"
            f"• {_bh_red(n_sem_eas)} <b>sem EAS</b>;<br>"
            f"• {_bh_red(n_sem_ecg)} <b>sem ECG</b>;<br>"
            f"• {_bh_red(n_sem_imc)} <b>sem IMC calculável</b> "
            f"(está faltando aferição de peso e/ou altura para "
            f"calcularmos o IMC)."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a3d:
        c1, c2 = st.columns(2)
        _kpi(c1, "📉 Sem aferição PA >180d",
             f"{n_sem_pa180:,}", _pct_hn(n_sem_pa180))
        _kpi(c2, "🩸 DM+HAS com PA >135/80",
             f"{n_dm_has_pa:,}", _pct_hn(n_dm_has_pa))
        c3, c4 = st.columns(2)
        _kpi(c3, "🧪 Sem creatinina (365d)",
             f"{n_sem_creat:,}", _pct_hn(n_sem_creat))
        _kpi(c4, "🧪 Sem colesterol (365d)",
             f"{n_sem_col:,}", _pct_hn(n_sem_col))
        c5, c6 = st.columns(2)
        _kpi(c5, "💉 Sem EAS (365d)",
             f"{n_sem_eas:,}", _pct_hn(n_sem_eas))
        _kpi(c6, "🫀 Sem ECG (365d)",
             f"{n_sem_ecg:,}", _pct_hn(n_sem_ecg))
        c7, _c8 = st.columns(2)
        _kpi(c7, "⚖️ Sem IMC calculável",
             f"{n_sem_imc:,}", _pct_hn(n_sem_imc))

    # ───────── ATO 4 — TRATAMENTO E SEGURANÇA FARMACOLÓGICA ─────────
    st.markdown("---")
    st.markdown("##### 4. Tratamento e segurança farmacológica")
    a4e, a4d = st.columns([1, 1.1])
    with a4e:
        n_em_trat = n_mono + n_dupla + n_tripla + n_quad
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Dos {_bh(n_has_total)} hipertensos, {_bh(n_em_trat)} "
            f"estão em <b>tratamento medicamentoso</b> "
            f"({_bh(n_sem_med)} sem nenhum anti-hipertensivo "
            f"prescrito).<br><br>"
            f"<b>Intensidade do tratamento:</b><br>"
            f"• {_bh(n_mono)} em <b>monoterapia</b>;<br>"
            f"• {_bh(n_dupla)} em <b>dupla terapia</b>;<br>"
            f"• {_bh(n_tripla)} em <b>tripla terapia</b>;<br>"
            f"• {_bh(n_quad)} em <b>quádrupla ou mais</b>.<br><br>"
            f"<b>Classes mais usadas:</b> "
            f"{_bh(n_ieca)} IECA · {_bh(n_bra)} BRA · "
            f"{_bh(n_bcc_dhp)} BCC di-hidro · "
            f"{_bh(n_tiazid)} tiazídico · "
            f"{_bh(n_betabloq)} betabloqueador · "
            f"{_bh(n_diur_alca)} diurético de alça · "
            f"{_bh(n_poup_k)} poupador de K · "
            f"{_bh(n_nitrato)} nitrato.<br><br>"
            f"<b>🚨 Alertas farmacológicos:</b><br>"
            f"• {_bh_red(n_ieca_bra)} com <b>IECA + BRA simultâneos</b> "
            f"(duplo bloqueio do SRAA, contraindicado pelas diretrizes);<br>"
            f"• {_bh_orange(n_alca_sem_icc)} com <b>diurético de alça "
            f"sem CID de ICC</b> (uso questionável fora de ICC ou "
            f"IRC avançada);<br>"
            f"• {_bh_orange(n_nit_sem_ci)} com <b>nitrato sem CID de "
            f"CI</b> (avaliar indicação);<br>"
            f"• {_bh_green(n_alca_icc)} com diurético de alça <b>e</b> "
            f"ICC (uso esperado);<br>"
            f"• {_bh_green(n_poup_k_icc)} com poupador de K <b>e</b> "
            f"ICC (uso esperado);<br>"
            f"• {_bh_green(n_nit_ci)} com nitrato <b>e</b> CI (uso "
            f"esperado)."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a4d:
        # Intensidade do tratamento (4 cards)
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-bottom:6px;'><b>Intensidade do tratamento</b></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        _kpi(c1, "💊 Monoterapia",
             f"{n_mono:,}", _pct_hn(n_mono))
        _kpi(c2, "💊💊 Dupla terapia",
             f"{n_dupla:,}", _pct_hn(n_dupla))
        c3, c4 = st.columns(2)
        _kpi(c3, "💊💊💊 Tripla terapia",
             f"{n_tripla:,}", _pct_hn(n_tripla))
        _kpi(c4, "💊⁴⁺ Quádrupla ou mais",
             f"{n_quad:,}", _pct_hn(n_quad))
        # Alertas farmacológicos críticos
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-top:10px; margin-bottom:6px;'>"
            f"<b>🚨 Alertas farmacológicos</b></div>",
            unsafe_allow_html=True,
        )
        c5, c6 = st.columns(2)
        _kpi(c5, "🚨 IECA + BRA simultâneos",
             f"{n_ieca_bra:,}", _pct_hn(n_ieca_bra))
        _kpi(c6, "⚠️ Diur. de alça sem CID de ICC",
             f"{n_alca_sem_icc:,}", _pct_hn(n_alca_sem_icc))
        c7, c8 = st.columns(2)
        _kpi(c7, "⚠️ Nitrato sem CID de CI",
             f"{n_nit_sem_ci:,}", _pct_hn(n_nit_sem_ci))
        _kpi(c8, "✅ Diur. de alça com ICC",
             f"{n_alca_icc:,}", _pct_hn(n_alca_icc))
        # Classes mais usadas (3 cards por linha)
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-top:10px; margin-bottom:6px;'>"
            f"<b>Classes prescritas</b> (paciente pode receber mais "
            f"de uma)</div>",
            unsafe_allow_html=True,
        )
        c9, c10, c11 = st.columns(3)
        _kpi(c9,  "IECA",            f"{n_ieca:,}",      _pct_hn(n_ieca))
        _kpi(c10, "BRA",             f"{n_bra:,}",       _pct_hn(n_bra))
        _kpi(c11, "BCC di-hidro",    f"{n_bcc_dhp:,}",   _pct_hn(n_bcc_dhp))
        c12, c13, c14 = st.columns(3)
        _kpi(c12, "BCC não di-hidro",f"{n_bcc_ndhp:,}",  _pct_hn(n_bcc_ndhp))
        _kpi(c13, "Tiazídico",       f"{n_tiazid:,}",    _pct_hn(n_tiazid))
        _kpi(c14, "Betabloqueador",  f"{n_betabloq:,}",  _pct_hn(n_betabloq))
        c15, c16, c17 = st.columns(3)
        _kpi(c15, "Diur. de alça",   f"{n_diur_alca:,}", _pct_hn(n_diur_alca))
        _kpi(c16, "Poupador de K",   f"{n_poup_k:,}",    _pct_hn(n_poup_k))
        _kpi(c17, "Nitrato",         f"{n_nitrato:,}",   _pct_hn(n_nitrato))
        c18, c19, c20 = st.columns(3)
        _kpi(c18, "Simpatolítico",   f"{n_simpat:,}",    _pct_hn(n_simpat))
        _kpi(c19, "Alfabloqueador",  f"{n_alfablo:,}",   _pct_hn(n_alfablo))
        _kpi(c20, "Vasodilatador",   f"{n_vasod:,}",     _pct_hn(n_vasod))

    # ───────── ATO 5 — COMORBIDADES E RISCO CV ─────────
    st.markdown("---")
    st.markdown("##### 5. Comorbidades associadas e risco cardiovascular")
    a5e, a5d = st.columns([1, 1.1])
    with a5e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Sobreposição entre HAS e outras condições "
            f"cardiometabólicas nos {_bh(n_has_total)} hipertensos:"
            f"<br><br>"
            f"• 🍬 {_bh(n_has_dm)} com <b>DM</b> "
            f"(meta PA &lt;130/80, IECA/BRA como 1ª linha);<br>"
            f"• 🫘 {_bh(n_has_irc)} com <b>IRC</b> "
            f"(IECA/BRA + SGLT-2 para nefroproteção);<br>"
            f"• 💔 {_bh(n_has_ci)} com <b>CI</b> "
            f"(estatina alta intensidade + AAS);<br>"
            f"• 🫀 {_bh(n_has_icc)} com <b>ICC</b> "
            f"(IECA/BRA/INRA + BB + ARM + SGLT-2);<br>"
            f"• 🧠 {_bh(n_has_avc)} com <b>AVC prévio</b> "
            f"(controle rigoroso de PA reduz reincidência).<br><br>"
            f"<b>Risco Cardiovascular (HEARTS / OMS / OPAS):</b><br>"
            f"🚨 {_bh_red(n_who_crit)} crítico (≥30%) · "
            f"🔴 {_bh_red(n_who_ma)} muito alto (20–30%) · "
            f"🟠 {_bh_orange(n_who_a)} alto (10–20%) · "
            f"🟡 {_bh(n_who_mod)} moderado (5–10%) · "
            f"🟢 {_bh_green(n_who_b)} baixo (&lt;5%)."
            + (f"<br><span style='color:#777777;'>"
               f"({_bh(n_who_nc)} sem variáveis suficientes para "
               f"calcular o risco — modelos lab e non-lab não "
               f"calculáveis)</span>" if n_who_nc > 0 else "")
            + f"</div>",
            unsafe_allow_html=True,
        )
    with a5d:
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-bottom:6px;'><b>Comorbidades associadas</b></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        _kpi(c1, "🍬 HAS + DM",  f"{n_has_dm:,}",  _pct_hn(n_has_dm))
        _kpi(c2, "🫘 HAS + IRC", f"{n_has_irc:,}", _pct_hn(n_has_irc))
        _kpi(c3, "💔 HAS + CI",  f"{n_has_ci:,}",  _pct_hn(n_has_ci))
        c4, c5, _c6 = st.columns(3)
        _kpi(c4, "🫀 HAS + ICC", f"{n_has_icc:,}", _pct_hn(n_has_icc))
        _kpi(c5, "🧠 HAS + AVC", f"{n_has_avc:,}", _pct_hn(n_has_avc))
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-top:10px; margin-bottom:6px;'>"
            f"<b>Risco Cardiovascular</b> (HEARTS / OMS / OPAS)</div>",
            unsafe_allow_html=True,
        )
        c7, c8, c9 = st.columns(3)
        _kpi(c7,  "🚨 Crítico (≥30%)",       f"{n_who_crit:,}", _pct_hn(n_who_crit))
        _kpi(c8,  "🔴 Muito alto (20–30%)",  f"{n_who_ma:,}",   _pct_hn(n_who_ma))
        _kpi(c9,  "🟠 Alto (10–20%)",        f"{n_who_a:,}",    _pct_hn(n_who_a))
        c10, c11, c12 = st.columns(3)
        _kpi(c10, "🟡 Moderado (5–10%)",     f"{n_who_mod:,}",  _pct_hn(n_who_mod))
        _kpi(c11, "🟢 Baixo (<5%)",          f"{n_who_b:,}",    _pct_hn(n_who_b))
        _kpi(c12, "❔ Sem variáveis p/ calcular",
             f"{n_who_nc:,}", _pct_hn(n_who_nc))

    # ───────── ATO 6 — COMPLEXIDADE CLÍNICA E FARMACOLÓGICA ─────────
    n_chb     = _vh('n_charl_baixo')
    n_chm     = _vh('n_charl_moderado')
    n_cha     = _vh('n_charl_alto')
    n_chma    = _vh('n_charl_muito_alto')
    n_multi   = _vh('n_multimorb')
    n_poli    = _vh('n_polifarm')
    n_hpoli   = _vh('n_hiperpoli')
    n_acb     = _vh('n_acb_alto')

    st.markdown("---")
    st.markdown("##### 6. Complexidade clínica e farmacológica")
    a6e, a6d = st.columns([1, 1.1])
    with a6e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Olhando para a <b>complexidade clínica</b> dos "
            f"{_bh(n_has_total)} hipertensos pela Carga de Morbidade:"
            f"<br>"
            f"• 🟢 {_bh_green(n_chb)} têm <b>carga baixa</b>;<br>"
            f"• 🟡 {_bh(n_chm)} têm <b>carga moderada</b>;<br>"
            f"• 🟠 {_bh_orange(n_cha)} têm <b>carga alta</b>;<br>"
            f"• 🔴 {_bh_red(n_chma)} têm <b>carga muito alta</b>.<br><br>"
            f"{_bh_orange(n_multi)} são <b>multimórbidos</b> "
            f"(≥2 morbidades crônicas) — pacientes que precisam de "
            f"abordagem coordenada e priorização clínica.<br><br>"
            f"<b>Carga farmacológica:</b><br>"
            f"• 💊 {_bh_orange(n_poli)} em <b>polifarmácia</b> "
            f"(≥5 medicamentos crônicos);<br>"
            f"• 💊💊 {_bh_red(n_hpoli)} em <b>hiperpolifarmácia</b> "
            f"(≥10 medicamentos crônicos);<br>"
            f"• 🧠 {_bh_red(n_acb)} com <b>alta carga "
            f"anticolinérgica</b> (ACB ≥3) — fator de risco "
            f"importante para queda, declínio cognitivo e delírio, "
            f"sobretudo em idosos."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a6d:
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-bottom:6px;'><b>Carga de Morbidade</b></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        _kpi(c1, "🟢 Baixa",       f"{n_chb:,}",  _pct_hn(n_chb))
        _kpi(c2, "🟡 Moderada",    f"{n_chm:,}",  _pct_hn(n_chm))
        _kpi(c3, "🟠 Alta",        f"{n_cha:,}",  _pct_hn(n_cha))
        _kpi(c4, "🔴 Muito alta",  f"{n_chma:,}", _pct_hn(n_chma))
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-top:10px; margin-bottom:6px;'>"
            f"<b>Multimorbidade e carga farmacológica</b></div>",
            unsafe_allow_html=True,
        )
        c5, c6 = st.columns(2)
        _kpi(c5, "🧬 Multimórbidos (≥2 morbidades)",
             f"{n_multi:,}", _pct_hn(n_multi))
        _kpi(c6, "💊 Polifarmácia (≥5 meds)",
             f"{n_poli:,}", _pct_hn(n_poli))
        c7, c8 = st.columns(2)
        _kpi(c7, "💊💊 Hiperpolifarmácia (≥10 meds)",
             f"{n_hpoli:,}", _pct_hn(n_hpoli))
        _kpi(c8, "🧠 Alta carga anticolinérgica (ACB ≥3)",
             f"{n_acb:,}", _pct_hn(n_acb))

    # ─── Lista nominal removida — usuário deve usar a aba "Meus Pacientes" ───
    st.markdown("---")
    st.info(
        "🧑‍⚕️ **Para abrir os pacientes individualmente**, vá para a "
        "aba **Meus Pacientes**. Lá é possível filtrar a lista "
        "nominal por **HAS**, por **Carga de Morbidade** e por "
        "**lacunas específicas** (sem PA recente, descontrolados, "
        "sem creatinina, sem ECG, IECA + BRA simultâneos etc.) "
        "e abrir o card completo de cada paciente."
    )


# ─────────────────────────────────────────────────────────────
# ABA 5 — DIABETES MELLITUS (DM)
# Mesma base de dados da aba "🩸 Diabetes", apresentada como história
# em 5 atos. Layout em 2 colunas: à esquerda o texto narrativo, à
# direita os cards (versão antiga). Mantém a tabela nominal embaixo.
# ─────────────────────────────────────────────────────────────
with tab_dm:
    st.markdown("#### Diabetes mellitus — narrativa da equipe")
    st.caption(
        "Mesma base da aba 🩸 Diabetes, contada como história em "
        "5 atos. À esquerda, o texto que conduz a leitura; à direita, "
        "os cards numéricos. Status do controle glicêmico considera "
        "HbA1c recente vs meta etária (<60a → 7,0%; 60–69a → 7,5%; "
        "≥70a → 8,0%)."
    )

    with st.spinner("Carregando indicadores de DM..."):
        ag_dn = carregar_diabetes_agregado(ap_sel, cli_sel, esf_sel)

    n_dm_n = int(ag_dn.get('n_dm', 0) or 0) or 1
    n_total_eq_n = int(ag_dn.get('n_total', 0) or 0) or 1

    def _val(k):
        return int(ag_dn.get(k, 0) or 0)

    def _pct_dn(num):
        return f"{int(num or 0)/n_dm_n*100:.0f}%"

    # Helpers de destaque inline na narrativa
    def _b(v):       return f"<b>{v}</b>"
    def _bred(v):    return f"<span style='color:#B71C1C; font-weight:700;'>{v}</span>"
    def _bgreen(v):  return f"<span style='color:#198754; font-weight:700;'>{v}</span>"
    def _borange(v): return f"<span style='color:#E69138; font-weight:700;'>{v}</span>"

    n_dm_total = _val('n_dm')
    n_pre      = _val('n_pre_dm')
    n_carga    = n_dm_total + n_pre
    n_sem_cid  = _val('n_sem_cid')
    pct_eq_dm    = (n_dm_total / n_total_eq_n * 100) if n_total_eq_n else 0
    pct_eq_carga = (n_carga    / n_total_eq_n * 100) if n_total_eq_n else 0

    n_ctrl     = _val('n_ctrl')
    n_desc     = _val('n_lac_desc')
    n_sem180   = _val('n_sem_a1c_180d')
    n_nunca    = _val('n_nunca_a1c')
    media_a1c  = ag_dn.get('media_a1c')

    n_sem_pe    = _val('n_sem_pe')
    n_sem_micro = _val('n_sem_micro')
    n_sem_creat = _val('n_sem_creat')
    n_sem_col   = _val('n_sem_col')

    n_insulina  = _val('n_em_insulina')
    n_nph_alta  = _val('n_nph_alta')
    n_metf_alta = _val('n_metf_total_alta')
    n_metf_xr   = _val('n_metf_xr_alta')
    n_sulfo     = _val('n_sulfo_mono')
    n_sglt2     = _val('n_complic_sem_sglt2')

    n_retino = _val('n_dm_retino')
    n_pe_cid = _val('n_dm_pe')
    n_neuro  = _val('n_dm_neuro')
    n_nefro  = _val('n_dm_nefro')
    n_cv     = _val('n_dm_complic_cv')

    # ───────── ATO 1 — POPULAÇÃO EM FOCO ─────────
    st.markdown("---")
    st.markdown("##### 1. Como foram identificados os diabéticos da equipe?")
    a1e, a1d = st.columns([1, 1.1])
    with a1e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Sua equipe tem {_b(n_dm_total)} <b>diabéticos</b> "
            f"({_b(f'{pct_eq_dm:.0f}%')} da população cadastrada) "
            f"e mais {_b(n_pre)} <b>pré-diabéticos</b> — uma <b>carga "
            f"total de {_b(n_carga)} pessoas</b> "
            f"({_b(f'{pct_eq_carga:.0f}%')} da equipe).<br><br>"
            f"Destes {_b(n_dm_total)} diabéticos, {_bred(n_sem_cid)} "
            f"<b>ainda não têm CID registrado</b>. Essa é a primeira "
            f"lacuna a fechar — sem CID o paciente não é capturado "
            f"pelos relatórios oficiais nem pelas buscas por morbidade."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a1d:
        c1, c2 = st.columns(2)
        _kpi(c1, "🩸 Diabéticos na equipe",
             f"{n_dm_total:,}", f"{pct_eq_dm:.0f}% da equipe")
        _kpi(c2, "🟡 Pré-diabéticos",
             f"{n_pre:,}",
             f"{(n_pre/n_total_eq_n*100):.0f}% da equipe")
        c3, c4 = st.columns(2)
        _kpi(c3, "📈 Pré-DM + DM (carga total)",
             f"{n_carga:,}", f"{pct_eq_carga:.0f}% da equipe")
        _kpi(c4, "⚠️ DM sem CID",
             f"{n_sem_cid:,}", _pct_dn(n_sem_cid))

    # ───────── ATO 2 — CONTROLE GLICÊMICO ─────────
    st.markdown("---")
    st.markdown("##### 2. Controle glicêmico")
    a2e, a2d = st.columns([1, 1.1])
    with a2e:
        media_str = (f"{float(media_a1c):.1f}%"
                     if media_a1c is not None else "—")
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Dos {_b(n_dm_total)} diabéticos, apenas "
            f"{_bgreen(n_ctrl)} estão <b>dentro da meta com HbA1c "
            f"recente</b> (≤180 dias). Outros {_bred(n_desc)} estão "
            f"<b>acima da meta</b> com exame recente.<br><br>"
            f"O grande grupo silencioso: {_bred(n_sem180)} "
            f"<b>não fizeram HbA1c nos últimos 180 dias</b> — e "
            f"destes, {_bred(n_nunca)} <b>nunca fizeram</b> "
            f"o exame em nosso banco de dados.<br><br>"
            f"A <b>HbA1c média da equipe</b> está em {_b(media_str)}."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a2d:
        c1, c2 = st.columns(2)
        _kpi(c1, "✅ Glicemia controlada (HbA1c <180d e na meta)",
             f"{n_ctrl:,}", _pct_dn(n_ctrl))
        _kpi(c2, "❌ HbA1c acima da meta",
             f"{n_desc:,}", _pct_dn(n_desc))
        c3, c4 = st.columns(2)
        _kpi(c3, "📉 Sem HbA1c (>180d)",
             f"{n_sem180:,}", _pct_dn(n_sem180))
        _kpi(c4, "🚫 Nunca fez HbA1c",
             f"{n_nunca:,}", _pct_dn(n_nunca))
        c5, _c6 = st.columns(2)
        _kpi(c5, "HbA1c média",
             f"{float(media_a1c):.1f}%" if media_a1c else "—")

    # ───────── ATO 2.5 — RESPOSTA AO DESCONTROLE (INÉRCIA / ESTAGNADO) ─
    st.markdown("---")
    st.markdown("##### 2.5 Resposta ao descontrole — "
                "inércia e tratamento estagnado")
    st.caption(
        "Como o esquema terapêutico tem respondido ao controle "
        "glicêmico, ao longo do último ano. Denominador são os "
        "diabéticos em tratamento ativo (≥1 prescrição em 365 "
        "dias); pacientes sem prescrição recente aparecem como "
        "categoria à parte. No diabetes o problema dominante "
        "costuma ser a estagnação, não a inércia médica."
    )
    with st.spinner("Carregando indicadores de inércia (DM)..."):
        ag_in_dm = carregar_inercia_agregado(ap_sel, cli_sel, esf_sel)
        bm_inercia_dm = carregar_inercia_benchmarks(ap_sel)
    _render_ato_inercia('DM', ag_in_dm, bm_inercia_dm, n_dm_total)

    # ───────── ATO 3 — LACUNAS DE EXAMES DE ROTINA ─────────
    st.markdown("---")
    st.markdown("##### 3. Lacunas de exames de rotina")
    a3e, a3d = st.columns([1, 1.1])
    with a3e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Quanto às ações de cuidado anuais junto aos "
            f"{_b(n_dm_total)} diabéticos:<br><br>"
            f"• {_bred(n_sem_pe)} <b>sem exame do pé</b> nos últimos "
            f"365 dias;<br>"
            f"• {_bred(n_sem_micro)} <b>sem microalbuminúria</b> "
            f"solicitada;<br>"
            f"• {_bred(n_sem_creat)} <b>sem creatinina</b>;<br>"
            f"• {_bred(n_sem_col)} <b>sem colesterol</b>.<br><br>"
            f"São lacunas de rastreio acionáveis em consulta — não "
            f"exigem decisão complexa, só lembrete e solicitação."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a3d:
        c1, c2 = st.columns(2)
        _kpi(c1, "🦶 Sem exame do pé (365d)",
             f"{n_sem_pe:,}", _pct_dn(n_sem_pe))
        _kpi(c2, "🧪 Sem microalbuminúria",
             f"{n_sem_micro:,}", _pct_dn(n_sem_micro))
        c3, c4 = st.columns(2)
        _kpi(c3, "🧪 Sem creatinina",
             f"{n_sem_creat:,}", _pct_dn(n_sem_creat))
        _kpi(c4, "🧪 Sem colesterol",
             f"{n_sem_col:,}", _pct_dn(n_sem_col))

    # ───────── ATO 4 — TRATAMENTO E SEGURANÇA ─────────
    st.markdown("---")
    st.markdown("##### 4. Tratamento e segurança farmacológica")
    a4e, a4d = st.columns([1, 1.1])
    with a4e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Quanto ao tratamento, {_b(n_insulina)} dos "
            f"{_b(n_dm_total)} diabéticos estão em <b>uso de algum "
            f"tipo de insulina</b>.<br><br>"
            f"Alertas farmacológicos a revisar:<br>"
            f"• {_borange(n_nph_alta)} com <b>NPH > 0,85 UI/kg</b> "
            f"(dose alta — sugere resistência ou erro de digitação);<br>"
            f"• {_borange(n_metf_alta)} com <b>Metformina total > "
            f"2.550 mg/dia</b>;<br>"
            f"• {_borange(n_metf_xr)} com <b>Metformina XR > "
            f"2.000 mg/dia</b>;<br>"
            f"• {_borange(n_sulfo)} em <b>sulfonilureia em "
            f"monoterapia</b> (perfil pouco favorável a longo prazo);<br>"
            f"• {_borange(n_sglt2)} com <b>DM complicado sem SGLT-2</b> "
            f"(oportunidade de proteção cardiorrenal)."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a4d:
        c1, c2 = st.columns(2)
        _kpi(c1, "💉 Em uso de insulina (qualquer tipo)",
             f"{n_insulina:,}", _pct_dn(n_insulina))
        _kpi(c2, "🚨 NPH > 0,85 UI/kg",
             f"{n_nph_alta:,}", _pct_dn(n_nph_alta))
        c3, c4 = st.columns(2)
        _kpi(c3, "🚨 Metformina (regular+XR) > 2.550 mg/dia",
             f"{n_metf_alta:,}", _pct_dn(n_metf_alta))
        _kpi(c4, "🚨 Metformina XR > 2.000 mg/dia",
             f"{n_metf_xr:,}", _pct_dn(n_metf_xr))
        c5, c6 = st.columns(2)
        _kpi(c5, "⚠️ Sulfonilureia em monoterapia",
             f"{n_sulfo:,}", _pct_dn(n_sulfo))
        _kpi(c6, "💊 DM complicado sem SGLT-2",
             f"{n_sglt2:,}", _pct_dn(n_sglt2))

    # ───────── ATO 5 — COMPLICAÇÕES JÁ DETECTADAS ─────────
    st.markdown("---")
    st.markdown("##### 5. Complicações do diabetes já detectadas")
    a5e, a5d = st.columns([1, 1.1])
    with a5e:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Pacientes com complicação <b>já registrada</b> em CID:"
            f"<br><br>"
            f"• {_bred(n_retino)} com <b>retinopatia diabética</b>;<br>"
            f"• {_bred(n_pe_cid)} com <b>pé diabético</b>;<br>"
            f"• {_bred(n_neuro)} com <b>neuropatia diabética</b>;<br>"
            f"• {_bred(n_nefro)} com <b>nefropatia diabética</b>;<br>"
            f"• {_bred(n_cv)} com <b>complicação cardiovascular do "
            f"DM</b>.<br><br>"
            f"Lembrar que <b>complicação ausente</b> no banco pode "
            f"significar <b>complicação não rastreada</b> — daí a "
            f"importância das lacunas do Ato 3."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a5d:
        c1, c2, c3 = st.columns(3)
        _kpi(c1, "👁️ Retinopatia",
             f"{n_retino:,}", _pct_dn(n_retino))
        _kpi(c2, "🦶 Pé diabético (CID)",
             f"{n_pe_cid:,}", _pct_dn(n_pe_cid))
        _kpi(c3, "🧠 Neuropatia",
             f"{n_neuro:,}", _pct_dn(n_neuro))
        c4, c5, _c6 = st.columns(3)
        _kpi(c4, "🫘 Nefropatia",
             f"{n_nefro:,}", _pct_dn(n_nefro))
        _kpi(c5, "❤️ Complicação CV do DM",
             f"{n_cv:,}", _pct_dn(n_cv))

    # ───────── ATO 6 — COMPLEXIDADE CLÍNICA E FARMACOLÓGICA ─────────
    n_chb_d   = _val('n_charl_baixo')
    n_chm_d   = _val('n_charl_moderado')
    n_cha_d   = _val('n_charl_alto')
    n_chma_d  = _val('n_charl_muito_alto')
    n_multi_d = _val('n_multimorb')
    n_poli_d  = _val('n_polifarm')
    n_hpoli_d = _val('n_hiperpoli')
    n_acb_d   = _val('n_acb_alto')

    st.markdown("---")
    st.markdown("##### 6. Complexidade clínica e farmacológica")
    a6e_d, a6d_d = st.columns([1, 1.1])
    with a6e_d:
        st.markdown(
            f"<div style='font-size:1.0em; line-height:1.65;'>"
            f"Olhando para a <b>complexidade clínica</b> dos "
            f"{_b(n_dm_total)} diabéticos pela Carga de Morbidade:<br>"
            f"• 🟢 {_bgreen(n_chb_d)} têm <b>carga baixa</b>;<br>"
            f"• 🟡 {_b(n_chm_d)} têm <b>carga moderada</b>;<br>"
            f"• 🟠 {_borange(n_cha_d)} têm <b>carga alta</b>;<br>"
            f"• 🔴 {_bred(n_chma_d)} têm <b>carga muito alta</b>.<br><br>"
            f"{_borange(n_multi_d)} são <b>multimórbidos</b> "
            f"(≥2 morbidades crônicas) — pacientes que precisam de "
            f"abordagem coordenada e priorização clínica.<br><br>"
            f"<b>Carga farmacológica:</b><br>"
            f"• 💊 {_borange(n_poli_d)} em <b>polifarmácia</b> "
            f"(≥5 medicamentos crônicos);<br>"
            f"• 💊💊 {_bred(n_hpoli_d)} em <b>hiperpolifarmácia</b> "
            f"(≥10 medicamentos crônicos);<br>"
            f"• 🧠 {_bred(n_acb_d)} com <b>alta carga "
            f"anticolinérgica</b> (ACB ≥3) — fator de risco "
            f"importante para queda, declínio cognitivo e delírio, "
            f"sobretudo em idosos."
            f"</div>",
            unsafe_allow_html=True,
        )
    with a6d_d:
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-bottom:6px;'><b>Carga de Morbidade</b></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        _kpi(c1, "🟢 Baixa",       f"{n_chb_d:,}",  _pct_dn(n_chb_d))
        _kpi(c2, "🟡 Moderada",    f"{n_chm_d:,}",  _pct_dn(n_chm_d))
        _kpi(c3, "🟠 Alta",        f"{n_cha_d:,}",  _pct_dn(n_cha_d))
        _kpi(c4, "🔴 Muito alta",  f"{n_chma_d:,}", _pct_dn(n_chma_d))
        st.markdown(
            f"<div style='font-size:0.85em; color:#555555; "
            f"margin-top:10px; margin-bottom:6px;'>"
            f"<b>Multimorbidade e carga farmacológica</b></div>",
            unsafe_allow_html=True,
        )
        c5, c6 = st.columns(2)
        _kpi(c5, "🧬 Multimórbidos (≥2 morbidades)",
             f"{n_multi_d:,}", _pct_dn(n_multi_d))
        _kpi(c6, "💊 Polifarmácia (≥5 meds)",
             f"{n_poli_d:,}", _pct_dn(n_poli_d))
        c7, c8 = st.columns(2)
        _kpi(c7, "💊💊 Hiperpolifarmácia (≥10 meds)",
             f"{n_hpoli_d:,}", _pct_dn(n_hpoli_d))
        _kpi(c8, "🧠 Alta carga anticolinérgica (ACB ≥3)",
             f"{n_acb_d:,}", _pct_dn(n_acb_d))

    # ─── Lista nominal removida — usuário deve usar a aba "Meus Pacientes" ───
    st.markdown("---")
    st.info(
        "🧑‍⚕️ **Para abrir os pacientes individualmente**, vá para a "
        "aba **Meus Pacientes**. Lá é possível filtrar a lista "
        "nominal por **DM**, por **Carga de Morbidade** e por "
        "**lacunas específicas** (descontrolados, sem HbA1c "
        "recente, sem exame do pé, ACB ≥ 3, NPH > 0,85 UI/kg, "
        "sulfonilureia em monoterapia etc.) e abrir o card "
        "completo de cada paciente."
    )


# ─────────────────────────────────────────────────────────────
# ABA 6 — LACUNAS DA EQUIPE × MUNICÍPIO
# ─────────────────────────────────────────────────────────────
with tab_lacunas:
    st.markdown(
        "#### Lacunas de cuidado — Equipe versus município"
    )
    st.caption(
        "Cada lacuna é calculada apenas sobre a população elegível "
        "(ex.: 'CI sem AAS' usa pacientes com CI como denominador). "
        "À esquerda, o racional clínico do grupo + as lacunas em "
        "destaque (piores ou melhores que o município). À direita, "
        "todas as lacunas do grupo: o fundo do card vai de verde "
        "(% baixa) a vermelho (% alta), a borda esquerda fica "
        "vermelha quando a equipe está acima do município, verde "
        "quando está abaixo, cinza quando próximo."
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

        # ───── Atos por grupo (ordem definida em _ORDEM_GRUPOS_LACUNAS) ─────
        for grupo in _ORDEM_GRUPOS_LACUNAS:
            df_g = df_lac[df_lac['grupo'] == grupo].copy()
            df_g = df_g[df_g['denominador'] > 0]
            if df_g.empty:
                continue
            df_g = df_g.sort_values('pct', ascending=False)

            st.markdown("---")
            st.markdown(f"##### {_LABEL_GRUPO_DISPLAY.get(grupo, grupo)}")

            e, d = st.columns([1, 1.3])
            with e:
                contexto = NARRATIVA_GRUPO_LACUNAS.get(grupo, "")
                df_pior = df_g.dropna(subset=['delta']).sort_values(
                    'delta', ascending=False)
                df_top_pior   = df_pior[df_pior['delta'] >  0.5].head(3)
                df_top_melhor = df_pior[df_pior['delta'] < -0.5].tail(3)

                html = (
                    f"<div style='line-height:1.6; font-size:0.95em;'>"
                    f"{contexto}</div>"
                )

                if not df_top_pior.empty:
                    html += (
                        "<div style='margin-top:14px;'>"
                        "<b style='color:#C0392B;'>⚠️ Onde sua equipe "
                        "está pior que o município:</b>"
                        "<ul style='margin:6px 0 0 0; padding-left:20px;'>"
                    )
                    for _, r in df_top_pior.iterrows():
                        html += (
                            f"<li style='margin-bottom:4px;'>"
                            f"<b>{r['lacuna']}</b> — "
                            f"<b style='color:#C0392B;'>"
                            f"{int(r['numerador'])}</b> "
                            f"({float(r['pct']):.0f}%) "
                            f"<span style='color:#C0392B;'>"
                            f"↑ +{float(r['delta']):.1f} pp</span>"
                            f"</li>"
                        )
                    html += "</ul></div>"

                if not df_top_melhor.empty:
                    html += (
                        "<div style='margin-top:10px;'>"
                        "<b style='color:#198754;'>✅ Onde sua equipe "
                        "está melhor que o município:</b>"
                        "<ul style='margin:6px 0 0 0; padding-left:20px;'>"
                    )
                    for _, r in df_top_melhor.iterrows():
                        html += (
                            f"<li style='margin-bottom:4px;'>"
                            f"<b>{r['lacuna']}</b> — "
                            f"<b style='color:#198754;'>"
                            f"{int(r['numerador'])}</b> "
                            f"({float(r['pct']):.0f}%) "
                            f"<span style='color:#198754;'>"
                            f"↓ {float(r['delta']):.1f} pp</span>"
                            f"</li>"
                        )
                    html += "</ul></div>"

                if df_top_pior.empty and df_top_melhor.empty:
                    html += (
                        "<div style='margin-top:10px; color:#6B7280;'>"
                        "Sua equipe está alinhada com a média do "
                        "município neste grupo (variação inferior a "
                        "±0,5 pp em todas as lacunas)."
                        "</div>"
                    )

                st.markdown(html, unsafe_allow_html=True)

            with d:
                rows = list(df_g.iterrows())
                # Grade 2 cards por linha
                for i in range(0, len(rows), 2):
                    sub = st.columns(2)
                    for j in range(2):
                        if i + j < len(rows):
                            _, r = rows[i + j]
                            _card_lacuna(sub[j], r)

        # ───────── Tabela completa com filtro ao final ─────────
        st.markdown("---")
        st.markdown("##### 📋 Tabela completa de lacunas")
        st.caption(
            "Visão tabular consolidada com gradiente de cor por % e "
            "variação em relação ao município. Filtre por grupo abaixo. "
            "Para abrir os pacientes individualmente em cada lacuna, "
            "vá para a aba 🧑‍⚕️ **Meus Pacientes** — lá é possível "
            "filtrar a lista nominal por lacuna específica e abrir o "
            "card de cada paciente."
        )

        grupos_disp = [g for g in _ORDEM_GRUPOS_LACUNAS
                       if g in df_lac['grupo'].dropna().unique()]
        filtro_grupo = st.multiselect(
            "Filtrar por grupo",
            options=grupos_disp, default=[],
            placeholder="Todos os grupos",
            format_func=lambda g: _LABEL_GRUPO_DISPLAY.get(g, g),
            key="lac_filtro_grupo_tab",
        )

        df_lac_tab = df_lac.sort_values(
            'pct', ascending=False, na_position='last')
        if filtro_grupo:
            df_lac_tab = df_lac_tab[df_lac_tab['grupo'].isin(filtro_grupo)]

        df_tab = pd.DataFrame({
            'Grupo':       df_lac_tab['grupo'].map(
                lambda g: _LABEL_GRUPO_DISPLAY.get(g, g)).values,
            'Lacuna':      df_lac_tab['lacuna'].values,
            'n / N':       df_lac_tab.apply(
                lambda r: f"{int(r['numerador'])} / {int(r['denominador'])}"
                          if r['denominador'] else "—",
                axis=1,
            ).values,
            '% Equipe':    df_lac_tab['pct'].astype(float).values,
            '% Município': df_lac_tab['pct_mun'].astype(float).values,
            'Variação':    df_lac_tab['delta'].astype(float).values,
        })

        def _fmt_variacao(v):
            if pd.isna(v):     return '—'
            if v > 0:          return f'↑ +{v:.1f}%'
            if v < 0:          return f'↓ {v:.1f}%'
            return '↔ 0,0%'

        def _cor_variacao(v):
            if pd.isna(v):     return ''
            if v > 0:          return 'color: #C0392B; font-weight: 600;'
            if v < 0:          return 'color: #27AE60; font-weight: 600;'
            return 'color: #6B7280;'

        def _gradiente_pct_tab(v, vmin=0.0, vmax=100.0):
            if pd.isna(v):     return ''
            norm = max(0.0, min(1.0, (float(v) - vmin) / (vmax - vmin)))
            if norm <= 0.5:
                t = norm * 2
                r = int(round(76  + (255 - 76)  * t))
                g = int(round(175 + (235 - 175) * t))
                b = int(round( 80 + ( 59 -  80) * t))
            else:
                t = (norm - 0.5) * 2
                r = int(round(255 + (231 - 255) * t))
                g = int(round(235 + ( 76 - 235) * t))
                b = int(round( 59 + ( 60 -  59) * t))
            return f'background-color: rgba({r},{g},{b},0.55);'

        styled = (
            df_tab.style
            .applymap(_gradiente_pct_tab, subset=['% Equipe', '% Município'])
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

