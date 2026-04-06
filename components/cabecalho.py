# components/cabecalho.py
"""
Cabeçalho unificado do Navegador Clínico.

Uso em cada página:
    from components.cabecalho import renderizar_cabecalho
    renderizar_cabecalho("Continuidade")   # nome exato da chave em ROTAS
"""

import streamlit as st
from streamlit_option_menu import option_menu
from utils.auth import (
    get_perfil, get_contexto_territorial, logout,
    ROTULOS_PERFIS, ICONES_PERFIS
)
from utils.data_loader import limpar_cache
from utils import theme as T

# ═══════════════════════════════════════════════════════════════
# ROTAS E ÍCONES — definidos UMA ÚNICA VEZ aqui
# Adicionar nova page = 1 entrada em ROTAS + 1 ícone em ICONES_MENU
# ═══════════════════════════════════════════════════════════════

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

# Garantia: ROTAS e ICONES_MENU devem ter o mesmo tamanho
assert len(ROTAS) == len(ICONES_MENU), (
    f"ROTAS tem {len(ROTAS)} entradas mas ICONES_MENU tem {len(ICONES_MENU)}. "
    f"Adicione o ícone correspondente ao adicionar uma nova rota."
)

_CSS_GLOBAL = f"""
<style>
    [data-testid="stSidebarNav"] {{ display: none; }}
    .nav-titulo h1 {{ margin: 0; padding: 0; color: {T.TEXT}; font-size: 1.6em; line-height: 1.2; }}
    .nav-titulo small {{ color: {T.TEXT_MUTED}; font-size: 0.45em; font-weight: 400; }}
    .nav-usuario {{ text-align: right; padding-top: 8px; color: {T.TEXT}; font-size: 0.88em; line-height: 1.6; }}
    .badge-contexto {{
        display: inline-block; background-color: {T.BADGE_BG};
        border: 1px solid {T.BADGE_BORDER}; border-radius: 20px;
        padding: 2px 12px; font-size: 0.78em; color: {T.BADGE_TEXT};
        font-weight: 600; margin-top: 4px;
    }}
</style>
"""


def _verificar_login() -> dict:
    usuario = st.session_state.get('usuario_global') or st.session_state.get('usuario_logado')
    if not usuario:
        st.warning("⚠️ Sessão expirada. Faça login novamente.")
        st.page_link("Home.py", label="→ Ir para o Login")
        st.stop()
    return usuario


def _linha_contexto(ctx: dict, perfil: str) -> str:
    if perfil in ('admin', 'gestor'):
        return "Acesso irrestrito"
    if ctx.get('esf'):
        return f"ESF: {ctx['esf']}"
    if ctx.get('clinica'):
        return f"Clínica: {ctx['clinica']}"
    if ctx.get('ap'):
        return f"AP: {ctx['ap']}"
    return "Território não selecionado"


def renderizar_cabecalho(pagina_atual: str) -> None:
    """
    Renderiza o cabeçalho completo.
    pagina_atual: chave exata do dicionário ROTAS (ex: "Diabetes", "Hipertensão")
    """
    if pagina_atual not in ROTAS:
        raise ValueError(
            f"Página '{pagina_atual}' não encontrada em ROTAS. "
            f"Páginas disponíveis: {list(ROTAS.keys())}"
        )

    # 1. Login
    usuario = _verificar_login()

    # 2. Dados do usuário
    nome      = usuario.get('nome_completo', 'Usuário') if isinstance(usuario, dict) else str(usuario)
    perfil    = get_perfil()
    rotulo    = ROTULOS_PERFIS.get(perfil, perfil)
    icone_u   = ICONES_PERFIS.get(perfil, '👤')
    ctx       = get_contexto_territorial()
    linha_ctx = _linha_contexto(ctx, perfil)

    # 3. CSS
    st.markdown(_CSS_GLOBAL, unsafe_allow_html=True)

    # 4. Header
    col_titulo, col_usuario = st.columns([3, 1])
    with col_titulo:
        st.markdown("""
        <div class='nav-titulo'>
            <h1>🏥 Navegador Clínico
                <small>SMS-RJ · Atenção Primária</small>
            </h1>
        </div>
        """, unsafe_allow_html=True)
    with col_usuario:
        st.markdown(f"""
        <div class='nav-usuario'>
            {icone_u} <strong>{nome}</strong><br>
            <span style='color:{T.TEXT_MUTED}; font-size:0.9em;'>{rotulo}</span><br>
            <span class='badge-contexto'>{linha_ctx}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"<hr style='border:none; border-top:1px solid {T.DIVIDER}; margin:10px 0 0 0;'>",
                unsafe_allow_html=True)

    # 5. Menu de navegação
    selected = option_menu(
        menu_title=None,
        options=list(ROTAS.keys()),
        icons=ICONES_MENU,
        default_index=list(ROTAS.keys()).index(pagina_atual),
        orientation="horizontal",
        styles={
            "container":         {"padding": "0!important", "background-color": T.NAV_BG},
            "icon":              {"font-size": "22px", "color": T.TEXT,
                                  "display": "block", "margin-bottom": "4px"},
            "nav-link":          {"font-size": "11px", "text-align": "center",
                                  "margin": "0px", "padding": "10px 18px",
                                  "color": T.NAV_LINK, "background-color": T.SECONDARY_BG,
                                  "--hover-color": T.NAV_HOVER, "display": "flex",
                                  "flex-direction": "column", "align-items": "center",
                                  "line-height": "1.2", "white-space": "nowrap"},
            "nav-link-selected": {"background-color": T.NAV_SELECTED_BG,
                                  "color": T.NAV_SELECTED_TEXT, "font-weight": "600"},
        }
    )
    if selected != pagina_atual:
        st.switch_page(ROTAS[selected])

    st.markdown(f"<hr style='border:none; border-top:1px solid {T.DIVIDER}; margin:0 0 16px 0;'>",
                unsafe_allow_html=True)

    # 6. Sidebar
    st.sidebar.markdown(f"### {icone_u} {nome}")
    st.sidebar.caption(rotulo)
    st.sidebar.caption(linha_ctx)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Ferramentas")

    if st.sidebar.button("🔄 Limpar Cache", use_container_width=True, key=f"_cache_{pagina_atual}"):
        limpar_cache()
        st.sidebar.success("✅ Cache limpo!")

    if st.sidebar.button("🚪 Sair", use_container_width=True, key=f"_logout_{pagina_atual}"):
        logout()