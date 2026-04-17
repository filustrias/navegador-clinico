# utils/relatos.py
import streamlit as st
import uuid
from datetime import datetime
from utils.bigquery_client import get_bigquery_client

def salvar_relato(
    cpf_paciente: str,
    nome_paciente: str,
    area_programatica: str,
    clinica: str,
    esf: str,
    usuario_relator: str,
    nome_relator: str,
    tipo_relato: str,
    campo_errado: str = None,
    valor_correto: str = None,
    informacao_ausente: str = None,
    data_desvinculacao: str = None,
    data_obito: str = None,
    observacoes: str = None
) -> bool:
    """Salva relato no BigQuery"""
    
    client = get_bigquery_client()
    id_relato = str(uuid.uuid4())
    
    # Formatar valores para SQL
    def sql_str(val):
        if val is None or val == '':
            return 'NULL'
        return f"'{str(val).replace(chr(39), chr(39)+chr(39))}'"  # Escape aspas
    
    def sql_date(val):
        if val is None or val == '':
            return 'NULL'
        return f"DATE('{val}')"
    
    query = f"""
    INSERT INTO `rj-sms-sandbox.sub_pav_us.MM_relatos_pacientes`
    (id_relato, cpf_paciente, nome_paciente, area_programatica, clinica, esf,
     usuario_relator, nome_relator, tipo_relato, campo_errado, valor_correto,
     informacao_ausente, data_desvinculacao, data_obito, observacoes)
    VALUES (
        '{id_relato}',
        {sql_str(cpf_paciente)},
        {sql_str(nome_paciente)},
        {sql_str(area_programatica)},
        {sql_str(clinica)},
        {sql_str(esf)},
        {sql_str(usuario_relator)},
        {sql_str(nome_relator)},
        {sql_str(tipo_relato)},
        {sql_str(campo_errado)},
        {sql_str(valor_correto)},
        {sql_str(informacao_ausente)},
        {sql_date(data_desvinculacao)},
        {sql_date(data_obito)},
        {sql_str(observacoes)}
    )
    """
    
    try:
        client.query(query).result()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar relato: {e}")
        return False

def formulario_relato(patient_data: dict, usuario: dict):
    """Exibe formulário de relato dentro do card do paciente"""
    
    st.markdown("### 📝 Relatar Problema de Informação")
    
    st.info("""
    Use este formulário para relatar problemas com as informações deste paciente:
    - Informações incorretas no navegador
    - Dados ausentes no cartão
    - Mudança de situação cadastral
    - Óbito do paciente
    """)
    
    # Tipo de relato
    tipo_relato = st.radio(
        "Que tipo de informação você quer relatar?",
        options=[
            "1 - Corrigir informação errada",
            "2 - Informação ausente",
            "3 - Paciente não pertence mais à ESF",
            "4 - Informar óbito"
        ],
        key=f"tipo_relato_{patient_data.get('cpf', 'unknown')}"
    )
    
    # Campos condicionais
    campo_errado = None
    valor_correto = None
    informacao_ausente = None
    data_desvinculacao = None
    data_obito = None
    observacoes = None
    
    if tipo_relato.startswith("1"):
        campo_errado = st.text_input(
            "Qual informação está errada?",
            placeholder="Ex: Data de nascimento, Nome, Diagnóstico...",
            key=f"campo_errado_{patient_data.get('cpf', 'unknown')}"
        )
        valor_correto = st.text_input(
            "Qual é a informação correta?",
            placeholder="Digite o valor correto...",
            key=f"valor_correto_{patient_data.get('cpf', 'unknown')}"
        )
        
    elif tipo_relato.startswith("2"):
        informacao_ausente = st.text_area(
            "Qual informação está ausente?",
            placeholder="Descreva a informação que deveria aparecer...",
            key=f"info_ausente_{patient_data.get('cpf', 'unknown')}"
        )
        
    elif tipo_relato.startswith("3"):
        data_desvinculacao = st.date_input(
            "Em que data o paciente deixou de ser vinculado a esta ESF?",
            value=None,
            key=f"data_desvinc_{patient_data.get('cpf', 'unknown')}"
        )
        
    elif tipo_relato.startswith("4"):
        data_obito = st.date_input(
            "Em que data o paciente faleceu?",
            value=None,
            key=f"data_obito_{patient_data.get('cpf', 'unknown')}"
        )
    
    # Observações adicionais (sempre visível)
    observacoes = st.text_area(
        "Observações adicionais (opcional)",
        placeholder="Informações complementares...",
        key=f"obs_{patient_data.get('cpf', 'unknown')}"
    )
    
    # Botão de envio
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("📤 Enviar Relato", type="primary", use_container_width=True,
                     key=f"btn_relato_{patient_data.get('cpf', 'unknown')}"):
            
            # Validações
            if tipo_relato.startswith("1") and (not campo_errado or not valor_correto):
                st.error("⚠️ Preencha o campo errado e o valor correto")
                return
            
            if tipo_relato.startswith("2") and not informacao_ausente:
                st.error("⚠️ Descreva a informação ausente")
                return
            
            if tipo_relato.startswith("3") and not data_desvinculacao:
                st.error("⚠️ Informe a data de desvinculação")
                return
                
            if tipo_relato.startswith("4") and not data_obito:
                st.error("⚠️ Informe a data do óbito")
                return
            
            # Salvar — aceita tanto nomes originais do banco quanto os aliases
            # do SELECT de Meus_Pacientes (nome_clinica_cadastro AS clinica_familia,
            # nome_esf_cadastro AS ESF).
            clinica_val = (patient_data.get('nome_clinica_cadastro')
                           or patient_data.get('clinica_familia'))
            esf_val     = (patient_data.get('nome_esf_cadastro')
                           or patient_data.get('ESF'))
            sucesso = salvar_relato(
                cpf_paciente=patient_data.get('cpf'),
                nome_paciente=patient_data.get('nome'),
                area_programatica=patient_data.get('area_programatica_cadastro'),
                clinica=clinica_val,
                esf=esf_val,
                usuario_relator=usuario['username'],
                nome_relator=usuario['nome_completo'],
                tipo_relato=tipo_relato.split(" - ")[0],
                campo_errado=campo_errado,
                valor_correto=valor_correto,
                informacao_ausente=informacao_ausente,
                data_desvinculacao=str(data_desvinculacao) if data_desvinculacao else None,
                data_obito=str(data_obito) if data_obito else None,
                observacoes=observacoes
            )
            
            if sucesso:
                st.success("✅ Relato enviado com sucesso! Obrigado pela contribuição.")
                st.balloons()