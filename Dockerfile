FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD python -c "\
import os;\
secrets = os.environ.get('STREAMLIT_SECRETS', '');\
secrets = secrets.replace('\\\\n', '\\n');\
os.makedirs('/root/.streamlit', exist_ok=True);\
open('/root/.streamlit/secrets.toml', 'w').write(secrets);\
print('secrets.toml criado:', len(secrets), 'chars');\
print('ENV vars:', [k for k in os.environ if 'SECRET' in k or 'GOOGLE' in k or 'GCP' in k or 'CRED' in k]);\
print('secrets preview:', secrets[:80] if secrets else 'VAZIO')\
" && streamlit run Home.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false