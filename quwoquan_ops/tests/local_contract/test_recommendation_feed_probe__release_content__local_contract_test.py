"""The release-mode recommendation probe cannot accept an empty premium pool.

spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _probe_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "acceptance"
        / "user_acceptance"
        / "service_ops"
        / "content-service"
        / "smoke"
        / "run_recommendation_feed_probe.py"
    )
    spec = importlib.util.spec_from_file_location("recommendation_feed_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_recommendation_probe__rejects_empty_items__local_contract() -> None:
    probe = _probe_module()

    assert probe.check_non_empty_items({"items": []}, required=True)
    assert probe.check_non_empty_items({"items": [{"postId": "video-1"}]}, required=True) == []
    assert probe.check_non_empty_items({"items": []}, required=False) == []
