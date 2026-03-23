import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from google.cloud import bigquery

# Importar do nosso sistema
from utils.bigquery_client import get_bigquery_client
import config

from utils.relatos import formulario_relato

# ═══════════════════════════════════════════════════════════════
# ANONIMIZAÇÃO DESATIVADA
# ═══════════════════════════════════════════════════════════════
# from utils.anonimizador import (
#     anonimizar_paciente, 
#     mostrar_badge_anonimo, 
#     anonimizar_ap,
#     anonimizar_clinica,
#     anonimizar_esf,
#     MODO_ANONIMO
# )

# Funções stub para substituir anonimização (retornam valor original)
def anonimizar_paciente(x): return x
def anonimizar_ap(x): return str(x) if x else x
def anonimizar_clinica(x): return str(x) if x else x
def anonimizar_esf(x): return str(x) if x else x
def mostrar_badge_anonimo(): pass
MODO_ANONIMO = False

from streamlit_option_menu import option_menu
from utils.auth import exibir_usuario_logado


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
    st.markdown("""
    <h1 style='margin: 0; padding: 0; color: #FAFAFA;'>
        🏥 Navegador Clínico <small style='color: #999; font-size: 0.5em;'>SMS-RJ</small>
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
    <div style='text-align: right; padding-top: 10px; color: #FAFAFA; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Menu horizontal
selected = option_menu(
    menu_title=None,
    options=["Home", "Minha População", "Meus Pacientes", "Lacunas de Cuidado", "Acesso e Continuidade"],
    icons=['house-fill', 'people-fill', 'person-lines-fill', 'exclamation-triangle-fill', 'arrow-repeat'],
    menu_icon="cast",
    default_index=2,  # Meus Pacientes está selecionado
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#0E1117"},
        "icon": {"color": "#FAFAFA", "font-size": "18px"}, 
        "nav-link": {
            "font-size": "16px",
            "text-align": "center",
            "margin": "0px",
            "padding": "10px 20px",
            "color": "#FAFAFA",
            "background-color": "#262730",
            "--hover-color": "#404040"
        },
        "nav-link-selected": {"background-color": "#404040", "color": "#FAFAFA", "font-weight": "bold"},
    }
)

# ⭐ NAVEGAÇÃO - TODAS AS OPÇÕES TRATADAS - INCLUINDO LACUNAS!
if selected == "Home":
    st.switch_page("Home.py")
elif selected == "Minha População":
    st.switch_page("pages/Minha_Populacao.py")
elif selected == "Lacunas de Cuidado":
    st.switch_page("pages/Lacunas_de_Cuidado.py")
elif selected == "Acesso e Continuidade":
    st.switch_page("pages/Acesso_Continuidade.py")
# Se selected == "Meus Pacientes", não faz nada (já está na página)

st.markdown("---")


# ============================================
# CONFIGURAÇÃO DE TEMA (página já configurada no início)
# ============================================



# Inicializar estados
if 'pagina_atual' not in st.session_state:
    st.session_state.pagina_atual = 0

if 'tema_escuro' not in st.session_state:
    st.session_state.tema_escuro = True

# Cores do tema
if st.session_state.tema_escuro:
    CORES = {
        'background': '#0e1117',
        'secondary_bg': '#262730',
        'text': '#fafafa',
        'primary': '#ff4b4b',
        'card_bg': '#1e1e2e',
        'border': '#464646',
        'input_bg': '#262730',
        'input_text': '#fafafa',
    }
else:
    CORES = {
        'background': '#ffffff',
        'secondary_bg': '#f0f2f6',
        'text': '#262730',
        'primary': '#ff4b4b',
        'card_bg': '#f8f9fa',
        'border': '#dee2e6',
        'input_bg': '#ffffff',
        'input_text': '#262730',
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
    limit=20
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
      dias_em_acompanhamento, 
      pct_consultas_medico_365d,
      pct_consultas_medicas_na_unidade_365d,
      pct_consultas_medicas_fora_365d,
      pct_consultas_enfermeiro_365d,
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
def count_total_patients(area=None, clinica=None, esf=None, idade_min=None, idade_max=None, morbidades=None, operador_morb="OR"):
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
    
    titulo_card = f"👤 **{nome}** - {idade} anos | 🏥 {morbidades_texto} | 💊 {medicamentos_texto} | ⚠️ {lacunas_texto}"
    
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
            "🚫 STOPP-START",
            "📈 Inércia Terapêutica",
            "📝 Relatar Problemas"  # ← NOVA TAB
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
            col_c, col_d = st.columns(2)
            
            with col_c:
                st.markdown("#### 🗓️ Última Consulta")
                st.write(f"**Médica:** {format_dias_consulta(patient_data.get('dias_desde_ultima_medica'))}")
                st.write(f"**Enfermagem:** {format_dias_consulta(patient_data.get('dias_desde_ultima_enfermagem'))}")
                st.write(f"**Tempo em acompanhamento:** {format_tempo_acompanhamento(patient_data.get('dias_em_acompanhamento'))}")
            
            with col_d:
                st.markdown("#### 📊 Perfil de Consultas (365 dias)")
                
                pct_medico = patient_data.get('pct_consultas_medico_365d')
                pct_medico_na_unidade = patient_data.get('pct_consultas_medicas_na_unidade_365d')
                pct_medico_fora = patient_data.get('pct_consultas_medicas_fora_365d')
                pct_enfermeiro = patient_data.get('pct_consultas_enfermeiro_365d')
                
                if pd.notna(pct_medico):
                    st.write(f"**Consultas médicas:** {pct_medico:.0f}%")
                    
                    if pd.notna(pct_medico_na_unidade) and pd.notna(pct_medico_fora):
                        st.caption(f"↳ {pct_medico_na_unidade:.0f}% na unidade, {pct_medico_fora:.0f}% fora")
                    
                    if pd.notna(pct_enfermeiro):
                        st.write(f"**Consultas enfermagem:** {pct_enfermeiro:.0f}%")
            
            st.markdown("---")
            st.markdown("#### 🎯 Alertas de Equidade no Cuidado")
            
            subatendimento = patient_data.get('alto_risco_baixo_acesso')
            sobreutilizacao = patient_data.get('baixo_risco_alto_acesso')
            risco_descompensacao = patient_data.get('alto_risco_intervalo_longo')
            
            tem_alerta = False
            
            if subatendimento in [True, 1, '1', 'True']:
                st.error("🔴 **Subatendimento de Caso Grave** - Paciente grave com acesso insuficiente")
                tem_alerta = True
            
            if risco_descompensacao in [True, 1, '1', 'True']:
                st.warning("🟠 **Risco de Descompensação** - Intervalos longos entre consultas")
                tem_alerta = True
            
            if sobreutilizacao in [True, 1, '1', 'True']:
                st.info("🟡 **Possível Sobreutilização** - Baixa complexidade com alto acesso")
                tem_alerta = True
            
            if not tem_alerta:
                st.success("✅ Continuidade adequada ao perfil do paciente")
        
        # ========== TAB 3: LACUNAS DE CUIDADO ==========
        with tab3:
            if n_lacunas == 0:
                st.success("✅ **Nenhuma lacuna de cuidado identificada**")
            else:
                st.warning(f"**{n_lacunas} lacunas identificadas**")
                
                lacunas_por_grupo, flags = extrair_lacunas_paciente(patient_data)
                
                # Mostrar flags primeiro (controlados, melhorando, piorando)
                if flags:
                    st.markdown("#### Status do Controle")
                    for flag in flags:
                        if "✅" in flag:
                            st.success(flag)
                        else:
                            st.warning(flag)
                    st.markdown("---")
                
                # Mostrar lacunas por grupo
                st.markdown("#### Lacunas Identificadas por Categoria")
                
                for grupo in GRUPOS_LACUNAS.keys():
                    if grupo in lacunas_por_grupo:
                        with st.expander(f"{GRUPOS_LACUNAS[grupo]} ({len(lacunas_por_grupo[grupo])})", expanded=False):
                            for lacuna in lacunas_por_grupo[grupo]:
                                st.write(f"• {lacuna}")
        
        # ========== TAB 4: STOPP-START (PLACEHOLDER) ==========
        with tab4:
            st.info("🚧 **Módulo em desenvolvimento**")
            st.markdown("""
            Esta aba apresentará:
            - Critérios STOPP identificados (medicamentos potencialmente inapropriados)
            - Critérios START identificados (omissões de tratamento)
            - Priorização por risco clínico
            - Sugestões de ajuste terapêutico
            """)
        
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

col_titulo, col_tema = st.columns([10, 1])

with col_titulo:
    st.title("👥 Meus Pacientes")

with col_tema:
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.session_state.tema_escuro:
        st.markdown("""
            <style>
                div[data-testid="column"]:last-child button {
                    background-color: #fafafa !important;
                    color: #262730 !important;
                    border: 1px solid #fafafa !important;
                }
                div[data-testid="column"]:last-child button:hover {
                    background-color: #e0e0e0 !important;
                    color: #262730 !important;
                }
            </style>
        """, unsafe_allow_html=True)
        if st.button("☀️ Claro", help="Mudar para tema claro", use_container_width=True):
            st.session_state.tema_escuro = False
            st.rerun()
    else:
        st.markdown("""
            <style>
                div[data-testid="column"]:last-child button {
                    background-color: #262730 !important;
                    color: #ffffff !important;
                    border: 1px solid #262730 !important;
                }
                div[data-testid="column"]:last-child button:hover {
                    background-color: #1e1e2e !important;
                    color: #ffffff !important;
                    border: 1px solid #1e1e2e !important;
                }
            </style>
        """, unsafe_allow_html=True)
        if st.button("🌙 Escuro", help="Mudar para tema escuro", use_container_width=True):
            st.session_state.tema_escuro = True
            st.rerun()

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
    operador_morb=operador_morb
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
        limit=PACIENTES_POR_PAGINA
    )

if df_pacientes.empty:
    st.warning("⚠️ Nenhum dado retornado")
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