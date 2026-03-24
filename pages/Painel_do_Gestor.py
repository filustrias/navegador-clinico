"""
Página: Painel do Gestor
Visão macro para gestores com KPIs e distribuição por AP
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.bigquery_client import get_bigquery_client
import config
from streamlit_option_menu import option_menu

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
# 🎨 CONFIGURAÇÃO DA PÁGINA E CABEÇALHO
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Painel do Gestor - Navegador Clínico",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# Menu horizontal de navegação
selected = option_menu(
    menu_title=None,
    options=["Home", "Painel do Gestor", "Minha População", "Meus Pacientes", "Lacunas de Cuidado", "Acesso e Continuidade"],
    icons=['house-fill', 'bar-chart-fill', 'people-fill', 'person-lines-fill', 'exclamation-triangle-fill', 'arrow-repeat'],
    menu_icon="cast",
    default_index=1,
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
elif selected == "Minha População":
    st.switch_page("pages/Minha_Populacao.py")
elif selected == "Meus Pacientes":
    st.switch_page("pages/Meus_Pacientes.py")
elif selected == "Lacunas de Cuidado":
    st.switch_page("pages/Lacunas_de_Cuidado.py")
elif selected == "Acesso e Continuidade":
    st.switch_page("pages/Acesso_Continuidade.py")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# 📊 CONTEÚDO: PAINEL DO GESTOR
# ═══════════════════════════════════════════════════════════════

st.title("📈 Painel do Gestor")
st.markdown("## 1. Visão Geral (Dashboard Macro)")

@st.cache_data(ttl=600, show_spinner="Carregando dados...")
def carregar_kpis():
    client = get_bigquery_client()
    query = f"""
    SELECT 
        COUNT(*) as total_pacientes,
        COUNTIF(total_morbidades >= 2) as multimorbidade,
        COUNTIF(charlson_categoria = 'Muito Alto') as muito_alto_risco,
        COUNTIF(polifarmacia = TRUE) as polifarmacia,
        COUNTIF(consultas_365d = 0) as sem_acompanhamento
    FROM `{config.PROJECT_ID}.{config.DATASET_ID}.{config.TABELA_FATO}`
    """
    return client.query(query).result().to_dataframe()

@st.cache_data(ttl=600, show_spinner="Gerando gráficos...")
def carregar_distribuicao_ap():
    client = get_bigquery_client()
    query = f"""
    SELECT 
        area_programatica_cadastro as ap,
        charlson_categoria as categoria,
        COUNT(*) as total
    FROM `{config.PROJECT_ID}.{config.DATASET_ID}.{config.TABELA_FATO}`
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
    return client.query(query).result().to_dataframe()

# --- 1.1 KPIs de Linha de Frente ---
st.subheader("📊 1.1 KPIs de Linha de Frente")
df_kpis = carregar_kpis()

if not df_kpis.empty:
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    
    with kpi1:
        st.metric("Total de Pacientes", f"{df_kpis['total_pacientes'][0]:,}".replace(",", "."))
    with kpi2:
        st.metric("Multimorbidade", f"{df_kpis['multimorbidade'][0]:,}".replace(",", "."))
    with kpi3:
        st.metric("Muito Alto Risco", f"{df_kpis['muito_alto_risco'][0]:,}".replace(",", "."))
    with kpi4:
        st.metric("Polifarmácia", f"{df_kpis['polifarmacia'][0]:,}".replace(",", "."))
    with kpi5:
        st.metric("Sem Acompanhamento", f"{df_kpis['sem_acompanhamento'][0]:,}".replace(",", "."))
else:
    st.warning("⚠️ Não foi possível carregar os KPIs.")

st.markdown("---")

# --- 1.2 Distribuição de Gravidade por AP ---
st.subheader("📊 1.2 Distribuição de Gravidade por AP")
df_ap = carregar_distribuicao_ap()

if not df_ap.empty:
    # Criar gráfico de barras empilhadas 100%
    fig = px.bar(
        df_ap, 
        x="ap", 
        y="total", 
        color="categoria",
        title="Distribuição de Categorias de Charlson por AP",
        labels={"ap": "Área Programática", "total": "Pacientes", "categoria": "Categoria Charlson"},
        barmode="stack",
        color_discrete_sequence=px.colors.qualitative.Safe,
        template="plotly_dark"
    )
    
    fig.update_layout(
        barmode="stack",
        barnorm="percent",
        yaxis_ticksuffix="%",
        legend_title_text='Gravidade (Charlson)',
        hovermode="x unified"
    )

    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ Não foi possível carregar os dados de distribuição por AP.")

# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Superintendência de Atenção Primária")
