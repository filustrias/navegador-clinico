"""
Gerenciamento de conexão com BigQuery
"""
from google.cloud import bigquery
import streamlit as st
from config import PROJECT_ID
from google.oauth2 import service_account

@st.cache_resource
def get_bigquery_client():
    """Conecta ao BigQuery usando Secrets do Streamlit Cloud"""
    
    # Tentar usar secrets do Streamlit Cloud primeiro
    if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        return bigquery.Client(
            credentials=credentials,
            project=st.secrets["gcp_service_account"]["project_id"]
        )
    
    # Fallback para credenciais locais (desenvolvimento)
    return bigquery.Client(project="rj-sms-sandbox")

def test_connection():
    """
    Testa a conexão com BigQuery
    """
    client = get_bigquery_client()
    if client:
        try:
            # Query simples para testar
            query = "SELECT 1 as test"
            result = client.query(query).result()
            return True
        except Exception as e:
            st.error(f"❌ Erro ao executar query de teste: {str(e)}")
            return False
    return False