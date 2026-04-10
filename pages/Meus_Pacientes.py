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
from streamlit_option_menu import option_menu
from utils.auth import exibir_usuario_logado
from utils import theme as T

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Meus Pacientes",
    page_icon="🧑‍⚕️",
    layout="wide"
)

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']

# Extrair dados do usuário
if isinstance(usuario_logado, dict):
    nome = usuario_logado.get('nome_completo', 'Usuário')
    esf = usuario_logado.get('esf') or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

# ═══════════════════════════════════════════════════════════════
# 🎨 CABEÇALHO CONSISTENTE
# ═══════════════════════════════════════════════════════════════

# Esconder o menu lateral nativo do Streamlit
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
    if esf != 'N/A':
        info_lines.append(f"ESF: {esf}")
    if clinica != 'N/A':
        info_lines.append(f"Clínica: {clinica}")
    if ap != 'N/A':
        info_lines.append(f"AP: {ap}")

    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: {T.TEXT}; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Pacientes"   # ← essa linha NÃO muda — cada arquivo tem o seu valor
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

ICONES_MENU = [
    "house-fill",               # Home
    "people-fill",              # População
    "person-lines-fill",        # Pacientes
    "exclamation-triangle-fill",# Lacunas
    "arrow-repeat",             # Continuidade
    "capsule",                  # Polifarmácia
    "droplet-fill",             # Diabetes
    "heart-pulse-fill",         # Hipertensão
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


# ============================================
# CONFIGURAÇÃO DE TEMA (página já configurada no início)
# ============================================



# Inicializar estados
if 'pagina_atual' not in st.session_state:
    st.session_state.pagina_atual = 0

CORES = {
    'background': T.BG,
    'secondary_bg': T.SECONDARY_BG,
    'text': T.TEXT,
    'primary': T.PRIMARY,
    'card_bg': T.CARD_BG,
    'border': T.BORDER,
    'input_bg': T.BG,
    'input_text': T.TEXT,
}

# CSS customizado com tema
st.markdown(f"""
    <style>
        /* Tema geral */
        .stApp {{
            background-color: {CORES['background']};
            color: {CORES['text']};
        }}
        
        /* Força cores corretas em TODOS os textos da sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {CORES['secondary_bg']} !important;
        }}
        
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] span:not([data-baseweb="tag"]) {{
            color: {CORES['text']} !important;
        }}
        
        /* Corrige labels específicos de widgets */
        .stSelectbox label,
        .stMultiSelect label,
        .stSlider label,
        .stRadio label,
        .stNumberInput label,
        .stTextInput label {{
            color: {CORES['text']} !important;
        }}
        
        /* Corrige texto dentro dos selectboxes */
        .stSelectbox [data-baseweb="select"] > div:first-child,
        .stMultiSelect [data-baseweb="select"] > div:first-child {{
            background-color: {CORES['input_bg']} !important;
        }}
        
        .stSelectbox [data-baseweb="select"] span,
        .stMultiSelect [data-baseweb="select"] span {{
            color: {CORES['input_text']} !important;
        }}
        
        /* Corrige dropdown menus */
        [data-baseweb="popover"] {{
            background-color: {CORES['input_bg']} !important;
        }}
        
        ul[role="listbox"] li {{
            color: {CORES['input_text']} !important;
            background-color: {CORES['input_bg']} !important;
        }}
        
        ul[role="listbox"] li:hover {{
            background-color: {CORES['border']} !important;
        }}
        
        /* Corrige slider */
        .stSlider > div > div > div > div {{
            color: {CORES['text']} !important;
        }}
        
        /* Corrige radio buttons */
        .stRadio > div label {{
            color: {CORES['text']} !important;
        }}
        
        /* Cards e expanders */
        .streamlit-expanderHeader {{
            background-color: {CORES['card_bg']} !important;
            border: 1px solid {CORES['border']} !important;
            color: {CORES['text']} !important;
        }}
        
        div[data-testid="stExpander"] {{
            background-color: {CORES['secondary_bg']};
            border: 1px solid {CORES['border']};
            color: {CORES['text']};
        }}
        
        /* Multiselect tags */
        span[data-baseweb="tag"] {{
            background-color: {CORES['primary']} !important;
            color: white !important;
        }}
        
        /* Info boxes */
        .stAlert {{
            color: {CORES['text']} !important;
        }}
    </style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES BIGQUERY ADAPTADAS
# ============================================

def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"

@st.cache_data(show_spinner=False, ttl=900)
def bq_query(sql: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
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
    'Doença da Tireoide': 'tireoide',
    
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

LACUNAS_COMPLETO = {
    # === CONTROLE DE PRESSÃO ARTERIAL (5) ===
    'lacuna_rastreio_PA_adulto': ('PA', 'Adulto sem rastreamento de PA (>365d)'),
    'lacuna_PA_hipertenso_180d': ('PA', 'Hipertenso sem aferição de PA (>180d)'),
    'lacuna_HAS_descontrolado_menor80': ('PA', 'HAS descontrolado <80a (≥140/90)'),
    'lacuna_HAS_descontrolado_80mais': ('PA', 'HAS descontrolado ≥80a (≥150/90)'),
    'lacuna_DM_HAS_PA_descontrolada': ('PA', 'DM+HAS com PA >135/80'),
    
    # === CONTROLE GLICÊMICO (4) ===
    'lacuna_DM_sem_HbA1c_recente': ('Glicemia', 'DM sem HbA1c recente (>180d)'),
    'lacuna_DM_descontrolado': ('Glicemia', 'DM descontrolado (HbA1c acima da meta)'),
    'lacuna_rastreio_DM_hipertenso': ('Glicemia', 'Hipertenso sem rastreio de DM (>365d)'),
    'lacuna_rastreio_DM_45mais': ('Glicemia', 'Adulto ≥45a sem rastreio de DM (>3a)'),
    
    # === EXAMES LABORATORIAIS (7) ===
    'lacuna_creatinina_HAS_DM': ('Exames', 'HAS/DM sem creatinina (365d)'),
    'lacuna_colesterol_HAS_DM': ('Exames', 'HAS/DM sem colesterol (365d)'),
    'lacuna_eas_HAS_DM': ('Exames', 'HAS/DM sem EAS (365d)'),
    'lacuna_ecg_HAS_DM': ('Exames', 'HAS/DM sem ECG (365d)'),
    'lacuna_DM_hba1c_nao_solicitado': ('Exames', 'DM sem HbA1c solicitado (365d)'),
    'lacuna_DM_microalbuminuria_nao_solicitado': ('Exames', 'DM sem microalbuminúria (365d)'),
    'lacuna_IMC_HAS_DM': ('Exames', 'HAS/DM sem IMC calculável'),
    
    # === PREVENÇÃO DE COMPLICAÇÕES DO DIABETES (3) ===
    'lacuna_DM_sem_exame_pe_365d': ('Complicações DM', 'DM sem exame do pé (>365d)'),
    'lacuna_DM_sem_exame_pe_180d': ('Complicações DM', 'DM sem exame do pé (>180d)'),
    'lacuna_DM_nunca_teve_exame_pe': ('Complicações DM', 'DM nunca teve exame do pé'),
    
    # === CARDIOPATIA ISQUÊMICA (4) ===
    'lacuna_CI_sem_AAS': ('CI', 'CI sem AAS/anticoagulante'),
    'lacuna_CI_sem_estatina_alta': ('CI', 'CI sem estatina alta intensidade'),
    'lacuna_CI_sem_estatina_qualquer': ('CI', 'CI sem qualquer estatina'),
    'lacuna_CI_ICC_sem_BB': ('CI', 'CI+ICC sem betabloqueador'),
    
    # === INSUFICIÊNCIA CARDÍACA - FALTA DE MEDICAMENTOS (5) ===
    'lacuna_ICC_sem_SGLT2': ('ICC', 'ICC sem SGLT-2'),
    'lacuna_ICC_sem_IECA_BRA': ('ICC', 'ICC sem IECA/BRA'),
    'lacuna_ICC_sem_INRA': ('ICC', 'ICC sem INRA (Sacubitril)'),
    'lacuna_ICC_sem_ARM': ('ICC', 'ICC sem ARM (Espironolactona)'),
    'lacuna_ICC_sem_SRAA_e_sem_hidralazina_nitrato': ('ICC', 'ICC sem SRAA nem H+N'),
    
    # === USO INADEQUADO/CONTRAINDICADO (5) ===
    'lacuna_IECA_BRA_concomitante': ('Uso Inadequado', '⚠️ IECA + BRA concomitante'),
    'lacuna_ICC_INRA_IECA_concomitante': ('Uso Inadequado', '⚠️ ICC: INRA + IECA (perigoso)'),
    'lacuna_ICC_uso_BCC_nao_DHP': ('Uso Inadequado', '⚠️ ICC + BCC não-DHP (contraindicado)'),
    'lacuna_ICC_uso_AINE': ('Uso Inadequado', '⚠️ ICC + AINE crônico'),
    'lacuna_diur_alca_sem_ICC': ('Uso Inadequado', '⚠️ Diurético de alça sem ICC'),
    
    # === IRC E DM COMPLICADO (2) ===
    'lacuna_IRC_sem_SGLT2': ('IRC/DM Complicado', 'IRC sem SGLT-2'),
    'lacuna_DM_complicado_sem_SGLT2': ('IRC/DM Complicado', 'DM+ICC/IRC/CI sem SGLT-2'),
    
    # === FIBRILAÇÃO ATRIAL (3) ===
    'lacuna_FA_sem_anticoagulacao': ('FA', 'FA sem anticoagulação'),
    'lacuna_FA_sem_controle_FC': ('FA', 'FA sem controle de FC'),
    'lacuna_FA_ICC_sem_digoxina': ('FA', 'FA+ICC sem digoxina'),
    
    # === ALERTA DE QUALIDADE (1) ===
    'HAS_sem_CID': ('Alerta', '⚠️ HAS sem CID registrado'),
}

# Flags positivos (não são lacunas, mas indicadores úteis)
FLAGS_POSITIVOS = {
    'DM_controlado': '✅ DM controlado',
    'DM_melhorando': '✅ DM melhorando',
}

FLAGS_ALERTA = {
    'DM_piorando': '⚠️ DM piorando',
}

# Grupos para organização na UI
GRUPOS_LACUNAS = {
    'PA': '🩺 Controle de Pressão Arterial',
    'Glicemia': '🩸 Controle Glicêmico',
    'Exames': '🔬 Exames Laboratoriais',
    'Complicações DM': '🦶 Prevenção de Complicações do Diabetes',
    'CI': '❤️ Cardiopatia Isquêmica',
    'ICC': '💔 Insuficiência Cardíaca',
    'Uso Inadequado': '⚠️ Uso Inadequado de Medicamentos',
    'IRC/DM Complicado': '🫘 IRC e Diabetes Complicado',
    'FA': '⚡ Fibrilação Atrial',
    'Alerta': '📋 Alertas de Qualidade',
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
    busca_nome=None
):
    """Carrega pacientes com paginação e filtros"""

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
    
    where_sql = " AND ".join(where_clauses)
    order_sql = "DESC" if ordem == "desc" else "ASC"
    
    # Construir SELECT com TODAS as morbidades convertidas para boolean
    morbidades_select = []
    for nome_portugues, col_ingles in MORBIDADES_MAP.items():
        alias = col_ingles
        morbidades_select.append(f"CASE WHEN {col_ingles} IS NOT NULL THEN TRUE ELSE FALSE END as {alias}")
    
    # Construir SELECT com TODAS as lacunas
    lacunas_select = []
    for campo_lacuna, (grupo, descricao) in LACUNAS_COMPLETO.items():
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
      percentual_risco_final,
      categoria_risco_final,
      variaveis_usadas_calculo,
      variaveis_ausentes_calculo,
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
      acb_score_total,
      categoria_acb,
      COALESCE(alerta_acb_idoso, FALSE) AS alerta_acb_idoso,
      ultimas_tres_PA,
      ultimas_tres_glicemias,
      ultimas_tres_A1C,
      -- TODAS as morbidades
      {', '.join(morbidades_select)},
      -- TODAS as lacunas e flags
      {', '.join(lacunas_select)}
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE {where_sql}
    ORDER BY total_morbidades {order_sql}
    LIMIT {limit} OFFSET {offset}
    """
    
    return bq_query(sql)

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
        stopp_acb_001_365d, stopp_acb_002_365d, stopp_acb_003_365d,
        stopp_acb_004_365d,
        stopp_ren_001_365d, stopp_ren_002_365d, stopp_ren_003_365d,
        -- START individuais (365d)
        start_cv_001_365d, start_cv_002_365d, start_cv_003_365d,
        start_cv_004_365d, start_cv_005_365d, start_cv_006_365d,
        start_snc_001_365d, start_snc_002_365d, start_snc_003_365d,
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
    return df.iloc[0].to_dict()


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
    return df.iloc[0].to_dict()

@st.cache_data(show_spinner=False, ttl=900)
def count_total_patients(area=None, clinica=None, esf=None, idade_min=None, idade_max=None, morbidades=None, operador_morb="OR", busca_nome=None):
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
    
    # Processar lacunas
    for campo_lacuna, (grupo, descricao) in LACUNAS_COMPLETO.items():
        valor = patient_data.get(campo_lacuna)
        
        if valor in [True, 1, '1', 'True', 'true', 'TRUE']:
            if grupo not in lacunas_por_grupo:
                lacunas_por_grupo[grupo] = []
            lacunas_por_grupo[grupo].append(descricao)
    
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

def create_patient_card(patient_data):

    # ✅ ANONIMIZAR DADOS (ADICIONAR ESTA LINHA)
    patient_data = anonimizar_paciente(patient_data)

    nome = patient_data.get('nome', 'Nome não informado')
    idade = patient_data.get('idade', 'N/A')
    n_morbidades = patient_data.get('N_morbidades', 0)
    n_medicamentos = patient_data.get('qtd_medicamentos_cronicos', 0)
    
    # Contar lacunas TRUE
    n_lacunas = sum(1 for campo, (grupo, desc) in LACUNAS_COMPLETO.items() 
                    if patient_data.get(campo) in [True, 1, '1', 'True'])
    
    # Processar morbidades
    if pd.isna(n_morbidades):
        morbidades_texto = "0 morbidades"
        n_morbidades = 0
    else:
        n_morbidades = int(n_morbidades)
        if n_morbidades == 0:
            morbidades_texto = "0 morbidades"
        elif n_morbidades == 1:
            morbidades_texto = "1 morbidade"
        else:
            morbidades_texto = f"{n_morbidades} morbidades"
    
    # Processar medicamentos
    if pd.isna(n_medicamentos):
        medicamentos_texto = "0 medicamentos"
    else:
        n_medicamentos = int(n_medicamentos)
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

    titulo_card = f"👤 **{nome}** - {idade} anos | 🏥 {morbidades_texto} | 💊 {medicamentos_texto}{acb_texto} | ⚠️ {lacunas_texto}"
    
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
            n_morb = int(n_morbidades) if not pd.isna(n_morbidades) else 0
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
                
                # Linha 3: última prescrição
                if pd.notna(dias_prescricao) and dias_prescricao != 9999:
                    dias = int(float(dias_prescricao))
                    st.write(f"Última prescrição há {dias} dias")

        


        # Últimas Medidas (linha completa abaixo)
        ultimas_pa = patient_data.get('ultimas_tres_PA')
        ultimas_glicemias = patient_data.get('ultimas_tres_glicemias')
        ultimas_a1c = patient_data.get('ultimas_tres_A1C')
            
        if pd.notna(ultimas_pa) or pd.notna(ultimas_glicemias) or pd.notna(ultimas_a1c):
            st.markdown("---")
            st.markdown("#### 📈 Últimas Medidas Registradas")
                
            col_pa, col_glic, col_a1c = st.columns(3)
                
            with col_pa:
                if pd.notna(ultimas_pa):
                    st.write(f"**Últimas 3 PA:**")
                    st.write(ultimas_pa)
                
            with col_glic:
                if pd.notna(ultimas_glicemias):
                    st.write(f"**Últimas 3 glicemias:**")
                    st.write(ultimas_glicemias)
                
            with col_a1c:
                if pd.notna(ultimas_a1c):
                    st.write(f"**Últimas 3 HbA1c:**")
                    st.write(ultimas_a1c)


        st.markdown("---")

        
        # ============================================
        # SUB-ABAS DETALHADAS
        # ============================================

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 Carga de Morbidade e Risco CV",
            "🔄 Continuidade do Cuidado",
            "⚠️ Lacunas de Cuidado",
            "💊 Polifarmácia e STOPP-START",
            "📈 Inércia Terapêutica",
            "📝 Relatar Problemas"
        ])

        
        # ========== TAB 1: CARGA DE MORBIDADE E RISCO CV ==========
        with tab1:
            col_a, col_b = st.columns(2)


            with col_a:
                st.markdown("#### 📊 Carga de Morbidade")
                
                charlson_score = patient_data.get('charlson_score')
                charlson_mediana = patient_data.get('charlson_mediana')
                charlson_cat = patient_data.get('charlson_categoria')
                
                if pd.notna(charlson_score) and pd.notna(charlson_cat):
                    # Converter para int para exibição
                    score = int(charlson_score)
                    
                    # Texto base com plural/singular correto
                    pontos_texto = "ponto" if score == 1 else "pontos"
                    
                    # Montar texto principal
                    texto_principal = f"**Carga de Morbidade:** {score} {pontos_texto}"
                    
                    # Adicionar informação da mediana se disponível
                    if pd.notna(charlson_mediana):
                        mediana = int(charlson_mediana)
                        mediana_texto = "ponto" if mediana == 1 else "pontos"
                        texto_principal += f" (A mediana neste grupo etário é {mediana} {mediana_texto}.)"
                    
                    st.write(texto_principal)
                    st.write(f"**Categoria:** {charlson_cat}")
                else:
                    st.info("Carga de morbidade não calculada")
            
            
            with col_b:
                st.markdown("#### ❤️ Risco Cardiovascular Global")
                
                percentual_risco = patient_data.get('percentual_risco_final')
                categoria_risco = patient_data.get('categoria_risco_final')
                
                if pd.notna(percentual_risco) and pd.notna(categoria_risco):
                    # Cor baseada no risco
                    if categoria_risco == 'Alto':
                        st.error(f"**🔴 {categoria_risco}**")
                    elif categoria_risco == 'Intermediário':
                        st.warning(f"**🟡 {categoria_risco}**")
                    else:
                        st.success(f"**🟢 {categoria_risco}**")
                    
                    st.write(f"**Risco Cardiovascular Global estimado:** {percentual_risco}")

                    # Linha em branco
                    st.write("")

                    # Variáveis usadas
                    variaveis_usadas = patient_data.get('variaveis_usadas_calculo')
                    if pd.notna(variaveis_usadas) and str(variaveis_usadas).strip():
                        st.markdown(f"* **Variáveis usadas no cálculo** - {variaveis_usadas}")

                    # Variáveis ausentes
                    variaveis_ausentes = patient_data.get('variaveis_ausentes_calculo')
                    if pd.notna(variaveis_ausentes) and str(variaveis_ausentes).strip():
                        st.markdown(f"* **Variáveis ausentes para o cálculo** - {variaveis_ausentes}")

                else:
                    st.info("Risco cardiovascular não calculado")
            

        
        # ========== TAB 2: CONTINUIDADE DO CUIDADO ==========
        with tab2:

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
                    '≥75% das consultas clínicas foram com o médico, '
                    'ou o médico foi o único profissional a consultar no período.'
                ),
                'enfermagem_centrado': (
                    '💉', 'Enfermagem-centrado',
                    '≥75% das consultas clínicas foram com o enfermeiro, '
                    'ou o enfermeiro foi o único profissional a consultar no período.'
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
                    pc = str(perfil_cuidado) if perfil_cuidado else 'indefinido'
                    em, lb, desc = PERFIL_LABEL.get(pc, ('❓', pc, '—'))
                    st.markdown(f"**{em} {lb}**")
                    st.caption(desc)

                    # Percentuais reais — mostrar o que compõe o perfil
                    linhas = []
                    if pd.notna(pct_medico) and pct_medico > 0:
                        linhas.append(f"🩺 Médico: **{pct_medico:.0f}%** das consultas")
                    if pd.notna(pct_enfermeiro) and pct_enfermeiro > 0:
                        linhas.append(f"💉 Enfermeiro: **{pct_enfermeiro:.0f}%** das consultas")
                    # técnico de enfermagem (residual)
                    pct_tec = None
                    if pd.notna(pct_medico) and pd.notna(pct_enfermeiro):
                        pct_tec_calc = 100 - (pct_medico or 0) - (pct_enfermeiro or 0)
                        if pct_tec_calc > 1:
                            linhas.append(f"🩹 Técnico: **{pct_tec_calc:.0f}%** das consultas")
                    if linhas:
                        st.markdown("  \n".join(linhas))

                    if pd.notna(intervalo):
                        st.caption(f"Intervalo mediano entre consultas: **{int(intervalo)} dias**")

            with cv2:
                with st.container(border=True):
                    st.caption("🏠 Longitudinalidade do cuidado")
                    if baixa_long in [True, 1, '1', 'True']:
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

            # ── BLOCO 3: Alertas ─────────────────────────────────
            st.markdown("#### 🎯 Alertas de Equidade no Cuidado")

            subatendimento      = patient_data.get('alto_risco_baixo_acesso')
            sobreutilizacao     = patient_data.get('baixo_risco_alto_acesso')
            risco_descompensacao= patient_data.get('alto_risco_intervalo_longo')
            tempo_acomp         = patient_data.get('dias_em_acompanhamento')

            tem_alerta = False

            if subatendimento in [True, 1, '1', 'True']:
                st.error(
                    "🔴 **Subatendimento de Caso Grave** — Paciente com alta carga de morbidade "
                    "e frequência de consultas abaixo do percentil 25 do seu grupo de pares. "
                    "Requer atenção prioritária da equipe."
                )
                tem_alerta = True

            if risco_descompensacao in [True, 1, '1', 'True']:
                st.warning(
                    "🟠 **Risco de Descompensação** — Intervalos longos entre consultas "
                    "para um paciente de alta complexidade. Avaliar reagendamento."
                )
                tem_alerta = True

            if sobreutilizacao in [True, 1, '1', 'True']:
                st.info(
                    "🟡 **Possível Sobreutilização** — Baixa carga de morbidade com "
                    "alta frequência de consultas. Avaliar se há outra necessidade não registrada."
                )
                tem_alerta = True

            if not tem_alerta:
                st.success("✅ Nenhum alerta de equidade identificado para este paciente.")

            if pd.notna(tempo_acomp):
                st.caption(f"Tempo em acompanhamento na unidade: **{format_tempo_acompanhamento(tempo_acomp)}**")
        
        # ========== TAB 3: LACUNAS DE CUIDADO ==========
        with tab3:
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

                # Ordem de prioridade: uso inadequado primeiro (risco imediato), depois falta de tratamento, depois monitoramento
                PRIORIDADE_GRUPOS = [
                    'Uso Inadequado',   # risco imediato — contraindicações
                    'CI',               # cardiopatia isquêmica — falta de tratamento
                    'ICC',              # insuficiência cardíaca — falta de tratamento
                    'IRC',              # renal crônica — falta de tratamento
                    'PA',               # pressão arterial — controle e monitoramento
                    'Glicemia',         # diabetes — controle e monitoramento
                    'Complicações DM',  # pé diabético
                    'Exames',           # monitoramento laboratorial
                    'Rastreamento',     # prevenção primária
                ]
                # Grupos definidos no GRUPOS_LACUNAS — usar ordem de prioridade se disponível, senão manter original
                grupos_ordenados = sorted(
                    lacunas_por_grupo.keys(),
                    key=lambda g: PRIORIDADE_GRUPOS.index(g) if g in PRIORIDADE_GRUPOS else 99
                )

                ICONE_GRUPO = {
                    'Uso Inadequado':  '⚠️',
                    'CI':              '❤️',
                    'ICC':             '💔',
                    'IRC':             '🫘',
                    'PA':              '🩺',
                    'Glicemia':        '🍬',
                    'Complicações DM': '🦶',
                    'Exames':          '🧪',
                    'Rastreamento':    '🔍',
                }

                for grupo in grupos_ordenados:
                    lacunas_grupo = lacunas_por_grupo[grupo]
                    icone = ICONE_GRUPO.get(grupo, '📌')
                    # Usar nomes do GRUPOS_LACUNAS se disponível
                    label_grupo = GRUPOS_LACUNAS.get(grupo, grupo)
                    # Uso inadequado abre expandido por ser risco imediato
                    aberto = grupo == 'Uso Inadequado'
                    with st.expander(
                        f"{icone} {label_grupo} ({len(lacunas_grupo)})",
                        expanded=aberto
                    ):
                        for lacuna in lacunas_grupo:
                            if '⚠️' in str(lacuna):
                                st.error(f"• {lacuna}")
                            else:
                                st.write(f"• {lacuna}")
        
        # ========== TAB 4: POLIFARMÁCIA E STOPP-START ==========
        with tab4:
            cpf_pac  = str(patient_data.get("cpf", ""))
            idade_pac = int(patient_data.get("idade", 0) or 0)

            with st.spinner("Carregando dados farmacológicos..."):
                dados_acb = buscar_acb_paciente(cpf_pac)
                dados_ss  = buscar_stopp_paciente(cpf_pac) if idade_pac >= 60 else {}

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
                "stopp_acb_001_365d": ("Carga ACB ≥ 4",             "≥2 anticolinérgicos",    "ACB total ≥ 4",  "Carga cumulativa — confusão, delirium, quedas."),
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
                "start_cv_003_365d":  ("DCV sem antiplatelet",  "AAS ou Clopidogrel",      "CI/AVC/DAP",     "Reduz eventos isquêmicos recorrentes."),
                "start_cv_004_365d":  ("ICC sem IECA/BRA",      "IECA ou BRA",             "ICC sistólica",  "Pilar do tratamento — reduz mortalidade."),
                "start_cv_005_365d":  ("FA sem anticoag.",      "Warfarina/DOAC",          "FA",             "Prevenção de AVC cardioembólico."),
                "start_cv_006_365d":  ("DM+IRC sem IECA/BRA",  "IECA ou BRA",             "DM + IRC",       "Retarda progressão da nefropatia."),
                "start_snc_001_365d": ("Parkinson s/ levo.",    "Levodopa/agonista",       "Parkinson",      "1ª linha — melhora função motora."),
                "start_snc_002_365d": ("Depressão s/ AD",       "ISRS ou IRSN",            "Depressão mod.", "AD não-TCA são mais seguros em idosos."),
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
                acb_total    = dados_acb.get("score_acb_total")
                acb_cronicos = None  # coluna removida da tabela
                n_acb_pos    = int(dados_acb.get("n_meds_acb_positivo") or 0)
                n_acb_alto   = int(dados_acb.get("n_meds_acb_alto") or 0)
                cat_acb      = dados_acb.get("categoria_acb", "—")

                if acb_total is not None:
                    acb_f    = float(acb_total)
                    acb_cr_f = float(acb_cronicos) if acb_cronicos else None
                    cor      = "🔴" if acb_f >= 3 else "🟠" if acb_f >= 1 else "🟢"

                    st.metric("Score total", f"{cor} {acb_f:.0f}")

                    # Score de crônicos em destaque — mais relevante clinicamente
                    if acb_cr_f is not None:
                        cor_cr = "🔴" if acb_cr_f >= 3 else "🟠" if acb_cr_f >= 1 else "🟢"
                        st.metric(
                            "Score crônicos",
                            f"{cor_cr} {acb_cr_f:.0f}",
                            help="Score ACB calculado apenas sobre medicamentos de uso contínuo. "
                                 "Mais relevante clinicamente que o score total."
                        )

                    st.metric("Meds ACB>0",  n_acb_pos)
                    st.metric("Meds ACB≥3",  n_acb_alto)
                    st.caption(f"Categoria: `{cat_acb}`")

                    if acb_f >= 3:
                        st.error(
                            "⚠️ **Carga anticolinérgica clinicamente significativa** "
                            "(ACB ≥ 3). Risco aumentado de confusão mental, "
                            "delirium e quedas — especialmente em idosos."
                        )
                    elif acb_f >= 1:
                        st.warning("Carga presente — monitorar sintomas cognitivos.")
                    else:
                        st.success("Sem carga anticolinérgica significativa.")
                else:
                    st.info("Sem dados ACB.")

        # ========== TAB 5: INÉRCIA TERAPÊUTICA (PLACEHOLDER) ==========
        with tab5:
            st.info("🚧 **Módulo em desenvolvimento**")
            st.markdown("""
            Esta aba apresentará:
            - Tempo de descontrole sem ajuste terapêutico
            - Progressão de parâmetros clínicos
            - Oportunidades de intensificação
            - Histórico de ajustes medicamentosos
            """)


        # ========== TAB 6: RELATAR PROBLEMA ==========
        with tab6:
            formulario_relato(patient_data, usuario_logado)
                
        

# ============================================
# INTERFACE PRINCIPAL
# ============================================

st.title("👥 Meus Pacientes")

st.markdown("### 📖 Lista Nominal de Pacientes")
st.markdown("---")

# SIDEBAR - FILTROS CASCATA
st.sidebar.header("🔍 Filtros")
mostrar_badge_anonimo()
st.sidebar.info("⚠️ Obrigatório selecionar: Área, Clínica e ESF")

df_options = load_filter_options_cascata()

if df_options.empty:
    st.error("Não foi possível carregar opções de filtro")
    st.stop()

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
if 'operador_morbidades' not in st.session_state:
    st.session_state.operador_morbidades = "OU (pelo menos uma)"

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
    st.stop()

if not clinica_selecionada:
    st.warning("⚠️ Selecione uma Clínica da Família")
    st.stop()

if not esf_selecionada:
    st.warning("⚠️ Selecione uma ESF")
    st.stop()

# Filtros adicionais
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎂 Filtro de Idade")
faixa_idade = st.sidebar.slider(
    "Faixa etária:",
    min_value=0,
    max_value=120,
    value=st.session_state.faixa_idade,
    step=1,
    key="idade_slider"
)
st.session_state.faixa_idade = faixa_idade

st.sidebar.markdown("---")
st.sidebar.markdown("### 🦠 Filtro de Morbidades")

morbidades_selecionadas = st.sidebar.multiselect(
    "Selecione morbidades:",
    options=LISTA_MORBIDADES,
    default=st.session_state.morbidades_selecionadas,
    key="morb_select"
)
st.session_state.morbidades_selecionadas = morbidades_selecionadas

operador_index = 0 if "OU" in st.session_state.operador_morbidades else 1

operador_morbidades = st.sidebar.radio(
    "Operador:",
    options=["OU (pelo menos uma)", "E (todas)"],
    index=operador_index,
    disabled=len(morbidades_selecionadas) == 0,
    key="operador_radio"
)
st.session_state.operador_morbidades = operador_morbidades
operador_morb = "AND" if "E" in operador_morbidades else "OR"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Ordenação")
ordem_opcoes = {
    "↓ Mais morbidades primeiro": "desc",
    "↑ Menos morbidades primeiro": "asc"
}
ordem_selecionada = st.sidebar.selectbox(
    "Ordenar por nº de morbidades:",
    options=list(ordem_opcoes.keys())
)
ordem = ordem_opcoes[ordem_selecionada]

# Campo de busca por nome
busca_nome_input = st.text_input(
    "🔍 Buscar paciente por nome",
    value=st.session_state.get('busca_nome_input', ''),
    placeholder="Digite o nome do paciente...",
    key="busca_nome_input",
)
busca_nome_raw = busca_nome_input.strip() if busca_nome_input else None
# No modo anônimo, a busca é feita no DataFrame (após anonimização), não no SQL
busca_nome_sql = busca_nome_raw if (busca_nome_raw and not MODO_ANONIMO) else None
busca_nome_local = busca_nome_raw if (busca_nome_raw and MODO_ANONIMO) else None

# Se busca mudou, volta para página 1
if 'busca_nome_anterior' not in st.session_state:
    st.session_state.busca_nome_anterior = None
if busca_nome_raw != st.session_state.busca_nome_anterior:
    st.session_state.pagina_atual = 0
    st.session_state.busca_nome_anterior = busca_nome_raw

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
    busca_nome=busca_nome_sql
)

if total_pacientes == 0:
    st.warning("⚠️ Nenhum paciente encontrado com os filtros aplicados")
    st.stop()

PACIENTES_POR_PAGINA = 20
total_paginas = (total_pacientes + PACIENTES_POR_PAGINA - 1) // PACIENTES_POR_PAGINA

if 'pagina_atual' not in st.session_state:
    st.session_state.pagina_atual = 0

pagina_atual = st.session_state.pagina_atual

filtros_texto = f"Área: {anonimizar_ap(area_selecionada)} | Clínica: {anonimizar_clinica(clinica_selecionada)} | ESF: {anonimizar_esf(esf_selecionada)}"

if morbidades_selecionadas:
    filtros_texto += f" | Morbidades filtradas: {len(morbidades_selecionadas)}"

st.info(f"📊 Filtros: {filtros_texto}")

st.success(f"**{estatisticas['total']} pacientes cadastrados | {estatisticas['multimorbidos']} multimórbidos | {estatisticas['polifarmacia']} em polifarmácia**")

if morbidades_selecionadas:
    if len(morbidades_selecionadas) == 1:
        morb_texto = morbidades_selecionadas[0]
    elif len(morbidades_selecionadas) == 2:
        operador_texto = " e " if "E" in operador_morbidades else " ou "
        morb_texto = f"{morbidades_selecionadas[0]}{operador_texto}{morbidades_selecionadas[1]}"
    else:
        operador_texto = " e " if "E" in operador_morbidades else " ou "
        morb_texto = ", ".join(morbidades_selecionadas[:-1]) + f"{operador_texto}{morbidades_selecionadas[-1]}"
    
    st.caption(f"Mostrando {total_pacientes} pacientes com {morb_texto} | Página {pagina_atual + 1} de {total_paginas}")
else:
    st.caption(f"Página {pagina_atual + 1} de {total_paginas}")

offset = pagina_atual * PACIENTES_POR_PAGINA

with st.spinner(f"Carregando página {pagina_atual + 1}..."):
    if busca_nome_local:
        # Modo anônimo: carregar todos os pacientes e filtrar localmente
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
        )
        # Anonimizar nomes e filtrar
        if not df_pacientes.empty and 'nome' in df_pacientes.columns:
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
            busca_nome=busca_nome_sql
        )

if df_pacientes.empty:
    st.warning("⚠️ Nenhum paciente encontrado" + (" para a busca informada." if busca_nome_raw else "."))
    st.stop()

# Botões de navegação (topo)
col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])

with col_nav1:
    if st.button("⬅️ Anterior", disabled=pagina_atual == 0):
        st.session_state.pagina_atual = max(0, pagina_atual - 1)
        st.rerun()

with col_nav2:
    st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Página {pagina_atual + 1} de {total_paginas}</div>", unsafe_allow_html=True)

with col_nav3:
    if st.button("Próxima ➡️", disabled=pagina_atual >= total_paginas - 1):
        st.session_state.pagina_atual = min(total_paginas - 1, pagina_atual + 1)
        st.rerun()

st.markdown("---")

# Exibir cards
st.markdown("### 👥 Pacientes")
for idx, (_, paciente) in enumerate(df_pacientes.iterrows()):
    paciente_dict = paciente.to_dict()
    create_patient_card(paciente_dict)

# Botões de navegação (rodapé)
st.markdown("---")
col_nav4, col_nav5, col_nav6 = st.columns([1, 2, 1])

with col_nav4:
    if st.button("⬅️ Página Anterior", disabled=pagina_atual == 0, key="btn_prev_bottom"):
        st.session_state.pagina_atual = max(0, pagina_atual - 1)
        st.rerun()

with col_nav5:
    st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Página {pagina_atual + 1} de {total_paginas}</div>", unsafe_allow_html=True)

with col_nav6:
    if st.button("Próxima Página ➡️", disabled=pagina_atual >= total_paginas - 1, key="btn_next_bottom"):
        st.session_state.pagina_atual = min(total_paginas - 1, pagina_atual + 1)
        st.rerun()

# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Navegador Clínico")