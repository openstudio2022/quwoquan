# rec-model-service: FastAPI + Python 3.11
ARG PYTHON_BASE_IMAGE=python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
FROM ${PYTHON_BASE_IMAGE}
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8 \
    PIP_PROGRESS_BAR=off \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

COPY quwoquan_service/services/rec-model-service/requirements.txt .
RUN if [ -n "${PIP_TRUSTED_HOST}" ]; then \
      python -m pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        --trusted-host "${PIP_TRUSTED_HOST}" \
        -r requirements.txt; \
    else \
      python -m pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        -r requirements.txt; \
    fi

COPY quwoquan_service/services/rec-model-service/generated/ ./generated/
COPY quwoquan_service/services/rec-model-service/app/ ./app/
COPY quwoquan_service/services/rec-model-service/api/ ./api/
COPY quwoquan_service/services/rec-model-service/features/ ./features/
COPY quwoquan_service/services/rec-model-service/models/ ./models/
COPY quwoquan_service/services/rec-model-service/configs/ ./configs/
COPY releases/config/recommendation-service/ ./releases/config/recommendation-service/
COPY quwoquan_service/services/rec-model-service/runtime_contract.py ./
COPY quwoquan_service/services/rec-model-service/main.py ./

COPY quwoquan_service/scripts/ml/artifact_store.py ./ml/artifact_store.py
COPY quwoquan_service/scripts/ml/model_registry.py ./ml/model_registry.py

ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1

RUN useradd -m app && mkdir -p /app/cache && chown -R app:app /app
ENV MODEL_CACHE_DIR=/app/cache
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
