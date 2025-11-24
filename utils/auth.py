# utils/auth.py
import streamlit as st
import hashlib
from utils.bigquery_client import get_bigquery_client

def hash_senha(senha: str) -> str:
    """Gera hash SHA256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

def verificar_login(username: str, senha: str) -> dict:
    """Verifica credenciais no BigQuery"""
    client = get_bigquery_client()
    senha_hash = hash_senha(senha)
    
    query = f"""
    SELECT username, nome_completo, email, perfil, area_programatica, clinica, esf
    FROM `rj-sms-sandbox.sub_pav_us.MM_usuarios_navegador`
    WHERE username = '{username}' 
    AND senha_hash = '{senha_hash}'
    AND ativo = TRUE
    """
    
    df = client.query(query).result().to_dataframe()
    
    if len(df) > 0:
        # Atualizar último acesso
        update_query = f"""
        UPDATE `rj-sms-sandbox.sub_pav_us.MM_usuarios_navegador`
        SET ultimo_acesso = CURRENT_TIMESTAMP()
        WHERE username = '{username}'
        """
        client.query(update_query).result()
        
        return df.iloc[0].to_dict()
    
    return None

def criar_usuario(username: str, senha: str, nome_completo: str, email: str = None, 
                  perfil: str = 'usuario', area_programatica: str = None, 
                  clinica: str = None, esf: str = None) -> bool:
    """Cria novo usuário no BigQuery"""
    client = get_bigquery_client()
    senha_hash = hash_senha(senha)
    
    query = f"""
    INSERT INTO `rj-sms-sandbox.sub_pav_us.MM_usuarios_navegador`
    (username, senha_hash, nome_completo, email, perfil, area_programatica, clinica, esf)
    VALUES (
        '{username}', 
        '{senha_hash}', 
        '{nome_completo}', 
        {'NULL' if not email else f"'{email}'"}, 
        '{perfil}',
        {'NULL' if not area_programatica else f"'{area_programatica}'"},
        {'NULL' if not clinica else f"'{clinica}'"},
        {'NULL' if not esf else f"'{esf}'"}
    )
    """
    
    try:
        client.query(query).result()
        return True
    except Exception as e:
        st.error(f"Erro ao criar usuário: {e}")
        return False

def login_form():
    """Exibe formulário de login e gerencia sessão"""
    
    # Se já logado, retorna dados do usuário
    if 'usuario_logado' in st.session_state and st.session_state.usuario_logado:
        return st.session_state.usuario_logado
    
    # Formulário de login
    st.markdown("## 🔐 Login")
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
        
        if submitted:
            if username and senha:
                usuario = verificar_login(username, senha)
                if usuario:
                    st.session_state.usuario_logado = usuario
                    st.success(f"Bem-vindo(a), {usuario['nome_completo']}!")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos")
            else:
                st.warning("⚠️ Preencha usuário e senha")
    
    return None

def logout():
    """Faz logout do usuário"""
    if 'usuario_logado' in st.session_state:
        del st.session_state.usuario_logado
    st.rerun()

def exibir_usuario_logado():
    """Exibe info do usuário na sidebar"""
    if 'usuario_logado' in st.session_state and st.session_state.usuario_logado:
        user = st.session_state.usuario_logado
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"👤 **{user['nome_completo']}**")
        st.sidebar.caption(f"Perfil: {user['perfil']}")
        if st.sidebar.button("🚪 Sair", use_container_width=True):
            logout()
        return True
    return False

def requer_login():
    """Decorator/função para exigir login"""
    if 'usuario_logado' not in st.session_state or not st.session_state.usuario_logado:
        login_form()
        st.stop()
    return st.session_state.usuario_logado