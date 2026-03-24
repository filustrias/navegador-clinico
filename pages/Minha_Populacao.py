"""
Página: Minha População
Visão agregada da população com pirâmides, prevalências e distribuições
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from components.filtros import filtros_territoriais
from utils.bigquery_client import get_bigquery_client
import config
import math

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

from utils.auth import exibir_usuario_logado


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
from streamlit_option_menu import option_menu

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

# Menu horizontal de navegação COM FUNCIONALIDADE
selected = option_menu(
    menu_title=None,
    options=["Home", "Painel do Gestor", "Minha População", "Meus Pacientes", "Lacunas de Cuidado", "Acesso e Continuidade"],
    icons=['house-fill', 'bar-chart-fill', 'people-fill', 'person-lines-fill', 'exclamation-triangle-fill', 'arrow-repeat'],
    menu_icon="cast",
    default_index=2,
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

# Navegação
if selected == "Home":
    st.switch_page("home.py")
elif selected == "Painel do Gestor":
    st.switch_page("pages/Painel_do_Gestor.py")
elif selected == "Meus Pacientes":
    st.switch_page("pages/Meus_Pacientes.py")
elif selected == "Lacunas de Cuidado":
    st.switch_page("pages/Lacunas_de_Cuidado.py")
elif selected == "Acesso e Continuidade":
    st.switch_page("pages/Acesso_Continuidade.py")
st.markdown("---")


# ✅ DICIONÁRIO COMPLETO DE MORBIDADES COM ÍCONES
MORBIDADES_COMPLETO = {
    # Geral
    'multimorbidade': {
        'nome': 'Multimorbidade (2+ condições)',
        'descricao': 'Presença de duas ou mais condições crônicas simultâneas. Aumenta complexidade do cuidado e risco de eventos adversos.',
        'categoria': 'Geral',
        'icone': '🏥'
    },
    
    # Cardiovascular
    'n_HAS': {
        'nome': 'Hipertensão Arterial Sistêmica',
        'descricao': 'Pressão arterial ≥140/90 mmHg. Principal fator de risco para AVC e infarto.',
        'categoria': 'Cardiovascular',
        'icone': '❤️'
    },
    'n_CI': {
        'nome': 'Cardiopatia Isquêmica',
        'descricao': 'Doença arterial coronariana, IAM prévio, angina.',
        'categoria': 'Cardiovascular',
        'icone': '💔'
    },
    'n_ICC': {
        'nome': 'Insuficiência Cardíaca',
        'descricao': 'Engloba tanto pacientes com fração de ejeção preservada quanto diminuida.',
        'categoria': 'Cardiovascular',
        'icone': '🫀'
    },
    'n_stroke': {
        'nome': 'AVC Prévio',
        'descricao': 'Acidente Vascular Cerebral e Acidente Isquêmico Transitório.',
        'categoria': 'Cardiovascular',
        'icone': '🧠'
    },
    'n_arritmia': {
        'nome': 'Arritmias Cardíacas',
        'descricao': 'Distúrbios do ritmo cardíaco (FA, flutter, taquicardias).',
        'categoria': 'Cardiovascular',
        'icone': '💓'
    },
    'n_valvular': {
        'nome': 'Valvulopatias',
        'descricao': 'Qualquer tipo de valvulopatia primárias oui secundárias.',
        'categoria': 'Cardiovascular',
        'icone': '🫀'
    },
    'n_circ_pulm': {
        'nome': 'Doenças Circulação Pulmonar',
        'descricao': 'Hipertensão pulmonar, embolia pulmonar.',
        'categoria': 'Cardiovascular',
        'icone': '🫁'
    },
    'n_vascular_periferica': {
        'nome': 'Doença Vascular Periférica',
        'descricao': 'Obstrução arterial Periférica.',
        'categoria': 'Cardiovascular',
        'icone': '🦵'
    },
    
    # Metabólico/Endócrino
    'n_DM': {
        'nome': 'Diabetes Mellitus',
        'descricao': 'Diabetes Mellitus tipo 1, tipo 2, MODY e LADA.',
        'categoria': 'Metabólico',
        'icone': '🍬'
    },
    'n_pre_DM': {
        'nome': 'Pré-Diabetes',
        'descricao': 'Glicemia de jejum 100-125 mg/dL ou HbA1c 5.7-6.4%.',
        'categoria': 'Metabólico',
        'icone': '⚠️'
    },
    'n_obesidade': {
        'nome': 'Obesidade',
        'descricao': 'IMC ≥30 kg/m². Fator de risco cardiovascular.',
        'categoria': 'Metabólico',
        'icone': '⚖️'
    },
    'n_obesidade_consolidada': {
        'nome': 'Obesidade Confirmada',
        'descricao': 'Obesidade documentada em múltiplas consultas.',
        'categoria': 'Metabólico',
        'icone': '⚖️'
    },
    'n_tireoide': {
        'nome': 'Doenças da Tireoide',
        'descricao': 'Hipotireoidismo, hipertireoidismo, nódulos.',
        'categoria': 'Endócrino',
        'icone': '🦋'
    },
    
    # Neurológico
    'n_epilepsy': {
        'nome': 'Epilepsia',
        'descricao': 'Qualquer crises convulsivas recorrentes registrada no prontuário.',
        'categoria': 'Neurológico',
        'icone': '⚡'
    },
    'n_parkinsonism': {
        'nome': 'Parkinsonismo',
        'descricao': 'Doença de Parkinson e síndromes parkinsonianas.',
        'categoria': 'Neurológico',
        'icone': '🤝'
    },
    'n_multiple_sclerosis': {
        'nome': 'Esclerose Múltipla',
        'descricao': 'Doença autoimune desmielinizante do SNC.',
        'categoria': 'Neurológico',
        'icone': '🧠'
    },
    'n_neuro': {
        'nome': 'Outras Doenças Neurológicas',
        'descricao': 'Neuropatias, mielopatias, outras condições neurológicas.',
        'categoria': 'Neurológico',
        'icone': '🧠'
    },
    'n_dementia': {
        'nome': 'Demências',
        'descricao': 'Alzheimer, demência vascular, outras demências.',
        'categoria': 'Neurológico',
        'icone': '🧓'
    },
    'n_plegia': {
        'nome': 'Plegias',
        'descricao': 'Hemiplegia, paraplegia, tetraplegia.',
        'categoria': 'Neurológico',
        'icone': '♿'
    },
    
    # Saúde Mental
    'n_psicoses': {
        'nome': 'Transtornos Psicóticos',
        'descricao': 'Esquizofrenia, transtorno bipolar, psicoses.',
        'categoria': 'Saúde Mental',
        'icone': '💭'
    },
    'n_depre_ansiedade': {
        'nome': 'Depressão e Ansiedade',
        'descricao': 'Transtornos depressivos e ansiosos.',
        'categoria': 'Saúde Mental',
        'icone': '😔'
    },
    
    # Respiratório
    'n_COPD': {
        'nome': 'DPOC',
        'descricao': 'Doença Pulmonar Obstrutiva Crônica.',
        'categoria': 'Respiratório',
        'icone': '🫁'
    },
    'n_asthma': {
        'nome': 'Asma',
        'descricao': 'Casos registrados com CID para Asma.',
        'categoria': 'Respiratório',
        'icone': '🌬️'
    },
    
    # Oncológico
    'n_neoplasia_mama': {
        'nome': 'Câncer de Mama',
        'descricao': 'Neoplasia maligna da mama.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    'n_neoplasia_colo_uterino': {
        'nome': 'Câncer de Colo Uterino',
        'descricao': 'Neoplasia maligna do colo do útero.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    'n_neoplasia_feminina_estrita': {
        'nome': 'Neoplasias Ginecológicas',
        'descricao': 'Cânceres específicos do aparelho reprodutor feminino.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    'n_neoplasia_masculina_estrita': {
        'nome': 'Câncer de Próstata',
        'descricao': 'Neoplasia maligna da próstata.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    'n_leukemia': {
        'nome': 'Leucemias',
        'descricao': 'Neoplasias hematológicas malignas.',
        'categoria': 'Oncológico',
        'icone': '🩸'
    },
    'n_lymphoma': {
        'nome': 'Linfomas',
        'descricao': 'Neoplasias do sistema linfático.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    'n_metastasis': {
        'nome': 'Câncer Metastático',
        'descricao': 'Neoplasias com metástases à distância.',
        'categoria': 'Oncológico',
        'icone': '⚠️'
    },
    'n_neoplasia_ambos_os_sexos': {
        'nome': 'Outros Cânceres',
        'descricao': 'Neoplasias que acometem ambos os sexos.',
        'categoria': 'Oncológico',
        'icone': '🎗️'
    },
    
    # Renal/Hematológico
    'n_IRC': {
        'nome': 'Doença Renal Crônica',
        'descricao': 'TFG <60 ml/min. Requer monitoramento rigoroso.',
        'categoria': 'Renal',
        'icone': '🩺'
    },
    'n_coagulo': {
        'nome': 'Distúrbios de Coagulação',
        'descricao': 'Trombofilias, anticoagulação.',
        'categoria': 'Hematológico',
        'icone': '🩸'
    },
    'n_anemias': {
        'nome': 'Anemias',
        'descricao': 'Redução de hemoglobina/eritrócitos.',
        'categoria': 'Hematológico',
        'icone': '🩸'
    },
    
    # Reumatológico
    'n_reumato': {
        'nome': 'Doenças Reumatológicas',
        'descricao': 'Artrite reumatoide, lúpus, outras doenças autoimunes.',
        'categoria': 'Reumatológico',
        'icone': '🦴'
    },
    
    # Substâncias
    'n_alcool': {
        'nome': 'Transtorno por Uso de Álcool',
        'descricao': 'Uso problemático de álcool.',
        'categoria': 'Substâncias',
        'icone': '🍺'
    },
    'n_drogas': {
        'nome': 'Transtorno por Uso de Drogas',
        'descricao': 'Uso problemático de substâncias ilícitas.',
        'categoria': 'Substâncias',
        'icone': '💉'
    },
    'n_tabaco': {
        'nome': 'Tabagismo',
        'descricao': 'Dependência de nicotina.',
        'categoria': 'Substâncias',
        'icone': '🚬'
    },
    
    # Gastrointestinal
    'n_peptic': {
        'nome': 'Doença Péptica',
        'descricao': 'Úlceras gástricas e duodenais.',
        'categoria': 'Gastrointestinal',
        'icone': '🫃'
    },
    'n_liver': {
        'nome': 'Doenças Hepáticas',
        'descricao': 'Hepatites, cirrose, esteatose.',
        'categoria': 'Gastrointestinal',
        'icone': '🫀'
    },
    'n_diverticular_disease': {
        'nome': 'Doença Diverticular',
        'descricao': 'Diverticulose e diverticulite.',
        'categoria': 'Gastrointestinal',
        'icone': '🫃'
    },
    'n_ibd': {
        'nome': 'Doença Inflamatória Intestinal',
        'descricao': 'Crohn, retocolite ulcerativa.',
        'categoria': 'Gastrointestinal',
        'icone': '🫃'
    },
    
    # Infecciosas
    'n_HIV': {
        'nome': 'HIV/AIDS',
        'descricao': 'Pacientes com Infecção pelo vírus HIV ou com síndrome da imunodeficiência adquirida.',
        'categoria': 'Infecciosas',
        'icone': '🦠'
    },
    
    # Outras
    'n_desnutricao': {
        'nome': 'Desnutrição',
        'descricao': 'Estado nutricional comprometido.',
        'categoria': 'Nutricional',
        'icone': '🍎'
    },
    'n_retardo_mental': {
        'nome': 'Deficiência Intelectual',
        'descricao': 'Limitação cognitiva significativa.',
        'categoria': 'Neurológico',
        'icone': '🧩'
    },
    'n_olhos': {
        'nome': 'Doenças Oftalmológicas',
        'descricao': 'Glaucoma, catarata, retinopatias, cegueira.',
        'categoria': 'Oftalmológico',
        'icone': '👁️'
    },
    'n_ouvidos': {
        'nome': 'Doenças Otológicas',
        'descricao': 'Perda auditiva, vertigem.',
        'categoria': 'Otorrinolaringologia',
        'icone': '👂'
    },
    'n_ma_formacoes': {
        'nome': 'Má-formações Congênitas',
        'descricao': 'Anomalias congênitas.',
        'categoria': 'Congênito',
        'icone': '👶'
    },
    'n_pele': {
        'nome': 'Doenças Dermatológicas',
        'descricao': 'Psoríase, eczema, outras dermatoses.',
        'categoria': 'Dermatológico',
        'icone': '🧴'
    },
    'n_painful_condition': {
        'nome': 'Condições Dolorosas Crônicas',
        'descricao': 'Dor crônica, fibromialgia.',
        'categoria': 'Dor',
        'icone': '⚡'
    },
    'n_prostate_disorder': {
        'nome': 'Doenças Prostáticas Benignas',
        'descricao': 'Hiperplasia prostática benigna.',
        'categoria': 'Urológico',
        'icone': '💧'
    },
    
    # Farmacológico
    'n_polifarmacia': {
        'nome': 'Polifarmácia (5-9 medicamentos)',
        'descricao': 'Uso de 5-9 medicamentos simultaneamente.',
        'categoria': 'Farmacológico',
        'icone': '💊'
    },
    'n_hiperpolifarmacia': {
        'nome': 'Hiperpolifarmácia (10+ medicamentos)',
        'descricao': 'Uso de 10+ medicamentos simultaneamente.',
        'categoria': 'Farmacológico',
        'icone': '💊'
    }
}

# ✅ MAPEAMENTO DE CATEGORIAS CONSOLIDADAS
CATEGORIA_CONSOLIDADA = {
    'Geral': 'Multimorbidade',
    'Cardiovascular': 'Problemas Cardiovasculares',
    'Metabólico': 'Problemas Metabólicos e Endócrinos',
    'Endócrino': 'Problemas Metabólicos e Endócrinos',
    'Neurológico': 'Problemas Neurológicos',
    'Saúde Mental': 'Saúde Mental e uso de substâncias',
    'Substâncias': 'Saúde Mental e uso de substâncias',
    'Respiratório': 'Problemas Respiratórios',
    'Oncológico': 'Problemas Oncológicos',
    'Renal': 'Problemas Renais e Hematológicos',
    'Hematológico': 'Problemas Renais e Hematológicos',
    'Reumatológico': 'Problemas Reumatológicos',
    'Gastrointestinal': 'Problemas Gastrointestinais',
    'Infecciosas': 'Doenças Infecciosas',
    'Nutricional': 'Outras Condições de Saúde',
    'Oftalmológico': 'Outras Condições de Saúde',
    'Otorrinolaringologia': 'Outras Condições de Saúde',
    'Congênito': 'Outras Condições de Saúde',
    'Dermatológico': 'Outras Condições de Saúde',
    'Dor': 'Outras Condições de Saúde',
    'Urológico': 'Outras Condições de Saúde',
    'Farmacológico': 'Polifarmácia'
}

# ✅ ORDEM DE EXIBIÇÃO DAS CATEGORIAS
ORDEM_CATEGORIAS = [
    'Multimorbidade',
    'Problemas Cardiovasculares',
    'Problemas Metabólicos e Endócrinos',
    'Problemas Neurológicos',
    'Problemas Oncológicos',
    'Saúde Mental e uso de substâncias',
    'Problemas Respiratórios',
    'Problemas Renais e Hematológicos',
    'Problemas Reumatológicos',
    'Problemas Gastrointestinais',
    'Doenças Infecciosas',
    'Polifarmácia',
    'Outras Condições de Saúde'
]

# ✅ ÍCONES DAS CATEGORIAS CONSOLIDADAS
ICONES_CATEGORIAS_CONSOLIDADAS = {
    'Geral': '📊',
    'Cardiovascular': '❤️',
    'Metabólico e Endócrino': '⚖️',
    'Neurológico': '🧠',
    'Oncológico': '🎗️',
    'Saúde Mental e Substâncias': '💭',
    'Respiratório': '🫁',
    'Renal e Hematológico': '🩺',
    'Reumatológico': '🦴',
    'Gastrointestinal': '🫃',
    'Infecciosas': '🦠',
    'Farmacológico': '💊',
    'Outras Condições': '📋'
}


def calcular_multimorbidade(df):
    """Calcula número de pacientes com 2+ morbidades"""
    if df.empty:
        return 0
    
    # Somar pacientes com 2 ou mais morbidades
    cols_multi = ['n_morb_2', 'n_morb_3', 'n_morb_4', 'n_morb_5', 
                  'n_morb_6', 'n_morb_7', 'n_morb_8_mais']
    
    total = 0
    for col in cols_multi:
        if col in df.columns:
            total += df[col].sum()
    
    return int(total)

@st.cache_data(ttl=600, show_spinner=False)
def run_query(query):
    """Executa query no BigQuery"""
    try:
        client = get_bigquery_client()
        df = client.query(query).result().to_dataframe(create_bqstorage_client=False)
        return df
    except Exception as e:
        st.error(f"❌ Erro ao executar query: {str(e)}")
        return pd.DataFrame()

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================

st.set_page_config(
    page_title="Minha População - Navegador Clínico",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# FUNÇÕES DE CARGA DE DADOS
# ============================================

def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"



# ✅ MUDAR TTL=600 PARA TTL=1 (ou comentar o cache completamente)
@st.cache_data(show_spinner=False, ttl=1)  # ← MUDAR DE 600 PARA 1
def carregar_dados_piramides(ap=None, clinica=None, esf=None):
    """Carrega dados agregados - COM AGREGAÇÃO NO BIGQUERY"""
    
    where_clauses = []
    if ap:
        where_clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:
        where_clauses.append(f"nome_esf_cadastro = '{esf}'")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
    SELECT 
        faixa_etaria,
        genero,
        SUM(total_pacientes) as total_pacientes,
        
        -- Contagens agregadas de morbidades
        SUM(n_morb_0) as n_morb_0,
        SUM(n_morb_1) as n_morb_1,
        SUM(n_morb_2) as n_morb_2,
        SUM(n_morb_3) as n_morb_3,
        SUM(n_morb_4) as n_morb_4,
        SUM(n_morb_5) as n_morb_5,
        SUM(n_morb_6) as n_morb_6,
        SUM(n_morb_7) as n_morb_7,
        SUM(n_morb_8_mais) as n_morb_8_mais,
        
        -- Charlson
        SUM(n_charlson_0) as n_charlson_0,
        SUM(n_charlson_1) as n_charlson_1,
        SUM(n_charlson_2) as n_charlson_2,
        SUM(n_charlson_3) as n_charlson_3,
        SUM(n_charlson_4) as n_charlson_4,
        SUM(n_charlson_5) as n_charlson_5,
        SUM(n_charlson_6) as n_charlson_6,
        SUM(n_charlson_7) as n_charlson_7,
        SUM(n_charlson_8) as n_charlson_8,
        SUM(n_charlson_9) as n_charlson_9,
        SUM(n_charlson_10) as n_charlson_10,
        SUM(n_charlson_11) as n_charlson_11,
        SUM(n_charlson_12) as n_charlson_12,
        SUM(n_charlson_13) as n_charlson_13,
        SUM(n_charlson_14) as n_charlson_14,
        SUM(n_charlson_15) as n_charlson_15,
        SUM(n_charlson_16_mais) as n_charlson_16_mais,
        
        -- Medicamentos
        SUM(n_nenhum_medicamento) as n_nenhum_medicamento,
        SUM(n_um_e_dois_medicamentos) as n_um_e_dois_medicamentos,
        SUM(n_tres_e_quatro_medicamentos) as n_tres_e_quatro_medicamentos,
        SUM(n_polifarmacia) as n_polifarmacia,
        SUM(n_hiperpolifarmacia) as n_hiperpolifarmacia,
        
        -- Cardiovascular
        SUM(n_HAS) as n_HAS,
        SUM(n_CI) as n_CI,
        SUM(n_ICC) as n_ICC,
        SUM(n_stroke) as n_stroke,
        SUM(n_arritmia) as n_arritmia,
        SUM(n_valvular) as n_valvular,
        SUM(n_circ_pulm) as n_circ_pulm,
        SUM(n_vascular_periferica) as n_vascular_periferica,
        
        -- Metabólico/Endócrino
        SUM(n_DM) as n_DM,
        SUM(n_pre_DM) as n_pre_DM,
        SUM(n_obesidade) as n_obesidade,
        SUM(n_obesidade_consolidada) as n_obesidade_consolidada,
        SUM(n_tireoide) as n_tireoide,
        
        -- Neurológico
        SUM(n_epilepsy) as n_epilepsy,
        SUM(n_parkinsonism) as n_parkinsonism,
        SUM(n_multiple_sclerosis) as n_multiple_sclerosis,
        SUM(n_neuro) as n_neuro,
        SUM(n_dementia) as n_dementia,
        SUM(n_plegia) as n_plegia,
        
        -- Saúde Mental
        SUM(n_psicoses) as n_psicoses,
        SUM(n_depre_ansiedade) as n_depre_ansiedade,
        
        -- Respiratório
        SUM(n_COPD) as n_COPD,
        SUM(n_asthma) as n_asthma,
        
        -- Oncológico
        SUM(n_neoplasia_mama) as n_neoplasia_mama,
        SUM(n_neoplasia_colo_uterino) as n_neoplasia_colo_uterino,
        SUM(n_neoplasia_feminina_estrita) as n_neoplasia_feminina_estrita,
        SUM(n_neoplasia_masculina_estrita) as n_neoplasia_masculina_estrita,
        SUM(n_leukemia) as n_leukemia,
        SUM(n_lymphoma) as n_lymphoma,
        SUM(n_metastasis) as n_metastasis,
        SUM(n_neoplasia_ambos_os_sexos) as n_neoplasia_ambos_os_sexos,
        
        -- Renal/Hematológico
        SUM(n_IRC) as n_IRC,
        SUM(n_coagulo) as n_coagulo,
        SUM(n_anemias) as n_anemias,
        
        -- Reumatológico
        SUM(n_reumato) as n_reumato,
        
        -- Substâncias
        SUM(n_alcool) as n_alcool,
        SUM(n_drogas) as n_drogas,
        SUM(n_tabaco) as n_tabaco,
        
        -- Gastrointestinal
        SUM(n_peptic) as n_peptic,
        SUM(n_liver) as n_liver,
        SUM(n_diverticular_disease) as n_diverticular_disease,
        SUM(n_ibd) as n_ibd,
        
        -- Infecciosas
        SUM(n_HIV) as n_HIV,
        
        -- Outras
        SUM(n_desnutricao) as n_desnutricao,
        SUM(n_retardo_mental) as n_retardo_mental,
        SUM(n_olhos) as n_olhos,
        SUM(n_ouvidos) as n_ouvidos,
        SUM(n_ma_formacoes) as n_ma_formacoes,
        SUM(n_pele) as n_pele,
        SUM(n_painful_condition) as n_painful_condition,
        SUM(n_prostate_disorder) as n_prostate_disorder
        
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    GROUP BY faixa_etaria, genero
    ORDER BY faixa_etaria, genero
    """
    
    result = run_query(sql)
    
    # ✅ DEBUG
    print(f"🔍 Colunas retornadas pela query: {len(result.columns)} colunas")
    print(f"🔍 Primeiras 10 colunas: {result.columns[:10].tolist()}")
    
    return result


@st.cache_data(show_spinner=False, ttl=900)
def carregar_metricas_resumo(ap=None, clinica=None, esf=None):
    """Carrega apenas métricas agregadas - SUPER RÁPIDO"""
    
    where_clauses = []
    
    if ap:
        where_clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica:
        where_clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:
        where_clauses.append(f"nome_esf_cadastro = '{esf}'")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
    SELECT 
        SUM(total_pacientes) as total_pop,
        SUM(n_morb_2 + n_morb_3 + n_morb_4 + n_morb_5 + n_morb_6 + n_morb_7 + n_morb_8_mais) as multimorbidos,
        SUM(n_polifarmacia) as polifarmacia,
        SUM(n_hiperpolifarmacia) as hiperpolifarmacia
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    """
    
    df = run_query(sql)  # ✅ MUDOU AQUI
    if not df.empty:
        return df.iloc[0].to_dict()
    return {'total_pop': 0, 'multimorbidos': 0, 'polifarmacia': 0, 'hiperpolifarmacia': 0}


# ============================================
# FUNÇÕES DE VISUALIZAÇÃO
# ============================================


def criar_piramide_populacional(df):
    """Cria pirâmide populacional por morbidades"""
    
    if df.empty:
        return None
    
    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', 
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']
    
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')
    
    generos = df['genero'].unique()
    if 'masculino' in generos:
        df_masc = df[df['genero'] == 'masculino'].copy()
        df_fem = df[df['genero'] == 'feminino'].copy()
    else:
        df_masc = df[df['genero'] == 'M'].copy()
        df_fem = df[df['genero'] == 'F'].copy()
    
    cores = px.colors.qualitative.Safe
    while len(cores) < 9:
        cores = cores + cores
    
    fig = go.Figure()
    
    estratos = [
        ('n_morb_8_mais', '8+ morbidades', cores[8]),
        ('n_morb_7', '7 morbidades', cores[7]),
        ('n_morb_6', '6 morbidades', cores[6]),
        ('n_morb_5', '5 morbidades', cores[5]),
        ('n_morb_4', '4 morbidades', cores[4]),
        ('n_morb_3', '3 morbidades', cores[3]),
        ('n_morb_2', '2 morbidades', cores[2]),
        ('n_morb_1', '1 morbidade', cores[1]),
        ('n_morb_0', '0 morbidades', cores[0])
    ]
    
    for campo, label, cor in estratos:
        if campo in df_masc.columns:
            fig.add_trace(go.Bar(
                y=df_masc['faixa_etaria'],
                x=-df_masc[campo],
                name=label,
                orientation='h',
                marker=dict(
                    color=cor,
                    line=dict(color='rgba(0,0,0,0.8)', width=0.5)
                ),
                text=df_masc[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color='white'),
                legendgroup=label,
                showlegend=True,
                hovertemplate='<b>%{y}</b><br>Homens: %{text:,}<extra></extra>'
            ))
    
    for campo, label, cor in estratos:
        if campo in df_fem.columns:
            fig.add_trace(go.Bar(
                y=df_fem['faixa_etaria'],
                x=df_fem[campo],
                name=label,
                orientation='h',
                marker=dict(
                    color=cor,
                    line=dict(color='rgba(0,0,0,0.8)', width=0.5)
                ),
                text=df_fem[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color='white'),
                legendgroup=label,
                showlegend=False,
                hovertemplate='<b>%{y}</b><br>Mulheres: %{x:,}<extra></extra>'
            ))
    
    # ✅ CALCULAR MÁXIMO - MAIS GRANULAR
    import math
    
    cols_morb = ['n_morb_0', 'n_morb_1', 'n_morb_2', 'n_morb_3', 'n_morb_4', 
                 'n_morb_5', 'n_morb_6', 'n_morb_7', 'n_morb_8_mais']
    cols_existentes_masc = [c for c in cols_morb if c in df_masc.columns]
    cols_existentes_fem = [c for c in cols_morb if c in df_fem.columns]
    
    if cols_existentes_masc and cols_existentes_fem:
        max_masc = df_masc[cols_existentes_masc].sum(axis=1).max()
        max_fem = df_fem[cols_existentes_fem].sum(axis=1).max()
        max_val = max(max_masc, max_fem)
    else:
        max_val = 1000
    
    # ✅ STEPS MAIS GRANULARES
    if max_val < 100:
        step = 20
    elif max_val < 300:
        step = 50
    elif max_val < 500:
        step = 100
    elif max_val < 1000:
        step = 200
    elif max_val < 3000:
        step = 500
    elif max_val < 5000:
        step = 1000
    elif max_val < 10000:
        step = 2000
    elif max_val < 30000:
        step = 5000
    elif max_val < 50000:
        step = 10000
    elif max_val < 100000:
        step = 25000
    else:
        step = 50000
    
    max_range = math.ceil(max_val / step) * step
    
    # Criar ticks
    num_ticks = 5
    tick_step = max_range // num_ticks
    tickvals = []
    ticktext = []
    for i in range(-num_ticks, num_ticks + 1):
        val = i * tick_step
        tickvals.append(val)
        ticktext.append(f'{abs(val):,}')
    
    fig.update_layout(
        title='Pirâmide Etária - Distribuição por Sexo e Número de Morbidades',
        barmode='relative',
        bargap=0.0,
        bargroupgap=0,
        height=700,
        xaxis=dict(
            title='População',
            range=[-max_range, max_range],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinewidth=3,
            zerolinecolor='white'
        ),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            title=dict(text='<b>Número de Morbidades</b>'),
            traceorder='normal'
        ),
        hovermode='closest',
        margin=dict(l=80, r=200, t=60, b=80)
    )
    
    fig.add_annotation(
        x=-max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Masculino</b>', showarrow=False,
        font=dict(size=16, color='#3498DB')
    )
    fig.add_annotation(
        x=max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Feminino</b>', showarrow=False,
        font=dict(size=16, color='#E91E63')
    )
    
    return fig


def criar_piramide_charlson(df):
    """Cria pirâmide por Carga de Morbidade (até 10+)"""
    
    if df.empty:
        return None
    
    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', 
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']
    
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')
    
    generos = df['genero'].unique()
    if 'masculino' in generos:
        df_masc = df[df['genero'] == 'masculino'].copy()
        df_fem = df[df['genero'] == 'feminino'].copy()
    else:
        df_masc = df[df['genero'] == 'M'].copy()
        df_fem = df[df['genero'] == 'F'].copy()
    
    # AGRUPAR 10+
    cols_10_mais = [f'n_charlson_{i}' for i in range(10, 16)] + ['n_charlson_16_mais']
    df_masc['charlson_10_mais'] = df_masc[[c for c in cols_10_mais if c in df_masc.columns]].sum(axis=1)
    df_fem['charlson_10_mais'] = df_fem[[c for c in cols_10_mais if c in df_fem.columns]].sum(axis=1)
    
    # PALETA - Verde → Amarelo → Vermelho
    cores = ['#2ECC71', '#58D68D', '#82E0AA', '#F7DC6F', '#F8C471', 
             '#EB984E', '#E67E22', '#E74C3C', '#C0392B', '#A93226', '#7B241C']
    
    fig = go.Figure()
    
    estratos_rev = [('charlson_10_mais', '10+ pontos', cores[10])]
    for i in range(9, -1, -1):
        col = f'n_charlson_{i}'
        label = '0 pontos' if i == 0 else ('1 ponto' if i == 1 else f'{i} pontos')
        estratos_rev.append((col, label, cores[i]))
    
    for campo, label, cor in estratos_rev:
        if campo in df_masc.columns:
            fig.add_trace(go.Bar(
                y=df_masc['faixa_etaria'], 
                x=-df_masc[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                text=df_masc[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=9, color='white'),
                legendgroup=label, 
                showlegend=True,
                hovertemplate='<b>%{y}</b><br>Homens: %{text:,}<extra></extra>'
            ))
    
    for campo, label, cor in estratos_rev:
        if campo in df_fem.columns:
            fig.add_trace(go.Bar(
                y=df_fem['faixa_etaria'], 
                x=df_fem[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                text=df_fem[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=9, color='white'),
                legendgroup=label, 
                showlegend=False,
                hovertemplate='<b>%{y}</b><br>Mulheres: %{x:,}<extra></extra>'
            ))
    
    # CALCULAR MÁXIMO
    import math
    cols_charlson = [c for c, _, _ in estratos_rev if c in df_masc.columns]
    
    if cols_charlson:
        max_masc = df_masc[cols_charlson].sum(axis=1).max()
        max_fem = df_fem[cols_charlson].sum(axis=1).max()
        max_val = max(max_masc, max_fem)
    else:
        max_val = 1000
    
    if max_val < 100:
        step = 20
    elif max_val < 300:
        step = 50
    elif max_val < 500:
        step = 100
    elif max_val < 1000:
        step = 200
    elif max_val < 3000:
        step = 500
    elif max_val < 5000:
        step = 1000
    elif max_val < 10000:
        step = 2000
    elif max_val < 30000:
        step = 5000
    elif max_val < 50000:
        step = 10000
    else:
        step = 25000
    
    max_range = math.ceil(max_val / step) * step
    num_ticks = 5
    tick_step = max_range // num_ticks
    tickvals = [i * tick_step for i in range(-num_ticks, num_ticks + 1)]
    ticktext = [f'{abs(val):,}' for val in tickvals]
    
    fig.update_layout(
        title='Pirâmide Etária - Distribuição por Sexo e Carga de Morbidade',
        barmode='relative', 
        bargap=0.0,
        bargroupgap=0,
        height=700,
        xaxis=dict(
            title='População', 
            range=[-max_range, max_range],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinewidth=3,
            zerolinecolor='white'
        ),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            title=dict(text='<b>Carga de Morbidade</b>')
        ),
        hovermode='closest',
        margin=dict(l=80, r=200, t=60, b=80)
    )
    
    fig.add_annotation(
        x=-max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Masculino</b>', showarrow=False,
        font=dict(size=16, color='#3498DB')
    )
    fig.add_annotation(
        x=max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Feminino</b>', showarrow=False,
        font=dict(size=16, color='#E91E63')
    )
    
    return fig


def criar_piramide_medicamentos(df):
    """Cria pirâmide por medicamentos"""
    
    if df.empty:
        return None
    
    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', 
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']
    
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')
    
    generos = df['genero'].unique()
    if 'masculino' in generos:
        df_masc = df[df['genero'] == 'masculino'].copy()
        df_fem = df[df['genero'] == 'feminino'].copy()
    else:
        df_masc = df[df['genero'] == 'M'].copy()
        df_fem = df[df['genero'] == 'F'].copy()
    
    cores = px.colors.qualitative.Safe
    while len(cores) < 5:
        cores = cores + cores
    
    fig = go.Figure()
    
    estratos = [
        ('n_hiperpolifarmacia', 'Hiperpolifarmácia (10+)', cores[4]),
        ('n_polifarmacia', 'Polifarmácia (5-9)', cores[3]),
        ('n_tres_e_quatro_medicamentos', '3-4 medicamentos', cores[2]),
        ('n_um_e_dois_medicamentos', '1-2 medicamentos', cores[1]),
        ('n_nenhum_medicamento', '0 medicamentos', cores[0])
    ]
    
    for campo, label, cor in estratos:
        if campo in df_masc.columns:
            fig.add_trace(go.Bar(
                y=df_masc['faixa_etaria'], 
                x=-df_masc[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.8)', width=0.5)),
                text=df_masc[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color='white'),
                legendgroup=label, 
                showlegend=True,
                hovertemplate='<b>%{y}</b><br>Homens: %{text:,}<extra></extra>'
            ))
    
    for campo, label, cor in estratos:
        if campo in df_fem.columns:
            fig.add_trace(go.Bar(
                y=df_fem['faixa_etaria'], 
                x=df_fem[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.8)', width=0.5)),
                text=df_fem[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color='white'),
                legendgroup=label, 
                showlegend=False,
                hovertemplate='<b>%{y}</b><br>Mulheres: %{x:,}<extra></extra>'
            ))
    
    # CALCULAR MÁXIMO
    import math
    cols_meds = ['n_nenhum_medicamento', 'n_um_e_dois_medicamentos', 
                 'n_tres_e_quatro_medicamentos', 'n_polifarmacia', 'n_hiperpolifarmacia']
    cols_existentes = [c for c in cols_meds if c in df_masc.columns]
    
    if cols_existentes:
        max_masc = df_masc[cols_existentes].sum(axis=1).max()
        max_fem = df_fem[cols_existentes].sum(axis=1).max()
        max_val = max(max_masc, max_fem)
    else:
        max_val = 1000
    
    if max_val < 100:
        step = 20
    elif max_val < 300:
        step = 50
    elif max_val < 500:
        step = 100
    elif max_val < 1000:
        step = 200
    elif max_val < 3000:
        step = 500
    elif max_val < 5000:
        step = 1000
    elif max_val < 10000:
        step = 2000
    elif max_val < 30000:
        step = 5000
    elif max_val < 50000:
        step = 10000
    else:
        step = 25000
    
    max_range = math.ceil(max_val / step) * step
    num_ticks = 5
    tick_step = max_range // num_ticks
    tickvals = [i * tick_step for i in range(-num_ticks, num_ticks + 1)]
    ticktext = [f'{abs(val):,}' for val in tickvals]
    
    fig.update_layout(
        title='Pirâmide Etária - Distribuição por Sexo e Complexidade Farmacológica',
        barmode='relative', 
        bargap=0.0,
        bargroupgap=0,
        height=700,
        xaxis=dict(
            title='População', 
            range=[-max_range, max_range],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinewidth=3,
            zerolinecolor='white'
        ),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            title=dict(text='<b>Medicamentos Crônicos</b>')
        ),
        hovermode='closest',
        margin=dict(l=80, r=250, t=60, b=80)
    )
    
    fig.add_annotation(
        x=-max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Masculino</b>', showarrow=False,
        font=dict(size=16, color='#3498DB')
    )
    fig.add_annotation(
        x=max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Feminino</b>', showarrow=False,
        font=dict(size=16, color='#E91E63')
    )
    
    return fig


def criar_grafico_charlson(df):
    """Cria gráfico de distribuição de Charlson"""
    
    # Agregar por categoria Charlson
    charlson_cols = [f'n_charlson_{i}' for i in range(17)]
    
    dados_charlson = []
    for i, col in enumerate(charlson_cols):
        if col in df.columns:
            n = df[col].sum()
            if i < 16:
                categoria = str(i)
            else:
                categoria = '16+'
            dados_charlson.append({'categoria': categoria, 'n_pacientes': n})
    
    df_charlson = pd.DataFrame(dados_charlson)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df_charlson['categoria'],
        y=df_charlson['n_pacientes'],
        marker=dict(color=px.colors.qualitative.Prism[4]),
        text=df_charlson['n_pacientes'],
        textposition='outside',
        hovertemplate='Charlson %{x}<br>Pacientes: %{y:,}<extra></extra>'
    ))
    
    fig.update_layout(
        title='Distribuição de Carga de Morbidade (Índice de Charlson)',
        xaxis_title='Pontuação de Charlson',
        yaxis_title='Número de Pacientes',
        height=400,
        showlegend=False
    )
    
    return fig

def criar_grafico_medicamentos(df):
    """Cria gráfico de distribuição de medicamentos"""
    
    categorias = [
        ('n_nenhum_medicamento', '0 medicamentos'),
        ('n_um_e_dois_medicamentos', '1-2 medicamentos'),
        ('n_tres_e_quatro_medicamentos', '3-4 medicamentos'),
        ('n_polifarmacia', 'Polifarmácia (5-9)'),
        ('n_hiperpolifarmacia', 'Hiperpolifarmácia (10+)')
    ]
    
    dados = []
    for campo, label in categorias:
        if campo in df.columns:
            n = df[campo].sum()
            dados.append({'categoria': label, 'n_pacientes': n})
    
    df_meds = pd.DataFrame(dados)
    
    fig = go.Figure()
    
    cores = px.colors.qualitative.Prism[:5]
    
    fig.add_trace(go.Bar(
        x=df_meds['categoria'],
        y=df_meds['n_pacientes'],
        marker=dict(color=cores),
        text=df_meds['n_pacientes'],
        textposition='outside',
        hovertemplate='%{x}<br>Pacientes: %{y:,}<extra></extra>'
    ))
    
    fig.update_layout(
        title='Distribuição de Complexidade Farmacológica',
        xaxis_title='',
        yaxis_title='Número de Pacientes',
        height=400,
        showlegend=False
    )
    
    return fig

def criar_visualizacao_morbidades_prevalentes(df):
    """Cria visualização de TODAS as morbidades - VERSÃO ELEGANTE"""
    
    if df.empty:
        return None, None
    
    total_pacientes = df['total_pacientes'].sum()
    
    # ✅ ADICIONAR MULTIMORBIDADE
    n_multi = calcular_multimorbidade(df)
    prev_multi = (n_multi / total_pacientes * 100) if total_pacientes > 0 else 0
    
    resultados = [{
        'Condição': 'Multimorbidade (2+ condições)',
        'N': n_multi,
        'Prevalência (%)': round(prev_multi, 1),
        'Descrição': 'Presença de duas ou mais condições crônicas. Aumenta complexidade do cuidado.',
        'Categoria': 'Geral',
        'Coluna': 'multimorbidade'
    }]
    
    # Calcular prevalências das outras condições
    for coluna, info in MORBIDADES_COMPLETO.items():
        if coluna == 'multimorbidade':
            continue
            
        if coluna in df.columns:
            n = int(df[coluna].sum())
            prev = (n / total_pacientes * 100) if total_pacientes > 0 else 0
            
            if n > 0:
                # ✅ MAPEAR PARA CATEGORIA CONSOLIDADA
                cat_original = info['categoria']
                cat_consolidada = CATEGORIA_CONSOLIDADA.get(cat_original, cat_original)
                
                resultados.append({
                    'Condição': info['nome'],
                    'N': n,
                    'Prevalência (%)': round(prev, 1),
                    'Descrição': info['descricao'],
                    'Categoria': cat_consolidada,
                    'Coluna': coluna
                })
    
    if not resultados:
        return None, None
    
    df_prev = pd.DataFrame(resultados).sort_values('Prevalência (%)', ascending=False)
    
    # GRÁFICO TOP 20
    df_top20 = df_prev.head(20).sort_values('Prevalência (%)', ascending=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=df_top20['Condição'],
        x=df_top20['Prevalência (%)'],
        orientation='h',
        text=df_top20['Prevalência (%)'].apply(lambda x: f'{x:.1f}%'),
        textposition='outside',
        marker=dict(
            color=df_top20['Prevalência (%)'],
            colorscale='YlOrRd',
            showscale=False
        ),
        hovertemplate='<b>%{y}</b><br>Prevalência: %{x:.1f}%<br>Pacientes: %{customdata:,}<extra></extra>',
        customdata=df_top20['N']
    ))
    
    max_prev = df_top20['Prevalência (%)'].max()
    range_max = max(50, math.ceil(max_prev / 10) * 10)
    
    fig.update_layout(
        title='Top 20 Condições Mais Prevalentes',
        xaxis=dict(
            title='Prevalência (%)',
            range=[0, range_max],
            tickmode='linear',
            tick0=0,
            dtick=5
        ),
        yaxis=dict(title=''),
        height=700,
        margin=dict(l=300, r=100, t=60, b=80)
    )
    
    return fig, df_prev

# ============================================
# INTERFACE PRINCIPAL
# ============================================

st.title("👥 Minha População")
st.markdown("Visão agregada das características demográficas e clínicas da população")
st.markdown("---")



# ============================================
# SIDEBAR - FILTROS
# ============================================

st.sidebar.title("Filtros")

territorio = filtros_territoriais(
    key_prefix="populacao",
    obrigatorio_esf=False,
    mostrar_todas_opcoes=True
)



# ============================================
# CARREGAR DADOS COM MEDIÇÃO DETALHADA
# ============================================

import time

## st.write("### ⏱️ Medindo Performance...")

# 1. Teste: Carregar métricas agregadas (deveria ser instantâneo)
inicio_metricas = time.time()
metricas = carregar_metricas_resumo(
    ap=territorio['ap'],
    clinica=territorio['clinica'],
    esf=territorio['esf']
)
fim_metricas = time.time()
tempo_metricas = fim_metricas - inicio_metricas

st.sidebar.info(f"⚡ Métricas: **{tempo_metricas:.2f}s**")

# 2. Teste: Carregar dados completos
inicio_dados = time.time()

with st.spinner("🔄 Carregando dados da população..."):
    df_dados = carregar_dados_piramides(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )

fim_dados = time.time()
tempo_dados = fim_dados - inicio_dados

st.sidebar.warning(f"🐌 Dados completos: **{tempo_dados:.2f}s**")

# Diagnóstico
if tempo_dados > 10:
    st.sidebar.error("⚠️ Carregamento MUITO lento! Veja possíveis causas:")
    st.sidebar.write("1. Conexão lenta com BigQuery")
    st.sidebar.write("2. Tabela sem índices/particionamento")
    st.sidebar.write("3. Região do BigQuery distante")

# ============================================
# MÉTRICAS GERAIS (TOPO)
# ============================================

metricas = carregar_metricas_resumo(
    ap=territorio['ap'],
    clinica=territorio['clinica'],
    esf=territorio['esf']
)

total_pop = int(metricas['total_pop'])
multimorbidos = int(metricas['multimorbidos'])
polifarmacia = int(metricas['polifarmacia'])
hiperpolifarmacia = int(metricas['hiperpolifarmacia'])

pct_multi = (multimorbidos / total_pop * 100) if total_pop > 0 else 0
pct_poli = (polifarmacia / total_pop * 100) if total_pop > 0 else 0
pct_hiper = (hiperpolifarmacia / total_pop * 100) if total_pop > 0 else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("👥 População Total", f"{total_pop:,}")

with col2:
    st.metric("🏥 Multimorbidade", f"{pct_multi:.1f}%", help=f"{multimorbidos:,} pacientes com 2+ morbidades")

with col3:
    st.metric("💊 Polifarmácia", f"{pct_poli:.1f}%", help=f"{polifarmacia:,} pacientes com 5-9 medicamentos")

with col4:
    st.metric("⚠️ Hiperpolifarmácia", f"{pct_hiper:.1f}%", help=f"{hiperpolifarmacia:,} pacientes com 10+ medicamentos")

st.markdown("---")




# ============================================
# TABS COM VISUALIZAÇÕES
# ============================================

# ========== TABS ==========
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Perfil Demográfico",
    "🏥 Morbidades Prevalentes", 
    "📈 Carga de Morbidade",
    "💊 Complexidade Farmacológica"
])

# TAB 1
with tab1:
    fig_piramide = criar_piramide_populacional(df_dados)
    if fig_piramide:
        st.plotly_chart(fig_piramide, use_container_width=True, key='piramide_morb')
    else:
        st.error("Erro ao criar pirâmide")



with tab2:
    st.markdown("### 🏥 Condições de Saúde Mais Prevalentes")
    
    fig_prev, df_prevalencias = criar_visualizacao_morbidades_prevalentes(df_dados)
    
    if fig_prev is not None and df_prevalencias is not None:
        # GRÁFICO
        st.plotly_chart(fig_prev, use_container_width=True, key='grafico_prevalencias')
        
        st.markdown("---")
        st.markdown(f"### 📋 Detalhamento por Categoria")
        
        # PROCESSAR POR CATEGORIA CONSOLIDADA
        for categoria in ORDEM_CATEGORIAS:
            df_cat = df_prevalencias[df_prevalencias['Categoria'] == categoria]
            
            if df_cat.empty:
                continue
            
            # Ordenar por prevalência
            df_cat = df_cat.sort_values('Prevalência (%)', ascending=False)
            
            # ✅ ÍCONE DA CATEGORIA
            icone = ICONES_CATEGORIAS_CONSOLIDADAS.get(categoria, '📌')
            
            # ✅ TÍTULO DA CATEGORIA
            st.markdown(f"## {icone} {categoria}")
            
            # ✅ GRID DE CARDS - 3 POR LINHA
            cols = st.columns(3)
            for idx, row in df_cat.iterrows():
                col_idx = df_cat.index.get_loc(idx) % 3
                
                with cols[col_idx]:
                    # Cor baseada na prevalência
                    if row['Prevalência (%)'] >= 20:
                        cor = '🔴'
                        delta_color = 'inverse'
                    elif row['Prevalência (%)'] >= 10:
                        cor = '🟠'
                        delta_color = 'inverse'
                    elif row['Prevalência (%)'] >= 5:
                        cor = '🟡'
                        delta_color = 'off'
                    else:
                        cor = '🔵'
                        delta_color = 'normal'
                    
                    # CONTAINER COM BORDA
                    with st.container(border=True):
                        # Badge + Nome
                        st.markdown(f"**{cor} {row['Condição']}**")
                        
                        # Métrica principal
                        st.metric(
                            label="Pacientes",
                            value=f"{row['N']:,}",
                            delta=f"{row['Prevalência (%)']}%",
                            delta_color=delta_color
                        )
                        
                        # Descrição
                        st.caption(row['Descrição'])
            
            st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.error("⚠️ Nenhuma condição encontrada")


# TAB 3
with tab3:
    st.markdown("""
    ### 📈 Carga de Morbidade
    
    Temos aqui uma apresentação da nossa população de acordo com a sua Carga de Morbidade, ou seja, de acordo com a carga de doenças 
    e a gravidade de cada uma delas, idade dos pacientes e a Complexidade Farmacológica (presença de poli ou hiperpolifarmácia).

    Identificarmos a carga de morbidade de nossos pacientes é importante para identificarmos aqueles que precisam de maior atenção da 
    equipe de saúde, pois estão em maior risco de eventos adversos e, principalmente, identificarmos se estamos dedicando tempo adequado para nossos 
    pacientes de acordo com a carga de morbidade de cada um deles.  
    
    **Categorias:**
    - 0-2: Baixa complexidade
    - 3-4: Moderada
    - 5-7: Alta
    - 8+: Muito alta
    """)
    
    fig_charlson = criar_piramide_charlson(df_dados)
    if fig_charlson:
        st.plotly_chart(fig_charlson, use_container_width=True, key='piramide_charlson')
    else:
        st.warning("Dados de Charlson não disponíveis")

# TAB 4
with tab4:
    st.markdown("""
    ### 💊 Complexidade Farmacológica
    
    Polifarmácia é definida com o uso concomitante de cinco ou mais medicamentos por um paciente e a hiperpolifarmácia o uso de 10 ou mais. É um problema que médicos de família e profissionais da Atenção Primária precisam estar rotineiramente atentos. 
    
    Suas consequências incluem risco aumentado de interações e efeitos adversos de medicamentos, quedas, declínio cognitivo e 
    diminuição da adesão ao tratamento. Para as famílias, isso pode significar maior sobrecarga no manejo dos medicamentos, 
    aumento dos custos pessoais e impacto na qualidade de vida.
    
    O sistema de saúde também é impactado pela polifarmácia, pois pacientes que fazem uso de maior número medicamentos cronicamente
    estão em maior risco de serem hospitalizados e, quando hospitalizados, de terem uma internação mais longa do que a média e com 
    maior risco de readmissão. 

    Isto eleva os gastos em saúde, tanto pelo custo direto dos medicamentos 
    quanto pelo tratamento de complicações decorrentes.
    
    """)
    
    fig_meds = criar_piramide_medicamentos(df_dados)
    if fig_meds:
        st.plotly_chart(fig_meds, use_container_width=True, key='piramide_meds')
    else:
        st.warning("Dados de medicamentos não disponíveis")




# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Navegador Clínico | Dados agregados da população")