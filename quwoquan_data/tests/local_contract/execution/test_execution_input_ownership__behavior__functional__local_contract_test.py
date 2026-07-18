"""Reusable input, execution output, and publish ownership contract."""
from __future__ import annotations

from core import paths
from content.execution import workspace


EXECUTION_ID = "20260711--travel-homepage-ownership--cn-zhejiang--canary-001"


def test_execution_plan_is_runtime_output_not_control_plane_state():
    spec_path = paths.execution_spec_path(EXECUTION_ID)
    assert spec_path == paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID / "0.plan" / "execution_spec.yaml"
    assert "control_plane/tasks" not in spec_path.as_posix()


def test_execution_root_allowlist_matches_work_package_contract():
    assert paths.EXECUTION_ROOT_ALLOWED_ENTRIES == frozenset(
        {
            "0.plan",
            "sources",
            "entities",
            "posts",
            "_shared",
            "evidence",
            "execution_manifest.json",
            "publish_ref.json",
        }
    )


def test_reusable_inputs_are_repo_owned_and_outside_output():
    for source in (
        paths.FAMILIES_ROOT,
        paths.CONTROL_PLANE_SHARED_ROOT,
        paths.SCHEMA_ROOT,
    ):
        assert not str(source).startswith(str(paths.OUTPUT_ROOT))
        assert not str(source).startswith(str(paths.PUBLISH_ROOT))


def test_publish_does_not_contain_runtime_or_configuration_files():
    if not paths.PUBLISH_ROOT.is_dir():
        return
    forbidden_names = {
        "execution_manifest.json",
        "execution_spec.yaml",
        "runtime_state.json",
        "execution_state.json",
        "prompt.md",
    }
    assert not [path for path in paths.PUBLISH_ROOT.rglob("*") if path.name in forbidden_names]
    assert not list(paths.PUBLISH_ROOT.rglob("*.recipe.yaml"))
    assert not list(paths.PUBLISH_ROOT.rglob("*.schema.json"))


def test_execution_publish_ref_binds_only_canonical_objects(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path)
    root = tmp_path / EXECUTION_ID
    root.mkdir(parents=True)

    path = workspace.write_publish_ref(
        EXECUTION_ID,
        entity_refs=["/entity/地点/景区/验收景区"],
        post_refs=["posts/article/攻略/验收景区/1"],
    )

    payload = workspace.read_json(path)
    assert payload == {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": EXECUTION_ID,
        "canonicalPublishRoot": "quwoquan_data/publish",
        "publishedRefs": {
            "entities": ["地点/景区/验收景区"],
            "posts": ["posts/article/攻略/验收景区/1"],
        },
    }
    assert "releaseId" not in payload
