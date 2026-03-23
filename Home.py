import streamlit as st
from utils.bigquery_client import test_connection
from utils.data_loader import limpar_cache
from utils.auth import requer_login
from streamlit_option_menu import option_menu

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Navegador Clínico",
    page_icon="🏥",
    layout="wide"
)

# ═══════════════════════════════════════════════════════════════
# ✅ LOGIN GLOBAL - EXIGIR EM TODA A APLICAÇÃO
# ═══════════════════════════════════════════════════════════════
usuario_logado = requer_login()

# ═══════════════════════════════════════════════════════════════
# SALVAR USUÁRIO NO SESSION STATE PARA OUTRAS PÁGINAS
# ═══════════════════════════════════════════════════════════════
st.session_state['usuario_global'] = usuario_logado

# ═══════════════════════════════════════════════════════════════
# EXTRAIR DADOS DO USUÁRIO (é um dicionário)
# ═══════════════════════════════════════════════════════════════
if isinstance(usuario_logado, dict):
    nome = usuario_logado.get('nome_completo', 'Usuário')
    esf = usuario_logado.get('esf') or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

# ═══════════════════════════════════════════════════════════════
# 🎨 CABEÇALHO COM INFO DO USUÁRIO E NAVEGAÇÃO
# ═══════════════════════════════════════════════════════════════

# Esconder o menu lateral nativo do Streamlit
st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

# Header com título e usuário
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
    options=["Home", "Minha População", "Meus Pacientes", "Lacunas de Cuidado", "Acesso e Continuidade"],
    icons=['house-fill', 'people-fill', 'person-lines-fill', 'exclamation-triangle-fill', 'arrow-repeat'],
    menu_icon="cast",
    default_index=0,
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

# ⭐ NAVEGAÇÃO REAL - Redirecionar para outras páginas
if selected == "Minha População":
    st.switch_page("pages/Minha_Populacao.py")
elif selected == "Meus Pacientes":
    st.switch_page("pages/Meus_Pacientes.py")
elif selected == "Lacunas de Cuidado":
    st.switch_page("pages/Lacunas_de_Cuidado.py")
elif selected == "Acesso e Continuidade":
    st.switch_page("pages/Acesso_Continuidade.py")
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# CONTEÚDO DA HOME
# ═══════════════════════════════════════════════════════════════

# Testar conexão com BigQuery
with st.spinner("🔍 Testando conexão com BigQuery..."):
    conexao_ok = test_connection()

if conexao_ok:
    st.success("✅ Conexão com BigQuery estabelecida com sucesso!")
else:
    st.error("❌ Não foi possível conectar ao BigQuery. Verifique suas credenciais.")
    st.stop()

st.markdown("---")

# Título e apresentação
st.title("🏥 Navegador Clínico - Multimorbidade")
st.markdown("### SMS-RJ | Superintendência de Atenção Primária")

# Conteúdo
st.markdown("""
## Bem-vindo ao Navegador Clínico

Esta plataforma foi desenvolvida para apoiar a gestão e o cuidado de pacientes 
com multimorbidade na Atenção Primária à Saúde do município do Rio de Janeiro.

### 📊 Funcionalidades disponíveis:

- **Minha População**: Visualize características demográficas e clínicas
- **Meus Pacientes**: Acesse informações individuais detalhadas
- **Lacunas de Cuidado**: Monitore indicadores de qualidade terapêutica
- **Análise de Morbidades**: Foco em condições específicas *(em desenvolvimento)*
- **Polifarmácia**: Identifique critérios STOPP-START *(em desenvolvimento)*
- **Benchmarks**: Compare resultados entre territórios *(em desenvolvimento)*
- **Base de Conhecimento**: Acesse conteúdo educativo *(em desenvolvimento)*

---

**Use os botões no topo para navegar entre as páginas** 👆
""")

# Ferramentas na sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔧 Ferramentas")
if st.sidebar.button("🔄 Limpar Cache"):
    limpar_cache()
    st.sidebar.success("✅ Cache limpo!")

# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Superintendência de Atenção Primária")