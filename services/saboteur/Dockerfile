FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/saboteur /app/services/saboteur

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.saboteur.app.main:app", "--host", "0.0.0.0", "--port", "8003"]
