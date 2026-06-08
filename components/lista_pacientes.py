import re
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from google.cloud import bigquery
from utils.bigquery_client import get_bigquery_client
import config
from utils.relatos import formulario_relato
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
    anonimizar_nome, anonimizar_paciente, mostrar_badge_anonimo, MODO_ANONIMO
)
from components.cabecalho import renderizar_cabecalho
from utils.auth import exibir_usuario_logado
from utils import theme as T
from utils.ipc import calcular_ipc

# Ícones para o cabeçalho do card — alinhados com CORES_IPC
ICONES_IPC = {
    'Crítico':  '🔴',
    'Alto':     '🟠',
    'Moderado': '🟡',
    'Baixo':    '🟢',
}


# Parser de historico_medicamentos_730d.
# Formato esperado por item, separados por ';':
#   Medicamento Xmg | posologia [TIPO, Nx, primeira há Yd, recente há Zd]
# Sufixo opcional ', sem prescrição recente' aparece quando
# tipo_medicamento = 'CRONICO' AND dias_recente > 180.
_HIST_BRACKET_RE = re.compile(r'^(.*?)\s*\[([^\]]+)\]\s*$')
_HIST_INT_RE     = re.compile(r'(\d+)')


def parse_historico_medicamentos(historico_str):
    """Parsea historico_medicamentos_730d em lista de dicts.

    Cada dict tem: Medicamento, Posologia, Tipo, N, '1ª há (d)',
    'Recente há (d)', Status. Linhas que não casam o padrão entram
    como fallback com Medicamento = texto bruto.
    """
    if historico_str is None or historico_str == '' or pd.isna(historico_str):
        return []

    def _int_or_none(s):
        if not s:
            return None
        m = _HIST_INT_RE.search(s)
        return int(m.group(1)) if m else None

    items = []
    for raw in str(historico_str).split(';'):
        raw = raw.strip()
        if not raw:
            continue
        m = _HIST_BRACKET_RE.match(raw)
        if not m:
            items.append({
                'Medicamento': raw, 'Posologia': '—',
                'Tipo': '—', 'N': None,
                '1ª há (d)': None, 'Recente há (d)': None,
                'Status': '—',
            })
            continue

        head = m.group(1).strip()
        meta = m.group(2).strip()

        if '|' in head:
            med, posologia = [p.strip() for p in head.split('|', 1)]
        else:
            med, posologia = head, '—'

        partes = [p.strip() for p in meta.split(',')]
        tipo     = partes[0] if len(partes) >= 1 else '—'
        n_rx     = _int_or_none(partes[1]) if len(partes) >= 2 else None
        primeira = _int_or_none(partes[2]) if len(partes) >= 3 else None
        recente  = _int_or_none(partes[3]) if len(partes) >= 4 else None
        sem_recente = (
            len(partes) >= 5
            and 'sem prescrição recente' in partes[4].lower()
        )

        items.append({
            'Medicamento':    med,
            'Posologia':      posologia,
            'Tipo':           tipo,
            'N':              n_rx,
            '1ª há (d)':      primeira,
            'Recente há (d)': recente,
            'Status':         'Sem prescrição recente' if sem_recente else 'Ativo',
        })

    return items

# ═══════════════════════════════════════════════════════════════

# ============================================
# Componente Lista de Pacientes — reutilizável
# ============================================
# Este módulo encapsula toda a UI da page Meus Pacientes em uma
# função renderizar_lista_pacientes(area, clinica, esf, scope,
# incluir_sidebar). É chamado tanto pela page Meus_Pacientes.py
# quanto pela aba "Meus Pacientes" da page Visao_ESF.py.

# ============================================
# FUNÇÕES BIGQUERY ADAPTADAS
# ============================================

def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"

@st.cache_data(show_spinner=False, ttl=900)
def bq_query(sql: str) -> pd.DataFrame:
    """Executa query no BigQuery com timeout.

    Sem timeout, `.result()` bloqueia indefinidamente se o BQ ou a
    rede travarem — e o script Streamlit fica pendurado. Com
    timeout, vira exceção capturada → st.error → a página continua.
    """
    try:
        client = get_bigquery_client()
        df = (client.query(sql)
                    .result(timeout=90)   # cliente desiste após 90s
                    .to_dataframe(create_bqstorage_client=False))
        return df
    except Exception as e:
        st.error(f"❌ Erro ao executar query: {str(e)}")
        return pd.DataFrame()

# ============================================
# MAPEAMENTO COMPLETO DE MORBIDADES (50 CONDIÇÕES)
# ============================================

MORBIDADES_MAP = {
    # === CARDIOVASCULARES (8) ===
    'Hipertensão Arterial': 'HAS',
    'Cardiopatia Isquêmica': 'CI',
    'Insuficiência Cardíaca': 'ICC',
    'AVC': 'stroke',
    'Arritmia': 'arritmia',
    'Doença Valvular': 'valvular',
    'Doença Vascular Periférica': 'vascular_periferica',
    'Doença Circulatória Pulmonar': 'circ_pulm',
    
    # === METABÓLICAS/ENDÓCRINAS (5) ===
    'Diabetes Mellitus': 'DM',
    'Pré-diabetes': 'pre_DM',
    'Dislipidemia': 'dislipidemia',
    'Obesidade': 'obesidade_consolidada',
    # 'Doença da Tireoide': 'tireoide',  # coluna removida temporariamente
    
    # === RENAIS (1) ===
    'Insuficiência Renal Crônica': 'IRC',
    
    # === RESPIRATÓRIAS (2) ===
    'DPOC': 'COPD',
    'Asma': 'asthma',
    
    # === NEUROLÓGICAS/PSIQUIÁTRICAS (8) ===
    'Demência': 'dementia',
    'Doença Neurológica': 'neuro',
    'Epilepsia': 'epilepsy',
    'Parkinsonismo': 'parkinsonism',
    'Esclerose Múltipla': 'multiple_sclerosis',
    'Plegia': 'plegia',
    'Psicose': 'psicoses',
    'Depressão e Ansiedade': 'depre_ansiedade',
    
    # === NEOPLASIAS (8) ===
    'Neoplasia de Mama': 'neoplasia_mama',
    'Neoplasia de Colo do Útero': 'neoplasia_colo_uterino',
    'Neoplasia Feminina (exceto mama/colo)': 'neoplasia_feminina_estrita',
    'Neoplasia Masculina': 'neoplasia_masculina_estrita',
    'Neoplasia (ambos os sexos)': 'neoplasia_ambos_os_sexos',
    'Leucemia': 'leukemia',
    'Linfoma': 'lymphoma',
    'Câncer Metastático': 'metastasis',
    
    # === GASTROINTESTINAIS/HEPÁTICAS (4) ===
    'Úlcera Péptica': 'peptic',
    'Doença Hepática': 'liver',
    'Doença Diverticular': 'diverticular_disease',
    'Doença Inflamatória Intestinal': 'ibd',
    
    # === INFECCIOSAS (1) ===
    'HIV/AIDS': 'HIV',
    
    # === HEMATOLÓGICAS (2) ===
    'Distúrbio de Coagulação': 'coagulo',
    'Anemia': 'anemias',
    
    # === REUMATOLÓGICAS (1) ===
    'Doença Reumatológica': 'reumato',
    
    # === SUBSTÂNCIAS (3) ===
    'Transtorno por Uso de Álcool': 'alcool',
    'Transtorno por Uso de Drogas': 'drogas',
    'Tabagismo': 'tabaco',
    
    # === NUTRICIONAIS (1) ===
    'Desnutrição': 'desnutricao',
    
    # === DEFICIÊNCIAS/SENSORIAIS (3) ===
    'Deficiência Intelectual': 'retardo_mental',
    'Doença Ocular': 'olhos',
    'Doença Auditiva': 'ouvidos',
    
    # === OUTRAS (4) ===
    'Malformação Congênita': 'ma_formacoes',
    'Doença de Pele': 'pele',
    'Condição Dolorosa Crônica': 'painful_condition',
    'Doença de Próstata': 'prostate_disorder',
}

# Lista ordenada para o filtro (por categoria) - 50 MORBIDADES
LISTA_MORBIDADES = [
    # Cardiovasculares
    'Hipertensão Arterial',
    'Cardiopatia Isquêmica',
    'Insuficiência Cardíaca',
    'AVC',
    'Arritmia',
    'Doença Valvular',
    'Doença Vascular Periférica',
    'Doença Circulatória Pulmonar',
    # Metabólicas
    'Diabetes Mellitus',
    'Pré-diabetes',
    'Dislipidemia',
    'Obesidade',
    'Doença da Tireoide',
    # Renais
    'Insuficiência Renal Crônica',
    # Respiratórias
    'DPOC',
    'Asma',
    # Neurológicas/Psiquiátricas
    'Demência',
    'Doença Neurológica',
    'Epilepsia',
    'Parkinsonismo',
    'Esclerose Múltipla',
    'Plegia',
    'Psicose',
    'Depressão e Ansiedade',
    # Neoplasias
    'Neoplasia de Mama',
    'Neoplasia de Colo do Útero',
    'Neoplasia Feminina (exceto mama/colo)',
    'Neoplasia Masculina',
    'Neoplasia (ambos os sexos)',
    'Leucemia',
    'Linfoma',
    'Câncer Metastático',
    # Gastrointestinais
    'Úlcera Péptica',
    'Doença Hepática',
    'Doença Diverticular',
    'Doença Inflamatória Intestinal',
    # Infecciosas
    'HIV/AIDS',
    # Hematológicas
    'Distúrbio de Coagulação',
    'Anemia',
    # Reumatológicas
    'Doença Reumatológica',
    # Substâncias
    'Transtorno por Uso de Álcool',
    'Transtorno por Uso de Drogas',
    'Tabagismo',
    # Nutricionais
    'Desnutrição',
    # Deficiências/Sensoriais
    'Deficiência Intelectual',
    'Doença Ocular',
    'Doença Auditiva',
    # Outras
    'Malformação Congênita',
    'Doença de Pele',
    'Condição Dolorosa Crônica',
    'Doença de Próstata',
]

# ============================================
# MAPEAMENTO COMPLETO DE LACUNAS (43 LACUNAS)
# ============================================

# ═══════════════════════════════════════════════════════════════
# LACUNAS — derivadas de utils/lacunas_config.py (fonte única de verdade,
# compartilhada com a page Lacunas de Cuidado).
# Estrutura local: {coluna_fato: (grupos_tuple, descricao, justificativa)}
#   - grupos_tuple: tupla de grupos aos quais a lacuna pertence (1 ou mais).
#   - justificativa: texto clínico exibido ao lado da lacuna no card.
# ═══════════════════════════════════════════════════════════════
from utils.lacunas_config import LACUNAS as _LACUNAS_CFG, get_grupos_ordenados

def _build_lacunas_completo():
    out = {}
    for nome, info in _LACUNAS_CFG.items():
        col = info["coluna_fato"]
        grupo = info["grupo"]
        grupos = tuple(grupo) if isinstance(grupo, list) else (grupo,)
        just = info.get("justificativa_clinica", "")
        out[col] = (grupos, nome, just)
    return out

LACUNAS_COMPLETO = _build_lacunas_completo()
GRUPOS_LACUNAS_ORDENADOS = get_grupos_ordenados()

# Flags clínicos — não são lacunas, mas indicadores auxiliares exibidos no card.
FLAGS_POSITIVOS = {
    'DM_controlado': '✅ DM controlado',
    'DM_melhorando': '✅ DM melhorando',
}

FLAGS_ALERTA = {
    'DM_piorando': '⚠️ DM piorando',
}

# ============================================
# [CONTINUA NO PRÓXIMO COMENTÁRIO - ARQUIVO MUITO GRANDE]
# Vou dividir em 2 partes
# ============================================

# ============================================
# FUNÇÕES DE CARGA OTIMIZADAS
# ============================================

@st.cache_data(show_spinner=False, ttl=900)
def load_filter_options_cascata(area=None, clinica=None):
    """Carrega opções de filtro de forma cascata"""
    where_clauses = []
    
    if area is not None:
        where_clauses.append(f"area_programatica_cadastro = '{str(area)}'")
    
    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{str(clinica)}'")
    
    where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
    SELECT DISTINCT
      area_programatica_cadastro,
      nome_clinica_cadastro,
      nome_esf_cadastro
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro IS NOT NULL {where_sql}
    ORDER BY area_programatica_cadastro, nome_clinica_cadastro, nome_esf_cadastro
    """
    
    return bq_query(sql)

@st.cache_data(show_spinner=False, ttl=900)
def load_patient_data_paginated(
    area=None,
    clinica=None,
    esf=None,
    idade_min=None,
    idade_max=None,
    morbidades=None,
    operador_morb="OR",
    ordem="desc",
    offset=0,
    limit=20,
    busca_nome=None,
    carga_morb=None,
    ordenar_por="morbidades",
    lacunas_filtro=None,
    rcv_filtro=None,
    apenas_insulina=False,
    apenas_inercia_clinica=False,
    apenas_inercia_estrutural=False,
    genero_filtro=None,
    apenas_polifarmacia=False,
    acb_filtro=None,
    apenas_stopp=False,
    apenas_hiperpolifarmacia=False,
    cpfs=None,
):
    """Carrega pacientes com paginação e filtros.

    Quando ``cpfs`` é uma tupla/lista não vazia, restringe o resultado
    àqueles CPFs (usado por chamadas que já têm uma seleção pronta —
    ex.: Top-10 da Visão ESF).
    """

    where_clauses = ["area_programatica_cadastro IS NOT NULL"]

    if cpfs:
        cpfs_sql = ", ".join(f"'{str(c)}'" for c in cpfs)
        where_clauses.append(f"cpf IN ({cpfs_sql})")

    if area is not None:
        where_clauses.append(f"area_programatica_cadastro = '{str(area)}'")

    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{str(clinica)}'")

    if esf:
        where_clauses.append(f"nome_esf_cadastro = '{str(esf)}'")

    if idade_min is not None and idade_max is not None:
        where_clauses.append(f"idade BETWEEN {int(idade_min)} AND {int(idade_max)}")

    if busca_nome:
        termo = busca_nome.replace("'", "\\'")
        where_clauses.append(f"LOWER(nome) LIKE '%{termo.lower()}%'")

    # Filtro de carga de morbidade
    if carga_morb and len(carga_morb) > 0:
        cats = ", ".join(f"'{c}'" for c in carga_morb)
        where_clauses.append(f"charlson_categoria IN ({cats})")

    # Filtro de morbidades
    if morbidades and len(morbidades) > 0:
        morb_cols = [MORBIDADES_MAP.get(m) for m in morbidades if m in MORBIDADES_MAP]

        if operador_morb == "AND":
            for col in morb_cols:
                where_clauses.append(f"{col} IS NOT NULL")
        else:  # OR
            morb_conditions = [f"{col} IS NOT NULL" for col in morb_cols]
            if morb_conditions:
                where_clauses.append(f"({' OR '.join(morb_conditions)})")

    # Filtro de lacunas
    if lacunas_filtro and len(lacunas_filtro) > 0:
        lac_conditions = [f"{lac} = TRUE" for lac in lacunas_filtro]
        where_clauses.append(f"({' OR '.join(lac_conditions)})")

    # Filtro de risco cardiovascular (categoria efetiva — espelha o cabeçalho do card).
    # Aplica primeiro a reclassificação SBC direta:
    #   DCV estabelecida (CI/AVC/DAP) → 'Muito alto'
    #   DM ou IRC                     → 'Alto'
    #   Caso contrário                → who_categoria_risco_simplificada
    # "Não calculado" = a categoria efetiva é NULL (nenhuma reclass + WHO não calculável)
    # e o paciente é elegível (40-80a, sem colesterol e sem IMC).
    rcv_efetivo_sql = (
        "CASE "
        "WHEN CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL "
        "THEN 'Muito alto' "
        "WHEN DM IS NOT NULL OR IRC IS NOT NULL "
        "THEN 'Alto' "
        "ELSE who_categoria_risco_simplificada "
        "END"
    )
    if rcv_filtro and len(rcv_filtro) > 0:
        rcv_conds = []
        cats_validas = [c for c in rcv_filtro if c != "Não calculado"]
        if cats_validas:
            cats_sql = ", ".join(f"'{c}'" for c in cats_validas)
            rcv_conds.append(f"{rcv_efetivo_sql} IN ({cats_sql})")
        if "Não calculado" in rcv_filtro:
            rcv_conds.append(
                f"({rcv_efetivo_sql} IS NULL "
                f"AND idade BETWEEN 40 AND 80 "
                f"AND colesterol_total IS NULL AND IMC IS NULL)"
            )
        where_clauses.append(f"({' OR '.join(rcv_conds)})")

    # Filtro: apenas pacientes em uso de insulina (qualquer tipo).
    # Usa as flags estruturais principio_INSULINA_* — bate com o KPI
    # populacional da page Diabetes e da Visão ESF (mesma janela do
    # pipeline). A coluna NPH (UI/kg) no card e o destaque vermelho
    # continuam usando o critério estrito (núcleo crônico atual).
    if apenas_insulina:
        where_clauses.append(
            "(principio_INSULINA_BASAL_HUMANA IS NOT NULL "
            "OR principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL "
            "OR principio_INSULINA_BASAL_ANALOGICA IS NOT NULL "
            "OR principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL "
            "OR principio_INSULINA_MISTA IS NOT NULL)"
        )

    # Filtros de inércia (taxonomia V3 — ver count_total_patients).
    if apenas_inercia_clinica:
        where_clauses.append(
            "(paciente_inercia_persistente_HAS = TRUE "
            "OR paciente_inercia_persistente_DM = TRUE "
            "OR paciente_descontrole_recente_sem_acao_HAS = TRUE "
            "OR paciente_descontrole_recente_sem_acao_DM = TRUE)"
        )

    if apenas_inercia_estrutural:
        where_clauses.append(
            "(paciente_inercia_falta_tratamento_HAS = TRUE "
            "OR paciente_inercia_falta_tratamento_DM = TRUE "
            "OR paciente_inercia_falta_aferi_HAS = TRUE "
            "OR paciente_inercia_falta_aferi_DM = TRUE "
            "OR paciente_sem_nenhuma_PA_HAS = TRUE "
            "OR paciente_sem_nenhuma_HbA1c_DM = TRUE)"
        )

    where_clauses += _where_filtros_extras(
        genero_filtro=genero_filtro, apenas_polifarmacia=apenas_polifarmacia,
        acb_filtro=acb_filtro, apenas_stopp=apenas_stopp,
        apenas_hiperpolifarmacia=apenas_hiperpolifarmacia,
    )

    where_sql = " AND ".join(where_clauses)
    order_dir = "DESC" if ordem == "desc" else "ASC"
    if ordenar_por == "dias_medico":
        order_col = "dias_desde_ultima_medica"
        order_sql = f"{order_dir} NULLS LAST"
    elif ordenar_por == "dias_prescricao":
        order_col = "dias_desde_ultima_prescricao_cronica"
        order_sql = f"{order_dir} NULLS LAST"
    elif ordenar_por == "acb":
        order_col = "acb_score_total"
        order_sql = f"{order_dir} NULLS LAST"
    elif ordenar_por == "rcv":
        order_col = "who_risco_cvd_pct"
        order_sql = f"{order_dir} NULLS LAST"
    elif ordenar_por == "dose_nph":
        order_col = "dose_NPH_ui_kg"
        order_sql = f"{order_dir} NULLS LAST"
    else:
        order_col = "total_morbidades"
        order_sql = order_dir
    
    # Construir SELECT com TODAS as morbidades convertidas para boolean
    morbidades_select = []
    for nome_portugues, col_ingles in MORBIDADES_MAP.items():
        alias = col_ingles
        morbidades_select.append(f"CASE WHEN {col_ingles} IS NOT NULL THEN TRUE ELSE FALSE END as {alias}")
    
    # Construir SELECT com TODAS as lacunas
    lacunas_select = []
    for campo_lacuna in LACUNAS_COMPLETO.keys():
        lacunas_select.append(campo_lacuna)
    
    # Adicionar flags
    for flag in FLAGS_POSITIVOS.keys():
        lacunas_select.append(flag)
    for flag in FLAGS_ALERTA.keys():
        lacunas_select.append(flag)
    
    sql = f"""
    SELECT 
      cpf,
      nome,
      data_nascimento,
      idade,
      genero,
      raca,
      area_programatica_cadastro,
      nome_clinica_cadastro as clinica_familia,
      nome_esf_cadastro as ESF,
      charlson_score,
      charlson_mediana,
      charlson_categoria,
      charlson_pontos_morbidades,
      charlson_pontos_idade,
      charlson_pontos_polifarmacia,
      percentual_risco_final,
      categoria_risco_final,
      variaveis_usadas_calculo,
      framingham_variaveis_ausentes,
      -- WHO HEARTS
      who_risco_cvd_pct,
      who_categoria_risco,
      who_categoria_risco_simplificada,
      who_modelo_utilizado,
      who_lab_calculavel,
      who_nonlab_calculavel,
      who_lab_variaveis_ausentes,
      who_nonlab_variaveis_ausentes,
      colesterol_total,
      hdl,
      pressao_sistolica,
      IMC,
      peso,
      altura,
      tabaco,
      dias_desde_ultima_medica,
      dias_desde_ultima_enfermagem,
      dias_desde_ultima_tecnico_enfermagem,
      dias_em_acompanhamento, 
      pct_consultas_medico_365d,
      pct_consultas_medicas_na_unidade_365d,
      pct_consultas_medicas_fora_365d,
      pct_consultas_enfermeiro_365d,
      consultas_365d,
      consultas_medicas_365d,
      consultas_enfermagem_365d,
      consultas_tecnico_enfermagem_365d,
      meses_com_consulta_12m,
      regularidade_acompanhamento,
      intervalo_mediano_dias,
      baixa_longitudinalidade,
      usuario_frequente_urgencia,
      perfil_cuidado_365d,
      alto_risco_baixo_acesso, 
      baixo_risco_alto_acesso,
      alto_risco_intervalo_longo,
      total_morbidades as N_morbidades,
      multimorbidade,
      nucleo_cronico_atual as medicamentos_cronicos,
      total_medicamentos_cronicos as qtd_medicamentos_cronicos,
      dias_desde_ultima_prescricao_cronica,
      polifarmacia,
      hiperpolifarmacia,
      -- Histórico farmacológico estendido (730d) e agudos recorrentes
      historico_medicamentos_730d,
      n_meds_distintos_730d,
      n_agudos_recorrentes,
      lista_agudos_recorrentes,
      -- Insulinas
      (principio_INSULINA_BASAL_HUMANA IS NOT NULL
       OR principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL
       OR principio_INSULINA_BASAL_ANALOGICA IS NOT NULL
       OR principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL
       OR principio_INSULINA_MISTA IS NOT NULL) AS usa_insulina,
      (principio_INSULINA_BASAL_HUMANA IS NOT NULL) AS usa_nph,
      dose_NPH_ui_kg,
      acb_score_total,
      categoria_acb,
      -- Série temporal do ACB (prescrição-âncora ~90/180/365d atrás).
      -- Ponto no tempo, NÃO soma acumulada. NULL = sem prescrição na
      -- banda (≠ 0) — propositalmente SEM COALESCE para preservar o NULL.
      acb_90d, acb_180d, acb_365d,
      n_meds_90d, n_meds_180d, n_meds_365d,
      COALESCE(alerta_acb_idoso, FALSE) AS alerta_acb_idoso,
      ultimas_tres_PA,
      ultimas_tres_glicemias,
      ultimas_tres_A1C,
      -- STOPP (insumo do IPC) — scalar subquery para evitar JOIN
      COALESCE(
        (SELECT s.total_criterios_stopp
         FROM `rj-sms-sandbox.sub_pav_us.MM_stopp_start` s
         WHERE s.cpf = `{_fqn(config.TABELA_FATO)}`.cpf),
        0
      ) AS total_criterios_stopp,
      -- Inércia terapêutica (taxonomia V3 — 11 categorias)
      -- Flags-mestras (12 booleanas, podem disparar em paralelo)
      paciente_inercia_persistente_HAS,
      paciente_inercia_persistente_DM,
      paciente_inercia_falta_tratamento_HAS,
      paciente_inercia_falta_tratamento_DM,
      paciente_inercia_falta_aferi_HAS,
      paciente_inercia_falta_aferi_DM,
      paciente_descontrole_recente_sem_acao_HAS,
      paciente_descontrole_recente_sem_acao_DM,
      paciente_renovado_controlado_atrasado_HAS,
      paciente_renovado_controlado_atrasado_DM,
      paciente_sem_nenhuma_PA_HAS,
      paciente_sem_nenhuma_HbA1c_DM,
      -- Status atual (cascata, 11 categorias mutuamente exclusivas)
      status_atual_HAS,
      status_atual_DM,
      -- Padrão de manejo (trajetória 365d)
      padrao_manejo_HAS,
      padrao_manejo_DM,
      -- Texto pré-formatado para card "Meus Pacientes"
      texto_meus_pacientes_HAS,
      texto_meus_pacientes_DM,
      -- Contadores de trajetória 365d — HAS (14)
      n_consultas_HAS_365d,
      n_consultas_inercia_persistente_HAS,
      n_consultas_descontrole_recente_HAS,
      n_consultas_renovado_controlado_atrasado_HAS,
      n_consultas_inercia_falta_aferi_HAS,
      n_consultas_sem_nenhuma_PA_HAS,
      n_consultas_intensificou_HAS,
      n_consultas_trocou_HAS,
      n_consultas_desintensificou_HAS,
      n_consultas_mantido_HAS,
      n_consultas_sem_comparacao_HAS,
      n_consultas_pa_controlada,
      n_consultas_pa_descontrolada,
      n_consultas_pa_sem_aferi,
      -- Contadores de trajetória 365d — DM (14)
      n_consultas_DM_365d,
      n_consultas_inercia_persistente_DM,
      n_consultas_descontrole_recente_DM,
      n_consultas_renovado_controlado_atrasado_DM,
      n_consultas_inercia_falta_aferi_DM,
      n_consultas_sem_nenhuma_HbA1c_DM,
      n_consultas_intensificou_DM,
      n_consultas_trocou_DM,
      n_consultas_desintensificou_DM,
      n_consultas_mantido_DM,
      n_consultas_sem_comparacao_DM,
      n_consultas_dm_controlado,
      n_consultas_dm_descontrolado,
      n_consultas_dm_sem_aferi,
      -- TODAS as morbidades
      {', '.join(morbidades_select)},
      -- TODAS as lacunas e flags
      {', '.join(lacunas_select)}
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE {where_sql}
    ORDER BY {order_col} {order_sql}
    LIMIT {limit} OFFSET {offset}
    """

    df_pac = bq_query(sql)

    # IPC — calculado após o load para que cada card tenha o índice
    # disponível no cabeçalho. Requer total_lacunas (soma das lacunas
    # individuais) e total_criterios_stopp (já vem da scalar subquery).
    if not df_pac.empty:
        bool_lac_cols = [c for c in LACUNAS_COMPLETO.keys() if c in df_pac.columns]
        if bool_lac_cols:
            df_pac['total_lacunas'] = (
                df_pac[bool_lac_cols].fillna(False).astype(bool).sum(axis=1)
            )
        else:
            df_pac['total_lacunas'] = 0
        df_pac = calcular_ipc(df_pac)

    return df_pac

@st.cache_data(show_spinner=False, ttl=900)
def get_statistics_summary(area=None, clinica=None, esf=None, idade_min=None, idade_max=None):
    """Obtém estatísticas resumidas dos pacientes filtrados"""
    
    where_clauses = ["area_programatica_cadastro IS NOT NULL"]
    
    if area is not None:
        where_clauses.append(f"area_programatica_cadastro = '{str(area)}'")
    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{str(clinica)}'")
    if esf:
        where_clauses.append(f"nome_esf_cadastro = '{str(esf)}'")
    if idade_min is not None and idade_max is not None:
        where_clauses.append(f"idade BETWEEN {int(idade_min)} AND {int(idade_max)}")
    
    where_sql = " AND ".join(where_clauses)
    
    sql = f"""
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN total_morbidades >= 2 THEN 1 END) as multimorbidos,
        COUNT(CASE WHEN polifarmacia = TRUE THEN 1 END) as polifarmacia,
        COUNT(CASE WHEN hiperpolifarmacia = TRUE THEN 1 END) as hiperpolifarmacia
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE {where_sql}
    """
    
    df = bq_query(sql)
    if not df.empty:
        return {
            'total': int(df['total'].iloc[0]),
            'multimorbidos': int(df['multimorbidos'].iloc[0]) if pd.notna(df['multimorbidos'].iloc[0]) else 0,
            'polifarmacia': int(df['polifarmacia'].iloc[0]) if pd.notna(df['polifarmacia'].iloc[0]) else 0,
            'hiperpolifarmacia': int(df['hiperpolifarmacia'].iloc[0]) if pd.notna(df['hiperpolifarmacia'].iloc[0]) else 0
        }
    return {'total': 0, 'multimorbidos': 0, 'polifarmacia': 0, 'hiperpolifarmacia': 0}


def _limpar_nan(d: dict) -> dict:
    """Converte NaN/NaT/NA → None num dict de valores escalares.

    Query de 1 linha (`WHERE cpf = 'X'`) traz coluna NULL como dtype
    `object` → valor `None`. Query em lote (`WHERE cpf IN (...)`) com
    mix de valores/NULL traz a mesma coluna como `float64` → valor
    `NaN`. O código de render faz `int(x or 0)`, e `int(NaN)` estoura
    ValueError (enquanto `int(None or 0)` = 0). Normalizar aqui
    mantém o mesmo formato dos dois caminhos.
    """
    limpo = {}
    for k, v in d.items():
        try:
            if pd.isna(v):
                v = None
        except (ValueError, TypeError):
            pass  # arrays/listas — não são escalares, mantém
        limpo[k] = v
    return limpo


@st.cache_data(show_spinner=False, ttl=900)
def buscar_stopp_paciente(cpf: str) -> dict:
    """Busca flags STOPP/START/Beers individuais de um paciente na MM_stopp_start."""
    sql = f"""
    SELECT
        -- Resumos
        COALESCE(total_criterios_stopp, 0) AS total_stopp,
        COALESCE(total_criterios_start,  0) AS total_start,
        COALESCE(total_criterios_beers,  0) AS total_beers,
        alerta_prescricao_idoso_ativo,
        alerta_queda_medicamentos,
        alerta_warfarina_fa,
        alerta_egfr_ausente_gabapentinoide,
        alerta_egfr_ausente_metformina,
        alerta_cascata_biperideno,
        -- STOPP individuais (365d)
        stopp_cv_001_365d, stopp_cv_002_365d, stopp_cv_003_365d,
        stopp_cv_004_365d, stopp_cv_005_365d, stopp_cv_006_365d,
        stopp_cv_007_365d, stopp_cv_008_365d, stopp_cv_009_365d,
        stopp_cv_010,
        stopp_snc_001_365d, stopp_snc_002_365d, stopp_snc_003_365d,
        stopp_snc_004_365d, stopp_snc_005_365d, stopp_snc_006_365d,
        stopp_snc_007_365d, stopp_snc_008_365d, stopp_snc_009_365d,
        stopp_snc_010_365d, stopp_snc_011_365d,
        stopp_end_001_365d, stopp_end_002_365d, stopp_end_003_365d,
        stopp_end_004_365d,
        stopp_mus_001_365d, stopp_mus_002_365d, stopp_mus_003_365d,
        stopp_mus_004_365d, stopp_mus_005_365d, stopp_mus_006_365d,
        stopp_acb_002_365d, stopp_acb_003_365d,
        stopp_acb_004_365d,
        stopp_ren_001_365d, stopp_ren_002_365d, stopp_ren_003_365d,
        -- START individuais (365d)
        start_cv_001_365d, start_cv_002_365d, start_cv_003_365d,
        start_cv_004_365d, start_cv_005_365d, start_cv_006_365d,
        start_snc_001_365d, start_snc_003_365d,
        start_resp_001_365d,
        -- Beers (365d)
        beers_001_365d, beers_002_365d, beers_003_365d,
        beers_004_365d, beers_005_365d, beers_006_365d, beers_007_365d
    FROM `rj-sms-sandbox.sub_pav_us.MM_stopp_start`
    WHERE cpf = '{cpf}'
    LIMIT 1
    """
    df = bq_query(sql)
    if df.empty:
        return {}
    return _limpar_nan(df.iloc[0].to_dict())


@st.cache_data(show_spinner=False, ttl=900)
def buscar_acb_paciente(cpf: str) -> dict:
    """Busca dados ACB detalhados do paciente em MM_mantidos_alterados_ultimas."""
    sql = f"""
    SELECT
        score_acb_total,
        n_meds_acb_positivo,
        n_meds_acb_alto,
        medicamentos_acb,
        categoria_acb,
        lista_medicamentos
    FROM `rj-sms-sandbox.sub_pav_us.MM_mantidos_alterados_ultimas`
    WHERE cpf = '{cpf}'
    LIMIT 1
    """
    df = bq_query(sql)
    if df.empty:
        return {}
    return _limpar_nan(df.iloc[0].to_dict())


@st.cache_data(show_spinner=False, ttl=900)
def buscar_acb_lote(cpfs: tuple) -> dict:
    """ACB para múltiplos pacientes numa só query — substitui N chamadas
    seriais a `buscar_acb_paciente` na renderização da lista. Retorna
    `{cpf: dict_dados}` (chaves em string p/ casar com `str(cpf)`).
    """
    if not cpfs:
        return {}
    cpfs_sql = ", ".join(f"'{c}'" for c in cpfs)
    sql = f"""
    SELECT
        cpf,
        score_acb_total,
        n_meds_acb_positivo,
        n_meds_acb_alto,
        medicamentos_acb,
        categoria_acb,
        lista_medicamentos
    FROM `rj-sms-sandbox.sub_pav_us.MM_mantidos_alterados_ultimas`
    WHERE cpf IN ({cpfs_sql})
    """
    df = bq_query(sql)
    if df.empty:
        return {}
    return {str(row['cpf']): _limpar_nan(row.to_dict())
            for _, row in df.iterrows()}


@st.cache_data(show_spinner=False, ttl=900)
def buscar_stopp_lote(cpfs: tuple) -> dict:
    """STOPP/START/Beers para múltiplos pacientes numa só query —
    substitui N chamadas a `buscar_stopp_paciente`. Filtra ≥60a no
    chamador (esta função apenas faz fan-out por CPF). Retorna
    `{cpf: dict_dados}`.
    """
    if not cpfs:
        return {}
    cpfs_sql = ", ".join(f"'{c}'" for c in cpfs)
    sql = f"""
    SELECT
        cpf,
        COALESCE(total_criterios_stopp, 0) AS total_stopp,
        COALESCE(total_criterios_start,  0) AS total_start,
        COALESCE(total_criterios_beers,  0) AS total_beers,
        alerta_prescricao_idoso_ativo,
        alerta_queda_medicamentos,
        alerta_warfarina_fa,
        alerta_egfr_ausente_gabapentinoide,
        alerta_egfr_ausente_metformina,
        alerta_cascata_biperideno,
        stopp_cv_001_365d, stopp_cv_002_365d, stopp_cv_003_365d,
        stopp_cv_004_365d, stopp_cv_005_365d, stopp_cv_006_365d,
        stopp_cv_007_365d, stopp_cv_008_365d, stopp_cv_009_365d,
        stopp_cv_010,
        stopp_snc_001_365d, stopp_snc_002_365d, stopp_snc_003_365d,
        stopp_snc_004_365d, stopp_snc_005_365d, stopp_snc_006_365d,
        stopp_snc_007_365d, stopp_snc_008_365d, stopp_snc_009_365d,
        stopp_snc_010_365d, stopp_snc_011_365d,
        stopp_end_001_365d, stopp_end_002_365d, stopp_end_003_365d,
        stopp_end_004_365d,
        stopp_mus_001_365d, stopp_mus_002_365d, stopp_mus_003_365d,
        stopp_mus_004_365d, stopp_mus_005_365d, stopp_mus_006_365d,
        stopp_acb_002_365d, stopp_acb_003_365d,
        stopp_acb_004_365d,
        stopp_ren_001_365d, stopp_ren_002_365d, stopp_ren_003_365d,
        start_cv_001_365d, start_cv_002_365d, start_cv_003_365d,
        start_cv_004_365d, start_cv_005_365d, start_cv_006_365d,
        start_snc_001_365d, start_snc_003_365d,
        start_resp_001_365d,
        beers_001_365d, beers_002_365d, beers_003_365d,
        beers_004_365d, beers_005_365d, beers_006_365d, beers_007_365d
    FROM `rj-sms-sandbox.sub_pav_us.MM_stopp_start`
    WHERE cpf IN ({cpfs_sql})
    """
    df = bq_query(sql)
    if df.empty:
        return {}
    return {str(row['cpf']): _limpar_nan(row.to_dict())
            for _, row in df.iterrows()}

def _where_filtros_extras(genero_filtro=None, apenas_polifarmacia=False,
                          acb_filtro=None, apenas_stopp=False,
                          apenas_hiperpolifarmacia=False):
    """Cláusulas WHERE dos filtros adicionais (sexo, polifarmácia,
    hiperpolifarmácia, carga ACB, STOPP/START). Compartilhado por
    count_total_patients e load_patient_data_paginated — ambos
    filtram a mesma tabela fato. Retorna lista de strings prontas
    para ``where_clauses.append``."""
    clausulas = []
    if genero_filtro == 'F':
        clausulas.append("LOWER(genero) IN ('f', 'feminino')")
    elif genero_filtro == 'M':
        clausulas.append("LOWER(genero) IN ('m', 'masculino')")
    if apenas_polifarmacia:
        # Mesma definição do KPI populacional (≥5 medicamentos crônicos).
        clausulas.append("polifarmacia = TRUE")
    if apenas_hiperpolifarmacia:
        # Hiperpolifarmácia — ≥10 medicamentos crônicos (KPI populacional).
        clausulas.append("hiperpolifarmacia = TRUE")
    if acb_filtro and len(acb_filtro) > 0:
        cats = ", ".join(f"'{c}'" for c in acb_filtro)
        clausulas.append(f"categoria_acb IN ({cats})")
    if apenas_stopp:
        # Tem ao menos um critério STOPP ou START ativo (subquery
        # correlacionada — MM_stopp_start não está na tabela fato).
        fato = f"`{_fqn(config.TABELA_FATO)}`"
        clausulas.append(
            "EXISTS (SELECT 1 FROM "
            "`rj-sms-sandbox.sub_pav_us.MM_stopp_start` s "
            f"WHERE s.cpf = {fato}.cpf "
            "AND (s.total_criterios_stopp > 0 "
            "OR s.total_criterios_start > 0))"
        )
    return clausulas


@st.cache_data(show_spinner=False, ttl=900)
def count_total_patients(area=None, clinica=None, esf=None, idade_min=None, idade_max=None, morbidades=None, operador_morb="OR", busca_nome=None, carga_morb=None, lacunas_filtro=None, rcv_filtro=None, apenas_insulina=False, apenas_inercia_clinica=False, apenas_inercia_estrutural=False,
                         genero_filtro=None, apenas_polifarmacia=False, acb_filtro=None, apenas_stopp=False,
                         apenas_hiperpolifarmacia=False):
    """Conta total de pacientes para paginação"""

    where_clauses = ["area_programatica_cadastro IS NOT NULL"]

    if area is not None:
        where_clauses.append(f"area_programatica_cadastro = '{str(area)}'")

    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{str(clinica)}'")

    if esf:
        where_clauses.append(f"nome_esf_cadastro = '{str(esf)}'")

    if idade_min is not None and idade_max is not None:
        where_clauses.append(f"idade BETWEEN {int(idade_min)} AND {int(idade_max)}")

    if busca_nome:
        termo = busca_nome.replace("'", "\\'")
        where_clauses.append(f"LOWER(nome) LIKE '%{termo.lower()}%'")

    # Filtro de carga de morbidade
    if carga_morb and len(carga_morb) > 0:
        cats = ", ".join(f"'{c}'" for c in carga_morb)
        where_clauses.append(f"charlson_categoria IN ({cats})")

    # Filtro de morbidades
    if morbidades and len(morbidades) > 0:
        morb_cols = [MORBIDADES_MAP.get(m) for m in morbidades if m in MORBIDADES_MAP]

        if operador_morb == "AND":
            for col in morb_cols:
                where_clauses.append(f"{col} IS NOT NULL")
        else:  # OR
            morb_conditions = [f"{col} IS NOT NULL" for col in morb_cols]
            if morb_conditions:
                where_clauses.append(f"({' OR '.join(morb_conditions)})")

    # Filtro de lacunas
    if lacunas_filtro and len(lacunas_filtro) > 0:
        lac_conditions = [f"{lac} = TRUE" for lac in lacunas_filtro]
        where_clauses.append(f"({' OR '.join(lac_conditions)})")

    # Filtro de risco cardiovascular (categoria efetiva — espelha o cabeçalho do card).
    # Aplica primeiro a reclassificação SBC direta:
    #   DCV estabelecida (CI/AVC/DAP) → 'Muito alto'
    #   DM ou IRC                     → 'Alto'
    #   Caso contrário                → who_categoria_risco_simplificada
    # "Não calculado" = a categoria efetiva é NULL (nenhuma reclass + WHO não calculável)
    # e o paciente é elegível (40-80a, sem colesterol e sem IMC).
    rcv_efetivo_sql = (
        "CASE "
        "WHEN CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL "
        "THEN 'Muito alto' "
        "WHEN DM IS NOT NULL OR IRC IS NOT NULL "
        "THEN 'Alto' "
        "ELSE who_categoria_risco_simplificada "
        "END"
    )
    if rcv_filtro and len(rcv_filtro) > 0:
        rcv_conds = []
        cats_validas = [c for c in rcv_filtro if c != "Não calculado"]
        if cats_validas:
            cats_sql = ", ".join(f"'{c}'" for c in cats_validas)
            rcv_conds.append(f"{rcv_efetivo_sql} IN ({cats_sql})")
        if "Não calculado" in rcv_filtro:
            rcv_conds.append(
                f"({rcv_efetivo_sql} IS NULL "
                f"AND idade BETWEEN 40 AND 80 "
                f"AND colesterol_total IS NULL AND IMC IS NULL)"
            )
        where_clauses.append(f"({' OR '.join(rcv_conds)})")

    # Filtro: apenas pacientes em uso de insulina (qualquer tipo).
    # Usa as flags estruturais principio_INSULINA_* — bate com o KPI
    # populacional da page Diabetes e da Visão ESF (mesma janela do
    # pipeline). A coluna NPH (UI/kg) no card e o destaque vermelho
    # continuam usando o critério estrito (núcleo crônico atual).
    if apenas_insulina:
        where_clauses.append(
            "(principio_INSULINA_BASAL_HUMANA IS NOT NULL "
            "OR principio_INSULINA_PRANDIAL_HUMANA IS NOT NULL "
            "OR principio_INSULINA_BASAL_ANALOGICA IS NOT NULL "
            "OR principio_INSULINA_PRANDIAL_ANALOGICA IS NOT NULL "
            "OR principio_INSULINA_MISTA IS NOT NULL)"
        )

    # Filtros de inércia (taxonomia V3 — duas frentes distintas):
    # • Clínica  = decisão médica frente ao descontrole.
    #   Cobre: inércia persistente + descontrole recente sem ação.
    # • Estrutural = sistema/equipe perdendo o paciente antes do médico
    #   poder agir. Cobre: falta de tratamento (busca ativa/ACS),
    #   falta de aferição (equipe afere) e sem nenhuma PA/HbA1c (cego).
    if apenas_inercia_clinica:
        where_clauses.append(
            "(paciente_inercia_persistente_HAS = TRUE "
            "OR paciente_inercia_persistente_DM = TRUE "
            "OR paciente_descontrole_recente_sem_acao_HAS = TRUE "
            "OR paciente_descontrole_recente_sem_acao_DM = TRUE)"
        )

    if apenas_inercia_estrutural:
        where_clauses.append(
            "(paciente_inercia_falta_tratamento_HAS = TRUE "
            "OR paciente_inercia_falta_tratamento_DM = TRUE "
            "OR paciente_inercia_falta_aferi_HAS = TRUE "
            "OR paciente_inercia_falta_aferi_DM = TRUE "
            "OR paciente_sem_nenhuma_PA_HAS = TRUE "
            "OR paciente_sem_nenhuma_HbA1c_DM = TRUE)"
        )

    where_clauses += _where_filtros_extras(
        genero_filtro=genero_filtro, apenas_polifarmacia=apenas_polifarmacia,
        acb_filtro=acb_filtro, apenas_stopp=apenas_stopp,
        apenas_hiperpolifarmacia=apenas_hiperpolifarmacia,
    )

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT COUNT(*) as total
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE {where_sql}
    """
    
    df = bq_query(sql)
    return int(df['total'].iloc[0]) if not df.empty else 0

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def format_value(value):
    if pd.isna(value):
        return "Não informado"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, (int, float)):
        return str(int(value)) if value == int(value) else f"{value:.1f}"
    return str(value)

def format_dias_consulta(value):
    if pd.isna(value):
        return "Não informado"
    try:
        dias = int(float(value))
        if dias == 9999:
            return "Nunca consultou"
        return f"{dias} dias"
    except:
        return "Não informado"

def format_tempo_acompanhamento(dias):
    """Converte dias em anos e meses"""
    if pd.isna(dias):
        return "Não informado"
    try:
        dias = int(float(dias))
        anos = dias // 365
        meses = (dias % 365) // 30
        
        if anos > 0 and meses > 0:
            return f"{anos} ano(s) e {meses} mês(es)"
        elif anos > 0:
            return f"{anos} ano(s)"
        else:
            return f"{meses} mês(es)"
    except:
        return "Não informado"

def extrair_morbidades_paciente(patient_data):
    """Extrai TODAS as morbidades TRUE do paciente"""
    morbidades_encontradas = []
    
    # Criar mapeamento inverso (coluna → nome em português)
    col_to_nome = {v: k for k, v in MORBIDADES_MAP.items()}
    
    # Verificar cada campo de morbidade na tabela
    for col_bd, nome_portugues in col_to_nome.items():
        valor = patient_data.get(col_bd)
        
        # Verificar se é TRUE
        if valor in [True, 1, '1', 'True', 'true', 'TRUE']:
            morbidades_encontradas.append(nome_portugues)
    
    # Lógica de Polifarmácia/Hiperpolifarmácia (mutuamente exclusiva)
    tem_hiperpolifarmacia = patient_data.get('hiperpolifarmacia') in [True, 1, '1', 'True']
    tem_polifarmacia = patient_data.get('polifarmacia') in [True, 1, '1', 'True']
    
    if tem_hiperpolifarmacia:
        morbidades_encontradas.append('Hiperpolifarmácia')
    elif tem_polifarmacia:
        morbidades_encontradas.append('Polifarmácia')
    
    return sorted(morbidades_encontradas)

def extrair_lacunas_paciente(patient_data):
    """Extrai lacunas TRUE do paciente, organizadas por grupo"""
    lacunas_por_grupo = {}
    
    # Processar lacunas — lacunas multi-grupo (HAS/DM) aparecem só uma vez,
    # no primeiro grupo da lista. Cada item é (descricao, justificativa).
    for campo_lacuna, (grupos, descricao, justificativa) in LACUNAS_COMPLETO.items():
        valor = patient_data.get(campo_lacuna)

        if valor in [True, 1, '1', 'True', 'true', 'TRUE']:
            grupo_primario = grupos[0]
            if grupo_primario not in lacunas_por_grupo:
                lacunas_por_grupo[grupo_primario] = []
            lacunas_por_grupo[grupo_primario].append((descricao, justificativa))
    
    # Processar flags positivos
    flags_ativos = []
    for flag, descricao in FLAGS_POSITIVOS.items():
        if patient_data.get(flag) in [True, 1, '1', 'True']:
            flags_ativos.append(descricao)
    
    # Processar flags de alerta
    for flag, descricao in FLAGS_ALERTA.items():
        if patient_data.get(flag) in [True, 1, '1', 'True']:
            flags_ativos.append(descricao)
    
    return lacunas_por_grupo, flags_ativos


# ─── Inércia terapêutica (taxonomia V3 — 11 categorias) ──────────
# Cada categoria do `status_atual_*` (cascata hierárquica) tem cor,
# rótulo, descrição clínica em português, ação esperada e indicação
# da frente de cuidado responsável. Cores seguem a paleta sugerida
# no dicionário de variáveis (seção 4.4) e no guia conceitual.
#
# Três frentes de cuidado, refletindo a tese central do guia:
# "o sistema perde pacientes antes que o médico tenha como agir".
#   🩺 frente médica   — decisão clínica (intensificar/trocar)
#   🩹 frente da equipe — aferição/exame de rotina
#   🏠 frente da busca ativa — paciente saiu da rede (ACS)
#   ✅ sem alerta de inércia — cuidado em curso ou estável
STATUS_INERCIA_V3 = {
    'INERCIA_PERSISTENTE': {
        'cor':    '#c0392b',
        'rotulo': 'Inércia persistente',
        'frente': '🩺 Frente médica',
        'desc':   ('Paciente com descontrole confirmado (aferição '
                   'recente acima da meta + histórico também '
                   'descontrolado, ou ≥2 medidas altas em 180 dias) e '
                   'esquema mantido na última consulta. É a inércia '
                   'no sentido clássico — há evidência clara de '
                   'descontrole sem ação clínica.'),
        'acao':   ('Avaliar adesão e causas secundárias; intensificar '
                   'o tratamento (aumentar dose, adicionar segunda '
                   'droga ou trocar de classe).'),
    },
    'INERCIA_POR_FALTA_DE_TRATAMENTO': {
        'cor':    '#d35400',
        'rotulo': 'Inércia por falta de tratamento',
        'frente': '🏠 Frente da busca ativa',
        'desc':   ('Paciente diagnosticado, mas sem nenhuma '
                   'prescrição registrada nos últimos 365 dias. Pode '
                   'ter saído da rede pública, estar em manejo '
                   'particular ou ter abandonado o seguimento — em '
                   'qualquer caso, o sistema perdeu o controle sobre '
                   'esse tratamento.'),
        'acao':   ('Acionar o Agente Comunitário de Saúde para visita '
                   'domiciliar — entender por que o paciente saiu do '
                   'seguimento e reativar o vínculo com a ESF.'),
    },
    'INERCIA_POR_FALTA_DE_AFERICAO': {
        'cor':    '#e67e22',
        'rotulo': 'Inércia por falta de aferição',
        'frente': '🩹 Frente da equipe',
        'desc':   ('Paciente em tratamento ativo. O histórico (180–730 '
                   'dias atrás) mostra descontrole, mas ninguém afere '
                   'nem solicita exame mais. A receita é renovada sem '
                   'nova informação clínica para apoiar a decisão.'),
        'acao':   ('Aferir hoje. Se confirmar descontrole, '
                   'intensificar imediatamente. Se estiver na meta, '
                   'manter e reagendar acompanhamento.'),
    },
    'DESCONTROLE_RECENTE_SEM_ACAO': {
        'cor':    '#e74c3c',
        'rotulo': 'Descontrole recente sem ação',
        'frente': '🩺 Frente médica',
        'desc':   ('O paciente estava na meta no histórico, mas a '
                   'última aferição mostrou descontrole — e o esquema '
                   'foi mantido. Não é inércia confirmada: a próxima '
                   'aferição vai dizer se foi pontual ou se virou '
                   'persistente.'),
        'acao':   ('Reagendar nova aferição em 4–6 semanas para '
                   'confirmar se o descontrole se sustenta. Se '
                   'persistir, intensificar.'),
    },
    'TRATAMENTO_SEM_NENHUMA_PA': {
        'cor':    '#f39c12',
        'rotulo': 'Em tratamento, nunca teve PA aferida',
        'frente': '🩹 Frente da equipe',
        'desc':   ('Paciente recebe receita há tempos, mas nunca teve '
                   'nenhuma PA aferida nos últimos 730 dias. Estamos '
                   'voando completamente cego sobre o controle '
                   'pressórico.'),
        'acao':   ('Aferir PA imediatamente — sem qualquer dado '
                   'clínico, qualquer decisão terapêutica é cega.'),
    },
    'TRATAMENTO_SEM_NENHUMA_HbA1c': {
        'cor':    '#f39c12',
        'rotulo': 'Em tratamento, nunca teve HbA1c',
        'frente': '🩹 Frente da equipe',
        'desc':   ('Paciente recebe antidiabético há tempos, mas não '
                   'há nenhuma HbA1c registrada nos últimos 730 dias. '
                   'Estamos voando completamente cego sobre o '
                   'controle glicêmico.'),
        'acao':   ('Solicitar HbA1c imediatamente — sem dado de '
                   'controle, qualquer ajuste terapêutico é cego.'),
    },
    'TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO': {
        'cor':    '#f1c40f',
        'rotulo': 'Tratamento renovado, controle não confirmado',
        'frente': '🩹 Frente da equipe',
        'desc':   ('O paciente estava na meta no histórico e a receita '
                   'foi renovada, mas a aferição/exame não foi feito '
                   'nesta janela. Não é alerta urgente — é só falta '
                   'de confirmação.'),
        'acao':   ('Aferir / solicitar exame na próxima oportunidade '
                   'para confirmar manutenção do controle.'),
    },
    'MANEJO_APROPRIADO': {
        'cor':    '#27ae60',
        'rotulo': 'Manejo apropriado',
        'frente': '✅ Sem alerta de inércia',
        'desc':   ('O paciente estava descontrolado e a equipe agiu: '
                   'intensificou ou trocou o esquema na última '
                   'consulta. Continuar descontrolado apesar da ação '
                   'não é inércia — pode ser resposta lenta ou '
                   'questão de adesão.'),
        'acao':   ('Aguardar 4–6 semanas para reavaliar a resposta '
                   'terapêutica. Reforçar adesão.'),
    },
    'CONTROLADO': {
        'cor':    '#16a085',
        'rotulo': 'Controlado',
        'frente': '✅ Sem alerta de inércia',
        'desc':   ('Paciente na meta, com consulta e aferição/exame '
                   'recentes. Cuidado em curso, estável.'),
        'acao':   'Manter conduta atual.',
    },
    'CONTROLADO_COM_LACUNA_CONSULTA': {
        'cor':    '#bdc3c7',
        'rotulo': 'Controlado, mas sem consulta recente',
        'frente': '🏠 Frente da busca ativa',
        'desc':   ('A última aferição estava na meta, mas faz mais de '
                   '180 dias sem nova consulta com prescrição. Pode '
                   'estar bem ou pode ter saído da rede — não dá pra '
                   'saber sem buscar.'),
        'acao':   ('Acionar o Agente Comunitário para confirmar se o '
                   'paciente segue em tratamento e tem suprimento da '
                   'medicação.'),
    },
    'DESCONTROLE_SEM_COMPARACAO': {
        'cor':    '#95a5a6',
        'rotulo': 'Descontrole sem histórico para comparar',
        'frente': 'ℹ️ Sem alerta de inércia',
        'desc':   ('Paciente novo na ESF, recém-diagnosticado ou '
                   'retornando de um hiato — descontrolado, mas sem '
                   'prescrição anterior na janela para classificar a '
                   'ação clínica.'),
        'acao':   ('Iniciar/retomar o tratamento e reavaliar em 4–6 '
                   'semanas. Não é caso de inércia.'),
    },
    'OUTRO': {
        'cor':    '#7f8c8d',
        'rotulo': 'Caso atípico',
        'frente': '⚠️ Caso residual',
        'desc':   ('Combinação de dados que não se encaixa em nenhuma '
                   'categoria padrão. Pode indicar registro '
                   'incompleto.'),
        'acao':   'Avaliar caso a caso.',
    },
}

# Padrão de manejo na trajetória 365d (≥2 consultas para ser avaliável).
CORES_PADRAO_MANEJO = {
    'PROATIVO': (
        '#27ae60',
        'Manejo proativo',
        'Em ≥50% das consultas com descontrole, a equipe intensificou '
        'ou trocou o esquema.'),
    'INERTE': (
        '#c0392b',
        'Manejo inerte',
        'Em ≥50% das consultas com descontrole, o esquema foi mantido '
        'sem ação.'),
    'ESTAGNADO': (
        '#e67e22',
        'Manejo estagnado',
        'Em ≥50% das consultas, o paciente vinha sem aferição/exame e '
        'o esquema foi mantido.'),
    'CONTROLADO': (
        '#16a085',
        'Controlado de modo consistente',
        'Em ≥50% das consultas, o paciente estava na meta.'),
    'MISTO': (
        '#f1c40f',
        'Padrão misto',
        'Trajetória heterogênea — nenhuma categoria atinge 50%.'),
    'MENOS_DE_2_CONSULTAS': (
        '#bdc3c7',
        'Trajetória não avaliável',
        'Menos de 2 consultas com prescrição em 365 dias.'),
}

# Cores dos segmentos da barra horizontal de trajetória 365d.
CORES_TRAJETORIA = {
    'intensificou':    ('#27ae60', 'Intensificou'),
    'trocou':          ('#16a085', 'Trocou'),
    'mantido':         ('#f1c40f', 'Mantido'),
    'desintensificou': ('#e67e22', 'Desintensificou'),
    'sem_comparacao':  ('#bdc3c7', 'Sem comparação'),
}


def _flags_inercia_ativas(patient_data, condicao: str):
    """Lista as flags-mestras V3 que estão TRUE para a condição (HAS
    ou DM), com texto curto em português e indicação da frente de
    cuidado. Útil para mostrar todas as 'frentes de inércia' nas
    quais o paciente está simultaneamente — informação que se perde
    no `status_atual_*` (cascata hierárquica)."""
    if condicao == 'HAS':
        flags = [
            ('paciente_inercia_persistente_HAS',
             'Em inércia persistente: descontrole confirmado e esquema mantido.',
             '🩺 frente médica'),
            ('paciente_inercia_falta_tratamento_HAS',
             'Sem nenhuma prescrição registrada nos últimos 365 dias.',
             '🏠 busca ativa pelo ACS'),
            ('paciente_inercia_falta_aferi_HAS',
             'Em tratamento, mas histórico de PA ruim e sem nova aferição.',
             '🩹 equipe afere hoje'),
            ('paciente_descontrole_recente_sem_acao_HAS',
             'Descontrolou agora, sem ação registrada no esquema.',
             '🩺 frente médica (confirmar)'),
            ('paciente_renovado_controlado_atrasado_HAS',
             'Estava na meta, esquema renovado sem nova aferição.',
             '🩹 aferir na próxima'),
            ('paciente_sem_nenhuma_PA_HAS',
             'Em tratamento, mas nunca teve PA aferida em 730 dias.',
             '🩹 aferir imediatamente'),
        ]
    else:
        flags = [
            ('paciente_inercia_persistente_DM',
             'Em inércia persistente: descontrole confirmado e esquema mantido.',
             '🩺 frente médica'),
            ('paciente_inercia_falta_tratamento_DM',
             'Sem nenhuma prescrição registrada nos últimos 365 dias.',
             '🏠 busca ativa pelo ACS'),
            ('paciente_inercia_falta_aferi_DM',
             'Em tratamento, mas histórico de HbA1c ruim e sem nova solicitação.',
             '🩹 equipe solicita exame'),
            ('paciente_descontrole_recente_sem_acao_DM',
             'Descontrolou agora, sem ação registrada no esquema.',
             '🩺 frente médica (confirmar)'),
            ('paciente_renovado_controlado_atrasado_DM',
             'Estava na meta, esquema renovado sem nova HbA1c.',
             '🩹 solicitar exame'),
            ('paciente_sem_nenhuma_HbA1c_DM',
             'Em tratamento, mas nunca teve HbA1c em 730 dias.',
             '🩹 solicitar exame imediatamente'),
        ]
    return [
        (texto, frente)
        for col, texto, frente in flags
        if patient_data.get(col) in [True, 1, '1', 'True']
    ]


def _render_inercia_condicao(patient_data, condicao: str):
    """Renderiza a seção de inércia de uma condição (HAS ou DM) na
    sub-aba 'Inércia' do card do paciente.

    Conteúdo:
      1. Header da condição (🩺 HAS / 🩸 DM).
      2. Alerta narrativo pré-formatado do pipeline (`texto_meus_pacientes_*`).
      3. Status principal (cascata): card colorido com rótulo, frente
         de cuidado, descrição clínica em português e ação esperada.
      4. Bullets das outras flags TRUE simultâneas — mostra que o
         paciente pode estar em mais de uma forma de inércia ao mesmo
         tempo (a cascata só expõe a primeira).
      5. Padrão de manejo 365d (trajetória, não snapshot).
      6. Barra horizontal empilhada das ações farmacológicas (365d).
      7. Métricas dos contadores de aferição/exame.

    Retorna True se renderizou algo (paciente tem a condição).
    """
    status = patient_data.get(f'status_atual_{condicao}')
    if status is None or (isinstance(status, float) and pd.isna(status)):
        return False

    nome_cond = 'Hipertensão' if condicao == 'HAS' else 'Diabetes'
    icone     = '🩺' if condicao == 'HAS' else '🩸'
    param     = 'PA' if condicao == 'HAS' else 'HbA1c'

    st.markdown(f"##### {icone} {nome_cond}")

    # 1. Alerta narrativo pré-formatado (vem do pipeline).
    texto = patient_data.get(f'texto_meus_pacientes_{condicao}')
    if pd.notna(texto) and texto:
        st.markdown(
            f"<div style='background:#FFF3E0; border-left:4px solid #E69138; "
            f"padding:10px 14px; margin:6px 0 14px 0; border-radius:4px; "
            f"font-size:0.95em; line-height:1.5;'>{texto}</div>",
            unsafe_allow_html=True,
        )

    # 2. Status principal (cascata). Card grande com fundo colorido,
    # rótulo, frente, descrição clínica e ação esperada — toda
    # explicação em português, sem pedir ao usuário decodificar siglas.
    info = STATUS_INERCIA_V3.get(str(status), STATUS_INERCIA_V3['OUTRO'])
    cor = info['cor']
    st.markdown(
        f"<div style='border-left:6px solid {cor}; background:#FAFAFA; "
        f"padding:14px 16px; margin:6px 0 12px 0; border-radius:4px;'>"
        f"<div style='font-size:0.82em; color:#666; letter-spacing:0.4px; "
        f"text-transform:uppercase; margin-bottom:4px;'>"
        f"Tipo principal de inércia (na última consulta)</div>"
        f"<div style='font-size:1.15em; font-weight:700; color:{cor}; "
        f"margin-bottom:4px;'>{info['rotulo']}</div>"
        f"<div style='font-size:0.88em; color:#444; margin-bottom:10px;'>"
        f"<b>{info['frente']}</b></div>"
        f"<div style='font-size:0.95em; line-height:1.55; color:#333; "
        f"margin-bottom:10px;'><b>O que isso significa:</b> {info['desc']}</div>"
        f"<div style='font-size:0.95em; line-height:1.55; color:#333;'>"
        f"<b>Ação esperada:</b> {info['acao']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 3. Outras flags TRUE simultâneas (paciente pode ter mais de
    # uma frente de inércia ao mesmo tempo).
    flags_ativas = _flags_inercia_ativas(patient_data, condicao)
    # Remove a flag que corresponde ao status principal — já foi mostrada.
    status_para_flag = {
        'INERCIA_PERSISTENTE':                   'Em inércia persistente',
        'INERCIA_POR_FALTA_DE_TRATAMENTO':       'Sem nenhuma prescrição',
        'INERCIA_POR_FALTA_DE_AFERICAO':         'Em tratamento, mas histórico',
        'DESCONTROLE_RECENTE_SEM_ACAO':          'Descontrolou agora',
        'TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO': 'Estava na meta, esquema renovado',
        'TRATAMENTO_SEM_NENHUMA_PA':             'Em tratamento, mas nunca teve PA',
        'TRATAMENTO_SEM_NENHUMA_HbA1c':          'Em tratamento, mas nunca teve HbA1c',
    }
    marcador_principal = status_para_flag.get(str(status))
    flags_extras = [
        (t, f) for (t, f) in flags_ativas
        if not (marcador_principal and t.startswith(marcador_principal))
    ]
    if flags_extras:
        bullets = "".join(
            f"<li style='margin-bottom:6px;'><b>{texto}</b> "
            f"<span style='color:#666; font-size:0.88em;'>"
            f"({frente})</span></li>"
            for texto, frente in flags_extras
        )
        st.markdown(
            f"<div style='margin:6px 0 14px 0; font-size:0.92em;'>"
            f"<div style='color:#555; margin-bottom:4px;'>"
            f"Este paciente também está em outras frentes de inércia "
            f"que rodam em paralelo:</div>"
            f"<ul style='margin:0; padding-left:20px; line-height:1.55;'>"
            f"{bullets}</ul></div>",
            unsafe_allow_html=True,
        )

    # 4. Padrão de manejo 365d (trajetória, não snapshot).
    padrao = patient_data.get(f'padrao_manejo_{condicao}')
    if pd.notna(padrao) and padrao:
        cor_p, label_p, desc_p = CORES_PADRAO_MANEJO.get(
            str(padrao), ('#9E9E9E', str(padrao), ''))
        st.markdown(
            f"<div style='margin:6px 0 12px 0;'>"
            f"<span style='font-size:0.85em; color:#555;'>"
            f"Padrão de manejo nos últimos 365 dias (trajetória):</span><br>"
            f"<span style='background:{cor_p}; color:white; padding:4px 10px; "
            f"border-radius:12px; font-weight:600; font-size:0.95em;'>"
            f"{label_p}</span>"
            f"<div style='font-size:0.88em; color:#555; margin-top:6px;'>"
            f"{desc_p}</div></div>",
            unsafe_allow_html=True,
        )

    # 5. Mini-barra horizontal da trajetória 365d (ações farmacológicas).
    n_total = patient_data.get(f'n_consultas_{condicao}_365d')
    n_total = int(n_total) if pd.notna(n_total) else 0
    if n_total > 0:
        chaves = [
            ('intensificou',    f'n_consultas_intensificou_{condicao}'),
            ('trocou',          f'n_consultas_trocou_{condicao}'),
            ('mantido',         f'n_consultas_mantido_{condicao}'),
            ('desintensificou', f'n_consultas_desintensificou_{condicao}'),
            ('sem_comparacao',  f'n_consultas_sem_comparacao_{condicao}'),
        ]
        segmentos, legenda = [], []
        for chave_cor, col in chaves:
            v = patient_data.get(col)
            n = int(v) if pd.notna(v) else 0
            if n == 0:
                continue
            cor_s, label_s = CORES_TRAJETORIA[chave_cor]
            pct = 100 * n / n_total
            segmentos.append(
                f"<div title='{label_s}: {n} consulta(s)' "
                f"style='flex:{pct}; background:{cor_s}; height:100%;'></div>"
            )
            legenda.append(
                f"<span style='display:inline-block; margin-right:14px; "
                f"font-size:0.82em;'>"
                f"<span style='display:inline-block; width:10px; height:10px; "
                f"background:{cor_s}; border-radius:2px; margin-right:4px; "
                f"vertical-align:middle;'></span>"
                f"{label_s} ({n})</span>"
            )
        if segmentos:
            st.markdown(
                f"<div style='margin:10px 0 4px 0; font-size:0.85em; color:#555;'>"
                f"Trajetória das {n_total} consulta(s) com prescrição de "
                f"{nome_cond.lower()} em 365 dias:</div>"
                f"<div style='display:flex; height:18px; border-radius:4px; "
                f"overflow:hidden; border:1px solid #E0E0E0;'>"
                f"{''.join(segmentos)}"
                f"</div>"
                f"<div style='margin:6px 0 10px 0;'>{''.join(legenda)}</div>",
                unsafe_allow_html=True,
            )

        # 6. Métricas (contadores de aferição/exame).
        if condicao == 'HAS':
            n_ctrl    = patient_data.get('n_consultas_pa_controlada')
            n_desc    = patient_data.get('n_consultas_pa_descontrolada')
            n_sem     = patient_data.get('n_consultas_pa_sem_aferi')
            n_cego    = patient_data.get('n_consultas_sem_nenhuma_PA_HAS')
        else:
            n_ctrl    = patient_data.get('n_consultas_dm_controlado')
            n_desc    = patient_data.get('n_consultas_dm_descontrolado')
            n_sem     = patient_data.get('n_consultas_dm_sem_aferi')
            n_cego    = patient_data.get('n_consultas_sem_nenhuma_HbA1c_DM')
        n_pers   = patient_data.get(f'n_consultas_inercia_persistente_{condicao}')
        n_faltaf = patient_data.get(f'n_consultas_inercia_falta_aferi_{condicao}')
        n_descr  = patient_data.get(f'n_consultas_descontrole_recente_{condicao}')

        def _ic(v):
            return int(v) if pd.notna(v) else 0

        c1, c2, c3 = st.columns(3)
        c1.metric(f"{param} controlada", _ic(n_ctrl))
        c2.metric(f"{param} descontrolada", _ic(n_desc))
        c3.metric("Sem aferição na consulta", _ic(n_sem))
        c4, c5, c6 = st.columns(3)
        c4.metric("Em inércia persistente", _ic(n_pers))
        c5.metric("Inércia por falta de aferição", _ic(n_faltaf))
        c6.metric("Descontrole recente", _ic(n_descr))

    return True


def create_patient_card(patient_data, key_prefix: str = '',
                        dados_acb=None, dados_stopp=None):
    """Renderiza o card expansível do paciente.

    ``key_prefix`` evita colisão de keys quando o mesmo paciente é
    renderizado em mais de um lugar na mesma page (ex.: aba 'Abertura
    - teste' e aba 'Meus Pacientes' da Visão ESF, que renderizam
    simultaneamente porque o Streamlit instancia ambas as abas).

    ``dados_acb`` e ``dados_stopp`` são opcionais e servem para
    pré-injetar os dados farmacológicos já buscados em lote
    (`buscar_acb_lote` / `buscar_stopp_lote`) no chamador — evita N
    queries seriais quando a lista renderiza N cards. Se vier None,
    o card faz fallback para a query por-paciente (compat).

    NOTA: já foi decorado com ``@st.fragment`` para isolar reruns,
    mas isso causava travamento da renderização da lista (o render
    parava no meio, ~card 7-10, sem retornar). `@st.fragment` em
    loop de muitos cards com layout aninhado pesado é instável.
    Removido. O isolamento de rerun deixou de ser necessário porque
    o batch (`buscar_*_lote`) tornou o rerun global barato — 2
    queries em vez de N. NÃO re-adicionar `@st.fragment` aqui sem
    resolver a instabilidade.
    """

    # Preserva original (não-anonimizado) para formulário de relato —
    # precisamos do território real ao registrar o problema.
    patient_data_original = patient_data
    patient_data = anonimizar_paciente(patient_data)

    nome = patient_data.get('nome', 'Nome não informado')
    idade = patient_data.get('idade', 'N/A')

    # Contar morbidades das colunas booleanas (mesma lógica de extrair_morbidades_paciente)
    lista_morb = extrair_morbidades_paciente(patient_data)
    n_morbidades = len(lista_morb)

    # Contar medicamentos da lista (string separada por ;)
    meds_lista_raw = str(patient_data.get('medicamentos_cronicos', '') or '')
    if meds_lista_raw.strip() and meds_lista_raw.strip() != '—':
        n_medicamentos = len([m.strip() for m in meds_lista_raw.split(';') if m.strip()])
    else:
        n_medicamentos = 0

    # Contar lacunas TRUE
    n_lacunas = sum(1 for campo in LACUNAS_COMPLETO
                    if patient_data.get(campo) in [True, 1, '1', 'True'])

    # Processar morbidades
    if n_morbidades == 0:
        morbidades_texto = "0 morbidades"
    elif n_morbidades == 1:
        morbidades_texto = "1 morbidade"
    else:
        morbidades_texto = f"{n_morbidades} morbidades"

    # Processar medicamentos
    if n_medicamentos == 0:
        medicamentos_texto = "0 medicamentos"
    elif n_medicamentos == 1:
        medicamentos_texto = "1 medicamento"
    else:
        medicamentos_texto = f"{n_medicamentos} medicamentos"
    
    # Processar lacunas
    if n_lacunas == 0:
        lacunas_texto = "0 lacunas"
    elif n_lacunas == 1:
        lacunas_texto = "1 lacuna"
    else:
        lacunas_texto = f"{n_lacunas} lacunas"
    
    # Processar ACB para o cabeçalho
    acb_val = patient_data.get("acb_score_total")
    if acb_val is None or (isinstance(acb_val, float) and pd.isna(acb_val)):
        acb_texto = ""
    else:
        acb_int = int(float(acb_val))
        acb_icone = "🔴" if acb_int >= 3 else "🟠" if acb_int >= 1 else "🟢"
        acb_texto = f" | {acb_icone} ACB {acb_int}"

    # Risco CV para o cabeçalho (padrão PAHO/HEARTS)
    # Reclassificação SBC direta prevalece: DCV estabelecida (CI/AVC/DAP) → Muito alto;
    # DM ou IRC → Alto. Só se nenhuma dessas condições se aplicar usamos o score WHO.
    from utils.risco_cv import icone_categoria_who, classificar_risco_direto
    _pac_dm_hdr  = patient_data.get('DM')  in [True, 1, '1', 'True']
    _pac_irc_hdr = patient_data.get('IRC') in [True, 1, '1', 'True']
    _pac_ci_hdr  = patient_data.get('CI')  in [True, 1, '1', 'True']
    _pac_avc_hdr = patient_data.get('stroke') in [True, 1, '1', 'True']
    _pac_dap_hdr = patient_data.get('vascular_periferica') in [True, 1, '1', 'True']
    _reclass_hdr = classificar_risco_direto(
        dm=_pac_dm_hdr, irc=_pac_irc_hdr,
        ci=_pac_ci_hdr, avc=_pac_avc_hdr, dap=_pac_dap_hdr,
    )
    if _reclass_hdr:
        # SBC direto — mapeia 'MUITO ALTO'/'ALTO' para rótulo PAHO
        cat_hdr = 'Muito alto' if _reclass_hdr['categoria'] == 'MUITO ALTO' else 'Alto'
    else:
        cat_simpl = patient_data.get('who_categoria_risco_simplificada')
        cat_hdr = cat_simpl if pd.notna(cat_simpl) and cat_simpl else None

    if cat_hdr:
        icone_rcv = icone_categoria_who(cat_hdr)
        rcv_texto = f" | {icone_rcv} RCV {cat_hdr}"
    else:
        rcv_texto = " | ❤️ RCV não calculado"

    # Alerta NPH em dose alta no cabeçalho — só se NPH está de fato na última
    # prescrição (nucleo_cronico_atual é o truth source).
    _usa_nph_hdr  = patient_data.get('usa_nph') in [True, 1, '1', 'True']
    _dose_nph_hdr = patient_data.get('dose_NPH_ui_kg')
    _meds_low_hdr = str(patient_data.get('medicamentos_cronicos') or '').lower()
    _nph_no_nucleo_hdr = ('nph' in _meds_low_hdr) or ('isofana' in _meds_low_hdr)
    if (_usa_nph_hdr and pd.notna(_dose_nph_hdr)
            and float(_dose_nph_hdr) > 0.8 and _nph_no_nucleo_hdr):
        nph_texto = f" | ⚠️ NPH {float(_dose_nph_hdr):.2f} UI/kg"
    else:
        nph_texto = ""

    # IPC no cabeçalho — sinal unificado de priorização
    ipc_val = patient_data.get('ipc')
    ipc_cat = patient_data.get('ipc_categoria')
    if pd.notna(ipc_val) and ipc_cat:
        icone_ipc = ICONES_IPC.get(ipc_cat, '⚪')
        ipc_texto = f"{icone_ipc} **IPC {float(ipc_val):.2f}** {ipc_cat} | "
    else:
        ipc_texto = ""

    # Carga de Morbidade no cabeçalho (sem mediana — mediana só no corpo)
    carga_val = patient_data.get('charlson_score')
    if pd.notna(carga_val):
        carga_int = int(carga_val)
        carga_texto = f" | ⚖️ Carga {carga_int}"
    else:
        carga_texto = ""

    titulo_card = (
        f"{ipc_texto}👤 **{nome}** - {idade} anos{carga_texto} "
        f"| 🏥 {morbidades_texto} | 💊 {medicamentos_texto}"
        f"{acb_texto}{rcv_texto}{nph_texto} | ⚠️ {lacunas_texto}"
    )
    
    with st.expander(titulo_card, expanded=False):
        
        # ============================================
        # VISÃO GERAL (TOPO) - 2 COLUNAS
        # ============================================
        col_esquerda, col_direita = st.columns(2)
        
        # COLUNA ESQUERDA - Dados Pessoais e Cadastro
        with col_esquerda:
            st.markdown("### 📋 Dados Pessoais")
            st.write(f"**Nome:** {format_value(patient_data.get('nome'))}")
            st.write(f"**Data de Nascimento:** {format_value(patient_data.get('data_nascimento'))}")
            st.write(f"**Idade:** {format_value(patient_data.get('idade'))} anos")
            st.write(f"**Gênero:** {format_value(patient_data.get('genero'))}")
            st.write(f"**Raça:** {format_value(patient_data.get('raca'))}")
            
            st.markdown("### 🏥 Dados de Cadastro")
            st.write(f"**Área Programática:** {format_value(patient_data.get('area_programatica_cadastro'))}")
            st.write(f"**Clínica da Família:** {format_value(patient_data.get('clinica_familia'))}")
            st.write(f"**ESF:** {format_value(patient_data.get('ESF'))}")
        
        # COLUNA DIREITA - Morbidades e Medicamentos
        with col_direita:
            st.markdown("### 🦠 Morbidades")
            n_morb = n_morbidades
            if n_morb == 0:
                st.write("**Nenhuma morbidade registrada**")
            else:
                st.write(f"**Número de morbidades:** {n_morb}")
                
                if n_morb >= 2:
                    data_multimorbidade = patient_data.get('multimorbidade')
                    if pd.notna(data_multimorbidade):
                        st.write(f"*Paciente identificado como multimórbido desde {data_multimorbidade}*")
                
                lista_morbidades = extrair_morbidades_paciente(patient_data)
                if lista_morbidades:
                    st.write(', '.join(lista_morbidades))
                else:
                    st.write("Não foi possível listar")


            st.markdown("### 💊 Medicamentos")

            n_meds = patient_data.get('qtd_medicamentos_cronicos', 0)
            dias_prescricao = patient_data.get('dias_desde_ultima_prescricao_cronica')
            medicamentos = patient_data.get('medicamentos_cronicos', '')

            if pd.isna(n_meds) or n_meds == 0:
                st.write("**Nenhum medicamento em uso**")
            else:
                # Linha 1: quantidade
                st.write(f"**{int(n_meds)} medicamentos em uso**")

                # Linha 2: lista de medicamentos
                if medicamentos and pd.notna(medicamentos) and str(medicamentos).strip():
                    st.write(str(medicamentos))

                # Linha 3: Insulina NPH com dose UI/kg (alerta se >0,8).
                # Fonte de verdade = núcleo crônico atual (última prescrição). Só exibe
                # se NPH aparece no texto da prescrição — principio_INSULINA_BASAL_HUMANA
                # pode estar defasado em relação ao que o médico prescreveu por último.
                usa_nph  = patient_data.get('usa_nph') in [True, 1, '1', 'True']
                dose_nph = patient_data.get('dose_NPH_ui_kg')
                meds_txt_low = str(medicamentos or '').lower()
                nph_no_nucleo = ('nph' in meds_txt_low) or ('isofana' in meds_txt_low)
                if usa_nph and pd.notna(dose_nph) and nph_no_nucleo:
                    dose_val = float(dose_nph)
                    texto_nph = f"Prescrição de Insulina NPH ({dose_val:.2f} UI/kg)"
                    if dose_val > 0.8:
                        st.markdown(
                            f"<div style='background:#FFCDD2; border-left:4px solid #C62828; "
                            f"padding:6px 10px; border-radius:4px; margin:4px 0; color:#B71C1C;'>"
                            f"⚠️ <strong>{texto_nph}</strong></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.write(texto_nph)

                # Linha 4: última prescrição
                if pd.notna(dias_prescricao) and dias_prescricao != 9999:
                    dias = int(float(dias_prescricao))
                    st.write(f"Última prescrição há {dias} dias")

        


        # Últimas Medidas — 4 colunas: antropometria, PA, glicemias, HbA1c
        ultimas_pa = patient_data.get('ultimas_tres_PA')
        ultimas_glicemias = patient_data.get('ultimas_tres_glicemias')
        ultimas_a1c = patient_data.get('ultimas_tres_A1C')
        med_peso   = patient_data.get('peso')
        med_altura = patient_data.get('altura')
        med_imc    = patient_data.get('IMC')

        def _fmt_medida(v, unidade, casas=1):
            """Formata um valor antropométrico; trata None/NaN/0 como ausente."""
            if pd.notna(v):
                try:
                    fv = float(v)
                    if fv > 0:
                        return f"{fv:.{casas}f} {unidade}"
                except (ValueError, TypeError):
                    pass
            return "—"

        def _render_col_medida(titulo, valor_str):
            """Coluna 'Últimas 3 X' — um valor por linha (separados por ';'),
            o primeiro marcado como o mais recente."""
            st.write(f"**{titulo}**")
            partes = [p.strip() for p in str(valor_str).split(';') if p.strip()]
            for i, p in enumerate(partes):
                if i == 0:
                    st.markdown(
                        f"{p} <span style='color:#888; font-size:0.85em;'>"
                        f"(mais recente)</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.write(p)

        _tem_antropo = any(
            pd.notna(v) for v in (med_peso, med_altura, med_imc)
        )
        if (_tem_antropo or pd.notna(ultimas_pa)
                or pd.notna(ultimas_glicemias) or pd.notna(ultimas_a1c)):
            st.markdown("---")
            st.markdown("#### 📈 Últimas Medidas Registradas")

            col_antropo, col_pa, col_glic, col_a1c = st.columns(4)

            with col_antropo:
                st.write("**Antropometria:**")
                st.write(f"Último peso: {_fmt_medida(med_peso, 'kg', 1)}")
                st.write(f"Altura: {_fmt_medida(med_altura, 'm', 2)}")
                st.write(f"Último IMC: {_fmt_medida(med_imc, 'kg/m²', 1)}")

            with col_pa:
                if pd.notna(ultimas_pa):
                    _render_col_medida("Últimas 3 PA:", ultimas_pa)

            with col_glic:
                if pd.notna(ultimas_glicemias):
                    _render_col_medida("Últimas 3 glicemias:", ultimas_glicemias)

            with col_a1c:
                if pd.notna(ultimas_a1c):
                    _render_col_medida("Últimas 3 HbA1c:", ultimas_a1c)


        st.markdown("---")

        
        # ============================================
        # SUB-ABAS DETALHADAS
        # ============================================

        # A sub-aba 'Inércia terapêutica' só aparece para pacientes com
        # HAS e/ou DM (sinalizado pelo pipeline via status_atual_*).
        _mostrar_inercia = (
            pd.notna(patient_data.get('status_atual_HAS')) or
            pd.notna(patient_data.get('status_atual_DM'))
        )
        _tab_labels = [
            "📊 Carga de Morbidade",
            "❤️ Risco Cardiovascular",
            "🔄 Continuidade do Cuidado",
            "⚠️ Lacunas de Cuidado",
        ]
        if _mostrar_inercia:
            _tab_labels.append("⏱️ Inércia")
        _tab_labels += [
            "💊 Polifarmácia e STOPP-START",
            "📜 Histórico farmacológico",
            "📝 Relatar Problemas",
        ]
        # Render preguiçoso das sub-abas. st.tabs renderizava as 8
        # abas de TODO card sempre (numa lista de 20 cards = 160
        # renders de aba por página). Trocado por segmented_control:
        # só o bloco da aba selecionada executa (`if _aba_card ==`).
        _cpk_card = str(patient_data.get('cpf', ''))
        _aba_card = st.segmented_control(
            "Seção", _tab_labels, default=_tab_labels[0],
            key=f"{key_prefix}aba_card_{_cpk_card}",
            label_visibility="collapsed",
        )
        if not _aba_card:
            _aba_card = _tab_labels[0]

        # ========== TAB 1: CARGA DE MORBIDADE ==========
        if _aba_card == "📊 Carga de Morbidade":
            st.markdown("#### 📊 Carga de Morbidade")
            charlson_score_val = patient_data.get('charlson_score')
            charlson_mediana_val = patient_data.get('charlson_mediana')
            charlson_cat = patient_data.get('charlson_categoria')
            p_morb = patient_data.get('charlson_pontos_morbidades')
            p_idade_ch = patient_data.get('charlson_pontos_idade')
            p_poli = patient_data.get('charlson_pontos_polifarmacia')

            if pd.notna(charlson_score_val) and pd.notna(charlson_cat):
                score = int(charlson_score_val)
                pontos_texto = "ponto" if score == 1 else "pontos"
                texto = f"**Carga de Morbidade:** {score} {pontos_texto}"
                if pd.notna(charlson_mediana_val):
                    mediana = int(charlson_mediana_val)
                    med_txt = "ponto" if mediana == 1 else "pontos"
                    texto += f" (A mediana neste grupo etário é {mediana} {med_txt}.)"
                st.write(texto)
                st.write(f"**Categoria:** {charlson_cat}")

                # Composição da pontuação
                componentes = []
                if pd.notna(p_morb) and int(p_morb) > 0:
                    componentes.append(f"morbidades ({int(p_morb)} pts)")
                if pd.notna(p_idade_ch) and int(p_idade_ch) > 0:
                    idade_pac = patient_data.get('idade', '')
                    componentes.append(f"idade de {idade_pac} anos ({int(p_idade_ch)} pts)")
                if pd.notna(p_poli) and int(p_poli) > 0:
                    componentes.append(f"polifarmácia ({int(p_poli)} pts)")

                # Listar morbidades do paciente
                morbs_pac = extrair_morbidades_paciente(patient_data)
                morbidades_str = ', '.join(morbs_pac) if morbs_pac else ''

                st.markdown("---")
                st.markdown("**Informações que geraram a pontuação:**")
                detalhes = []
                if morbidades_str:
                    detalhes.append(morbidades_str)
                detalhes.extend(componentes)
                st.write(', '.join(detalhes) + '.')
            else:
                st.info("Carga de morbidade não calculada.")

        # ========== TAB 2: RISCO CARDIOVASCULAR ==========
        if _aba_card == "❤️ Risco Cardiovascular":
            from utils.risco_cv import (calcular_who_lab, calcular_who_nonlab,
                                        calcular_risco_completo, cor_categoria_who,
                                        cor_categoria_completa, classificar_risco_direto,
                                        icone_categoria_who)

            st.markdown("#### ❤️ Risco Cardiovascular — WHO HEARTS")

            who_risco = patient_data.get('who_risco_cvd_pct')
            who_cat = patient_data.get('who_categoria_risco')
            who_cat_simpl = patient_data.get('who_categoria_risco_simplificada')
            who_modelo = patient_data.get('who_modelo_utilizado')
            who_lab_calc = patient_data.get('who_lab_calculavel')
            who_nonlab_calc = patient_data.get('who_nonlab_calculavel')
            pac_idade = patient_data.get('idade')
            pac_genero = patient_data.get('genero', '')
            pac_pas = patient_data.get('pressao_sistolica')
            pac_col = patient_data.get('colesterol_total')
            pac_imc = patient_data.get('IMC')
            pac_dm = patient_data.get('DM') in [True, 1, '1', 'True']
            pac_irc = patient_data.get('IRC') in [True, 1, '1', 'True']
            pac_ci = patient_data.get('CI') in [True, 1, '1', 'True']
            pac_avc = patient_data.get('stroke') in [True, 1, '1', 'True']
            pac_dap = patient_data.get('vascular_periferica') in [True, 1, '1', 'True']
            pac_tabaco_registrado = pd.notna(patient_data.get('tabaco'))
            pac_tabaco_desconhecido = not pac_tabaco_registrado

            # Reclassificação direta (DCV, DM, IRC)
            reclass_direto = classificar_risco_direto(
                dm=pac_dm, irc=pac_irc, ci=pac_ci, avc=pac_avc, dap=pac_dap
            )

            # Função para exibir resultado do RCV
            def _mostrar_resultado_rcv(resultado, recalc=False):
                cat = resultado.get('categoria', '')
                cor_r = cor_categoria_completa(cat)
                icone = icone_categoria_who(cat)
                sufixo = " (recalculado)" if recalc else ""
                risco = resultado.get('risco_pct')
                modelo = resultado.get('modelo', '')
                motivo = resultado.get('motivo', '')

                if risco is not None:
                    titulo = f"{icone} Risco CV em 10 anos: {risco:.1f}%{sufixo}"
                else:
                    titulo = f"{icone} Risco CV: {cat}{sufixo}"

                detalhes = f"<p style='margin:5px 0 0 0; color:{cor_r};'><strong>Categoria: {cat}</strong></p>"
                if motivo:
                    detalhes += f"<p style='margin:5px 0 0 0; color:#666;'>Motivo: {motivo}</p>"
                if modelo:
                    detalhes += f"<p style='margin:2px 0 0 0; color:#999; font-size:0.85em;'>Modelo: {modelo}</p>"

                st.markdown(
                    f"<div style='background:{cor_r}20; border-left:6px solid {cor_r}; "
                    f"padding:16px; border-radius:8px; margin:8px 0;'>"
                    f"<h3 style='margin:0; color:{cor_r};'>{titulo}</h3>"
                    f"{detalhes}</div>",
                    unsafe_allow_html=True
                )

            cpk = patient_data.get('cpf', '')
            genero_pronome = "Esta paciente" if pac_genero and pac_genero.lower() in ('f','feminino') else "Este paciente"
            pac_peso = patient_data.get('peso')
            pac_altura = patient_data.get('altura')

            # Verificar faixa etária
            if pac_idade and (pac_idade < 40 or pac_idade > 80):
                st.warning(f"⚠️ Idade do paciente ({pac_idade} anos) fora da faixa WHO HEARTS (40-80 anos). Cálculo não disponível para esta faixa.")

            else:
                falta_pas = not pd.notna(pac_pas)
                falta_col = not pd.notna(pac_col)
                falta_imc = not pd.notna(pac_imc)
                falta_algo = falta_pas or falta_col or falta_imc or pac_tabaco_desconhecido

                col_esq, col_dir = st.columns([1, 1])

                # Resultado recalculado pelo usuário — persistido em
                # session_state para sobreviver a reruns subsequentes.
                # Aparece NA COLUNA DIREITA (junto ao formulário); a
                # esquerda continua mostrando o valor original do banco.
                _recalc_key = f"{key_prefix}rcv_recalc_{cpk}"
                _resultado_recalc = st.session_state.get(_recalc_key)

                # ── COLUNA ESQUERDA: Resultado original do datalake ──
                with col_esq:
                    # Mostrar reclassificação direta se aplicável
                    if reclass_direto:
                        _mostrar_resultado_rcv(reclass_direto)

                    # Mostrar WHO do banco se disponível (usa categoria
                    # simplificada PAHO/HEARTS). Quando há reclassificação
                    # direta, score WHO NÃO é exibido (não é o risco final).
                    cat_badge = who_cat_simpl if pd.notna(who_cat_simpl) and who_cat_simpl else None
                    if cat_badge and not reclass_direto:
                        who_res = {'risco_pct': who_risco if pd.notna(who_risco) else None,
                                   'categoria': cat_badge,
                                   'modelo': "Lab-based" if who_modelo == 'lab' else "Non-lab"}
                        _mostrar_resultado_rcv(who_res)
                    if cat_badge:
                        if pac_idade and pac_idade >= 70:
                            st.caption(
                                "**Nota ≥70 anos:** a idade domina o cálculo. "
                                "Considerar expectativa de vida, fragilidade e preferências."
                            )
                    elif not reclass_direto:
                        st.info("Score WHO não calculado — dados insuficientes.")

                    st.markdown("**Dados provenientes do datalake:**")
                    if pd.notna(pac_pas): st.write(f"✅ PAS: {int(pac_pas)} mmHg")
                    else: st.write("🔴 PAS: não informada")
                    if pd.notna(pac_col): st.write(f"✅ Colesterol: {int(pac_col)} mg/dL")
                    else: st.write("🔴 Colesterol: não disponível")
                    if pd.notna(pac_imc): st.write(f"✅ IMC: {pac_imc:.1f} kg/m²")
                    else: st.write(f"🔴 IMC: não calculável")
                    st.write(f"{'✅' if pac_dm else '⬜'} Diabetes: {'Sim' if pac_dm else 'Não'}")
                    if pac_tabaco_registrado: st.write("✅ Tabagismo: Sim (registrado)")
                    else: st.write("❓ Tabagismo: não informado")

                # ── COLUNA DIREITA: Formulário para dados faltantes ──
                with col_dir:
                    if falta_algo:
                        st.markdown("**Complete para calcular (ou recalcular):**")

                        input_pas = int(pac_pas) if pd.notna(pac_pas) else None
                        input_col = int(pac_col) if pd.notna(pac_col) else None
                        input_imc = float(pac_imc) if pd.notna(pac_imc) else None
                        input_tabaco = "Sim" if pac_tabaco_registrado else None

                        if falta_pas:
                            input_pas = st.number_input(
                                "PAS (mmHg)", min_value=80, max_value=250, value=130, step=1,
                                key=f"{key_prefix}rcv_pas_{cpk}")

                        if falta_col:
                            input_col = st.number_input(
                                "Colesterol total (mg/dL) — 0 se não souber",
                                min_value=0, max_value=500, value=0, step=1,
                                key=f"{key_prefix}rcv_col_{cpk}")

                        if falta_imc:
                            st.markdown("**Peso e altura:**")
                            ic1, ic2 = st.columns(2)
                            peso_default = float(pac_peso) if pd.notna(pac_peso) and pac_peso > 0 else 70.0
                            peso_clamp = max(30.0, min(300.0, peso_default))
                            alt_raw = int(float(pac_altura)*100) if pd.notna(pac_altura) and pac_altura > 0 else 165
                            alt_clamp = max(100, min(230, alt_raw))
                            with ic1:
                                input_peso = st.number_input(
                                    "Peso (kg)", min_value=30.0, max_value=300.0,
                                    value=peso_clamp,
                                    step=0.1, format="%.1f", key=f"{key_prefix}rcv_peso_{cpk}")
                            with ic2:
                                input_altura = st.number_input(
                                    "Altura (cm)", min_value=100, max_value=230,
                                    value=alt_clamp,
                                    step=1, key=f"{key_prefix}rcv_alt_{cpk}")
                            input_imc = round(input_peso / ((input_altura/100)**2), 1)
                            st.caption(f"IMC calculado: **{input_imc:.1f} kg/m²**")

                        if pac_tabaco_desconhecido:
                            input_tabaco = st.radio(
                                f"{genero_pronome} é tabagista?",
                                options=["Não", "Sim"], index=0,
                                key=f"{key_prefix}rcv_tab_{cpk}", horizontal=True)

                        if st.button(
                            "🧮 Calcular risco com estes valores",
                            key=f"{key_prefix}rcv_btn_{cpk}", type="primary",
                            use_container_width=True,
                        ):
                            genero_c = str(pac_genero).lower().strip() if pac_genero else ''
                            tab_c = (input_tabaco == "Sim") if input_tabaco else False
                            col_val = input_col if input_col and input_col > 0 else None
                            imc_val = input_imc if input_imc and input_imc > 0 else None
                            idade_c = int(pac_idade) if pd.notna(pac_idade) else None
                            pas_c = int(input_pas) if input_pas else None

                            resultado = calcular_risco_completo(
                                genero=genero_c, idade=idade_c,
                                pressao_sistolica=pas_c,
                                colesterol_total_mgdl=col_val,
                                imc=imc_val,
                                dm=pac_dm, tabaco=tab_c,
                                irc=pac_irc, ci=pac_ci, avc=pac_avc, dap=pac_dap,
                            )

                            if resultado:
                                st.session_state[_recalc_key] = resultado
                            else:
                                st.session_state.pop(_recalc_key, None)
                                falta_motivos = []
                                if not genero_c or genero_c not in ('m', 'f', 'masculino', 'feminino'):
                                    falta_motivos.append(f"gênero ('{pac_genero}' inválido)")
                                if idade_c is None or not (40 <= idade_c <= 80):
                                    falta_motivos.append(f"idade ({pac_idade}) fora da faixa 40-80")
                                if pas_c is None:
                                    falta_motivos.append("PAS")
                                if col_val is None and imc_val is None:
                                    falta_motivos.append("colesterol e IMC (ao menos um)")
                                motivo = "; ".join(falta_motivos) if falta_motivos else "dados insuficientes"
                                st.error(f"❌ Não foi possível calcular — {motivo}.")

                        # Lê o resultado da session_state (canônica) em
                        # vez de variável local — garante que a exibição
                        # capte o valor recém-gravado pelo clique no
                        # mesmo render, sem depender de continuidade de
                        # escopo entre blocos `with`/`if` aninhados.
                        _resultado_recalc = st.session_state.get(_recalc_key)

                        if _resultado_recalc:
                            st.markdown(
                                "<div style='margin-top:10px;'></div>",
                                unsafe_allow_html=True,
                            )
                            _mostrar_resultado_rcv(
                                _resultado_recalc, recalc=True,
                            )
                            if st.button(
                                "↺ Limpar recálculo",
                                key=f"{key_prefix}rcv_limpar_{cpk}",
                            ):
                                st.session_state.pop(_recalc_key, None)
                                st.rerun()
                    else:
                        st.success("✅ Todos os dados disponíveis no datalake.")
            

        
        # ========== TAB 3: CONTINUIDADE DO CUIDADO ==========
        if _aba_card == "🔄 Continuidade do Cuidado":

            # ── BLOCO 1: Frequência de Consultas ─────────────────
            st.markdown("#### 🗓️ Frequência de Consultas")
            fc1, fc2, fc3, fc4 = st.columns(4)

            dias_med  = patient_data.get('dias_desde_ultima_medica')
            dias_enf  = patient_data.get('dias_desde_ultima_enfermagem')
            dias_tec  = patient_data.get('dias_desde_ultima_tecnico_enfermagem')
            cons_365  = patient_data.get('consultas_365d')
            cons_med  = patient_data.get('consultas_medicas_365d')
            cons_enf  = patient_data.get('consultas_enfermagem_365d')
            cons_tec  = patient_data.get('consultas_tecnico_enfermagem_365d')
            meses_con = patient_data.get('meses_com_consulta_12m')
            regular   = patient_data.get('regularidade_acompanhamento')
            intervalo = patient_data.get('intervalo_mediano_dias')

            with fc1:
                with st.container(border=True):
                    st.caption("🩺 Última consulta médica")
                    v = format_dias_consulta(dias_med)
                    if pd.notna(dias_med):
                        cor = "🔴" if dias_med > 365 else ("🟠" if dias_med > 180 else "🟢")
                        st.markdown(f"**{cor} {v}**")
                        st.caption(f"{int(cons_med or 0)} consultas no último ano")
                    else:
                        st.markdown(f"**{v}**")

            with fc2:
                with st.container(border=True):
                    st.caption("💉 Última consulta de enfermagem")
                    v = format_dias_consulta(dias_enf)
                    if pd.notna(dias_enf):
                        cor = "🔴" if dias_enf > 365 else ("🟠" if dias_enf > 180 else "🟢")
                        st.markdown(f"**{cor} {v}**")
                        st.caption(f"{int(cons_enf or 0)} consultas no último ano")
                    else:
                        st.markdown(f"**{v}**")

            with fc3:
                with st.container(border=True):
                    st.caption("🩹 Última consulta técnico de enfermagem")
                    v = format_dias_consulta(dias_tec)
                    if pd.notna(dias_tec):
                        cor = "🔴" if dias_tec > 365 else ("🟠" if dias_tec > 180 else "🟢")
                        st.markdown(f"**{cor} {v}**")
                        st.caption(f"{int(cons_tec or 0)} consultas no último ano")
                    else:
                        st.markdown(f"**{v}**")

            with fc4:
                with st.container(border=True):
                    st.caption("📅 Regularidade do acompanhamento")
                    CORES_REG = {
                        'regular':            ('🟢', 'Regular'),
                        'irregular':          ('🟡', 'Irregular'),
                        'esporadico':         ('🟠', 'Esporádico'),
                        'sem_acompanhamento': ('🔴', 'Sem acompanhamento'),
                    }
                    emoji, label = CORES_REG.get(str(regular).lower(), ('⚪', str(regular) if regular else '—'))
                    st.markdown(f"**{emoji} {label}**")
                    if pd.notna(meses_con):
                        st.caption(f"{int(meses_con)} meses com consulta nos últimos 12")

            st.markdown("---")

            # ── BLOCO 2: Continuidade e Vínculo ──────────────────
            st.markdown("#### 🔗 Continuidade e Vínculo com a Equipe")
            cv1, cv2, cv3 = st.columns(3)

            pct_medico          = patient_data.get('pct_consultas_medico_365d')
            pct_na_unidade      = patient_data.get('pct_consultas_medicas_na_unidade_365d')
            pct_fora            = patient_data.get('pct_consultas_medicas_fora_365d')
            pct_enfermeiro      = patient_data.get('pct_consultas_enfermeiro_365d')
            baixa_long          = patient_data.get('baixa_longitudinalidade')
            perfil_cuidado      = patient_data.get('perfil_cuidado_365d')
            freq_urgencia       = patient_data.get('usuario_frequente_urgencia')

            PERFIL_LABEL = {
                'medico_centrado': (
                    '🩺', 'Médico-centrado',
                    '≥75% das consultas clínicas (médico + enfermeiro) foram '
                    'com o médico, ou o médico foi o único profissional clínico '
                    'no período. O técnico de enfermagem não entra nesta '
                    'classificação.'
                ),
                'enfermagem_centrado': (
                    '💉', 'Enfermagem-centrado',
                    '≥75% das consultas clínicas (médico + enfermeiro) foram '
                    'com o enfermeiro, ou o enfermeiro foi o único profissional '
                    'clínico no período. O técnico de enfermagem não entra nesta '
                    'classificação.'
                ),
                'compartilhado': (
                    '🤝', 'Cuidado compartilhado',
                    'Médico e enfermeiro participaram com pelo menos 25% das consultas cada. '
                    'Modelo de cuidado colaborativo entre os dois profissionais.'
                ),
                'sem_consultas': (
                    '⚪', 'Sem consultas clínicas',
                    'Nenhuma consulta com médico, enfermeiro ou técnico de enfermagem '
                    'foi registrada nos últimos 365 dias.'
                ),
                'indefinido': (
                    '❓', 'Perfil indefinido',
                    'Não foi possível classificar o perfil de cuidado com os dados disponíveis.'
                ),
            }

            with cv1:
                with st.container(border=True):
                    st.caption("🔄 Perfil de cuidado (últimos 365 dias)")

                    # Contagens absolutas (lidas no BLOCO 1 desta aba).
                    _n_med = int(cons_med) if pd.notna(cons_med) else 0
                    _n_enf = int(cons_enf) if pd.notna(cons_enf) else 0
                    _n_tec = int(cons_tec) if pd.notna(cons_tec) else 0
                    _n_clin = _n_med + _n_enf
                    _n_tot = (int(cons_365) if pd.notna(cons_365)
                              else _n_clin + _n_tec)

                    if _n_tot <= 0:
                        st.markdown(
                            "**⚪ Sem consultas registradas** nos últimos "
                            "365 dias."
                        )
                    else:
                        # ── Divisão 1: distribuição do TOTAL de consultas ──
                        _pct_clin = _n_clin / _n_tot * 100
                        _pct_tec  = _n_tec / _n_tot * 100
                        st.markdown(
                            f"<div style='font-size:0.9em; line-height:1.7;'>"
                            f"<b>{_pct_clin:.0f}%</b> com médico "
                            f"(<b>{_n_med}</b>) ou enfermeiro (<b>{_n_enf}</b>)"
                            f"<br>"
                            f"<b>{_pct_tec:.0f}%</b> com técnico de enfermagem "
                            f"(<b>{_n_tec}</b>)</div>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Total: {_n_tot} consultas em 365 dias.")

                        st.divider()

                        # ── Divisão 2: consultas CLÍNICAS → classificação ──
                        # Conclusão derivada das próprias consultas clínicas
                        # exibidas (médico vs. enfermeiro), para o rótulo
                        # seguir os números do card. Técnico não entra.
                        if _n_clin > 0:
                            _m_clin = _n_med / _n_clin * 100
                            _e_clin = _n_enf / _n_clin * 100
                            st.markdown(
                                f"<div style='font-size:0.9em; line-height:1.7;'>"
                                f"Das consultas <b>clínicas</b> "
                                f"(médico + enfermeiro):<br>"
                                f"🩺 médico <b>{_m_clin:.0f}%</b> · "
                                f"💉 enfermeiro <b>{_e_clin:.0f}%</b></div>",
                                unsafe_allow_html=True,
                            )
                            if _m_clin >= 75:
                                _pem, _plb = '🩺', 'Médico-centrado'
                            elif _e_clin >= 75:
                                _pem, _plb = '💉', 'Enfermagem-centrado'
                            else:
                                _pem, _plb = '🤝', 'Cuidado compartilhado'
                            st.markdown(f"➡️ **{_pem} {_plb}**")
                        else:
                            st.markdown(
                                "➡️ **⚪ Sem consultas clínicas** "
                                "(médico ou enfermeiro) no período."
                            )

                    if pd.notna(intervalo):
                        st.caption(
                            f"Intervalo mediano entre consultas: "
                            f"**{int(intervalo)} dias**"
                        )

            with cv2:
                with st.container(border=True):
                    st.caption("🏠 Longitudinalidade do cuidado")
                    # Longitudinalidade mede ONDE ocorrem as consultas médicas
                    # (na unidade vs. fora). Sem consulta médica no período não
                    # há vínculo a avaliar — não confundir ausência de sinal
                    # (baixa_longitudinalidade = False por falta de consultas)
                    # com vínculo preservado.
                    if _n_med <= 0:
                        st.markdown("**⚠️ Sem vínculo no período**")
                        st.caption(
                            "Nenhuma consulta médica registrada nos últimos "
                            "365 dias — não há longitudinalidade a avaliar. "
                            "A continuidade do cuidado está comprometida pela "
                            "ausência de contato com a equipe."
                        )
                    elif baixa_long in [True, 1, '1', 'True']:
                        st.markdown("**⚠️ Baixa longitudinalidade**")
                        st.caption(
                            "Mais de 50% das consultas médicas ocorreram **fora** da unidade "
                            "de referência do cadastro. Indica fragmentação do vínculo — "
                            "o paciente busca cuidado em outros locais com mais frequência."
                        )
                        if pd.notna(pct_na_unidade) and pd.notna(pct_fora):
                            st.markdown(
                                f"↳ **{pct_na_unidade:.0f}%** na unidade de referência  \n"
                                f"↳ **{pct_fora:.0f}%** fora da unidade"
                            )
                    else:
                        st.markdown("**✅ Longitudinalidade adequada**")
                        st.caption(
                            "A maioria das consultas médicas ocorre na própria unidade "
                            "de referência. Indica vínculo preservado com a equipe."
                        )
                        if pd.notna(pct_na_unidade):
                            st.markdown(f"↳ **{pct_na_unidade:.0f}%** das consultas na unidade")

            with cv3:
                with st.container(border=True):
                    st.caption("🚨 Uso de serviços de urgência")
                    cons_urg = patient_data.get('consultas_urgencia_365d')
                    dias_urg = patient_data.get('dias_desde_ultima_urgencia')
                    if freq_urgencia in [True, 1, '1', 'True']:
                        st.markdown("**🚨 Uso frequente de urgência**")
                        st.caption(
                            "3 ou mais atendimentos em UPA, CER ou hospital de urgência "
                            "nos últimos 365 dias. Pode indicar dificuldade de acesso "
                            "à atenção primária ou descompensação clínica recorrente."
                        )
                        if pd.notna(cons_urg):
                            st.markdown(f"↳ **{int(cons_urg)} atendimentos** em urgência no último ano")
                        if pd.notna(dias_urg):
                            st.markdown(f"↳ Último atendimento há **{int(dias_urg)} dias**")
                    else:
                        st.markdown("**✅ Sem uso frequente de urgência**")
                        st.caption("Menos de 3 atendimentos em urgência nos últimos 365 dias.")
                        if pd.notna(cons_urg) and cons_urg > 0:
                            st.markdown(f"↳ {int(cons_urg)} atendimento(s) no período")
                        elif pd.notna(cons_urg):
                            st.caption("Nenhum atendimento em urgência no período.")

            st.markdown("---")

            tempo_acomp = patient_data.get('dias_em_acompanhamento')
            if pd.notna(tempo_acomp):
                st.caption(f"Tempo em acompanhamento na unidade: **{format_tempo_acompanhamento(tempo_acomp)}**")
        
        # ========== TAB 4: LACUNAS DE CUIDADO ==========
        if _aba_card == "⚠️ Lacunas de Cuidado":
            if n_lacunas == 0:
                st.success("✅ **Nenhuma lacuna de cuidado identificada**")
            else:
                # Badge de gravidade pelo número de lacunas
                if n_lacunas >= 5:
                    st.error(f"🔴 **{n_lacunas} lacunas identificadas** — Atenção prioritária recomendada")
                elif n_lacunas >= 3:
                    st.warning(f"🟠 **{n_lacunas} lacunas identificadas** — Revisão clínica necessária")
                else:
                    st.warning(f"🟡 **{n_lacunas} lacuna(s) identificada(s)**")

                lacunas_por_grupo, flags = extrair_lacunas_paciente(patient_data)

                # Mostrar flags de controle (controlado, melhorando, piorando)
                if flags:
                    st.markdown("#### 📋 Status do Controle")
                    for flag in flags:
                        if "✅" in flag:
                            st.success(flag)
                        else:
                            st.warning(flag)
                    st.markdown("---")

                st.markdown("#### Lacunas Identificadas por Categoria")

                # Ordem de prioridade: prescrições inapropriadas primeiro (risco imediato),
                # depois falta de tratamento, por fim rastreio
                PRIORIDADE_GRUPOS = [
                    'Prescrições Inapropriadas',
                    'Cardiopatia Isquêmica (CI)',
                    'ICC e IRC (manejo clínico)',
                    'Fibrilação Atrial (FA)',
                    'Hipertensão (HAS)',
                    'Diabetes Mellitus (DM)',
                    'Rastreio',
                ]
                grupos_ordenados = sorted(
                    lacunas_por_grupo.keys(),
                    key=lambda g: PRIORIDADE_GRUPOS.index(g) if g in PRIORIDADE_GRUPOS else 99
                )

                ICONE_GRUPO = {
                    'Prescrições Inapropriadas':    '⚠️',
                    'Cardiopatia Isquêmica (CI)':   '❤️',
                    'ICC e IRC (manejo clínico)':   '💔',
                    'Fibrilação Atrial (FA)':       '⚡',
                    'Hipertensão (HAS)':            '🩺',
                    'Diabetes Mellitus (DM)':       '🍬',
                    'Rastreio':                     '🔍',
                }

                for grupo in grupos_ordenados:
                    lacunas_grupo = lacunas_por_grupo[grupo]
                    icone = ICONE_GRUPO.get(grupo, '📌')
                    # Prescrições inapropriadas abrem expandidas (risco imediato)
                    aberto = grupo == 'Prescrições Inapropriadas'
                    is_alerta = grupo == 'Prescrições Inapropriadas'
                    with st.expander(
                        f"{icone} {grupo} ({len(lacunas_grupo)})",
                        expanded=aberto
                    ):
                        for desc_lac, just_lac in lacunas_grupo:
                            titulo = f"**{desc_lac}**"
                            corpo = f"<span style='color:#666; font-size:0.9em;'>{just_lac}</span>" if just_lac else ""
                            bullet = "🔴" if is_alerta else "•"
                            st.markdown(
                                f"{bullet} {titulo}"
                                + (f"<br>&nbsp;&nbsp;&nbsp;{corpo}" if corpo else ""),
                                unsafe_allow_html=True
                            )

        # ========== TAB INÉRCIA (condicional, V3) ==========
        # O rótulo "⏱️ Inércia" só entra em _tab_labels quando
        # _mostrar_inercia é True — então a condição abaixo só pode
        # ser verdadeira para pacientes com HAS/DM avaliáveis.
        if _aba_card == "⏱️ Inércia":
            st.markdown("#### ⏱️ Inércia terapêutica")
            st.caption(
                "Em qual(is) tipo(s) de inércia este paciente está, "
                "e qual a frente de cuidado responsável por agir. "
                "A taxonomia separa **inércia clínica** (decisão "
                "médica diante do descontrole) de **inércia "
                "estrutural** (problemas anteriores: paciente "
                "sem prescrição, sem aferição, ou perdido da "
                "rede — antes do médico poder agir)."
            )
            _tem_has = _render_inercia_condicao(patient_data, 'HAS')
            _tem_dm  = _render_inercia_condicao(patient_data, 'DM')
            if not (_tem_has or _tem_dm):
                st.info("Paciente sem HAS nem DM avaliáveis pelo pipeline.")

        # ========== TAB 5: POLIFARMÁCIA E STOPP-START ==========
        if _aba_card == "💊 Polifarmácia e STOPP-START":
            cpf_pac  = str(patient_data.get("cpf", ""))
            idade_pac = int(patient_data.get("idade", 0) or 0)

            # Prioriza dados pré-buscados em lote (chamador fez
            # `buscar_*_lote` antes do loop). Se None, cai pra query
            # por-paciente — só ocorre em cenários sem batch.
            if dados_acb is None:
                with st.spinner("Carregando dados farmacológicos..."):
                    dados_acb = buscar_acb_paciente(cpf_pac)
            if dados_stopp is None:
                if idade_pac >= 60:
                    with st.spinner("Carregando dados farmacológicos..."):
                        dados_stopp = buscar_stopp_paciente(cpf_pac)
                else:
                    dados_stopp = {}
            dados_ss = dados_stopp

            # ── Nota sobre a janela temporal dos critérios ─────────
            st.info(
                "ℹ️ **Como interpretar estes critérios.** Os critérios "
                "STOPP/START/Beers referem-se a uma **janela de 365 "
                "dias**. Isso foi feito porque conseguimos saber quando "
                "um medicamento **entrou** na vida do paciente, mas não "
                "quando ele **saiu**. Por isso, é provável que vários "
                "critérios positivos já não existam mais — a medicação "
                "pode ter sido retirada. Use esta tela como um **guia "
                "para orientar a revisão das prescrições**, e não como "
                "um diagnóstico definitivo."
            )

            # ── 5 colunas ──────────────────────────────────────────
            c_rx, c_stopp, c_start, c_beers, c_acb = st.columns([2, 2, 2, 2, 1.5])

            # ════════════════════════════════════════════
            # COL 1 — PRESCRIÇÕES
            # ════════════════════════════════════════════
            with c_rx:
                st.markdown("##### 💊 Prescrições crônicas")
                meds_raw     = patient_data.get("medicamentos_cronicos", "") or ""
                acb_positivos = str(dados_acb.get("medicamentos_acb") or "")
                acb_dict = {}
                if acb_positivos:
                    for item in acb_positivos.split("|"):
                        partes = item.strip().split(":")
                        if len(partes) == 2:
                            acb_dict[partes[0].strip().upper()] = partes[1].strip()

                if meds_raw and str(meds_raw).strip():
                    meds_lista = [m.strip() for m in str(meds_raw).replace(";", "\n").split("\n") if m.strip()]
                    for med in meds_lista:
                        acb_val = next((v for k, v in acb_dict.items() if k in med.upper()), None)
                        if acb_val:
                            score = int(acb_val) if str(acb_val).isdigit() else 0
                            badge = f" `ACB {acb_val}` {'⚠️' if score >= 3 else '🔸'}"
                            st.markdown(f"• {med}{badge}")
                        else:
                            st.markdown(f"• {med}")
                else:
                    st.info("Sem prescrições.")

            # ════════════════════════════════════════════
            # MAPA DE CRITÉRIOS
            # ════════════════════════════════════════════
            STOPP_INFO = {
                "stopp_cv_001_365d":  ("Anti-hipert. central",       "Clonidina/Metildopa",    "HAS",            "Hipotensão ortostática e bradicardia. Alternativas disponíveis."),
                "stopp_cv_002_365d":  ("Alfa-bloqueador p/ HAS",     "Doxazosina/Prazosina",   "HAS",            "Risco de síncope e hipotensão ortostática."),
                "stopp_cv_003_365d":  ("Nifedipina imediata",        "Nifedipina cp comum",    "HAS / CI",       "Hipotensão reflexa. Usar liberação lenta."),
                "stopp_cv_004_365d":  ("Amiodarona 1ª linha FA",     "Amiodarona",             "FA sem ICC",     "Maior toxicidade que BB/digoxina/BCC."),
                "stopp_cv_005_365d":  ("BCC não-DHP + ICC",          "Verapamil/Diltiazem",    "ICC sistólica",  "Efeito inotrópico negativo — descompensa ICC."),
                "stopp_cv_006_365d":  ("Diurético alça p/ HAS",      "Furosemida",             "HAS sem ICC",    "Alternativas mais seguras disponíveis."),
                "stopp_cv_007_365d":  ("Dronedarona + ICC",          "Dronedarona",            "ICC",            "Aumenta mortalidade em ICC."),
                "stopp_cv_008_365d":  ("Digoxina + IRC grave",       "Digoxina",               "eGFR < 30",      "Toxicidade digitálica por acúmulo renal."),
                "stopp_cv_009_365d":  ("Dabigatrana + IRC grave",    "Dabigatrana",            "eGFR < 30",      "Risco de sangramento grave."),
                "stopp_cv_010":       ("Rivaroxabana + IRC grave",   "Rivaroxabana",           "eGFR < 15",      "Contraindicado — acúmulo."),
                "stopp_snc_001_365d": ("Benzodiazepínico",           "BZD (qualquer)",         "Idoso ≥65",      "Quedas, sedação, confusão, dependência."),
                "stopp_snc_002_365d": ("Hipnótico Z",                "Zolpidem/Zopiclona",     "Idoso ≥65",      "Mesmo risco de BZD para quedas."),
                "stopp_snc_003_365d": ("Tricíclico (TCA)",           "Amitriptilina...",       "Idoso ≥65",      "Cardiotóxico, anticolinérgico, risco de queda."),
                "stopp_snc_004_365d": ("TCA + demência",             "TCA (qualquer)",         "Demência",       "Piora cognitiva e risco de delirium."),
                "stopp_snc_005_365d": ("Paroxetina",                 "Paroxetina",             "Idoso ≥65",      "ISRS mais anticolinérgico. Usar alternativa."),
                "stopp_snc_006_365d": ("Antipsicótico típico",       "Haloperidol...",         "Idoso ≥65",      "Síndrome extrapiramidal, hipotensão, queda."),
                "stopp_snc_007_365d": ("Antipsicótico + Parkinson",  "Antipsicótico",          "Parkinson/Dem.", "Piora extrapiramidal. Risco de AVC."),
                "stopp_snc_008_365d": ("Metoclopramida + Parkinson", "Metoclopramida",         "Parkinson",      "Antagonista dopaminérgico — piora sintomas."),
                "stopp_snc_009_365d": ("Cascata biperideno",         "Biperideno",             "Em uso antipsic.","Cascata: antipsicótico → EPE → biperideno."),
                "stopp_snc_010_365d": ("Levodopa sem Parkinson",     "Levodopa/agonista",      "Sem Parkinson",  "Sem indicação estabelecida."),
                "stopp_snc_011_365d": ("Opioide forte sem indic.",   "Morfina/Oxicodona",      "Dor leve-mod.",  "1ª linha inadequada — não segue escada WHO."),
                "stopp_end_001_365d": ("Sulfonilureia longa ação",   "Glibenclamida",          "DM + idoso",     "Hipoglicemia prolongada — meia-vida longa."),
                "stopp_end_002_365d": ("Pioglitazona + ICC",         "Pioglitazona",           "ICC + DM",       "Retenção hídrica — exacerba ICC."),
                "stopp_end_003_365d": ("Metformina + IRC grave",     "Metformina",             "eGFR < 30",      "Risco de acidose lática."),
                "stopp_end_004_365d": ("Insulina escala móvel",      "Insulina regular",       "DM + idoso",     "Sem basal — risco de hipoglicemia."),
                "stopp_mus_001_365d": ("AINE + IRC",                 "AINEs",                  "eGFR < 50",      "Piora função renal."),
                "stopp_mus_002_365d": ("AINE + ICC",                 "AINEs",                  "ICC",            "Retenção hídrica — piora ICC."),
                "stopp_mus_003_365d": ("AINE + HAS descontr.",       "AINEs",                  "PAS ≥ 160",      "Antagoniza anti-hipertensivo."),
                "stopp_mus_004_365d": ("AINE + anticoagulante",      "AINEs",                  "Em anticoag.",   "Risco de sangramento GI."),
                "stopp_mus_005_365d": ("Corticoide crônico + AR",    "Prednisona",             "Artrite reum.",  "DMARDs são preferíveis."),
                "stopp_mus_006_365d": ("Relaxante muscular",         "Ciclobenzaprina",        "Idoso ≥65",      "Sedação e queda."),
                "stopp_acb_002_365d": ("Anti-histam. 1ª ger.",       "Prometazina/Hidroxizina","Idoso ≥65",      "Alta atividade anticolinérgica central."),
                "stopp_acb_003_365d": ("Anticolinérg. bexiga",       "Oxibutinina/Tolterodina","Idoso ≥65",      "Retenção urinária e piora cognitiva."),
                "stopp_acb_004_365d": ("Antiespasmódico GI",         "Hioscina/Buscopan",      "Idoso ≥65",      "Anticolinérgico — sedação e confusão."),
                "stopp_ren_001_365d": ("Gabapentinoide s/ ajuste",   "Gabapentina/Pregabalina","eGFR < 60",      "Dose precisa ajuste. Acúmulo → queda."),
                "stopp_ren_002_365d": ("Espironolactona + IRC",      "Espironolactona",        "eGFR < 30",      "Hipercalemia grave."),
                "stopp_ren_003_365d": ("Tramadol + IRC",             "Tramadol",               "eGFR < 30",      "Convulsão e sedação por acúmulo."),
            }

            START_INFO = {
                "start_cv_001_365d":  ("HAS s/ tratamento",    "Anti-hipertensivo",       "PAS ≥ 160",      "Principal causa evitável de AVC e IAM."),
                "start_cv_002_365d":  ("CI sem estatina",       "Estatina",                "Card. isquêmica","Reduz mortalidade CV comprovadamente."),
                "start_cv_003_365d":  ("DCV sem antiagregante plaquetário",  "AAS ou Clopidogrel",      "CI/AVC/DAP",     "Reduz eventos isquêmicos recorrentes."),
                "start_cv_004_365d":  ("ICC sem IECA/BRA",      "IECA ou BRA",             "ICC sistólica",  "Pilar do tratamento — reduz mortalidade."),
                "start_cv_005_365d":  ("FA sem anticoag.",      "Warfarina/DOAC",          "FA",             "Prevenção de AVC cardioembólico."),
                "start_cv_006_365d":  ("DM+IRC sem IECA/BRA",  "IECA ou BRA",             "DM + IRC",       "Retarda progressão da nefropatia."),
                "start_snc_001_365d": ("Parkinson s/ levo.",    "Levodopa/agonista",       "Parkinson",      "1ª linha — melhora função motora."),
                "start_snc_003_365d": ("Demência s/ iColin.",   "Donepezila/Rivastigmina", "Demência l-m",   "Melhora cognitiva modesta. Padrão de cuidado."),
                "start_resp_001_365d":("DPOC s/ broncodil.",    "Broncodilatador inalat.", "DPOC/Asma",      "Alívio sintomático e prevenção exacerbações."),
            }

            BEERS_INFO = {
                "beers_001_365d": ("Sulfonilureia (toda classe)","Gliclazida/Glipizida","DM ≥65",         "Beers expande: toda classe. Risco hipoglicemia."),
                "beers_002_365d": ("Warfarina em FA s/ DOAC",  "Warfarina",           "FA",              "DOACs preferíveis. SUS: indisponível na farm. popular."),
                "beers_003_365d": ("Rivaroxabana em FA",        "Rivaroxabana",        "FA",              "Apixabana tem melhor perfil em idosos com IRC."),
                "beers_004_365d": ("AAS prev. primária",        "AAS",                 "≥60 s/ DCV",      "Risco sangramento > benefício. USPSTF 2023."),
                "beers_005_365d": ("Antipsic. + epilepsia",     "Olanzapina/Clozapina","Epilepsia",       "Reduzem limiar convulsivo."),
                "beers_006_365d": ("Opioide + BZD",             "Opioide + BZD",       "Uso concomit.",   "Depressão respiratória sinérgica — overdose."),
                "beers_007_365d": ("ISRS + Tramadol",           "ISRS + Tramadol",     "Uso concomit.",   "Síndrome serotonérgica."),
            }

            # ════════════════════════════════════════════
            # COL 2 — STOPP
            # ════════════════════════════════════════════
            with c_stopp:
                stopp_ativos = {f: info for f, info in STOPP_INFO.items()
                                if dados_ss.get(f) is True}
                n_stopp = len(stopp_ativos)
                st.markdown(f"##### 🚫 STOPP ({n_stopp})")
                if idade_pac < 65:
                    st.caption("Critérios aplicam-se a ≥65 anos.")
                elif not stopp_ativos:
                    st.success("✅ Nenhum critério ativo.")
                else:
                    for flag, info in stopp_ativos.items():
                        nome_c, med, cond, just = info
                        sev = info[4] if len(info) > 4 else ""
                        cor = "🔴" if sev == "Alta" else "🟠" if sev == "Média" else "🟡"
                        st.markdown(f"**{cor} {nome_c}**")
                        st.caption(f"💊 {med} | 🏥 {cond}")
                        st.caption(f"_{just}_")
                        st.markdown("---")

                # Alertas compactos
                if dados_ss.get("alerta_queda_medicamentos"):
                    st.warning("⚠️ Risco de queda — verificar histórico.")
                if dados_ss.get("alerta_egfr_ausente_gabapentinoide"):
                    st.warning("⚠️ Gabapentinoide sem TFG — solicitar creatinina.")
                if dados_ss.get("alerta_egfr_ausente_metformina"):
                    st.warning("⚠️ Metformina sem TFG — solicitar creatinina.")
                if dados_ss.get("alerta_cascata_biperideno"):
                    st.warning("⚠️ Cascata biperideno — rever antipsicótico.")

            # ════════════════════════════════════════════
            # COL 3 — START
            # ════════════════════════════════════════════
            with c_start:
                start_ativos = {f: info for f, info in START_INFO.items()
                                if dados_ss.get(f) is True}
                n_start = len(start_ativos)
                st.markdown(f"##### ❌ START ({n_start})")
                if idade_pac < 65:
                    st.caption("Critérios aplicam-se a ≥65 anos.")
                elif not start_ativos:
                    st.success("✅ Nenhuma omissão.")
                else:
                    for flag, info in start_ativos.items():
                        nome_c, med_ind, cond, just = info
                        st.markdown(f"**❌ {nome_c}**")
                        st.caption(f"✅ {med_ind} | 🏥 {cond}")
                        st.caption(f"_{just}_")
                        st.markdown("---")

            # ════════════════════════════════════════════
            # COL 4 — BEERS
            # ════════════════════════════════════════════
            with c_beers:
                beers_ativos = {f: info for f, info in BEERS_INFO.items()
                                if dados_ss.get(f) is True}
                n_beers = len(beers_ativos)
                st.markdown(f"##### 🔵 Beers ({n_beers})")
                if idade_pac < 60:
                    st.caption("Critérios aplicam-se a ≥60 anos.")
                elif not beers_ativos:
                    st.success("✅ Nenhum critério ativo.")
                else:
                    for flag, info in beers_ativos.items():
                        nome_c, med, cond, just = info
                        st.markdown(f"**🔵 {nome_c}**")
                        st.caption(f"💊 {med} | 🏥 {cond}")
                        st.caption(f"_{just}_")
                        st.markdown("---")

                if dados_ss.get("alerta_warfarina_fa"):
                    st.info("ℹ️ Warfarina em FA — verificar se DOAC foi tentado.")

            # ════════════════════════════════════════════
            # COL 5 — ACB
            # ════════════════════════════════════════════
            with c_acb:
                st.markdown("##### 🔴 ACB")

                def _acb_ponto(v):
                    return None if (v is None or pd.isna(v)) else int(v)

                def _parse_meds_acb(s):
                    """'Hioscina N(3); Dexclorfeniramina(3)' →
                    [('Hioscina N', 3), ('Dexclorfeniramina', 3)]."""
                    out = []
                    if not s or str(s).strip().lower() == 'nan':
                        return out
                    for item in str(s).split(';'):
                        item = item.strip()
                        if item.endswith(')') and '(' in item:
                            nome = item[:item.rfind('(')].strip()
                            try:
                                sc = int(item[item.rfind('(') + 1:-1].strip())
                            except ValueError:
                                continue
                            if nome:
                                out.append((nome, sc))
                    return out

                acb_total = dados_acb.get("score_acb_total")
                cat_acb   = dados_acb.get("categoria_acb", "—")

                # 1) Escore nos últimos 180 dias = acb_180d (ponto-no-tempo).
                # NULL = sem prescrição na janela (≠ 0) → "sem registro".
                _acb180 = _acb_ponto(patient_data.get("acb_180d"))
                if _acb180 is None:
                    st.metric("Escore nos últimos 180 dias", "—")
                    st.caption("Sem registro de prescrição na janela de 180 dias.")
                else:
                    _c180 = "🔴" if _acb180 >= 3 else "🟠" if _acb180 >= 1 else "🟢"
                    st.metric("Escore nos últimos 180 dias", f"{_c180} {_acb180}")

                # 2) Medicamentos que somam o escore (prescrição atual).
                # A quebra por medicamento só existe para a prescrição atual
                # (medicamentos_acb), não por janela temporal.
                _meds_acb = _parse_meds_acb(dados_acb.get("medicamentos_acb"))
                if _meds_acb:
                    st.markdown("**Anticolinérgicos na prescrição atual**")
                    _lin = []
                    for _nome, _sc in sorted(_meds_acb, key=lambda x: -x[1]):
                        _corm = ("#C62828" if _sc >= 3 else
                                 "#E69138" if _sc >= 1 else "#2E7D32")
                        _lin.append(
                            f"<div style='font-size:0.85em; margin:2px 0;'>"
                            f"<b style='color:{_corm};'>{_sc}</b> · {_nome}</div>"
                        )
                    st.markdown("".join(_lin), unsafe_allow_html=True)
                    if acb_total is not None:
                        st.caption(f"Soma (prescrição atual): ACB {int(float(acb_total))}")

                    # 3) Quais medicamentos com ACB ≥ 3
                    _altos = [n for n, s in _meds_acb if s >= 3]
                    if _altos:
                        st.markdown(f"**Com ACB ≥ 3:** {', '.join(_altos)}")
                elif acb_total is None and _acb180 is None:
                    st.info("Sem dados ACB.")

                if cat_acb and cat_acb != "—":
                    st.caption(f"Categoria: `{cat_acb}`")

                # 4) Evolução do ACB (janelas 365/180/90 — o "atual" já
                # está no topo). Ponto-no-tempo da prescrição-âncora;
                # NULL = sem prescrição na banda (≠ 0), sempre "sem registro".
                _serie_acb = [
                    ("≈365d", patient_data.get("acb_365d"), patient_data.get("n_meds_365d")),
                    ("≈180d", patient_data.get("acb_180d"), patient_data.get("n_meds_180d")),
                    ("≈90d",  patient_data.get("acb_90d"),  patient_data.get("n_meds_90d")),
                ]
                st.markdown("**📈 Evolução do ACB**")
                if all(_acb_ponto(v) is None for _r, v, _n in _serie_acb):
                    st.caption("Sem registro de ACB nas janelas de 90/180/365 dias.")
                else:
                    st.caption(
                        "Escore da prescrição mais próxima de cada janela "
                        "(ponto no tempo, não soma acumulada)."
                    )
                    _linhas_acb = []
                    for _rot, _val, _nm in _serie_acb:
                        _v = _acb_ponto(_val)
                        if _v is None:
                            _linhas_acb.append(
                                f"<div style='font-size:0.85em; margin:2px 0;'>"
                                f"<b>{_rot}:</b> <span style='color:#9CA3AF;'>"
                                f"sem registro na janela</span></div>"
                            )
                        else:
                            _cor = ("#C62828" if _v >= 3 else
                                    "#E69138" if _v >= 1 else "#2E7D32")
                            _nmv = _acb_ponto(_nm)
                            _nmtxt = (
                                f" <span style='color:#9CA3AF;'>· {_nmv} "
                                f"med(s)</span>" if _nmv is not None else ""
                            )
                            _linhas_acb.append(
                                f"<div style='font-size:0.85em; margin:2px 0;'>"
                                f"<b>{_rot}:</b> "
                                f"<b style='color:{_cor};'>ACB {_v}</b>"
                                f"{_nmtxt}</div>"
                            )
                    st.markdown("".join(_linhas_acb), unsafe_allow_html=True)

                # 5) Caixa de alerta — baseada no escore da prescrição atual
                # (acb_score_total), que é o que tem carga de medicamento.
                if acb_total is not None:
                    _acbf = float(acb_total)
                    if _acbf >= 3:
                        st.error(
                            "⚠️ **Carga anticolinérgica clinicamente significativa** "
                            "(ACB ≥ 3). Risco aumentado de confusão mental, "
                            "delirium e quedas — especialmente em idosos."
                        )
                    elif _acbf >= 1:
                        st.warning("Carga presente — monitorar sintomas cognitivos.")
                    else:
                        st.success("Sem carga anticolinérgica significativa.")

        # ========== TAB HISTÓRICO FARMACOLÓGICO (730d) ==========
        if _aba_card == "📜 Histórico farmacológico":
            st.markdown("#### 📜 Histórico farmacológico — últimos 730 dias")

            n_dist_730 = patient_data.get('n_meds_distintos_730d')
            if pd.notna(n_dist_730):
                st.caption(
                    f"**{int(n_dist_730)} medicamentos distintos** "
                    f"prescritos nos últimos 730 dias."
                )

            n_agudos_rec = patient_data.get('n_agudos_recorrentes')
            lista_agudos_rec = patient_data.get('lista_agudos_recorrentes')
            if pd.notna(n_agudos_rec) and int(n_agudos_rec) >= 2:
                st.warning(
                    f"⚠️ **{int(n_agudos_rec)} agudos recorrentes** "
                    f"(≥2 prescrições em 180 dias — possível "
                    f"'agudo virando crônico')"
                )
                if lista_agudos_rec and pd.notna(lista_agudos_rec):
                    st.markdown(f"**Lista:** {lista_agudos_rec}")

            historico_730 = patient_data.get('historico_medicamentos_730d')
            if not historico_730 or pd.isna(historico_730):
                st.info(
                    "Sem histórico de prescrições registrado nos últimos "
                    "730 dias."
                )
            else:
                items_hist = parse_historico_medicamentos(historico_730)
                if not items_hist:
                    st.info("Não foi possível parsear o histórico.")
                    with st.expander("Ver texto bruto"):
                        st.text(historico_730)
                else:
                    df_hist = pd.DataFrame(items_hist)

                    # Converte colunas numéricas para Int64 nullable
                    # (None vira pd.NA — evita TypeError no sort).
                    for _col_num in ('N', '1ª há (d)', 'Recente há (d)'):
                        df_hist[_col_num] = pd.to_numeric(
                            df_hist[_col_num], errors='coerce'
                        ).astype('Int64')

                    # Ordena por "Recente há (d)" asc (mais recentes primeiro);
                    # NaN no fim.
                    df_hist = df_hist.sort_values(
                        'Recente há (d)', ascending=True, na_position='last'
                    ).reset_index(drop=True)

                    # Highlights:
                    #   CRONICO sem prescrição recente → vermelho-claro
                    #   AGUDO com N >= 2               → laranja-claro
                    def _row_color(row):
                        tipo = row.get('Tipo', '')
                        status = row.get('Status', '')
                        n_val = row.get('N')
                        if tipo == 'CRONICO' and status == 'Sem prescrição recente':
                            return ['background-color: #fde2e2'] * len(row)
                        if (tipo == 'AGUDO' and n_val is not None
                                and not pd.isna(n_val) and int(n_val) >= 2):
                            return ['background-color: #ffe9d2'] * len(row)
                        return [''] * len(row)

                    styled = df_hist.style.apply(_row_color, axis=1)
                    st.dataframe(
                        styled, hide_index=True, use_container_width=True
                    )

                    st.caption(
                        "🔴 Linha vermelha: medicamento crônico sem prescrição "
                        "recente (>180d). 🟠 Linha laranja: medicamento agudo "
                        "com prescrições recorrentes (≥2 em 180d)."
                    )

                    with st.expander("Ver texto bruto"):
                        st.text(historico_730)

        # ========== TAB 7: RELATAR PROBLEMA ==========
        if _aba_card == "📝 Relatar Problemas":
            usuario_logado = st.session_state.get('usuario_global', {})
            formulario_relato(patient_data_original, usuario_logado, key_prefix=key_prefix)
                
        


# ============================================
# FUNÇÃO PÚBLICA — RENDERIZA A LISTA DE PACIENTES
# ============================================
def renderizar_lista_pacientes(
    area: str = None,
    clinica: str = None,
    esf: str = None,
    scope: str = "lp",
    incluir_sidebar: bool = True,
):
    """
    Renderiza a interface completa da Lista Nominal de Pacientes.

    Quando incluir_sidebar=True (uso na page Meus_Pacientes), os
    seletores de AP/Clínica/ESF aparecem na sidebar e definem o
    território. Quando incluir_sidebar=False (uso embarcado, ex.:
    aba em Visao_ESF), os parâmetros area/clinica/esf são usados
    diretamente.
    """
    # Chave de paginação por escopo (cada caller tem sua própria página atual)
    pag_key = f"{scope}_pagina_atual"
    if pag_key not in st.session_state:
        st.session_state[pag_key] = 0

    # ============================================
    # INTERFACE PRINCIPAL
    # ============================================

    # Título em linha única (economia de altura).
    st.markdown("## 👥 Meus Pacientes — 📖 Lista Nominal de Pacientes")
    st.markdown("---")

    if incluir_sidebar:
        # SIDEBAR - FILTROS CASCATA
        st.sidebar.header("🔍 Filtros")
        mostrar_badge_anonimo()
        st.sidebar.info("⚠️ Obrigatório selecionar: Área, Clínica e ESF")

        df_options = load_filter_options_cascata()

        if df_options.empty:
            st.error("Não foi possível carregar opções de filtro")
            return

        # Inicializar session_state
        if 'area_selecionada' not in st.session_state:
            st.session_state.area_selecionada = None
        if 'clinica_selecionada' not in st.session_state:
            st.session_state.clinica_selecionada = None
        if 'esf_selecionada' not in st.session_state:
            st.session_state.esf_selecionada = None
        if 'faixa_idade' not in st.session_state:
            st.session_state.faixa_idade = (0, 120)
        if 'morbidades_selecionadas' not in st.session_state:
            st.session_state.morbidades_selecionadas = []

        # Filtro Área
        areas_disponiveis = sorted(df_options['area_programatica_cadastro'].dropna().unique().tolist())

        area_index = 0
        if st.session_state.area_selecionada:
            try:
                area_index = areas_disponiveis.index(st.session_state.area_selecionada) + 1
            except:
                area_index = 0

        area_selecionada = st.sidebar.selectbox(
            "Área Programática: *",
            options=[None] + areas_disponiveis,
            format_func=lambda x: "Selecione..." if x is None else anonimizar_ap(str(x)),
            key="area_select",
            index=area_index
        )
        st.session_state.area_selecionada = area_selecionada

        # Filtro Clínica
        if area_selecionada:
            df_filtrado_area = load_filter_options_cascata(area=area_selecionada)
            if not df_filtrado_area.empty and 'nome_clinica_cadastro' in df_filtrado_area.columns:
                clinicas_disponiveis = sorted(df_filtrado_area['nome_clinica_cadastro'].dropna().unique().tolist())
            else:
                clinicas_disponiveis = []
        else:
            clinicas_disponiveis = []

        clinica_index = 0
        if st.session_state.clinica_selecionada and clinicas_disponiveis:
            try:
                clinica_index = clinicas_disponiveis.index(st.session_state.clinica_selecionada) + 1
            except:
                clinica_index = 0

        clinica_selecionada = st.sidebar.selectbox(
            "Clínica da Família: *",
            options=[None] + clinicas_disponiveis,
            format_func=lambda x: "Selecione..." if x is None else anonimizar_clinica(x),
            key="clinica_select",
            disabled=not area_selecionada,
            index=clinica_index if clinicas_disponiveis else 0
        )
        st.session_state.clinica_selecionada = clinica_selecionada

        # Filtro ESF
        if area_selecionada and clinica_selecionada:
            df_filtrado_clinica = load_filter_options_cascata(area=area_selecionada, clinica=clinica_selecionada)
            if not df_filtrado_clinica.empty and 'nome_esf_cadastro' in df_filtrado_clinica.columns:
                esfs_disponiveis = sorted(df_filtrado_clinica['nome_esf_cadastro'].dropna().unique().tolist())
            else:
                esfs_disponiveis = []
        else:
            esfs_disponiveis = []

        esf_index = 0
        if st.session_state.esf_selecionada and esfs_disponiveis:
            try:
                esf_index = esfs_disponiveis.index(st.session_state.esf_selecionada) + 1
            except:
                esf_index = 0

        esf_selecionada = st.sidebar.selectbox(
            "ESF: *",
            options=[None] + esfs_disponiveis,
            format_func=lambda x: "Selecione..." if x is None else anonimizar_esf(x),
            key="esf_select",
            disabled=not clinica_selecionada,
            index=esf_index if esfs_disponiveis else 0
        )
        st.session_state.esf_selecionada = esf_selecionada

        # Verificar filtros obrigatórios
        if not area_selecionada:
            st.warning("⚠️ Selecione uma Área Programática")
            return

        if not clinica_selecionada:
            st.warning("⚠️ Selecione uma Clínica da Família")
            return

        if not esf_selecionada:
            st.warning("⚠️ Selecione uma ESF")
            return
    else:
        # Modo embarcado — território vem dos parâmetros da função.
        if not (area and clinica and esf):
            st.warning("⚠️ Território não informado para a lista de pacientes.")
            return
        area_selecionada = area
        clinica_selecionada = clinica
        esf_selecionada = esf
        # Inicializar defaults usados pelos filtros do corpo principal
        if 'faixa_idade' not in st.session_state:
            st.session_state.faixa_idade = (0, 120)
        if 'morbidades_selecionadas' not in st.session_state:
            st.session_state.morbidades_selecionadas = []

    # ═══════════════════════════════════════════════════════════════
    # FILTROS — linha única de 5 colunas. Cada coluna empilha seus
    # widgets na vertical. Os controles de 'ordenar por' ficam
    # distribuídos junto dos filtros relacionados (3 deles); os
    # outros 3 ficam na 5ª coluna.
    # ═══════════════════════════════════════════════════════════════
    g1, g2, g3, g4, g5 = st.columns(5)

    with g1:
        st.markdown("**👤 Identificação**")
        busca_nome_input = st.text_input(
            "Buscar por nome",
            value=st.session_state.get('busca_nome_input', ''),
            placeholder="Nome do paciente...",
            key="busca_nome_input",
        )
        faixa_idade = st.slider(
            "Faixa etária",
            min_value=0, max_value=120,
            value=st.session_state.faixa_idade,
            step=1, key="idade_slider",
        )
        st.session_state.faixa_idade = faixa_idade
        _sexo_opcoes = {"Todos": None, "Feminino": "F", "Masculino": "M"}
        _sexo_sel = st.selectbox(
            "Sexo", options=list(_sexo_opcoes.keys()), key="sexo_filtro")
        genero_filtro = _sexo_opcoes[_sexo_sel]
        st.markdown("**🎯 Priorização**")
        ipc_filtro = st.multiselect(
            "IPC — priorização do cuidado",
            options=["Crítico", "Alto", "Moderado", "Baixo"],
            default=[], placeholder="Todos",
            help="Categoria do Índice de Priorização do Cuidado "
                 "(IPC): combina Carga de Morbidade, lacunas, dias "
                 "sem médico, ACB e STOPP. Crítico ≥0,75; Alto "
                 "0,50–0,74; Moderado 0,25–0,49; Baixo <0,25.",
            key="ipc_filtro",
        )

    with g2:
        st.markdown("**🏥 Condições clínicas**")
        morbidades_selecionadas = st.multiselect(
            "🦠 Morbidades",
            options=LISTA_MORBIDADES,
            default=st.session_state.morbidades_selecionadas,
            placeholder="Todas",
            key="morb_select",
        )
        st.session_state.morbidades_selecionadas = morbidades_selecionadas
        # Morbidades sempre combinadas com E (todas) — operador fixo,
        # sem widget de escolha (decisão de UX: OU não é necessário).
        operador_morb = "AND"
        ordem_opcoes = {
            "↓ Mais morbidades primeiro": ("morbidades", "desc"),
            "↑ Menos morbidades primeiro": ("morbidades", "asc"),
        }
        ord1 = st.selectbox(
            "↕️ Ordenar por morbidades",
            options=list(ordem_opcoes.keys()), key="ord_morb")
        carga_morb_filtro = st.multiselect(
            "📊 Carga de morbidade",
            options=["Muito Alto", "Alto", "Moderado", "Baixo"],
            default=[], placeholder="Todas", key="carga_morb_filtro",
        )
        rcv_filtro = st.multiselect(
            "❤️ Risco Cardiovascular",
            options=["Baixo", "Moderado", "Alto", "Muito alto", "Crítico", "Não calculado"],
            default=[], placeholder="Todos",
            help="'Não calculado' = pacientes elegíveis (40-80 anos) sem DM/IRC/DCV estabelecida e sem colesterol nem IMC para o cálculo.",
            key="rcv_filtro",
        )

    with g3:
        st.markdown("**💊 Farmacológico**")
        apenas_insulina = st.checkbox(
            "💉 Em uso de insulina",
            value=False, key="apenas_insulina_filter",
            help="Qualquer tipo: NPH, regular, análogos basal/prandial e misturas.",
        )
        apenas_polifarmacia = st.checkbox(
            "💊 Em polifarmácia (≥5)",
            value=False, key="apenas_polifarmacia_filter",
            help="5 ou mais medicamentos crônicos em uso (definição do indicador populacional).",
        )
        apenas_hiperpolifarmacia = st.checkbox(
            "💊 Em hiperpolifarmácia (≥10)",
            value=False, key="apenas_hiperpolifarmacia_filter",
            help="10 ou mais medicamentos crônicos em uso (definição do indicador populacional).",
        )
        apenas_stopp = st.checkbox(
            "⚠️ Com critério STOPP/START",
            value=False, key="apenas_stopp_filter",
            help="Pacientes com ao menos um critério STOPP (prescrição potencialmente inapropriada) ou START (omissão de tratamento indicado) ativo.",
        )
        acb_filtro = st.multiselect(
            "🔴 Carga anticolinérgica (ACB)",
            options=["MUITO_ALTO", "ALTO", "MODERADO", "BAIXO"],
            default=[], placeholder="Todas", key="acb_filtro",
            help="Categoria de carga anticolinérgica acumulada das prescrições do paciente.",
        )
        ord_presc_opcoes = {
            "— Não ordenar": None,
            "↓ Mais dias sem prescrição": ("dias_prescricao", "desc"),
            "↑ Menos dias sem prescrição": ("dias_prescricao", "asc"),
        }
        ord3 = st.selectbox(
            "↕️ Ordenar por dias sem prescrição",
            options=list(ord_presc_opcoes.keys()), key="ord_presc")

    with g4:
        st.markdown("**⚠️ Lacunas e inércia**")
        grupo_lacuna_sel = st.selectbox(
            "Grupo de lacunas",
            options=["Todos"] + GRUPOS_LACUNAS_ORDENADOS,
            key="grupo_lacuna_filtro",
        )
        if grupo_lacuna_sel == "Todos":
            lacunas_disp = [(k, desc) for k, (grupos, desc, _) in LACUNAS_COMPLETO.items()]
        else:
            lacunas_disp = [(k, desc) for k, (grupos, desc, _) in LACUNAS_COMPLETO.items()
                            if grupo_lacuna_sel in grupos]
        lacunas_selecionadas = st.multiselect(
            "Filtrar por lacunas",
            options=[k for k, _ in lacunas_disp],
            format_func=lambda k: dict(lacunas_disp).get(k, k),
            default=[], placeholder="Todas", key="lacunas_filtro",
        )
        apenas_inercia_clinica = st.checkbox(
            "🩺 Inércia clínica (HAS/DM)",
            value=False, key="apenas_inercia_clinica_filter",
            help="Pacientes com descontrole confirmado e esquema mantido "
                 "(INERCIA_PERSISTENTE) ou que descontrolaram agora sem "
                 "ação registrada (DESCONTROLE_RECENTE_SEM_ACAO). Frente "
                 "de decisão médica — avaliar adesão e intensificar.",
        )
        apenas_inercia_estrutural = st.checkbox(
            "🏠 Inércia estrutural (HAS/DM)",
            value=False, key="apenas_inercia_estrutural_filter",
            help="Pacientes sem prescrição em 365 dias (busca ativa pelo "
                 "ACS), em tratamento mas sem aferição/exame recente "
                 "(equipe afere) ou nunca aferidos em 730 dias (voando "
                 "cego). Frente de organização do cuidado pela equipe.",
        )
        ord_medico_opcoes = {
            "— Não ordenar": None,
            "↓ Mais dias sem médico": ("dias_medico", "desc"),
            "↑ Menos dias sem médico": ("dias_medico", "asc"),
        }
        ord2 = st.selectbox(
            "↕️ Ordenar por dias sem médico",
            options=list(ord_medico_opcoes.keys()), key="ord_med")

    with g5:
        st.markdown("**↕️ Ordenar por**")
        ord_acb_opcoes = {
            "— Não ordenar": None,
            "↓ Maior ACB primeiro": ("acb", "desc"),
            "↑ Menor ACB primeiro": ("acb", "asc"),
        }
        ord4 = st.selectbox("🔴 Score ACB", options=list(ord_acb_opcoes.keys()), key="ord_acb")
        ord_rcv_opcoes = {
            "— Não ordenar": None,
            "↓ Maior risco primeiro": ("rcv", "desc"),
            "↑ Menor risco primeiro": ("rcv", "asc"),
        }
        ord5 = st.selectbox("❤️ Risco CV", options=list(ord_rcv_opcoes.keys()), key="ord_rcv")
        ord_nph_opcoes = {
            "— Não ordenar": None,
            "↓ Maior dose NPH/kg primeiro": ("dose_nph", "desc"),
            "↑ Menor dose NPH/kg primeiro": ("dose_nph", "asc"),
        }
        ord6 = st.selectbox("💉 Dose NPH (UI/kg)", options=list(ord_nph_opcoes.keys()), key="ord_nph")

    # Determinar ordenação (prioridade: dose NPH > rcv > médico > prescrição > ACB > morbidades)
    if ord_nph_opcoes[ord6]:
        ordenar_por = "dose_nph"
        ordem = ord_nph_opcoes[ord6][1]
    elif ord_rcv_opcoes[ord5]:
        ordenar_por = "rcv"
        ordem = ord_rcv_opcoes[ord5][1]
    elif ord_medico_opcoes[ord2]:
        ordenar_por = ord_medico_opcoes[ord2][0]
        ordem = ord_medico_opcoes[ord2][1]
    elif ord_presc_opcoes[ord3]:
        ordenar_por = ord_presc_opcoes[ord3][0]
        ordem = ord_presc_opcoes[ord3][1]
    elif ord_acb_opcoes[ord4]:
        ordenar_por = "acb"
        ordem = ord_acb_opcoes[ord4][1]
    else:
        ordenar_por = "morbidades"
        ordem = ordem_opcoes[ord1][1]

    busca_nome_raw = busca_nome_input.strip() if busca_nome_input else None
    # No modo anônimo, a busca é feita no DataFrame (após anonimização), não no SQL
    busca_nome_sql = busca_nome_raw if (busca_nome_raw and not MODO_ANONIMO) else None
    busca_nome_local = busca_nome_raw if (busca_nome_raw and MODO_ANONIMO) else None

    # Se busca mudou, volta para página 1
    busca_anterior_key = f"{scope}_busca_nome_anterior"
    if busca_anterior_key not in st.session_state:
        st.session_state[busca_anterior_key] = None
    if busca_nome_raw != st.session_state[busca_anterior_key]:
        st.session_state[pag_key] = 0
        st.session_state[busca_anterior_key] = busca_nome_raw

    # ÁREA PRINCIPAL - PAGINAÇÃO
    estatisticas = get_statistics_summary(
        area=area_selecionada,
        clinica=clinica_selecionada,
        esf=esf_selecionada,
        idade_min=faixa_idade[0],
        idade_max=faixa_idade[1]
    )

    total_pacientes = count_total_patients(
        area=area_selecionada,
        clinica=clinica_selecionada,
        esf=esf_selecionada,
        idade_min=faixa_idade[0],
        idade_max=faixa_idade[1],
        morbidades=morbidades_selecionadas,
        operador_morb=operador_morb,
        busca_nome=busca_nome_sql,
        carga_morb=tuple(carga_morb_filtro) if carga_morb_filtro else None,
        lacunas_filtro=tuple(lacunas_selecionadas) if lacunas_selecionadas else None,
        rcv_filtro=tuple(rcv_filtro) if rcv_filtro else None,
        apenas_insulina=apenas_insulina,
        apenas_inercia_clinica=apenas_inercia_clinica,
        apenas_inercia_estrutural=apenas_inercia_estrutural,
        genero_filtro=genero_filtro,
        apenas_polifarmacia=apenas_polifarmacia,
        apenas_hiperpolifarmacia=apenas_hiperpolifarmacia,
        acb_filtro=tuple(acb_filtro) if acb_filtro else None,
        apenas_stopp=apenas_stopp,
    )

    if total_pacientes == 0:
        st.warning("⚠️ Nenhum paciente encontrado com os filtros aplicados")
        return

    PACIENTES_POR_PAGINA = 20
    total_paginas = (total_pacientes + PACIENTES_POR_PAGINA - 1) // PACIENTES_POR_PAGINA

    if pag_key not in st.session_state:
        st.session_state[pag_key] = 0

    pagina_atual = st.session_state[pag_key]

    filtros_texto = f"Área: {anonimizar_ap(area_selecionada)} | Clínica: {anonimizar_clinica(clinica_selecionada)} | ESF: {anonimizar_esf(esf_selecionada)}"
    if morbidades_selecionadas:
        filtros_texto += f" | Morbidades: {len(morbidades_selecionadas)}"
    if carga_morb_filtro:
        filtros_texto += f" | Carga: {', '.join(carga_morb_filtro)}"
    if lacunas_selecionadas:
        filtros_texto += f" | Lacunas: {len(lacunas_selecionadas)}"
    if rcv_filtro:
        filtros_texto += f" | RCV: {', '.join(rcv_filtro)}"
    if ipc_filtro:
        filtros_texto += f" | IPC: {', '.join(ipc_filtro)}"
    if apenas_insulina:
        filtros_texto += " | 💉 Em insulina"
    if apenas_inercia_clinica:
        filtros_texto += " | 🩺 Inércia clínica"
    if apenas_inercia_estrutural:
        filtros_texto += " | 🏠 Inércia estrutural"
    if genero_filtro:
        filtros_texto += f" | Sexo: {'Feminino' if genero_filtro == 'F' else 'Masculino'}"
    if apenas_polifarmacia:
        filtros_texto += " | 💊 Polifarmácia"
    if apenas_hiperpolifarmacia:
        filtros_texto += " | 💊 Hiperpolifarmácia"
    if acb_filtro:
        filtros_texto += f" | ACB: {', '.join(acb_filtro)}"
    if apenas_stopp:
        filtros_texto += " | ⚠️ STOPP/START"

    # Placeholders para o cabeçalho de "X pacientes encontrados" e
    # caption de paginação. Serão preenchidos depois do load para
    # refletir filtros locais (IPC / busca anônima) que só são
    # aplicados no Python, depois do SQL.
    header_placeholder  = st.empty()
    estat_placeholder   = st.empty()
    caption_placeholder = st.empty()

    estat_placeholder.success(
        f"**{estatisticas['total']} pacientes cadastrados | "
        f"{estatisticas['multimorbidos']} multimórbidos | "
        f"{estatisticas['polifarmacia']} em polifarmácia**"
    )

    offset = pagina_atual * PACIENTES_POR_PAGINA

    # IPC é calculado em Python (em load_patient_data_paginated, após
    # o SQL). Para filtrar por categoria de IPC precisamos carregar
    # tudo e filtrar localmente — mesmo padrão da busca anônima.
    filtragem_local = bool(busca_nome_local) or bool(ipc_filtro)

    with st.spinner(f"Carregando página {pagina_atual + 1}..."):
        if filtragem_local:
            # Carrega tudo (até 5000) e aplica filtros locais.
            df_pacientes = load_patient_data_paginated(
                area=area_selecionada,
                clinica=clinica_selecionada,
                esf=esf_selecionada,
                idade_min=faixa_idade[0],
                idade_max=faixa_idade[1],
                morbidades=morbidades_selecionadas,
                operador_morb=operador_morb,
                ordem=ordem,
                offset=0,
                limit=5000,
                carga_morb=tuple(carga_morb_filtro) if carga_morb_filtro else None,
                ordenar_por=ordenar_por,
                lacunas_filtro=tuple(lacunas_selecionadas) if lacunas_selecionadas else None,
                rcv_filtro=tuple(rcv_filtro) if rcv_filtro else None,
                apenas_insulina=apenas_insulina,
                apenas_inercia_clinica=apenas_inercia_clinica,
                apenas_inercia_estrutural=apenas_inercia_estrutural,
                genero_filtro=genero_filtro,
                apenas_polifarmacia=apenas_polifarmacia,
                apenas_hiperpolifarmacia=apenas_hiperpolifarmacia,
                acb_filtro=tuple(acb_filtro) if acb_filtro else None,
                apenas_stopp=apenas_stopp,
            )
            # Filtro de IPC (categoria já vem calculada em
            # load_patient_data_paginated via calcular_ipc).
            if ipc_filtro and not df_pacientes.empty \
               and 'ipc_categoria' in df_pacientes.columns:
                df_pacientes = df_pacientes[
                    df_pacientes['ipc_categoria'].isin(ipc_filtro)
                ]
            # Busca por nome no modo anônimo
            if busca_nome_local and not df_pacientes.empty \
               and 'nome' in df_pacientes.columns:
                df_pacientes['nome_anon'] = df_pacientes.apply(
                    lambda r: anonimizar_nome(
                        str(r.get('cpf') or r.get('nome', '')),
                        r.get('genero', '')
                    ), axis=1
                )
                df_pacientes = df_pacientes[
                    df_pacientes['nome_anon'].str.lower().str.contains(busca_nome_local.lower(), na=False)
                ]
                df_pacientes = df_pacientes.drop(columns=['nome_anon'])
            total_pacientes = len(df_pacientes)
            total_paginas = max(1, (total_pacientes + PACIENTES_POR_PAGINA - 1) // PACIENTES_POR_PAGINA)
            pagina_atual = min(pagina_atual, total_paginas - 1)
            df_pacientes = df_pacientes.iloc[offset:offset + PACIENTES_POR_PAGINA]
        else:
            df_pacientes = load_patient_data_paginated(
                area=area_selecionada,
                clinica=clinica_selecionada,
                esf=esf_selecionada,
                idade_min=faixa_idade[0],
                idade_max=faixa_idade[1],
                morbidades=morbidades_selecionadas,
                operador_morb=operador_morb,
                ordem=ordem,
                offset=offset,
                limit=PACIENTES_POR_PAGINA,
                busca_nome=busca_nome_sql,
                carga_morb=tuple(carga_morb_filtro) if carga_morb_filtro else None,
                ordenar_por=ordenar_por,
                lacunas_filtro=tuple(lacunas_selecionadas) if lacunas_selecionadas else None,
                rcv_filtro=tuple(rcv_filtro) if rcv_filtro else None,
                apenas_insulina=apenas_insulina,
                apenas_inercia_clinica=apenas_inercia_clinica,
                apenas_inercia_estrutural=apenas_inercia_estrutural,
                genero_filtro=genero_filtro,
                apenas_polifarmacia=apenas_polifarmacia,
                apenas_hiperpolifarmacia=apenas_hiperpolifarmacia,
                acb_filtro=tuple(acb_filtro) if acb_filtro else None,
                apenas_stopp=apenas_stopp,
            )

    if df_pacientes.empty:
        # Quando filtros locais (IPC / busca anônima) zeram o
        # resultado, total_pacientes já foi recalculado para 0 acima.
        # Atualiza o header para refletir.
        if filtragem_local:
            header_placeholder.markdown(
                f"**📊 0 pacientes encontrados** | {filtros_texto}"
            )
        st.warning("⚠️ Nenhum paciente encontrado" + (" para a busca informada." if busca_nome_raw else "."))
        return

    # Atualiza o header com o total real (pós-filtros locais quando
    # aplicável) e a caption de paginação.
    header_placeholder.markdown(
        f"**📊 {total_pacientes:,} pacientes encontrados** | {filtros_texto}"
    )
    if morbidades_selecionadas:
        # Morbidades sempre combinadas com E (operador fixo).
        if len(morbidades_selecionadas) == 1:
            morb_texto = morbidades_selecionadas[0]
        elif len(morbidades_selecionadas) == 2:
            morb_texto = f"{morbidades_selecionadas[0]} e {morbidades_selecionadas[1]}"
        else:
            morb_texto = ", ".join(morbidades_selecionadas[:-1]) + f" e {morbidades_selecionadas[-1]}"
        caption_placeholder.caption(
            f"Mostrando {total_pacientes} pacientes com {morb_texto} | "
            f"Página {pagina_atual + 1} de {total_paginas}"
        )
    else:
        caption_placeholder.caption(
            f"Página {pagina_atual + 1} de {total_paginas}"
        )

    # Botões de navegação (topo)
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])

    with col_nav1:
        if st.button("⬅️ Anterior", disabled=pagina_atual == 0,
                     key=f"{scope}_btn_prev_top"):
            st.session_state[pag_key] = max(0, pagina_atual - 1)
            st.rerun()

    with col_nav2:
        st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Página {pagina_atual + 1} de {total_paginas}</div>", unsafe_allow_html=True)

    with col_nav3:
        if st.button("Próxima ➡️", disabled=pagina_atual >= total_paginas - 1,
                     key=f"{scope}_btn_next_top"):
            st.session_state[pag_key] = min(total_paginas - 1, pagina_atual + 1)
            st.rerun()

    st.markdown("---")

    # Exibir cards
    st.markdown("### 👥 Pacientes")

    # Pré-busca farmacológica em lote (1 query ACB + 1 STOPP p/ todos
    # os pacientes da página, em vez de 2 queries por card). Reduz de
    # ~20 queries seriais para 2 quando a página tem 10 pacientes —
    # bottleneck principal da renderização da lista.
    _cpfs_pagina = tuple(
        str(p.get('cpf', '')) for _, p in df_pacientes.iterrows() if p.get('cpf')
    )
    _cpfs_idosos = tuple(
        str(p.get('cpf', '')) for _, p in df_pacientes.iterrows()
        if p.get('cpf') and int(p.get('idade', 0) or 0) >= 60
    )
    _mapa_acb   = buscar_acb_lote(_cpfs_pagina)
    _mapa_stopp = buscar_stopp_lote(_cpfs_idosos)

    for idx, (_, paciente) in enumerate(df_pacientes.iterrows()):
        paciente_dict = paciente.to_dict()
        _cpf = str(paciente_dict.get('cpf', ''))
        create_patient_card(
            paciente_dict, key_prefix=f"{scope}_",
            dados_acb=_mapa_acb.get(_cpf, {}),
            dados_stopp=_mapa_stopp.get(_cpf, {}),
        )

    # Botões de navegação (rodapé)
    st.markdown("---")
    col_nav4, col_nav5, col_nav6 = st.columns([1, 2, 1])

    with col_nav4:
        if st.button("⬅️ Página Anterior", disabled=pagina_atual == 0,
                     key=f"{scope}_btn_prev_bottom"):
            st.session_state[pag_key] = max(0, pagina_atual - 1)
            st.rerun()

    with col_nav5:
        st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Página {pagina_atual + 1} de {total_paginas}</div>", unsafe_allow_html=True)

    with col_nav6:
        if st.button("Próxima Página ➡️", disabled=pagina_atual >= total_paginas - 1,
                     key=f"{scope}_btn_next_bottom"):
            st.session_state[pag_key] = min(total_paginas - 1, pagina_atual + 1)
            st.rerun()

    # Rodapé
    st.markdown("---")
    st.caption("SMS-RJ | Navegador Clínico")
