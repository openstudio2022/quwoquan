# ML scripts (rec-model-training)

Training pipeline: events → samples → dataset → train / multiobjective → evaluate → gate → ModelRegistry.  
Fields and collections follow `contracts/metadata/_projections/` (learning_events, training_samples, model_registry).

## Run order

1. **SampleJoiner** (optional if events already in MongoDB): `python -m scripts.ml.sample_joiner --scenario content_feed`
2. **DatasetManager**: time-split samples into train/val/test
3. **train.py**: `python -m scripts.ml.train --scenario content_feed [--datasetId ...]`
4. **evaluate.py**: offline metrics
5. **ModelRegistry**: write version + artifact path to rec_model_registry

## Env

- **Python venv**: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。macOS 上 lightgbm 需 OpenMP：`brew install libomp`。若无 lightgbm，`train.py` / `train_multiobjective.py` 会直接退出 1，且不会写入 ModelRegistry。
- `MONGODB_URI`: for rec_learning_events, rec_training_samples, rec_model_registry. Local Docker Compose runs use `mongodb://127.0.0.1:27017/?directConnection=true`.
- `OSS_*` or local path for model artifact (optional)

## Docker

See Dockerfile; run with `train.py --scenario content_feed`.

## Operations

- `make verify-ml-e2e-live REC_MODEL_URL=...`：用真实 rec-model-service 做端到端验收，不会走 `--skip-service`。
- `make verify-ml-guardrail`：基于 `rec_learning_events` 计算 CTR / engagement，并在阈值触发时输出 rule-only cutover 结论。
- `make verify-ml-drift`：基于 `rec_training_samples` 与 `rm_recommend_feature` 计算 PSI 漂移，支持 `ML_DRIFT_BASELINE_DATE` 按日期切基线。
