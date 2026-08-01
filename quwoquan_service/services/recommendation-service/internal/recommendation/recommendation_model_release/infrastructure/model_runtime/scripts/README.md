# ML scripts (rec-model-training)

Training pipeline: events → samples → dataset → train / multiobjective → quality evidence → Stage → CAS Activate.
Fields and collections follow the object-local `recommendation_model_release` contracts.

## Run order

From `quwoquan_service`, run the training lane through the service-owned scripts:

1. **SampleJoiner** (optional if events already in MongoDB):
   `python3 services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/sample_joiner.py --scenario content_feed`
2. **DatasetManager**: time-split samples into train/val/test.
3. **train.py**:
   `python3 services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/train.py --scenario content_feed [--datasetId ...]`
4. **evaluate.py / evaluate_gate.py**: evaluate an explicit immutable artifact and produce verification evidence.
5. **Stage**: training uploads the artifact and calls the generated RecommendationModelRelease HTTP facade; activation is a separate CAS command after approval.

## Env

- **Python venv**: `python3 -m venv .venv && .venv/bin/pip install -r services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/requirements.txt`。macOS 上 lightgbm 需 OpenMP：`brew install libomp`。若无 lightgbm，`train.py` / `train_multiobjective.py` 会直接退出 1，且不会写入 ModelRegistry。
- 依赖边界：服务根 `services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/requirements.txt` 只负责 FastAPI 推理镜像；本目录 `scripts/requirements.txt` 只负责训练、评估和样本处理。CI 与训练镜像必须引用后者，不能把两条运行面重新合并成一个隐式依赖集。
- `MONGODB_URI`: Recommendation-owned learning, training and replay collections. Local Docker Compose runs use `mongodb://127.0.0.1:27017/?directConnection=true`.
- `RECOMMENDATION_SERVICE_INTERNAL_URL`, `RECOMMENDATION_MODEL_MANAGE_TOKEN`, `RECOMMENDATION_FEATURE_CONTRACT_DIGEST`: required Stage/Activate facade inputs.
- `MODEL_ARTIFACT_*`: required immutable S3-compatible artifact storage configuration.

## Docker

从 `quwoquan_service/` 根构建，确保训练镜像与 Serving 同时打包 canonical
`intersection_kind_registry.yaml` 和同一 matched-edge encoder：

`docker build -f services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/Dockerfile .`

## Operations

- `make verify-ml-e2e-live REC_MODEL_URL=...`：用真实 recommendation-service 做端到端验收，不会走 `--skip-service`。
- `make verify-ml-guardrail`：基于 `rec_learning_events` 计算 CTR / engagement，并在阈值触发时输出 rule-only cutover 结论。
- `make verify-ml-drift`：基于 `rec_training_samples` 与 `rm_recommend_feature` 计算 PSI 漂移，支持 `ML_DRIFT_BASELINE_DATE` 按日期切基线。
