"""
Componentes de filtros reutilizáveis
"""
import streamlit as st
from utils.data_loader import carregar_opcoes_filtros
from utils.anonimizador import (
    anonimizar_ap,
    anonimizar_clinica,
    anonimizar_esf,
    mostrar_badge_anonimo,
    MODO_ANONIMO
)



def filtros_territoriais(
    key_prefix="",
    obrigatorio_esf=False,
    mostrar_todas_opcoes=True
):
    """
    Renderiza filtros hierárquicos: AP > Clínica > ESF
    """
    
    # ✅ Mostrar badge de modo anônimo
    mostrar_badge_anonimo()
    
    # Carregar opções disponíveis
    opcoes = carregar_opcoes_filtros()
    
    if not opcoes['areas']:
        st.sidebar.error("❌ Não foi possível carregar opções de filtros")
        return {'ap': None, 'clinica': None, 'esf': None}
    
    # Área Programática
    areas = opcoes['areas']
    if mostrar_todas_opcoes:
        areas_display = ["Selecione..."] + areas
    else:
        areas_display = areas
    
    ap_selecionada = st.sidebar.selectbox(
        "📍 Área Programática",
        options=areas_display,
        format_func=lambda x: x if x == "Selecione..." else anonimizar_ap(str(x)),
        key=f"{key_prefix}_ap"
    )
    
    # Resetar se "Selecione..."
    if ap_selecionada == "Selecione...":
        ap_selecionada = None
    
    # Filtrar clínicas baseado na AP
    if ap_selecionada and ap_selecionada in opcoes['clinicas']:
        clinicas = opcoes['clinicas'][ap_selecionada]
    else:
        # Mostrar todas se AP não selecionada
        clinicas = []
        for ap_clinicas in opcoes['clinicas'].values():
            clinicas.extend(ap_clinicas)
        clinicas = sorted(list(set(clinicas)))
    
    if mostrar_todas_opcoes:
        clinicas_display = ["Selecione..."] + clinicas
    else:
        clinicas_display = clinicas
    
    clinica_selecionada = st.sidebar.selectbox(
        "🏥 Clínica da Família",
        options=clinicas_display,
        format_func=lambda x: x if x == "Selecione..." else anonimizar_clinica(x),
        key=f"{key_prefix}_clinica",
        disabled=not clinicas
    )
    
    if clinica_selecionada == "Selecione...":
        clinica_selecionada = None
    
    # Filtrar ESF baseado na clínica
    if clinica_selecionada and clinica_selecionada in opcoes['esf']:
        esf_list = opcoes['esf'][clinica_selecionada]
    else:
        esf_list = []
    
    if not obrigatorio_esf and mostrar_todas_opcoes:
        esf_display = ["Selecione..."] + esf_list
    else:
        esf_display = esf_list
    
    esf_selecionada = st.sidebar.selectbox(
        "👥 Equipe ESF",
        options=esf_display,
        format_func=lambda x: x if x == "Selecione..." else anonimizar_esf(x),
        key=f"{key_prefix}_esf",
        disabled=not esf_list
    )
    
    if esf_selecionada == "Selecione...":
        esf_selecionada = None
    
    # Retornar valores
    return {
        'ap': ap_selecionada,
        'clinica': clinica_selecionada,
        'esf': esf_selecionada
    }


def filtros_morbidades(key_prefix="", logica_padrao="E"):
    """
    Renderiza filtros de morbidades com lógica E/OU
    """
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🏥 Filtrar por Morbidades")
    
    # Lógica E/OU
    logica = st.sidebar.radio(
        "Lógica de filtro",
        options=["E", "OU"],
        index=0 if logica_padrao == "E" else 1,
        key=f"{key_prefix}_logica",
        help="E = paciente tem TODAS as condições | OU = paciente tem PELO MENOS UMA"
    )
    
    # Checkboxes das morbidades (campos DATE na sua tabela)
    dm = st.sidebar.checkbox("Diabetes", key=f"{key_prefix}_dm")
    has = st.sidebar.checkbox("Hipertensão", key=f"{key_prefix}_has")
    dislip = st.sidebar.checkbox("Dislipidemia", key=f"{key_prefix}_dislip")
    obesidade = st.sidebar.checkbox("Obesidade", key=f"{key_prefix}_obesidade")
    irc = st.sidebar.checkbox("Doença Renal Crônica", key=f"{key_prefix}_irc")
    ci = st.sidebar.checkbox("Cardiopatia Isquêmica", key=f"{key_prefix}_ci")
    icc = st.sidebar.checkbox("Insuficiência Cardíaca", key=f"{key_prefix}_icc")
    
    filtros = {}
    if dm:
        filtros['DM'] = True
    if has:
        filtros['HAS'] = True
    if dislip:
        filtros['dislipidemia'] = True
    if obesidade:
        filtros['obesidade'] = True
    if irc:
        filtros['IRC'] = True
    if ci:
        filtros['CI'] = True
    if icc:
        filtros['ICC'] = True
    
    return {
        'filtros': filtros,
        'logica': logica
    }


def filtro_busca_paciente(key_prefix=""):
    """
    Campo de busca por nome ou CPF
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Buscar Paciente")
    
    busca = st.sidebar.text_input(
        "Nome ou CPF",
        placeholder="Digite para buscar...",
        key=f"{key_prefix}_busca",
        label_visibility="collapsed"
    )
    
    return busca.strip() if busca else None


def filtro_ordenacao(key_prefix=""):
    """
    Seletor de ordenação
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Ordenar por")
    
    campo = st.sidebar.selectbox(
        "Campo",
        options=[
            "Nome (A-Z)",
            "Idade (maior)",
            "Idade (menor)", 
            "Mais morbidades",
            "Menos morbidades",
            "Risco CV (alto primeiro)"
        ],
        key=f"{key_prefix}_ord_campo"
    )
    
    # Mapear para campos reais
    mapa_campos = {
        "Nome (A-Z)": ("nome", "ASC"),
        "Idade (maior)": ("idade", "DESC"),
        "Idade (menor)": ("idade", "ASC"),
        "Mais morbidades": ("total_morbidades", "DESC"),
        "Menos morbidades": ("total_morbidades", "ASC"),
        "Risco CV (alto primeiro)": ("risco_cardiovascular", "DESC")
    }
    
    return mapa_campos.get(campo, ("nome", "ASC"))