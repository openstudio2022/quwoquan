# rec-model-service: FastAPI + Python 3.11
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generated/ ./generated/
COPY app/ ./app/
COPY api/ ./api/
COPY features/ ./features/
COPY models/ ./models/
COPY configs/ ./configs/
COPY runtime_contract.py ./
COPY main.py ./

ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1

RUN useradd -m app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
