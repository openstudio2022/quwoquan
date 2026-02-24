#!/usr/bin/env python3
"""Offline evaluation: AUC/NDCG/GAUC placeholder. Load model and samples, compute metrics."""
import argparse
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--model-path", default="")
    args = p.parse_args()
    # Placeholder: return fixed metrics; implement with lightgbm + sklearn.metrics when needed
    print('{"auc": 0.5, "ndcg": 0.5}', file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
