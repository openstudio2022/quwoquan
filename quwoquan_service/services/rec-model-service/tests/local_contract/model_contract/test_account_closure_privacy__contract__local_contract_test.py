from __future__ import annotations

import inspect
from pathlib import Path
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[3]
for import_root in (SERVICE_ROOT, SERVICE_ROOT / "scripts"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def test_rec_model_runtime_is_not_a_second_account_closure_consumer() -> None:
    runtime_paths = [
        SERVICE_ROOT / "main.py",
        SERVICE_ROOT / "api",
        SERVICE_ROOT / "models",
    ]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in runtime_paths
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    requirements = (SERVICE_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "UserAccountClosed" not in source
    assert "events.user.account" not in source
    assert "redis" not in requirements.lower()


def test_score_cache_identity_is_excluded() -> None:
    from api import capacity

    source = inspect.getsource(capacity.score_cache_key)
    assert "userId" not in source
    assert "personaId" not in source
    assert "sessionId" not in source


def test_training_and_replay_scripts_enforce_closed_subject_guard() -> None:
    sample_joiner = (SERVICE_ROOT / "scripts/sample_joiner.py").read_text(
        encoding="utf-8",
    )
    replay_dataset = (SERVICE_ROOT / "scripts/replay_dataset.py").read_text(
        encoding="utf-8",
    )
    privacy_guard = (SERVICE_ROOT / "scripts/privacy_guard.py").read_text(
        encoding="utf-8",
    )

    for source in (sample_joiner, replay_dataset):
        assert "privacy_guard" in source
    assert "closed_account_subject_tombstones" in privacy_guard
    assert "privacy_invalidated" in replay_dataset

    for script_name in (
        "train.py",
        "train_embedding.py",
        "train_multiobjective.py",
        "evaluate.py",
    ):
        source = (SERVICE_ROOT / "scripts" / script_name).read_text(
            encoding="utf-8",
        )
        assert "privacy_guard" in source


class _TombstoneCollection:
    def __init__(self, digests: set[str]) -> None:
        self._digests = digests

    def find(self, query, projection):  # noqa: ANN001
        requested = set(query["_id"]["$in"])
        return [{"_id": digest} for digest in requested & self._digests]


class _PrivacyDb:
    def __init__(self, digests: set[str]) -> None:
        self._tombstones = _TombstoneCollection(digests)

    def __getitem__(self, name: str):
        if name != "closed_account_subject_tombstones":
            raise KeyError(name)
        return self._tombstones


def test_offline_guard_filters_hmac_tombstoned_subjects() -> None:
    import privacy_guard

    secret = "offline-privacy-contract-secret-32-bytes"
    closed_id = "closed-persona"
    db = _PrivacyDb({privacy_guard.subject_digest(closed_id, secret)})

    accepted, closed = privacy_guard.reject_closed_documents(
        db,
        [
            {"userId": closed_id, "targetId": "post-1"},
            {"userId": "open-persona", "targetId": "post-2"},
        ],
        secret=secret,
    )

    assert closed == {closed_id}
    assert accepted == [{"userId": "open-persona", "targetId": "post-2"}]
