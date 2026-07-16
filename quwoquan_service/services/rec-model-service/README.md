# recommendation-service

Recommendation model inference service. Scoring is exposed only through the generated
ModelRelease named Reader contract; `/health` is the infrastructure liveness endpoint.

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
- `AUTH_JWT_SECRET` / `AUTH_JWT_ISSUER` / `AUTH_JWT_AUDIENCE` /
  `AUTH_JWT_TOKEN_VERSION` are required; scoring accepts only short-lived service tokens
  with scope `recommendation.model.score`.
- Contract mismatch causes startup to fail immediately (fail-fast).
- Optional model envs (future): `REC_MODEL_CONTENT_FEED_PATH`, `REC_MODEL_CIRCLE_DISCOVERY_PATH`, `REC_MODEL_FRIEND_SUGGESTION_PATH`.
- **content-service** integration: set `rec_model_service.url` (e.g. `http://localhost:18090` or `http://rec-model-service:8000` in same docker network), `rec_model_service.timeout_ms`, `rec_model_service.enabled: true`.

## Docker

From `quwoquan_service`: `docker compose up -d rec-model-service`. Service listens on port 18090 (host) → 8000 (container). Same compose network as postgres/mongodb/redis for future ModelRegistry.

## Contract

- `contracts/metadata/recommendation/model_release/{fields,service,errors}.yaml`
- Codegen: `make codegen-rec-model-python` (from quwoquan_service root)
