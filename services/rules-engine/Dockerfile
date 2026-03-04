FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY services/__init__.py ./services/
COPY services/rules-engine/ ./services/rules-engine/
CMD ["python", "services/rules-engine/main.py"]
