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
    1. Railway → gcp_creds.txt (via GOOGLE_APPLICATION_CREDENTIALS)
    2. Railway → variável GOOGLE_APPLICATION_CREDENTIALS_JSON
    3. Streamlit Cloud → st.secrets['gcp_service_account']
    4. Streamlit Cloud → st.secrets['gcp_credentials'] (legado)
    5. Local → Application Default Credentials
    """

    # 1. Railway — arquivo de credenciais via ENV
    creds_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_file and os.path.exists(creds_file):
        try:
            with open(creds_file) as f:
                info = json.load(f)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            print("DEBUG - autenticado via arquivo", flush=True)
            return bigquery.Client(
                credentials=credentials,
                project=info.get('project_id', 'rj-sms-sandbox')
            )
        except Exception as e:
            print(f"ERRO arquivo credenciais: {e}", flush=True)

    # 2. Railway — JSON via variável de ambiente
    creds_json = os.getenv('GOOGLE_CREDENTIALS') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_json:
        try:
            info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            print("DEBUG - autenticado via variável JSON", flush=True)
            return bigquery.Client(
                credentials=credentials,
                project=info.get('project_id', 'rj-sms-sandbox')
            )
        except Exception as e:
            print(f"ERRO JSON variável: {e}", flush=True)
    else:
        print("VARIAVEL VAZIA OU AUSENTE", flush=True)

    # 3. Streamlit Cloud — service account
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

    # 4. Streamlit Cloud — OAuth legado
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

    # 5. Railway — STREAMLIT_SECRETS (variável de ambiente)
    streamlit_secrets = os.getenv('STREAMLIT_SECRETS')
    if streamlit_secrets:
        print(f"DEBUG - STREAMLIT_SECRETS encontrada ({len(streamlit_secrets)} chars)", flush=True)
        info = None
        # Tenta TOML (formato secrets.toml do Streamlit)
        try:
            import tomllib
            import io
            parsed = tomllib.load(io.BytesIO(streamlit_secrets.encode('utf-8')))
            info = parsed.get('gcp_service_account', parsed)
            print(f"DEBUG - TOML parse ok, keys: {list(info.keys())[:5]}", flush=True)
        except Exception as e:
            print(f"DEBUG - TOML parse falhou: {e}", flush=True)
        # Tenta JSON
        if not info:
            try:
                parsed = json.loads(streamlit_secrets)
                info = parsed.get('gcp_service_account', parsed) if isinstance(parsed, dict) else None
                print(f"DEBUG - JSON parse ok, keys: {list(info.keys())[:5]}", flush=True)
            except Exception as e:
                print(f"DEBUG - JSON parse falhou: {e}", flush=True)
        if info and info.get('type') == 'service_account':
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/bigquery"]
                )
                print("DEBUG - autenticado via STREAMLIT_SECRETS", flush=True)
                return bigquery.Client(
                    credentials=credentials,
                    project=info.get('project_id', 'rj-sms-sandbox')
                )
            except Exception as e:
                print(f"ERRO STREAMLIT_SECRETS: {e}", flush=True)
        else:
            print(f"DEBUG - info nao encontrado ou nao eh service_account", flush=True)

    # 6. Local
    return bigquery.Client(project="rj-sms-sandbox")