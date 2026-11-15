FROM python:3.10-slim
WORKDIR /app
RUN mkdir -p /data
COPY task-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY task-service/ .
COPY auth.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]