FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG GOOGLE_CREDENTIALS
RUN echo "$GOOGLE_CREDENTIALS" > /app/credentials.json
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

CMD streamlit run Home.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false