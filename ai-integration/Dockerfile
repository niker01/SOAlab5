FROM python:3.10-slim
WORKDIR /app
RUN mkdir -p /data
COPY ai-integration/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ai-integration/ .
COPY auth.py .
COPY observability.py .
EXPOSE 8000
