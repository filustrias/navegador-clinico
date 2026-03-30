FROM python:3.11-slim
 
WORKDIR /app
 
# Dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
 
# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copiar código
COPY . .
 
# Iniciar com porta dinâmica do Railway
CMD streamlit run Home.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false