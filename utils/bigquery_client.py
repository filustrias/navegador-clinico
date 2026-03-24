# utils/bigquery_client.py
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente de um arquivo .env, se existir
load_dotenv()


def test_connection():
    """Testa conexão com BigQuery"""
    try:
        client = get_bigquery_client()
        query = "SELECT 1 as test"
        result = client.query(query).result()
        return True
    except Exception as e:
        print(f"Erro na conexão: {e}")
        return False
        
@st.cache_resource
def get_bigquery_client():
    """Conecta ao BigQuery usando Secrets do Streamlit Cloud ou credenciais locais"""
    
    # 1. Tentar carregar credenciais de serviço do st.secrets (formato Streamlit Cloud)
    # Procuramos por uma seção 'gcp_service_account' que contém o JSON do Service Account
    try:
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            creds_info = dict(st.secrets["gcp_service_account"])
            credentials = service_account.Credentials.from_service_account_info(creds_info)
            return bigquery.Client(credentials=credentials, project=creds_info.get("project_id", "rj-sms-sandbox"))
            
        # 2. Tentar usar o formato OAuth2 que estava no código original
        if hasattr(st, 'secrets') and 'gcp_credentials' in st.secrets:
            credentials = Credentials(
                token=None,
                refresh_token=st.secrets["gcp_credentials"]["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=st.secrets["gcp_credentials"]["client_id"],
                client_secret=st.secrets["gcp_credentials"]["client_secret"]
            )
            return bigquery.Client(
                credentials=credentials,
                project="rj-sms-sandbox"
            )
    except Exception as e:
        # Se houver erro ao ler secrets (ex: arquivo não encontrado), ignoramos e vamos para o fallback
        pass
    
    # 3. Fallback para credenciais locais (GOOGLE_APPLICATION_CREDENTIALS do .env)
    return bigquery.Client(project="rj-sms-sandbox")