FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /data
COPY notification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY notification-service/ .
COPY auth.py .
COPY observability.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]