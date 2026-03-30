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
    1. Railway / produção  → variável de ambiente GOOGLE_APPLICATION_CREDENTIALS_JSON (JSON completo)
    2. Streamlit Cloud     → st.secrets['gcp_service_account'] (service account) 
                           → st.secrets['gcp_credentials'] (OAuth — legado)
    3. Local               → Application Default Credentials (gcloud auth application-default login)
    """

    # ── 1. Railway: JSON da service account via variável de ambiente ──
    creds_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_json:
        try:
            info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            return bigquery.Client(
                credentials=credentials,
                project=info.get('project_id', 'rj-sms-sandbox')
            )
        except Exception as e:
            print(f"Erro ao usar GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")

    # ── 2a. Streamlit Cloud: service account em st.secrets ────────────
    if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
        try:
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
            print(f"Erro ao usar gcp_service_account: {e}")

    # ── 2b. Streamlit Cloud: OAuth legado ─────────────────────────────
    if hasattr(st, 'secrets') and 'gcp_credentials' in st.secrets:
        try:
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
            print(f"Erro ao usar gcp_credentials: {e}")

    # ── 3. Local: Application Default Credentials ─────────────────────
    return bigquery.Client(project="rj-sms-sandbox")
