"""
Home.py — entrypoint do Navegador Clínico.

Responsabilidades:
  1. Tela de seleção de perfil (ESF, Gerente, AP, SAP).
  2. Login do perfil escolhido (hardcoded por enquanto — só ESF
     habilitado: usuário 'equipe', senha 'esf123').
  3. Tela de seleção territorial (AP → Clínica → ESF).
  4. Roteamento via st.navigation: para o perfil 'equipe', apenas a
     page Visão ESF é exposta. Demais pages do diretório pages/
     ficam ocultas até implementarmos as visualizações dos outros
     perfis.
"""

import streamlit as st

from utils.auth import (
    verificar_login_demo,
    set_contexto_territorial,
    logout,
)
from utils.data_loader import carregar_opcoes_filtros
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
)
from utils import theme as T


# ═══════════════════════════════════════════════════════════════
# Page config — único do app (entrypoint)
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Navegador Clínico",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Esconde o menu nativo de pages (sidebar) — navegação é controlada
# manualmente com st.switch_page, condicional a perfil + contexto.
st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════
# Estado da sessão
# ═══════════════════════════════════════════════════════════════
def _init_state():
    defaults = {
        'usuario_logado':       None,
        'usuario_global':       None,    # compat. com outras pages
        'contexto_territorial': None,
        'perfil_em_login':      None,    # perfil clicado no card
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


# ═══════════════════════════════════════════════════════════════
# Tela 1 — seleção de perfil (4 cards)
# ═══════════════════════════════════════════════════════════════
def render_selecao_perfil():
    st.markdown(
        f"<div style='text-align:center; margin-top:24px;'>"
        f"<h1 style='margin-bottom:6px;'>🏥 Navegador Clínico</h1>"
        f"<p style='font-size:1.05em; color:{T.TEXT_MUTED};'>"
        f"Multimorbidade, polifarmácia e qualidade do cuidado na "
        f"Atenção Primária do município do Rio de Janeiro."
        f"</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("### Selecione seu perfil de acesso")
    st.markdown("&nbsp;")

    perfis = [
        {
            'icon': '👨‍⚕️',
            'titulo': 'ESF',
            'subtitulo': 'Equipe de Saúde da Família',
            'perfil': 'equipe',
            'disponivel': True,
        },
        {
            'icon': '🏥',
            'titulo': 'Gerente',
            'subtitulo': 'Gerente de Clínica',
            'perfil': 'gerente',
            'disponivel': False,
        },
        {
            'icon': '📍',
            'titulo': 'AP',
            'subtitulo': 'Coordenação de Área Programática',
            'perfil': 'gestor',
            'disponivel': False,
        },
        {
            'icon': '🛠️',
            'titulo': 'Admin',
            'subtitulo': 'Acesso completo (todas as pages)',
            'perfil': 'admin',
            'disponivel': True,
        },
    ]

    cols = st.columns(4)
    for col, p in zip(cols, perfis):
        with col:
            st.markdown(
                f"<div style='border:1px solid {T.BORDER}; "
                f"border-radius:10px; padding:18px 14px; "
                f"text-align:center; height:160px; "
                f"background:{T.CARD_BG};'>"
                f"<div style='font-size:2.6em; line-height:1;'>"
                f"{p['icon']}</div>"
                f"<div style='font-size:1.15em; font-weight:600; "
                f"margin-top:6px; color:{T.TEXT};'>{p['titulo']}</div>"
                f"<div style='font-size:0.85em; color:{T.TEXT_MUTED}; "
                f"margin-top:4px; line-height:1.3;'>{p['subtitulo']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if p['disponivel']:
                if st.button(
                    f"Entrar como {p['titulo']}",
                    use_container_width=True,
                    type="primary",
                    key=f"btn_perfil_{p['perfil']}",
                ):
                    st.session_state['perfil_em_login'] = p['perfil']
                    st.rerun()
            else:
                st.button(
                    "🚧 Em construção",
                    use_container_width=True,
                    disabled=True,
                    key=f"btn_perfil_{p['perfil']}",
                )


# ═══════════════════════════════════════════════════════════════
# Tela 2 — login (form usuário + senha)
# ═══════════════════════════════════════════════════════════════
def render_login(perfil: str):
    rotulos = {
        'equipe':  '👨‍⚕️ Equipe de Saúde da Família',
        'gerente': '🏥 Gerente de Clínica',
        'gestor':  '📍 Coordenação de Área Programática',
        'admin':   '🛠️ Admin (acesso completo)',
    }
    rotulo = rotulos.get(perfil, perfil)

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(f"## {rotulo}")
        st.caption("Entre com seu usuário e senha:")
        with st.form("form_login", clear_on_submit=False):
            username = st.text_input("Usuário")
            senha    = st.text_input("Senha", type="password")
            cb1, cb2 = st.columns(2)
            with cb1:
                voltar = st.form_submit_button(
                    "⬅️ Voltar", use_container_width=True
                )
            with cb2:
                entrar = st.form_submit_button(
                    "Entrar", type="primary", use_container_width=True
                )

        if voltar:
            st.session_state['perfil_em_login'] = None
            st.rerun()

        if entrar:
            if not username or not senha:
                st.warning("⚠️ Preencha usuário e senha.")
            else:
                user = verificar_login_demo(
                    username, senha, perfil_esperado=perfil
                )
                if user:
                    st.session_state['usuario_logado'] = user
                    st.session_state['usuario_global'] = user
                    st.session_state['perfil_em_login'] = None
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos.")


# ═══════════════════════════════════════════════════════════════
# Tela 3 — seleção territorial (AP → Clínica → ESF)
# ═══════════════════════════════════════════════════════════════
def render_selecao_territorial():
    user = st.session_state['usuario_logado']

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(
            f"### 👋 Olá, **{user.get('nome_completo', 'colega')}**"
        )
        st.markdown("##### Selecione sua equipe")
        st.caption(
            "Escolha a Área Programática, a Clínica e a Equipe de "
            "Saúde da Família que você acompanha. Depois de "
            "confirmar, você entra direto na Visão ESF."
        )

        opcoes = carregar_opcoes_filtros()
        aps = sorted(opcoes.get('areas', []))
        if not aps:
            st.error("Sem opções de filtro disponíveis.")
            return

        ap = st.selectbox(
            "Área Programática",
            options=[None] + aps,
            format_func=lambda x: (
                "— Selecione —" if x is None else anonimizar_ap(str(x))
            ),
            key="seltrr_ap",
        )

        clinicas = sorted(opcoes.get('clinicas', {}).get(ap, [])) if ap else []
        cli = st.selectbox(
            "Clínica da Família",
            options=[None] + clinicas,
            format_func=lambda x: (
                "— Selecione —" if x is None else anonimizar_clinica(x)
            ),
            key="seltrr_cli",
            disabled=not ap,
        )

        esfs = sorted(opcoes.get('esf', {}).get(cli, [])) if cli else []
        esf = st.selectbox(
            "Equipe ESF",
            options=[None] + esfs,
            format_func=lambda x: (
                "— Selecione —" if x is None else anonimizar_esf(x)
            ),
            key="seltrr_esf",
            disabled=not cli,
        )

        pode_confirmar = bool(ap and cli and esf)

        st.markdown("&nbsp;")
        cb1, cb2 = st.columns([1, 2])
        with cb1:
            if st.button(
                "🚪 Sair",
                use_container_width=True,
                key="seltrr_sair",
            ):
                logout()
        with cb2:
            if st.button(
                "✅ Confirmar e entrar",
                type="primary",
                disabled=not pode_confirmar,
                use_container_width=True,
                key="seltrr_ok",
            ):
                set_contexto_territorial(ap=ap, clinica=cli, esf=esf)
                st.rerun()


# ═══════════════════════════════════════════════════════════════
# ROTEAMENTO
# ═══════════════════════════════════════════════════════════════
usuario = st.session_state.get('usuario_logado')

# Etapa 1: não logado → seleção de perfil ou login
if not usuario:
    if st.session_state.get('perfil_em_login'):
        render_login(st.session_state['perfil_em_login'])
    else:
        render_selecao_perfil()
    st.stop()

_perfil = usuario.get('perfil', 'equipe')

# Etapa 2: ESF precisa selecionar AP/Clínica/ESF antes de entrar em
# Visão ESF. Outros perfis (admin / gestor / gerente) têm acesso a
# todas as pages — vão direto para a Home com o menu horizontal.
if _perfil == 'equipe':
    if not st.session_state.get('contexto_territorial'):
        render_selecao_territorial()
        st.stop()
    # ESF logado e com contexto: redireciona para Visão ESF
    st.switch_page("pages/Visao_ESF.py")

# ═══════════════════════════════════════════════════════════════
# Home para perfis não-ESF (admin / gestor / gerente)
# Renderiza o menu horizontal de pages (via renderizar_cabecalho) +
# uma lista de page_links como ponto de partida. Cada page mantém
# seu próprio set_page_config + sidebar de filtros editáveis.
# ═══════════════════════════════════════════════════════════════
from components.cabecalho import renderizar_cabecalho
renderizar_cabecalho("Home")

st.markdown("## 👋 Bem-vindo")
st.caption(
    "Você tem acesso a todas as visualizações do Navegador Clínico. "
    "Use o menu acima ou os atalhos abaixo para navegar."
)

st.markdown("---")
st.markdown("### 📑 Visualizações disponíveis")

links = [
    ("pages/Minha_Populacao.py",     "👥 Minha População",
     "Pirâmides etárias, distribuição da Carga de Morbidade."),
    ("pages/Meus_Pacientes.py",      "🧑‍⚕️ Meus Pacientes",
     "Lista nominal completa com filtros e card por paciente."),
    ("pages/Lacunas_de_Cuidado.py",  "⚠️ Lacunas de Cuidado",
     "Lacunas de cuidado por território, com benchmark."),
    ("pages/Acesso_Continuidade.py", "🔄 Acesso e Continuidade",
     "Indicadores de regularidade, fragmentação e iniquidade."),
    ("pages/Polifarmacia_ACB.py",    "💊 Carga farmacológica",
     "Polifarmácia, STOPP/START/Beers e Escore ACB."),
    ("pages/Diabetes.py",            "🩸 Diabetes",
     "Controle glicêmico, complicações e farmacologia."),
    ("pages/Hipertensao.py",         "🩺 Hipertensão",
     "Controle pressórico, medicamentos e Risco CV (HEARTS)."),
    ("pages/Risco_Cardiovascular.py","❤️ Risco Cardiovascular",
     "Comparação dos estimadores Framingham/SBC e WHO/HEARTS."),
    ("pages/Visao_ESF.py",           "📋 Visão ESF",
     "Visão consolidada por equipe (storytelling em abas)."),
]

for path, titulo, descricao in links:
    col_a, col_b = st.columns([3, 5])
    with col_a:
        st.page_link(path, label=titulo)
    with col_b:
        st.caption(descricao)
