FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/triage /app/services/triage

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.triage.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
