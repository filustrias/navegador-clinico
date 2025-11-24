# utils/bigquery_client.py
import streamlit as st
from google.cloud import bigquery
from google.oauth2.credentials import Credentials


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
    
    # Tentar usar secrets do Streamlit Cloud primeiro
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
    
    # Fallback para credenciais locais (desenvolvimento)
    return bigquery.Client(project="rj-sms-sandbox")