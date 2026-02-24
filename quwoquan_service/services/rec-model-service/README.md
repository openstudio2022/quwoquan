# rec-model-service

Recommendation model inference service. POST /v1/score (multi-scenario), GET /health.

## Run locally

```bash
pip install -r requirements.txt
PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 18090
```

## Test

```bash
PYTHONPATH=. pytest tests/ -v
```

## Config / env

- No required env for rule-based scoring. Optional: MongoDB/Redis/OSS for ModelRegistry (future).
- **content-service** integration: set `rec_model_service.url` (e.g. `http://localhost:18090` or `http://rec-model-service:8000` in same docker network), `rec_model_service.timeout_ms`, `rec_model_service.enabled: true`.

## Docker

From `quwoquan_service`: `docker compose up -d rec-model-service`. Service listens on port 18090 (host) → 8000 (container). Same compose network as postgres/mongodb/redis for future ModelRegistry.

## Contract

- `contracts/metadata/rec_model_service/`, `contracts/openapi/rec-model-service.v1.yaml`
- Codegen: `make codegen-rec-model-python` (from quwoquan_service root)
