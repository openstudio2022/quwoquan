# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
from __future__ import annotations

import ast

from support.path_setup import model_runtime_root

SERVICE_ROOT = model_runtime_root()


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
    assert "UserAccountClosed" not in source
    assert "events.user.account" not in source


def test_score_cache_identity_is_excluded() -> None:
    capacity_source = (SERVICE_ROOT / "api/capacity.py").read_text(encoding="utf-8")
    capacity_module = ast.parse(capacity_source)
    score_cache_key = next(
        node
        for node in capacity_module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "score_cache_key"
    )
    source = ast.get_source_segment(capacity_source, score_cache_key)
    assert source is not None
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
    assert "recommendation_subject_closure_facts" in privacy_guard
    assert "closed_account_subject_tombstones" not in privacy_guard
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


class _SubjectClosureCollection:
    def __init__(self, subject_ids: set[str]) -> None:
        self._subject_ids = subject_ids

    def find(self, query, projection):  # noqa: ANN001
        requested = set(query["subjectIds"]["$in"])
        matched = requested & self._subject_ids
        return [{"subjectIds": sorted(matched)}] if matched else []


class _PrivacyDb:
    def __init__(self, subject_ids: set[str]) -> None:
        self._closures = _SubjectClosureCollection(subject_ids)

    def __getitem__(self, name: str):
        if name != "recommendation_subject_closure_facts":
            raise KeyError(name)
        return self._closures


def test_offline_guard_filters_recommendation_subject_closure_facts() -> None:
    import privacy_guard

    closed_id = "closed-persona"
    db = _PrivacyDb({closed_id})

    accepted, closed = privacy_guard.reject_closed_documents(
        db,
        [
            {"userId": closed_id, "targetId": "post-1"},
            {"userId": "open-persona", "targetId": "post-2"},
        ],
    )

    assert closed == {closed_id}
    assert accepted == [{"userId": "open-persona", "targetId": "post-2"}]
