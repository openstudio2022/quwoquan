from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


import feature_drift_monitor
import activation_gate
import online_guardrail


class _FakeExposureCollection:
    def __init__(
        self,
        impression_count: int,
        model_impression_count: int,
    ) -> None:
        self._impression_count = impression_count
        self._model_impression_count = model_impression_count

    def count_documents(self, query):  # noqa: D401, ANN001
        if query.get("modelBucket") == "model":
            return self._model_impression_count
        return self._impression_count

    def find(self, query, projection=None):  # noqa: D401, ANN001
        return [{"_id": f"exposure-{index}"} for index in range(self._impression_count)]


class _FakeFeedbackCollection:
    def __init__(self, action_counts: dict[str, int]) -> None:
        self._action_counts = action_counts

    def aggregate(self, pipeline):  # noqa: D401, ANN001
        return [
            {"_id": action, "count": count}
            for action, count in self._action_counts.items()
        ]


class _FakeGuardrailDb:
    def __init__(self, exposures: object, feedbacks: object) -> None:
        self._exposures = exposures
        self._feedbacks = feedbacks

    def __getitem__(self, name: str) -> object:
        if name == "recommendation_exposure_facts":
            return self._exposures
        if name == "recommendation_feedback_facts":
            return self._feedbacks
        raise KeyError(name)


class _FakeGuardrailClient:
    def __init__(self, db: object) -> None:
        self._db = db

    def __getitem__(self, name: str) -> object:
        if name != "quwoquan_recommendation":
            raise KeyError(name)
        return self._db


class _Cursor:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self._docs = docs

    def sort(self, *args, **kwargs):  # noqa: D401, ANN001
        return self

    def limit(self, limit: int):  # noqa: D401, ANN001
        self._docs = self._docs[:limit]
        return self

    def __iter__(self):
        return iter(self._docs)


class _FeatureCollection:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self._docs = docs

    @staticmethod
    def _match_doc(doc: dict[str, object], query: dict[str, object]) -> bool:
        scenario = query.get("scenario")
        if scenario is not None and doc.get("scenario") != scenario:
            return False

        ts_filter = query.get("ts")
        if isinstance(ts_filter, dict) and "$lt" in ts_filter:
            if doc.get("ts") is None or doc["ts"] >= ts_filter["$lt"]:
                return False

        feature_key = next((key for key in query if key.startswith("userFeatures.")), None)
        if feature_key is None:
            return True

        feature_name = feature_key.split(".", 1)[1]
        user_features = doc.get("userFeatures", {})
        return feature_name in user_features

    def find(self, query, projection=None):  # noqa: D401, ANN001
        docs = [doc for doc in self._docs if self._match_doc(doc, query)]
        return _Cursor(docs)


class _FeatureDb:
    def __init__(self, training_docs: list[dict[str, object]], current_docs: list[dict[str, object]]) -> None:
        self._training = _FeatureCollection(training_docs)
        self._current = _FeatureCollection(current_docs)

    def __getitem__(self, name: str) -> object:
        if name == "rec_training_samples":
            return self._training
        if name == "rm_recommend_feature":
            return self._current
        raise KeyError(name)


class _FeatureClient:
    def __init__(self, db: object) -> None:
        self._db = db

    def __getitem__(self, name: str) -> object:
        if name != "quwoquan_content":
            raise KeyError(name)
        return self._db


def _build_feature_docs(
    *,
    value: float,
    count: int,
    scenario: str,
    start_at: datetime,
) -> list[dict[str, object]]:
    docs: list[dict[str, object]] = []
    for index in range(count):
        docs.append(
            {
                "scenario": scenario,
                "ts": start_at + timedelta(minutes=index),
                "userFeatures": {
                    feature: value for feature in feature_drift_monitor.MONITORED_FEATURES
                },
            }
        )
    return docs


def test_online_guardrail_main_emits_ops_rollout_gate_block(tmp_path, monkeypatch) -> None:
    exposures = _FakeExposureCollection(
        impression_count=400,
        model_impression_count=260,
    )
    feedbacks = _FakeFeedbackCollection(
        action_counts={"click": 8, "like": 12, "share": 4},
    )
    monkeypatch.setattr(
        online_guardrail,
        "MongoClient",
        lambda *args, **kwargs: _FakeGuardrailClient(
            _FakeGuardrailDb(exposures, feedbacks)
        ),
    )
    out_path = tmp_path / "guardrail_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "online_guardrail.py",
            "--scenario",
            "content_feed",
            "--window-hours",
            "4",
            "--dry-run",
            "--out",
            str(out_path),
        ],
    )

    exit_code = online_guardrail.main()

    assert exit_code == 1
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["status"] == "GATE_BLOCK_DRYRUN"
    assert report["action"] == "ops_rollout_required"
    assert report["environment"] == "gamma"
    assert "CTR=" in report["reason"] or "EngagementRate=" in report["reason"]


def test_activation_gate_reuses_immutable_stage_evidence() -> None:
    candidate = {
        "releaseId": "content-feed-20260802-001",
        "scenario": "content_feed",
        "status": "pass",
        "evaluationMetrics": {"auc": 0.72, "ndcg_20": 0.24},
    }
    active = {
        "evaluationMetrics": {"auc": 0.71, "ndcg_20": 0.23},
    }

    passed, reason = activation_gate.evaluate_activation_evidence(candidate, active)

    assert passed is True
    assert "AUC=" in reason


def test_activation_gate_rejects_nonpassing_or_incomplete_evidence() -> None:
    passed, reason = activation_gate.evaluate_activation_evidence(
        {
            "releaseId": "content-feed-20260802-002",
            "scenario": "content_feed",
            "status": "blocked",
            "evaluationMetrics": {"auc": 0.72, "ndcg_20": 0.24},
        }
    )
    assert passed is False
    assert "not a passing" in reason

    passed, reason = activation_gate.evaluate_activation_evidence({})
    assert passed is False
    assert "releaseId and scenario" in reason


def test_feature_drift_monitor_main_reports_alert_and_baseline_date(tmp_path, monkeypatch) -> None:
    baseline_docs = _build_feature_docs(
        value=1.0,
        count=80,
        scenario="content_feed",
        start_at=datetime(2026, 4, 30, 9, 0, 0),
    )
    current_docs = _build_feature_docs(
        value=5.0,
        count=80,
        scenario="content_feed",
        start_at=datetime(2026, 5, 2, 9, 0, 0),
    )
    monkeypatch.setattr(
        feature_drift_monitor,
        "MongoClient",
        lambda *args, **kwargs: _FeatureClient(_FeatureDb(baseline_docs, current_docs)),
    )
    out_path = tmp_path / "drift_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "feature_drift_monitor.py",
            "--scenario",
            "content_feed",
            "--baseline-date",
            "2026-05-01",
            "--out",
            str(out_path),
        ],
    )

    exit_code = feature_drift_monitor.main()

    assert exit_code == 1
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["baseline_date"] == "2026-05-01T00:00:00"
    assert report["overall_status"] == "alert"
    assert report["alert_features"]
    assert set(report["alert_features"]) == set(feature_drift_monitor.MONITORED_FEATURES)
