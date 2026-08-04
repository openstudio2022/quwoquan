# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-005
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-006
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-002

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from quwoquan_ops.gate.verify_service_architecture import (
    is_substantive_test_source,
    object_contract_semantic_issues,
    valid_object_test_spec_refs,
)


ROOT = Path(__file__).resolve().parents[3]


def test_service_architecture_governance_facade() -> None:
    result = subprocess.run(
        [sys.executable, "quwoquan_ops/gate/verify_service_architecture.py"],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_object_evidence_rejects_support_files_and_empty_tests(tmp_path: Path) -> None:
    support = tmp_path / "support.go"
    support.write_text("package sample\n\nfunc BuildFixture() {}\n", encoding="utf-8")
    empty_go_test = tmp_path / "empty_test.go"
    empty_go_test.write_text(
        "package sample\n\nfunc TestEmpty(t *testing.T) {}\n",
        encoding="utf-8",
    )
    real_go_test = tmp_path / "contract_test.go"
    real_go_test.write_text(
        "package sample\n\nfunc TestContract(t *testing.T) {\n\tif false { t.Fatal(\"unreachable\") }\n}\n",
        encoding="utf-8",
    )
    empty_python_test = tmp_path / "test_empty.py"
    empty_python_test.write_text("def test_empty():\n    pass\n", encoding="utf-8")
    real_python_test = tmp_path / "test_contract.py"
    real_python_test.write_text("def test_contract():\n    assert 1 == 1\n", encoding="utf-8")

    assert not is_substantive_test_source(support)
    assert not is_substantive_test_source(empty_go_test)
    assert is_substantive_test_source(real_go_test)
    assert not is_substantive_test_source(empty_python_test)
    assert is_substantive_test_source(real_python_test)


def test_object_evidence_requires_an_existing_feature_tree_acceptance_anchor(
    tmp_path: Path,
) -> None:
    spec_path = "specs/feature-tree/sample/" "capability/story/spec.md"
    spec = tmp_path / spec_path
    spec.parent.mkdir(parents=True)
    spec.write_text(
        '# Story\n\n<a id="gwt-001"></a>\n### GWT-001 behavior\n',
        encoding="utf-8",
    )
    valid = tmp_path / "valid_test.go"
    valid_ref = f"{spec_path}#gwt-001"
    valid.write_text(
        f"// spec_ref: {valid_ref}\n"
        "package sample\n\nfunc TestContract(t *testing.T) { t.Fatal() }\n",
        encoding="utf-8",
    )
    refs, issues = valid_object_test_spec_refs(valid, tmp_path)
    assert refs == {valid_ref}
    assert issues == []

    missing_anchor = tmp_path / "missing_anchor_test.go"
    missing_anchor_ref = f"{spec_path}#gwt-002"
    missing_anchor.write_text(
        f"// spec_ref: {missing_anchor_ref}\n"
        "package sample\n\nfunc TestContract(t *testing.T) { t.Fatal() }\n",
        encoding="utf-8",
    )
    refs, issues = valid_object_test_spec_refs(missing_anchor, tmp_path)
    assert refs == set()
    assert issues == [
        f"spec_ref acceptance anchor does not exist: {missing_anchor_ref}"
    ]


def test_object_semantics_are_kind_aware_and_reject_generic_placeholders() -> None:
    projection = {
        "kind": "projection",
        "description": "由权威事件重建且只提供命名读取的投影视图。",
        "identity": {"fields": ["id"], "version_source": "checkpoint"},
        "access": {
            "commands": "none",
            "queries": "named_reader",
            "cross_context": "public_contract_only",
        },
        "business_rules": ["只从权威事件重建，不接受客户端直接写入。"],
    }
    assert object_contract_semantic_issues(projection) == []

    projection["description"] = "某某领域对象契约"
    projection["identity"]["version_source"] = "field"
    projection["access"]["commands"] = "aggregate_facade"
    projection["business_rules"] = [""]
    issues = object_contract_semantic_issues(projection)
    assert any("generic" in issue for issue in issues)
    assert any("version_source" in issue for issue in issues)
    assert any("access.commands" in issue for issue in issues)
    assert any("business_rules[0]" in issue for issue in issues)
