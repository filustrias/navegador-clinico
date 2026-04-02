# utils/bigquery_client.py
import os
import json
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials


def test_connection():
    """Testa conexão com BigQuery"""
    try:
        client = get_bigquery_client()
        client.query("SELECT 1").result()
        return True
    except Exception as e:
        print(f"Erro na conexão: {e}")
        return False


@st.cache_resource
def get_bigquery_client():
    """Conecta ao BigQuery.

    Ordem de prioridade:
    1. Railway → variável GOOGLE_APPLICATION_CREDENTIALS_JSON
    2. Streamlit Cloud → st.secrets['gcp_service_account']
    3. Streamlit Cloud → st.secrets['gcp_credentials'] (legado)
    4. Local → Application Default Credentials
    """

    # 1. Railway — OAuth com credenciais pessoais
    client_id = os.getenv('GCP_CLIENT_ID')
    client_secret = os.getenv('GCP_CLIENT_SECRET')
    refresh_token = os.getenv('GCP_REFRESH_TOKEN')

    print(f"DEBUG - client_id presente: {bool(client_id)}")
    print(f"DEBUG - client_secret presente: {bool(client_secret)}")
    print(f"DEBUG - refresh_token presente: {bool(refresh_token)}")

    if client_id and client_secret and refresh_token:
        try:
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            client = bigquery.Client(
                credentials=credentials,
                project="rj-sms-sandbox"
            )
            print("DEBUG - cliente BigQuery criado com sucesso via OAuth")
            return client
        except Exception as e:
            print(f"DEBUG - Erro OAuth Railway: {e}")
            raise  # re-lança o erro para aparecer no traceback

    # 2. Streamlit Cloud — service account
    try:
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            info = dict(st.secrets['gcp_service_account'])
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            return bigquery.Client(
                credentials=credentials,
                project=info.get('project_id', 'rj-sms-sandbox')
            )
    except Exception as e:
        print(f"Erro gcp_service_account: {e}")

    # 3. Streamlit Cloud — OAuth legado
    try:
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
        print(f"Erro gcp_credentials: {e}")

    # 4. Local
    return bigquery.Client(project="rj-sms-sandbox")