"""
Page: Meus Pacientes
====================

Wrapper fino que delega toda a UI para
`components.lista_pacientes.renderizar_lista_pacientes`. A mesma
função é usada na aba "Meus Pacientes" da page Visão ESF.
"""
import streamlit as st
from components.cabecalho import renderizar_cabecalho
from components.lista_pacientes import renderizar_lista_pacientes

st.set_page_config(
    page_title="Meus Pacientes",
    page_icon="🧑‍⚕️",
    layout="wide",
)

# Verificar login (renderizar_cabecalho também faz, mas reforça aqui)
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

renderizar_cabecalho("Pacientes")

renderizar_lista_pacientes(scope="page", incluir_sidebar=True)
