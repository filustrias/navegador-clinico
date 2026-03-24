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
        COUNTIF(charlson_score >= 10) as muito_alto_risco,
        COUNTIF(polifarmacia = TRUE) as polifarmacia,
        COUNTIF(consultas_365d = 0) as sem_acompanhamento,
        COUNTIF(charlson_score >= 7 AND percentil_consultas_vs_grupo = 'abaixo_p25') as pacientes_invisiveis
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

@st.cache_data(ttl=600, show_spinner="Calculando riscos...")
def carregar_risco_cardiovascular():
    client = get_bigquery_client()
    query = f"""
    SELECT 
        risco_cardiovascular as categoria,
        COUNT(*) as total
    FROM `{config.PROJECT_ID}.{config.DATASET_ID}.{config.TABELA_FATO}`
    WHERE risco_cardiovascular IS NOT NULL
      AND risco_cardiovascular != 'NÃO CLASSIFICADO'
    GROUP BY 1
    ORDER BY 
        CASE categoria
            WHEN 'MUITO ALTO' THEN 1
            WHEN 'ALTO' THEN 2
            WHEN 'INTERMEDIÁRIO' THEN 3
            WHEN 'BAIXO' THEN 4
            ELSE 5
        END
    """
    return client.query(query).result().to_dataframe()

# --- CSS para os Cards ---
st.markdown("""
<style>
    .kpi-container {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 20px;
    }
    .kpi-card {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 15px;
        flex: 1;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-top: 5px solid #212121;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .kpi-title {
        color: #5F6368;
        font-size: 0.75rem;
        font-weight: bold;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    .kpi-value {
        color: #202124;
        font-size: 1.8rem;
        font-weight: bold;
        margin: 5px 0;
    }
    .kpi-subtitle {
        color: #70757A;
        font-size: 0.75rem;
    }
    /* Cores das bordas superiores */
    .border-total { border-top-color: #1A73E8; }
    .border-multi { border-top-color: #12B5CB; }
    .border-poly { border-top-color: #E37400; }
    .border-risk { border-top-color: #D93025; }
    .border-follow { border-top-color: #A50E0E; }
    .border-invisible { border-top-color: #9333EA; }
</style>
""", unsafe_allow_html=True)

# --- 1.1 KPIs de Linha de Frente ---
df_kpis = carregar_kpis()

if not df_kpis.empty:
    kpi = df_kpis.iloc[0]
    
    # Formatação dos valores
    total_pacientes = f"{int(kpi['total_pacientes']):,}".replace(",", ".")
    multimorbidade = f"{int(kpi['multimorbidade']):,}".replace(",", ".")
    perc_multi = (kpi['multimorbidade'] / kpi['total_pacientes'] * 100) if kpi['total_pacientes'] > 0 else 0
    
    polifarmacia = f"{int(kpi['polifarmacia']):,}".replace(",", ".")
    perc_poly = (kpi['polifarmacia'] / kpi['total_pacientes'] * 100) if kpi['total_pacientes'] > 0 else 0
    
    muito_alto_risco = f"{int(kpi['muito_alto_risco']):,}".replace(",", ".")
    sem_acompanhamento = f"{int(kpi['sem_acompanhamento']):,}".replace(",", ".")
    pacientes_invisiveis = f"{int(kpi['pacientes_invisiveis']):,}".replace(",", ".")
    
    st.markdown(f"""
    <div class="kpi-container">
        <div class="kpi-card border-total">
            <div class="kpi-title">TOTAL DE PACIENTES</div>
            <div class="kpi-value">{total_pacientes}</div>
            <div class="kpi-subtitle">cadastros ativos ESF</div>
        </div>
        <div class="kpi-card border-multi">
            <div class="kpi-title">COM MULTIMORBIDADE</div>
            <div class="kpi-value">{multimorbidade}</div>
            <div class="kpi-subtitle">{perc_multi:.1f}% — ≥2 condições crônicas</div>
        </div>
        <div class="kpi-card border-poly">
            <div class="kpi-title">POLIFARMÁCIA</div>
            <div class="kpi-value">{polifarmacia}</div>
            <div class="kpi-subtitle">{perc_poly:.1f}% — 5+ medicamentos crônicos</div>
        </div>
        <div class="kpi-card border-risk">
            <div class="kpi-title">MUITO ALTO RISCO</div>
            <div class="kpi-value">{muito_alto_risco}</div>
            <div class="kpi-subtitle">Charlson score ≥10</div>
        </div>
        <div class="kpi-card border-follow">
            <div class="kpi-title">SEM ACOMPANHAMENTO</div>
            <div class="kpi-value">{sem_acompanhamento}</div>
            <div class="kpi-subtitle">+365 dias sem consulta registrada</div>
        </div>
        <div class="kpi-card border-invisible">
            <div class="kpi-title">PACIENTES INVISÍVEIS</div>
            <div class="kpi-value">{pacientes_invisiveis}</div>
            <div class="kpi-subtitle">Charlson ≥7, acesso < P25</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("⚠️ Não foi possível carregar os KPIs.")

st.markdown("---")

# --- 1.2 Distribuição de Gravidade e Risco Cardiovascular ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="margin-bottom: 0;">Distribuição Charlson por Área Programática (%)</h3>
            <span style="background-color: #1a202c; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold;">Score modificado</span>
        </div>
    """, unsafe_allow_html=True)
    df_ap = carregar_distribuicao_ap()
    if not df_ap.empty:
        fig_ap = px.bar(
            df_ap, 
            x="ap", 
            y="total", 
            color="categoria",
            barmode="stack",
            color_discrete_map={
                "Baixo": "#C6F6D5",
                "Moderado": "#FEEBC8",
                "Alto": "#FED7D7",
                "Muito Alto": "#FEB2B2"
            },
            template="plotly_white",
            height=350
        )
        fig_ap.update_layout(
            barnorm="percent",
            yaxis_ticksuffix="%",
            legend_title_text='Gravidade (Charlson)',
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title=None,
            yaxis_title=None,
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_ap, use_container_width=True)
        st.markdown("""
            <div style="font-size: 0.8rem; color: #718096; margin-top: 10px; border-top: 1px dotted #CBD5E0; padding-top: 10px;">
                Charlson modificado: morbidades + faixa etária + polifarmácia · Seção 11 · MM_2026_novos_cadastros
            </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ Dados de AP indisponíveis.")

with col_right:
    st.markdown('<h3 style="margin-bottom: 30px;">Risco Cardiovascular</h3>', unsafe_allow_html=True)
    df_risco = carregar_risco_cardiovascular()
    if not df_risco.empty:
        fig_risco = px.pie(
            df_risco, 
            values='total', 
            names='categoria', 
            hole=.6,
            color='categoria',
            color_discrete_map={
                "MUITO ALTO": "#C53030",
                "ALTO": "#DD6B20",
                "INTERMEDIÁRIO": "#9C4221",
                "BAIXO": "#22543D"
            },
            template="plotly_white",
            height=350
        )
        fig_risco.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_risco, use_container_width=True)
        st.markdown("""
            <div style="font-size: 0.8rem; color: #718096; margin-top: 10px; border-top: 1px dotted #CBD5E0; padding-top: 10px;">
                Escore Framingham por pontos · Reclassificação SBC 2019 · Seções 9-10
            </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ Dados de risco cardiovascular indisponíveis.")

# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Superintendência de Atenção Primária")
