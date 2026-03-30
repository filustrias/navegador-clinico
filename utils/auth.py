# utils/auth.py
import streamlit as st
import hashlib
from utils.bigquery_client import get_bigquery_client

# ═══════════════════════════════════════════════════════════════
# PERFIS VÁLIDOS E SUAS HIERARQUIAS
# ═══════════════════════════════════════════════════════════════

PERFIS_VALIDOS = ['admin', 'gestor', 'gerente', 'equipe']

# Hierarquia: cada perfil inclui as permissões dos abaixo dele
HIERARQUIA_PERFIS = {
    'admin':   4,
    'gestor':  3,
    'gerente': 2,
    'equipe':  1,
}

# Rótulos de exibição para cada perfil
ROTULOS_PERFIS = {
    'admin':   'Administrador',
    'gestor':  'Gestor Municipal',
    'gerente': 'Gerente de Clínica',
    'equipe':  'Equipe de Saúde da Família',
}

# Ícones por perfil
ICONES_PERFIS = {
    'admin':   '⚙️',
    'gestor':  '🏛️',
    'gerente': '🏥',
    'equipe':  '👨‍⚕️',
}


# ═══════════════════════════════════════════════════════════════
# FUNÇÕES EXISTENTES — sem alteração
# ═══════════════════════════════════════════════════════════════

def hash_senha(senha: str) -> str:
    """Gera hash SHA256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()


def verificar_login(username: str, senha: str) -> dict:
    """Verifica credenciais no BigQuery"""
    client = get_bigquery_client()
    senha_hash = hash_senha(senha)

    query = f"""
    SELECT username, nome_completo, email, perfil, area_programatica, clinica, esf,
           ultimo_acesso
    FROM `rj-sms-sandbox.sub_pav_us.MM_usuarios_navegador`
    WHERE username = '{username}'
      AND senha_hash = '{senha_hash}'
      AND ativo = TRUE
    """

    df = client.query(query).result().to_dataframe()

    if len(df) > 0:
        update_query = f"""
        UPDATE `rj-sms-sandbox.sub_pav_us.MM_usuarios_navegador`
        SET ultimo_acesso = CURRENT_TIMESTAMP()
        WHERE username = '{username}'
        """
        client.query(update_query).result()
        return df.iloc[0].to_dict()

    return None


def criar_usuario(username: str, senha: str, nome_completo: str, email: str = None,
                  perfil: str = 'equipe', area_programatica: str = None,
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
    if 'usuario_logado' in st.session_state and st.session_state.usuario_logado:
        return st.session_state.usuario_logado

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
    """Faz logout do usuário e limpa contexto territorial"""
    for chave in ['usuario_logado', 'usuario_global', 'contexto_territorial']:
        if chave in st.session_state:
            del st.session_state[chave]
    st.rerun()


def exibir_usuario_logado():
    """Exibe info do usuário na sidebar"""
    if 'usuario_logado' in st.session_state and st.session_state.usuario_logado:
        user = st.session_state.usuario_logado
        perfil = user.get('perfil', 'equipe')
        rotulo = ROTULOS_PERFIS.get(perfil, perfil)
        icone = ICONES_PERFIS.get(perfil, '👤')

        st.sidebar.markdown("---")
        st.sidebar.markdown(f"{icone} **{user['nome_completo']}**")
        st.sidebar.caption(f"{rotulo}")
        if st.sidebar.button("🚪 Sair", use_container_width=True):
            logout()
        return True
    return False


def requer_login():
    """
    MODO DESENVOLVIMENTO — login desativado.
    Para reativar: comente o bloco DEV e descomente o bloco PROD.
    """
    # ── DEV: bypass de login ──────────────────────────────────
    usuario_dev = {
        'username':      'dev',
        'nome_completo': 'Usuário Dev',
        'email':         'dev@sms.rio',
        'perfil':        'admin',          # acesso irrestrito
        'area_programatica': None,
        'clinica':       None,
        'esf':           None,
        'ultimo_acesso': None,
    }
    st.session_state['usuario_logado'] = usuario_dev
    return usuario_dev
    # ── PROD: descomente abaixo e remova o bloco DEV ──────────
    # if 'usuario_logado' not in st.session_state or not st.session_state.usuario_logado:
    #     login_form()
    #     st.stop()
    # return st.session_state.usuario_logado


# ═══════════════════════════════════════════════════════════════
# FUNÇÕES NOVAS — suporte aos 4 perfis
# ═══════════════════════════════════════════════════════════════

def get_perfil() -> str:
    """
    Retorna o perfil do usuário logado.
    Uso: perfil = get_perfil()  →  'admin' | 'gestor' | 'gerente' | 'equipe'
    """
    usuario = st.session_state.get('usuario_logado') or {}
    return usuario.get('perfil', 'equipe')


def get_contexto_territorial() -> dict:
    """
    Retorna o contexto territorial ativo da sessão.
    Preenchido pela Home após seleção do usuário.

    Retorna dict com chaves: ap, clinica, esf
    Valores None significam "sem restrição" (válido para gestor/admin).
    """
    return st.session_state.get('contexto_territorial', {
        'ap': None,
        'clinica': None,
        'esf': None,
    })


def set_contexto_territorial(ap=None, clinica=None, esf=None):
    """
    Salva o contexto territorial na sessão.
    Chamado pela Home após o usuário selecionar seu território.
    """
    st.session_state['contexto_territorial'] = {
        'ap': ap,
        'clinica': clinica,
        'esf': esf,
    }


def perfil_permite(acao: str) -> bool:
    """
    Verifica se o perfil atual tem permissão para uma ação.

    Ações disponíveis:
      'ver_todos_territorios'   → admin, gestor
      'ver_lista_nominal'       → todos
      'ver_benchmarks'          → admin, gestor
      'trocar_territorio'       → admin, gestor (gerente/equipe ficam fixos)
      'ver_dados_admin'         → apenas admin

    Uso:
      if perfil_permite('ver_todos_territorios'):
          ...
    """
    perfil = get_perfil()
    nivel = HIERARQUIA_PERFIS.get(perfil, 1)

    regras = {
        'ver_todos_territorios': nivel >= 3,   # admin, gestor
        'ver_lista_nominal':     nivel >= 1,   # todos
        'ver_benchmarks':        nivel >= 3,   # admin, gestor
        'trocar_territorio':     nivel >= 3,   # admin, gestor
        'ver_dados_admin':       nivel >= 4,   # apenas admin
    }

    return regras.get(acao, False)