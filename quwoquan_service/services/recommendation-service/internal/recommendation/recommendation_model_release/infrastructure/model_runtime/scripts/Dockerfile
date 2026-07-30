# Training image: LightGBM + pymongo for rec-model-training pipeline
FROM python:3.11-slim

WORKDIR /app

COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/*.py ./scripts/
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml ./scripts/feature_registry.yaml
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/README.md ./scripts/README.md
COPY services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/features/ ./features/
COPY services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml ./contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml

ENV PYTHONUNBUFFERED=1

# Build from quwoquan_service root so training and serving package the same
# canonical encoder and registry source.
# Run with: docker run --rm -e MONGODB_URI=... rec-train
CMD ["python", "scripts/train.py", "--scenario", "content_feed"]
