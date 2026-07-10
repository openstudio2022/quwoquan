# Training image: LightGBM + pymongo for rec-model-training pipeline
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY feature_registry.yaml README.md ./

ENV PYTHONUNBUFFERED=1

# Run with: docker run --rm -e MONGODB_URI=... rec-train python train.py --scenario content_feed
CMD ["python", "train.py", "--scenario", "content_feed"]
