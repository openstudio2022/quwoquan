# recommendation-service

Recommendation model inference service. POST /v1/score (multi-scenario), GET /health.

## Run locally

```bash
pip install -r requirements.txt
SERVICE_NAME=recommendation-service APP_ENV=dev PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 18090
```

## Test

```bash
PYTHONPATH=. pytest tests/ -v
```

## Config / env contract (fail-fast)

- `APP_ENV` must be one of `dev` / `integration` / `prod`.
- `SERVICE_NAME` when provided must be `recommendation-service`.
- For `integration` / `prod`, `CONFIG_VERSION` / `IMAGE_VERSION` / `CONFIG_ROOT` are required.
- Contract mismatch causes startup to fail immediately (fail-fast).
- Optional model envs (future): `REC_MODEL_CONTENT_FEED_PATH`, `REC_MODEL_CIRCLE_DISCOVERY_PATH`, `REC_MODEL_FRIEND_SUGGESTION_PATH`.
- **content-service** integration: set `rec_model_service.url` (e.g. `http://localhost:18090` or `http://rec-model-service:8000` in same docker network), `rec_model_service.timeout_ms`, `rec_model_service.enabled: true`.

## Docker

From `quwoquan_service`: `docker compose up -d rec-model-service`. Service listens on port 18090 (host) → 8000 (container). Same compose network as postgres/mongodb/redis for future ModelRegistry.

## Contract

- `contracts/metadata/rec_model_service/`, `contracts/openapi/rec-model-service.v1.yaml`
- Codegen: `make codegen-rec-model-python` (from quwoquan_service root)
