from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "ml"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import evaluate_gate  # noqa: E402


class _EmptyCollection:
    def find_one(self, *args, **kwargs):
        return None


class _EmptyDb:
    def __getitem__(self, name: str):
        return _EmptyCollection()


class _EmptyClient:
    def __init__(self, *args, **kwargs):
        self._db = _EmptyDb()

    def __getitem__(self, name: str):
        return self._db


class _ThresholdCollection:
    def __init__(self, latest_doc: dict[str, object]) -> None:
        self.latest_doc = latest_doc

    def find_one(self, query, sort=None):  # noqa: D401, ANN001
        if query.get("production") is True:
            return None
        if query.get("scenario") == self.latest_doc.get("scenario"):
            return self.latest_doc
        return None


class _ThresholdDb:
    def __init__(self, collection: _ThresholdCollection) -> None:
        self._collection = collection

    def __getitem__(self, name: str):
        return self._collection


class _ThresholdClient:
    def __init__(self, collection: _ThresholdCollection) -> None:
        self._db = _ThresholdDb(collection)

    def __getitem__(self, name: str):
        return self._db


def test_evaluate_gate_blocks_without_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(evaluate_gate, "MongoClient", _EmptyClient)
    out = tmp_path / "eval_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_gate.py",
            "--scenario",
            "content_feed",
            "--mongodb-uri",
            "mongodb://localhost:27017",
            "--db",
            "quwoquan_content",
            "--out",
            str(out),
        ],
    )

    assert evaluate_gate.main() == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert "no model found" in report["reason"]


@pytest.mark.parametrize(
    ("scenario", "metrics", "dry_run", "expected_status", "expected_reason"),
    [
        (
            "content_feed",
            {"auc": 0.55, "ndcg_20": 0.06},
            False,
            "blocked",
            "AUC 0.5500 < absolute min 0.65",
        ),
        (
            "content_feed",
            {"auc": 0.55, "ndcg_20": 0.06},
            True,
            "pass",
            "v=v1 AUC=0.5500 NDCG=0.0600",
        ),
        (
            "content_feed_multiobjective",
            {"fused_auc": 0.48, "ndcg_20": 0.06},
            False,
            "blocked",
            "fused_auc 0.4800 < absolute min 0.6",
        ),
        (
            "content_feed_multiobjective",
            {"fused_auc": 0.48, "ndcg_20": 0.06},
            True,
            "pass",
            "v=v1 fused_auc=0.4800",
        ),
    ],
)
def test_evaluate_gate_uses_dry_run_and_multiobjective_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    metrics: dict[str, float],
    dry_run: bool,
    expected_status: str,
    expected_reason: str,
) -> None:
    latest_doc = {
        "scenario": scenario,
        "version": "v1",
        "metrics": metrics,
        "createdAt": 1,
    }
    collection = _ThresholdCollection(latest_doc)
    monkeypatch.setattr(evaluate_gate, "MongoClient", lambda *args, **kwargs: _ThresholdClient(collection))
    out = tmp_path / "eval_report.json"
    argv = [
        "evaluate_gate.py",
        "--scenario",
        scenario,
        "--mongodb-uri",
        "mongodb://localhost:27017",
        "--db",
        "quwoquan_content",
        "--out",
        str(out),
    ]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)

    rc = evaluate_gate.main()
    assert rc == (0 if expected_status == "pass" else 1)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == expected_status
    if expected_status == "pass":
        assert report["reason"] == expected_reason
    else:
        assert expected_reason in report["reason"]
