import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
from utils.bigquery_client import get_bigquery_client

# ═══════════════════════════════════════════════════════════════
# ANONIMIZAÇÃO DESATIVADA
# ═══════════════════════════════════════════════════════════════
# from utils.anonimizador import (
#     anonimizar_ap,
#     anonimizar_clinica,
#     anonimizar_esf,
#     mostrar_badge_anonimo,
#     MODO_ANONIMO
# )

# Funções stub para substituir anonimização (retornam valor original)
def anonimizar_ap(x): return str(x) if x else x
def anonimizar_clinica(x): return str(x) if x else x
def anonimizar_esf(x): return str(x) if x else x
def mostrar_badge_anonimo(): pass
MODO_ANONIMO = False

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Lacunas de Cuidado",
    page_icon="⚠️",
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
    default_index=3,
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
    st.switch_page("Home.py")
elif selected == "Minha População":
    st.switch_page("pages/Minha_Populacao.py")
elif selected == "Meus Pacientes":
    st.switch_page("pages/Meus_Pacientes.py")
elif selected == "Acesso e Continuidade":
    st.switch_page("pages/Acesso_Continuidade.py")
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# FUNÇÃO PARA CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def carregar_lacunas():
    """Carrega dados de lacunas de cuidado"""
    client = get_bigquery_client()
    
    query = """
    SELECT 
        categoria,
        lacuna,
        area_programatica_cadastro,
        nome_clinica_cadastro,
        nome_esf_cadastro,
        n_total_elegivel,
        n_com_lacuna,
        percentual_lacuna
    FROM `rj-sms-sandbox.sub_pav_us.MM_sumario_lacunas`
    WHERE percentual_lacuna IS NOT NULL
    ORDER BY area_programatica_cadastro, nome_clinica_cadastro, nome_esf_cadastro
    """
    
    df = client.query(query).to_dataframe()
    return df

# ═══════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
st.title("⚠️ Lacunas de Cuidado")

with st.spinner("📊 Carregando dados de lacunas..."):
    try:
        df = carregar_lacunas()
        st.success(f"✅ {len(df):,} registros carregados")
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {str(e)}")
        st.stop()

# ═══════════════════════════════════════════════════════════════
# USAR NOMES REAIS (ANONIMIZAÇÃO DESATIVADA)
# ═══════════════════════════════════════════════════════════════
# Criar colunas que usam os valores reais ao invés de anonimizados
df['ap_anonima'] = df['area_programatica_cadastro'].apply(
    lambda x: str(x) if pd.notna(x) else x
)
df['clinica_anonima'] = df['nome_clinica_cadastro'].apply(
    lambda x: str(x) if pd.notna(x) else x
)
df['esf_anonima'] = df['nome_esf_cadastro'].apply(
    lambda x: str(x) if pd.notna(x) else x
)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR - FILTROS (BADGE ANONIMIZAÇÃO DESATIVADO)
# ═══════════════════════════════════════════════════════════════
# mostrar_badge_anonimo()  # Desativado

st.sidebar.header("🔍 Filtros")

# ═══════════════════════════════════════════════════════════════
# FILTRO DE CATEGORIA
# ═══════════════════════════════════════════════════════════════
categorias_disponiveis = ['Todas'] + sorted([c for c in df['categoria'].unique() if c is not None and pd.notna(c)])
categoria_selecionada = st.sidebar.selectbox(
    "📋 Categoria",
    options=categorias_disponiveis,
    index=0
)

# ═══════════════════════════════════════════════════════════════
# FILTRO DE LACUNA (depende da categoria)
# ═══════════════════════════════════════════════════════════════
if categoria_selecionada != 'Todas':
    df_temp_lacuna = df[df['categoria'] == categoria_selecionada]
else:
    df_temp_lacuna = df

lacunas_disponiveis = ['Todas'] + sorted([l for l in df_temp_lacuna['lacuna'].unique() if l is not None and pd.notna(l)])
lacuna_selecionada = st.sidebar.selectbox(
    "🏷️ Lacuna Específica",
    options=lacunas_disponiveis,
    index=0
)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Território")

# ═══════════════════════════════════════════════════════════════
# FILTRO HIERÁRQUICO - ÁREA PROGRAMÁTICA (ANONIMIZADA)
# ═══════════════════════════════════════════════════════════════
aps_disponiveis = ['Todas'] + sorted([ap for ap in df['ap_anonima'].unique() if ap is not None and pd.notna(ap)])
ap_selecionada = st.sidebar.selectbox(
    "🗺️ Área Programática",
    options=aps_disponiveis,
    index=0
)

# Filtrar clínicas baseado na AP selecionada
if ap_selecionada != 'Todas':
    df_filtrado_ap = df[df['ap_anonima'] == ap_selecionada]
else:
    df_filtrado_ap = df

clinicas_disponiveis = ['Todas'] + sorted([c for c in df_filtrado_ap['clinica_anonima'].unique() if c is not None and pd.notna(c)])
clinica_selecionada = st.sidebar.selectbox(
    "🏥 Clínica",
    options=clinicas_disponiveis,
    index=0
)

# Filtrar ESF baseado na clínica selecionada
if clinica_selecionada != 'Todas':
    df_filtrado_clinica = df_filtrado_ap[df_filtrado_ap['clinica_anonima'] == clinica_selecionada]
else:
    df_filtrado_clinica = df_filtrado_ap

esfs_disponiveis = ['Todas'] + sorted([e for e in df_filtrado_clinica['esf_anonima'].unique() if e is not None and pd.notna(e)])
esf_selecionada = st.sidebar.selectbox(
    "👥 Equipe de Saúde da Família",
    options=esfs_disponiveis,
    index=0
)

# ═══════════════════════════════════════════════════════════════
# APLICAR TODOS OS FILTROS
# ═══════════════════════════════════════════════════════════════
df_filtrado = df.copy()

if categoria_selecionada != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_selecionada]

if lacuna_selecionada != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['lacuna'] == lacuna_selecionada]

if ap_selecionada != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['ap_anonima'] == ap_selecionada]

if clinica_selecionada != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['clinica_anonima'] == clinica_selecionada]

if esf_selecionada != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['esf_anonima'] == esf_selecionada]

# ═══════════════════════════════════════════════════════════════
# CARDS DE MÉTRICAS
# ═══════════════════════════════════════════════════════════════
st.markdown("### 📊 Visão Geral")

col1, col2, col3, col4 = st.columns(4)

with col1:
    n_registros = len(df_filtrado)
    st.metric("📝 Total de Registros", f"{n_registros:,}")

with col2:
    n_categorias = df_filtrado['categoria'].nunique()
    st.metric("📋 Categorias", n_categorias)

with col3:
    media_lacuna = df_filtrado['percentual_lacuna'].mean() if len(df_filtrado) > 0 else 0
    st.metric("📊 Lacuna Média", f"{media_lacuna:.1f}%")

with col4:
    max_lacuna = df_filtrado['percentual_lacuna'].max() if len(df_filtrado) > 0 else 0
    st.metric("⚠️ Lacuna Máxima", f"{max_lacuna:.1f}%")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# VISUALIZAÇÕES
# ═══════════════════════════════════════════════════════════════

# Abas para organizar visualizações
tab1, tab2, tab3 = st.tabs(["📊 Por Categoria", "🏥 Por Território", "📋 Dados Detalhados"])

with tab1:
    st.subheader("📊 Lacunas por Categoria")
    
    # Agrupar por categoria
    df_categoria = df_filtrado.groupby('categoria').agg({
        'percentual_lacuna': 'mean'
    }).reset_index().sort_values('percentual_lacuna', ascending=True)
    
    if not df_categoria.empty:
        fig_categoria = px.bar(
            df_categoria,
            x='percentual_lacuna',
            y='categoria',
            orientation='h',
            labels={'percentual_lacuna': 'Percentual Médio de Lacuna (%)', 'categoria': 'Categoria'},
            color='percentual_lacuna',
            color_continuous_scale='Reds',
            title='Percentual Médio de Lacuna por Categoria'
        )
        fig_categoria.update_layout(height=500, showlegend=False)
        st.plotly_chart(fig_categoria, use_container_width=True)
    else:
        st.info("Nenhum dado disponível para os filtros selecionados")

with tab2:
    st.subheader("🗺️ Lacunas por Território")
    
    # ═══════════════════════════════════════════════════════════════
    # 🎻 VIOLIN PLOT - DISTRIBUIÇÃO POR ÁREA PROGRAMÁTICA
    # ═══════════════════════════════════════════════════════════════
    st.markdown("### 📊 Distribuição de Clínicas por Área")
    
    # Agregar dados por clínica para o violin plot (cada ponto = uma clínica)
    df_clinica_violin = df_filtrado.groupby(['ap_anonima', 'clinica_anonima']).agg({
        'percentual_lacuna': 'mean'
    }).reset_index()
    
    if not df_clinica_violin.empty and len(df_clinica_violin) > 0:
        # Ordenar APs para exibição consistente
        ap_ordenadas = sorted(df_clinica_violin['ap_anonima'].unique().tolist())
        
        # Criar violin plot com pontos - EIXO X CATEGÓRICO
        fig_violin = px.violin(
            df_clinica_violin,
            x='ap_anonima',
            y='percentual_lacuna',
            color='ap_anonima',
            box=True,  # Adiciona boxplot interno
            points='all',  # Mostra todos os pontos (cada clínica)
            hover_data=['clinica_anonima'],
            labels={
                'percentual_lacuna': '% Lacuna',
                'ap_anonima': 'Área Programática',
                'clinica_anonima': 'Clínica'
            },
            title='Distribuição de % Lacuna por Área Programática | Cada Ponto = Uma Clínica',
            category_orders={'ap_anonima': ap_ordenadas}
        )
        
        fig_violin.update_layout(
            height=500,
            showlegend=False,
            xaxis_title='Área Programática',
            yaxis_title='% Lacuna',
            yaxis=dict(range=[0, 100]),
            xaxis_type='category'  # FORÇAR EIXO X COMO CATEGÓRICO
        )
        
        # Ajustar tamanho dos pontos
        fig_violin.update_traces(
            pointpos=0,
            jitter=0.3,
            marker=dict(size=6, opacity=0.7)
        )
        
        st.plotly_chart(fig_violin, use_container_width=True)
        
        st.info("💡 **Interpretação:** Cada ponto = uma clínica. A largura do violin indica onde há mais clínicas com aquele %. O boxplot interno mostra mediana e quartis.")
    else:
        st.info("Nenhum dado disponível para o violin plot")
    
    st.markdown("---")
    
    # ═══════════════════════════════════════════════════════════════
    # GRÁFICOS DE BARRAS
    # ═══════════════════════════════════════════════════════════════
    col1, col2 = st.columns(2)
    
    with col1:
        # Por Área Programática (anonimizada)
        df_ap = df_filtrado.groupby('ap_anonima').agg({
            'percentual_lacuna': 'mean'
        }).reset_index().sort_values('percentual_lacuna', ascending=False)
        
        if not df_ap.empty:
            fig_ap = px.bar(
                df_ap,
                x='ap_anonima',
                y='percentual_lacuna',
                labels={'percentual_lacuna': 'Lacuna (%)', 'ap_anonima': 'Área Programática'},
                color='percentual_lacuna',
                color_continuous_scale='Oranges',
                title='Lacuna Média por Área Programática'
            )
            fig_ap.update_layout(height=400, showlegend=False)
            fig_ap.update_xaxes(type='category')
            st.plotly_chart(fig_ap, use_container_width=True)
    
    with col2:
        # Por Clínica (top 10) - anonimizada
        df_clinica = df_filtrado.groupby('clinica_anonima').agg({
            'percentual_lacuna': 'mean'
        }).reset_index().sort_values('percentual_lacuna', ascending=False).head(10)
        
        if not df_clinica.empty:
            fig_clinica = px.bar(
                df_clinica,
                x='clinica_anonima',
                y='percentual_lacuna',
                labels={'percentual_lacuna': 'Lacuna (%)', 'clinica_anonima': 'Clínica'},
                color='percentual_lacuna',
                color_continuous_scale='Reds',
                title='Top 10 Clínicas com Maior Lacuna'
            )
            fig_clinica.update_layout(height=400, showlegend=False)
            fig_clinica.update_xaxes(tickangle=45, type='category')
            st.plotly_chart(fig_clinica, use_container_width=True)

with tab3:
    st.subheader("📋 Dados Detalhados")
    
    # Selecionar colunas para exibição (usando anonimizadas)
    colunas_exibir = ['categoria', 'lacuna', 'ap_anonima', 'clinica_anonima', 
                      'esf_anonima', 'n_total_elegivel', 'n_com_lacuna', 'percentual_lacuna']
    
    # Renomear para exibição
    df_exibir = df_filtrado[colunas_exibir].copy()
    df_exibir.columns = ['Categoria', 'Lacuna', 'Área Programática', 'Clínica', 
                         'ESF', 'Total Elegível', 'Com Lacuna', '% Lacuna']
    
    # Configurar exibição
    st.dataframe(
        df_exibir.sort_values('% Lacuna', ascending=False),
        use_container_width=True,
        height=500
    )
    
    # Botão para download
    csv = df_exibir.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="lacunas_cuidado.csv",
        mime="text/csv"
    )

# ═══════════════════════════════════════════════════════════════
# ANÁLISE DE LACUNAS CRÍTICAS
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("🚨 Lacunas Críticas (> 50%)")

df_criticas = df_filtrado[df_filtrado['percentual_lacuna'] > 50].sort_values('percentual_lacuna', ascending=False)

if not df_criticas.empty:
    st.warning(f"⚠️ Identificadas **{len(df_criticas)}** lacunas críticas nos filtros selecionados")
    
    # Mostrar top 10 (com dados anonimizados)
    df_criticas_exibir = df_criticas.head(10)[['categoria', 'lacuna', 'clinica_anonima', 
                                                'esf_anonima', 'percentual_lacuna']].copy()
    df_criticas_exibir.columns = ['Categoria', 'Lacuna', 'Clínica', 'ESF', '% Lacuna']
    
    st.dataframe(df_criticas_exibir, use_container_width=True)
else:
    st.success("✅ Nenhuma lacuna crítica identificada nos filtros selecionados")

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ | Superintendência de Atenção Primária | Lacunas de Cuidado")