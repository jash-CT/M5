FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY services/__init__.py ./services/
COPY services/scada-gateway/ ./services/scada-gateway/
CMD ["python", "services/scada-gateway/main.py"]
