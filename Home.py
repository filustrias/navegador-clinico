import streamlit as st
from utils.bigquery_client import test_connection
from utils.data_loader import limpar_cache
from utils.auth import requer_login, exibir_usuario_logado

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
exibir_usuario_logado()

# ═══════════════════════════════════════════════════════════════
# SALVAR USUÁRIO NO SESSION STATE PARA OUTRAS PÁGINAS
# ═══════════════════════════════════════════════════════════════
st.session_state['usuario_global'] = usuario_logado

# Resto do código da Home...



# Título
st.title("🏥 Navegador Clínico - Multimorbidade")
st.markdown("### SMS-RJ | Superintendência de Atenção Primária")

st.markdown("---")

# Testar conexão com BigQuery
with st.spinner("🔍 Testando conexão com BigQuery..."):
    conexao_ok = test_connection()

if conexao_ok:
    st.success("✅ Conexão com BigQuery estabelecida com sucesso!")
else:
    st.error("❌ Não foi possível conectar ao BigQuery. Verifique suas credenciais.")
    st.stop()

# Conteúdo
st.markdown("""
## Bem-vindo ao Navegador Clínico

Esta plataforma foi desenvolvida para apoiar a gestão e o cuidado de pacientes 
com multimorbidade na Atenção Primária à Saúde do município do Rio de Janeiro.

### 📊 Funcionalidades disponíveis:

- **Minha População**: Visualize características demográficas e clínicas
- **Meus Pacientes**: Acesse informações individuais detalhadas
- **Análise de Morbidades**: Foco em condições específicas
- **Polifarmácia**: Identifique critérios STOPP-START
- **Lacunas de Cuidado**: Monitore indicadores de qualidade
- **Benchmarks**: Compare resultados entre territórios
- **Base de Conhecimento**: Acesse conteúdo educativo

---

👈 **Use o menu lateral para navegar entre as páginas**
""")

# Botão para limpar cache (apenas para desenvolvedores)
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔧 Ferramentas")
if st.sidebar.button("🔄 Limpar Cache"):
    limpar_cache()

# Rodapé
st.markdown("---")
st.caption("SMS-RJ")