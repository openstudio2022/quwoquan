# recommendation-service model runtime: FastAPI + Python 3.11
ARG PYTHON_BASE_IMAGE=python:3.11
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ARG PIP_FALLBACK_INDEX_URL=https://pypi.org/simple
FROM ${PYTHON_BASE_IMAGE}
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ARG PIP_FALLBACK_INDEX_URL

WORKDIR /app

# lightgbm loads libgomp at runtime; python slim images do not ship it by default.
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi \
  && if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
    fi \
  && apt-get update \
  && apt-get install -y --no-install-recommends libgomp1 \
  && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8 \
    PIP_PROGRESS_BAR=off \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_FALLBACK_INDEX_URL=${PIP_FALLBACK_INDEX_URL}

COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/requirements.txt .
RUN set -e; \
    install_from_index() { \
      index_url="$1"; \
      trusted_host="$2"; \
      if [ -n "${trusted_host}" ]; then \
        python -m pip install --no-cache-dir \
          --index-url "${index_url}" \
          --trusted-host "${trusted_host}" \
          -r requirements.txt; \
      else \
        python -m pip install --no-cache-dir \
          --index-url "${index_url}" \
          -r requirements.txt; \
      fi; \
    }; \
    if ! install_from_index "${PIP_INDEX_URL}" "${PIP_TRUSTED_HOST}"; then \
      if [ "${PIP_INDEX_URL}" = "${PIP_FALLBACK_INDEX_URL}" ]; then \
        exit 1; \
      fi; \
      echo "Primary Python index failed, retrying with fallback ${PIP_FALLBACK_INDEX_URL}" >&2; \
      install_from_index "${PIP_FALLBACK_INDEX_URL}" ""; \
    fi

COPY services/recommendation-service/generated/ ./generated/
COPY services/recommendation-service/internal/recommendation/ ./internal/recommendation/
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/api/ ./api/
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/features/ ./features/
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/models/ ./models/
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/security/ ./security/
COPY services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml ./contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/runtime_contract.py ./
COPY services/recommendation-service/cmd/api/main.py ./
COPY services/recommendation-service/cmd/api/stream_redis.py ./

COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/artifact_store.py ./scripts/artifact_store.py

ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1
ENV REC_MODEL_UVICORN_WORKERS=2

RUN useradd -m app && mkdir -p /app/cache && chown -R app:app /app
ENV MODEL_CACHE_DIR=/app/cache
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${REC_MODEL_UVICORN_WORKERS:-2}"]
