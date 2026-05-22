from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ml"))

import feature_drift_monitor
import online_guardrail


class _FakeGuardrailCollection:
    def __init__(
        self,
        impression_count: int,
        action_counts: dict[str, int],
        model_impression_count: int,
    ) -> None:
        self._impression_count = impression_count
        self._action_counts = action_counts
        self._model_impression_count = model_impression_count

    def count_documents(self, query):  # noqa: D401, ANN001
        if query.get("eventType") == "rec_impression" and "context.score" in query:
            return self._model_impression_count
        return self._impression_count

    def aggregate(self, pipeline):  # noqa: D401, ANN001
        match = pipeline[0]["$match"]
        if match.get("eventType") == "rec_engagement":
            return [{"_id": action, "count": count} for action, count in self._action_counts.items()]
        if match.get("eventType") == "rec_impression":
            return [{"_id": None, "count": self._model_impression_count}]
        return []


class _FakeGuardrailDb:
    def __init__(self, collection: object) -> None:
        self._collection = collection

    def __getitem__(self, name: str) -> object:
        if name != "rec_learning_events":
            raise KeyError(name)
        return self._collection


class _FakeGuardrailClient:
    def __init__(self, db: object) -> None:
        self._db = db

    def __getitem__(self, name: str) -> object:
        if name != "quwoquan_content":
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


def test_online_guardrail_main_triggers_rule_only_cutover_dry_run(tmp_path, monkeypatch) -> None:
    collection = _FakeGuardrailCollection(
        impression_count=400,
        action_counts={"click": 8, "like": 12, "share": 4},
        model_impression_count=260,
    )
    monkeypatch.setattr(
        online_guardrail,
        "MongoClient",
        lambda *args, **kwargs: _FakeGuardrailClient(_FakeGuardrailDb(collection)),
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
    assert report["status"] == "RULE_ONLY_CUTOVER_DRYRUN"
    assert report["action"] == "rule_only_cutover"
    assert "CTR=" in report["reason"] or "EngagementRate=" in report["reason"]


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
