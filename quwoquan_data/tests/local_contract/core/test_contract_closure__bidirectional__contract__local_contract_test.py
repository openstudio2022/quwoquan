from __future__ import annotations

import json
from pathlib import Path

from verify.verify_contract_closure import evaluate


def _schema(root: Path, relative: str, identity: str, **extra: object) -> None:
    path = root / "quwoquan_data/schema" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"quwoquan_data/schema/{relative}",
        "type": "object",
        "properties": {"schema": {"const": identity}},
        **extra,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    tombstones = root / "quwoquan_data/control_plane/_shared/schema_retirement_tombstones.json"
    if not tombstones.exists():
        tombstones.parent.mkdir(parents=True, exist_ok=True)
        tombstones.write_text(json.dumps({"schema": "quwoquan_data.schema_retirement_tombstones.v1", "entries": []}), encoding="utf-8")


def _consumer(root: Path, source: str) -> None:
    path = root / "quwoquan_data/scripts/consumer.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t1
def test_live_root_and_supporting_ref_close_bidirectionally(tmp_path: Path) -> None:
    _schema(tmp_path, "content/support.schema.json", "quwoquan_data.support")
    _schema(
        tmp_path,
        "content/live.schema.json",
        "quwoquan_data.live",
        properties={
            "schema": {"const": "quwoquan_data.live"},
            "support": {"$ref": "support.schema.json"},
        },
    )
    _consumer(tmp_path, 'assert_valid({}, "content", "live")\n')

    assert evaluate(tmp_path) == []


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t2
def test_unbound_schema_fails_instead_of_becoming_a_candidate(tmp_path: Path) -> None:
    _schema(tmp_path, "content/orphan.schema.json", "quwoquan_data.orphan")
    _consumer(tmp_path, "VALUE = 'unrelated'\n")

    assert any("no production consumer" in issue for issue in evaluate(tmp_path))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t3
def test_deleted_authority_leaves_a_dangling_consumer_ref(tmp_path: Path) -> None:
    _schema(
        tmp_path,
        "content/live.schema.json",
        "quwoquan_data.live",
        properties={
            "schema": {"const": "quwoquan_data.live"},
            "missing": {"$ref": "missing.schema.json"},
        },
    )
    _consumer(tmp_path, 'SCHEMA = "quwoquan_data.live"\n')

    assert any("dangling external $ref" in issue for issue in evaluate(tmp_path))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t4
def test_duplicate_logical_identity_fails(tmp_path: Path) -> None:
    _schema(tmp_path, "content/one.schema.json", "quwoquan_data.same")
    _schema(tmp_path, "content/two.schema.json", "quwoquan_data.same")
    _consumer(tmp_path, 'SCHEMA = "quwoquan_data.same"\n')

    assert any("duplicate schema identity" in issue for issue in evaluate(tmp_path))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t5
def test_python_literal_loader_is_a_real_production_binding(tmp_path: Path) -> None:
    _schema(tmp_path, "content/live.schema.json", "quwoquan_data.live")
    _consumer(tmp_path, 'assert_valid({}, "content", "live")\n')

    assert evaluate(tmp_path) == []


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t7
def test_nested_payload_schema_const_is_not_a_root_identity(tmp_path: Path) -> None:
    _schema(
        tmp_path,
        "content/live.schema.json",
        "quwoquan_data.live",
        properties={
            "schema": {"const": "quwoquan_data.live"},
            "payload": {
                "type": "object",
                "properties": {"schema": {"const": "quwoquan_data.nested"}},
            },
        },
    )
    _schema(tmp_path, "content/other.schema.json", "quwoquan_data.nested")
    _consumer(tmp_path, 'assert_valid({}, "content", "live")\nassert_valid({}, "content", "other")\n')

    assert evaluate(tmp_path) == []


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t8
def test_arbitrary_tuple_and_identity_string_are_not_production_bindings(tmp_path: Path) -> None:
    _schema(tmp_path, "content/orphan.schema.json", "quwoquan_data.orphan")
    _consumer(tmp_path, 'PAIR = ("content", "orphan")\nNOTE = "quwoquan_data.orphan"\n')

    assert any("no production consumer" in issue for issue in evaluate(tmp_path))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t5
def test_explicit_dynamic_dispatch_registry_is_a_closed_binding(tmp_path: Path) -> None:
    _schema(tmp_path, "content/live.schema.json", "quwoquan_data.live")
    _consumer(tmp_path, 'AUTHOR_ARTIFACT_SCHEMAS = {"carrier": ("content", "live")}\nassert_valid({}, *AUTHOR_ARTIFACT_SCHEMAS["carrier"])\n')

    assert evaluate(tmp_path) == []


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t9
def test_external_ref_cannot_escape_data_schema_root(tmp_path: Path) -> None:
    _schema(
        tmp_path,
        "content/live.schema.json",
        "quwoquan_data.live",
        properties={
            "schema": {"const": "quwoquan_data.live"},
            "escape": {"$ref": "../../outside.schema.json"},
        },
    )
    (tmp_path / "quwoquan_data/outside.schema.json").write_text("{}", encoding="utf-8")
    _consumer(tmp_path, 'assert_valid({}, "content", "live")\n')

    assert any("escapes Data schema root" in issue for issue in evaluate(tmp_path))


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-009.t9
def test_comment_path_and_static_instance_are_not_executable_roots(tmp_path: Path) -> None:
    _schema(tmp_path, "content/orphan.schema.json", "quwoquan_data.orphan")
    _consumer(tmp_path, '# load_schema("content", "orphan")\nNOTE = "quwoquan_data/schema/content/orphan.schema.json"\n')
    asset = tmp_path / "quwoquan_app/assets/content/alpha/manifest.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(json.dumps({"schema": "quwoquan_data.orphan"}), encoding="utf-8")
    assert any("no production consumer" in issue for issue in evaluate(tmp_path))


def test_unknown_dynamic_loader_fails_closed(tmp_path: Path) -> None:
    _schema(tmp_path, "content/live.schema.json", "quwoquan_data.live")
    _consumer(tmp_path, 'def consume(domain, name):\n    assert_valid({}, domain, name)\n')
    assert any("dynamic schema call" in issue for issue in evaluate(tmp_path))


def test_registry_missing_target_fails_closed(tmp_path: Path) -> None:
    _schema(tmp_path, "content/live.schema.json", "quwoquan_data.live")
    _consumer(tmp_path, 'LIVE_SCHEMAS = {"bad": ("content", "missing")}\nassert_valid({}, *LIVE_SCHEMAS["bad"])\n')
    assert any("registry target does not exist" in issue for issue in evaluate(tmp_path))


def test_verify_only_cannot_close_authority(tmp_path: Path) -> None:
    _schema(tmp_path, "content/live.schema.json", "quwoquan_data.live")
    path = tmp_path / "quwoquan_data/scripts/verify/check.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('assert_valid({}, "content", "live")\n', encoding="utf-8")
    assert any("no production consumer" in issue for issue in evaluate(tmp_path))


def test_retired_path_and_identity_cannot_be_restored(tmp_path: Path) -> None:
    _schema(tmp_path, "content/new.schema.json", "quwoquan_data.retired")
    tombstones = tmp_path / "quwoquan_data/control_plane/_shared/schema_retirement_tombstones.json"
    tombstones.write_text(json.dumps({"schema": "quwoquan_data.schema_retirement_tombstones.v1", "entries": [{"path": "content/old.schema.json", "identities": ["quwoquan_data.retired"]}]}), encoding="utf-8")
    _consumer(tmp_path, 'assert_valid({}, "content", "new")\n')
    assert any("restores retired schema identity" in issue for issue in evaluate(tmp_path))


def test_go_importer_requires_loader_validator_call_chain(tmp_path: Path) -> None:
    _schema(tmp_path, "content/post_manifest.schema.json", "quwoquan_data.post_manifest")
    metadata = tmp_path / "quwoquan_service/services/content-service/contracts/content/post/operations.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text("external_schema_imports:\n- schema_path: quwoquan_data/schema/content/post_manifest.schema.json\n  loader_ref: quwoquan_service/loader.go#LoadPosts\n  validator_ref: quwoquan_service/validator.go#ValidatePost\n", encoding="utf-8")
    (tmp_path / "quwoquan_service/loader.go").write_text("package x\nfunc LoadPosts() {}\n", encoding="utf-8")
    (tmp_path / "quwoquan_service/validator.go").write_text("package x\nfunc ValidatePost() {}\n", encoding="utf-8")
    assert any("loader does not call declared validator" in issue for issue in evaluate(tmp_path))
