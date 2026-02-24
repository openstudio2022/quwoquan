# ML scripts (rec-model-training)

Training pipeline: events → samples → dataset → train → ModelRegistry.  
Fields and collections follow `contracts/metadata/_projections/` (learning_events, training_samples, model_registry).

## Run order

1. **SampleJoiner** (optional if events already in MongoDB): `python -m scripts.ml.sample_joiner --scenario content_feed`
2. **DatasetManager**: time-split samples into train/val/test
3. **train.py**: `python -m scripts.ml.train --scenario content_feed [--datasetId ...]`
4. **evaluate.py**: offline metrics
5. **ModelRegistry**: write version + artifact path to rec_model_registry

## Env

- **Python venv**: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。macOS 上 lightgbm 需 OpenMP：`brew install libomp`。若无 lightgbm，train.py 会写占位模型并照常写 ModelRegistry。
- `MONGODB_URI`: for rec_learning_events, rec_training_samples, rec_model_registry
- `OSS_*` or local path for model artifact (optional)

## Docker

See Dockerfile; run with `train.py --scenario content_feed`.
