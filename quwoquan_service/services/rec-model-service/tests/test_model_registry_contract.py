from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ml"))

import model_registry
import model_registry_cli


class _FakeCollection:
    def __init__(self, doc: dict[str, object]) -> None:
        self.doc = doc
        self.updated = False

    def find_one(self, query, sort=None):  # noqa: D401, ANN001
        return self.doc

    def update_many(self, *args, **kwargs):  # noqa: D401, ANN001
        self.updated = True

    def update_one(self, *args, **kwargs):  # noqa: D401, ANN001
        self.updated = True


def _matches_query(doc: dict[str, object], query: dict[str, object]) -> bool:
    for key, expected in query.items():
        if isinstance(expected, dict) and "$exists" in expected:
            exists = key in doc and doc[key] is not None
            if bool(expected["$exists"]) != exists:
                return False
            continue
        if doc.get(key) != expected:
            return False
    return True


class _StatefulCollection:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self.docs = {doc["_id"]: doc for doc in docs}

    def find_one(self, query, sort=None):  # noqa: D401, ANN001
        candidates = [doc for doc in self.docs.values() if _matches_query(doc, query)]
        if not candidates:
            return None
        if sort:
            key, direction = sort[0]
            candidates.sort(key=lambda doc: doc.get(key), reverse=direction < 0)
        return candidates[0]

    def update_many(self, *args, **kwargs):  # noqa: D401, ANN001
        return None

    def update_one(self, query, update):  # noqa: D401, ANN001
        target_id = query.get("_id")
        if target_id not in self.docs:
            return None
        doc = self.docs[target_id]
        for field, value in update.get("$set", {}).items():
            doc[field] = value
        return None


class _FakeDb:
    def __init__(self, collection: object) -> None:
        self._collection = collection

    def __getitem__(self, name: str) -> object:
        if name != "rec_model_registry":
            raise KeyError(name)
        return self._collection


def test_write_registry_rejects_production_without_artifact_uri() -> None:
    with pytest.raises(RuntimeError, match="artifactUri"):
        model_registry.write_registry(
            mongo_db={},
            scenario="content_feed",
            version="v2026.05.16.0",
            metrics={"auc": 0.9},
            artifact_path="/tmp/model.txt",
            artifact_uri="",
            model_type="lgb",
            production=True,
        )


def test_promote_rejects_missing_artifact_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = {
        "scenario": "content_feed",
        "version": "v2026.05.16.0",
        "metrics": {"auc": 0.9},
        "artifactPath": "/tmp/model.txt",
        "artifactUri": "",
        "production": False,
    }
    fake_db = _FakeDb(_FakeCollection(doc))
    monkeypatch.setattr(model_registry_cli, "_connect", lambda: fake_db)

    with pytest.raises(SystemExit) as exc:
        model_registry_cli.cmd_promote(argparse.Namespace(scenario="content_feed", version="", force=False))

    assert exc.value.code == 1


def test_rollback_restores_previous_production(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = [
        {
            "_id": "current",
            "scenario": "content_feed",
            "version": "v2026.05.16.3",
            "production": True,
            "createdAt": 3,
        },
        {
            "_id": "candidate",
            "scenario": "content_feed",
            "version": "v2026.05.16.2",
            "production": False,
            "createdAt": 2,
        },
        {
            "_id": "rolled",
            "scenario": "content_feed",
            "version": "v2026.05.16.1",
            "production": False,
            "createdAt": 1,
            "rolledBackAt": "already-rolled",
        },
    ]
    fake_coll = _StatefulCollection(docs)
    fake_db = _FakeDb(fake_coll)
    monkeypatch.setattr(model_registry_cli, "_connect", lambda: fake_db)

    model_registry_cli.cmd_rollback(argparse.Namespace(scenario="content_feed"))

    assert fake_coll.docs["current"]["production"] is False
    assert "rolledBackAt" in fake_coll.docs["current"]
    assert fake_coll.docs["candidate"]["production"] is True
    assert "restoredAt" in fake_coll.docs["candidate"]
    assert fake_coll.docs["rolled"]["production"] is False

