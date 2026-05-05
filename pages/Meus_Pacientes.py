"""
Page: Meus Pacientes
====================

Wrapper fino que delega toda a UI para
`components.lista_pacientes.renderizar_lista_pacientes`.

Comportamento por perfil:
  - 'equipe' (ESF): território vem fixo do contexto_territorial; a
    sidebar mostra "Sua equipe" + botões de voltar/trocar/sair, e
    o componente é chamado com incluir_sidebar=False.
  - Outros perfis: comportamento clássico, sidebar do componente
    com selectboxes editáveis.
"""
import streamlit as st
from components.cabecalho import renderizar_cabecalho
from components.lista_pacientes import renderizar_lista_pacientes
from utils.auth import (
    requer_login, get_perfil, get_contexto_territorial, logout,
)
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
)

st.set_page_config(
    page_title="Meus Pacientes",
    page_icon="🧑‍⚕️",
    layout="wide",
)

# Login obrigatório
_usuario = requer_login()
_perfil  = get_perfil()

renderizar_cabecalho("Pacientes")

if _perfil == 'equipe':
    # ESF: usa contexto territorial fixo, sidebar custom (sem
    # selectboxes do componente).
    _ctx = get_contexto_territorial()
    _ap  = _ctx.get('ap')
    _cli = _ctx.get('clinica')
    _esf = _ctx.get('esf')
    if not (_ap and _cli and _esf):
        st.error(
            "⚠️ Sua equipe não está selecionada. Volte para a tela "
            "inicial e escolha sua AP, Clínica e ESF."
        )
        st.page_link("Home.py", label="↩ Voltar para a tela inicial",
                      icon="🏠")
        st.stop()

    st.sidebar.header("🎯 Sua equipe")
    st.sidebar.markdown(
        f"**AP:** {anonimizar_ap(str(_ap))}  \n"
        f"**Clínica:** {anonimizar_clinica(_cli)}  \n"
        f"**ESF:** {anonimizar_esf(_esf)}"
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("↩ Voltar à Visão ESF",
                          use_container_width=True,
                          type="primary", key="mp_voltar"):
        st.switch_page("pages/Visao_ESF.py")
    if st.sidebar.button("🔄 Trocar equipe", use_container_width=True,
                          key="mp_trocar"):
        st.session_state['contexto_territorial'] = None
        st.switch_page("Home.py")
    if st.sidebar.button("🚪 Sair", use_container_width=True,
                          key="mp_sair"):
        logout()

    renderizar_lista_pacientes(
        area=_ap, clinica=_cli, esf=_esf,
        scope="esf", incluir_sidebar=False,
    )
else:
    # Outros perfis: sidebar do componente com selectboxes editáveis
    renderizar_lista_pacientes(scope="page", incluir_sidebar=True)
