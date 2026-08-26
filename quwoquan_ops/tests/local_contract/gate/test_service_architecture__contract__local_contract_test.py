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
    go_import_declarations,
    is_substantive_test_source,
    lifecycle_authored_consumers,
    lifecycle_handler_binding_issues,
    object_contract_semantic_issues,
    object_entrypoint_mode,
    valid_object_test_spec_refs,
)


ROOT = Path(__file__).resolve().parents[4]


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


def test_cross_service_boundary_reads_imports_not_path_literals() -> None:
    real_import = (
        "package conversation\n"
        "\n"
        "import (\n"
        '\t"fmt"\n'
        '\tgovernance "quwoquan_service/services/user-service/internal/relationship"\n'
        ")\n"
    )
    declarations = go_import_declarations(real_import)
    assert "user-service/internal/relationship" in declarations

    single_line_import = (
        "package conversation\n"
        '\nimport "quwoquan_service/services/user-service/generated/events"\n'
    )
    assert "user-service/generated/events" in go_import_declarations(
        single_line_import
    )

    # 测试枚举别的服务的路径做扫描目标，是数据不是依赖：边界判定不得据此报违规。
    path_literal_only = (
        "package conversation\n"
        "\n"
        'import "testing"\n'
        "\n"
        "func TestHomology(t *testing.T) {\n"
        "\tcarriers := map[string][]string{\n"
        '\t\t"go-struct": {"quwoquan_service/services/user-service/internal/relationship"},\n'
        "\t}\n"
        "\t_ = carriers\n"
        "}\n"
    )
    assert "user-service" not in go_import_declarations(path_literal_only)


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


def test_object_evidence_accepts_list_block_and_rejects_bare_strings(
    tmp_path: Path,
) -> None:
    """列表块与同行 marker 同源生效；裸字符串字面量不构成对象证据。"""
    marker = "spec_" + "ref"
    spec_path = "specs/feature-tree/sample/" "capability/story/spec.md"
    spec = tmp_path / spec_path
    spec.parent.mkdir(parents=True)
    spec.write_text(
        '# Story\n\n<a id="gwt-001"></a>\n### GWT-001 behavior\n',
        encoding="utf-8",
    )

    block = tmp_path / "test_block.py"
    block.write_text(
        '"""Docstring contract.\n'
        f"{marker}:\n"
        f"  - {spec_path}#gwt-001.t2\n"
        '"""\n'
        "def test_contract():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    refs, issues = valid_object_test_spec_refs(block, tmp_path)
    # `.tN` 子句剥离到主锚点做存在性校验。
    assert refs == {f"{spec_path}#gwt-001"}
    assert issues == []

    bare_only = tmp_path / "test_bare.py"
    bare_only.write_text(
        f'bare = "{spec_path}#gwt-001"\n'
        "def test_contract():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    refs, issues = valid_object_test_spec_refs(bare_only, tmp_path)
    assert refs == set()
    assert issues == []


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


def lifecycle_projection_document() -> dict[str, object]:
    return {
        "lifecycle": {
            "source_events": ["content.post.PostPublished"],
            "event_consumers": [
                {
                    "name": "ProjectPublishedPost",
                    "kind": "projector",
                    "facet": "PublishedPostConsumer",
                    "method": "processOnce",
                    "idempotency": "aggregate_version",
                }
            ],
        }
    }


def test_dec011_lifecycle_only_projection_requires_a_real_same_object_handler(
    tmp_path: Path,
) -> None:
    object_root = tmp_path / "internal/content/published_post_view"
    handler = object_root / "adapters/inbound/post_consumer.py"
    handler.parent.mkdir(parents=True)
    handler.write_text(
        "class PublishedPostConsumer:\n"
        "    def process_once(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    assert object_entrypoint_mode("projection", [], [], consumers) == (
        "lifecycle",
        [],
    )
    assert lifecycle_handler_binding_issues(consumers, object_root, [handler]) == []


def test_dec011_lifecycle_entrypoint_rejects_empty_or_malformed_authorship() -> None:
    assert object_entrypoint_mode("projection", [], [], []) == (
        None,
        [
            (
                "canonical object must own an HTTP operation, typed runtime entrypoint, "
                "or object-local lifecycle consumer handler"
            )
        ],
    )
    consumers, issues = lifecycle_authored_consumers(
        {"lifecycle": {"event_consumers": []}}
    )
    assert consumers == []
    assert "lifecycle entrypoint requires a non-empty source_events string list" in issues
    assert "lifecycle.event_consumers must be a non-empty list" in issues


def test_dec011_lifecycle_entrypoint_rejects_fake_cross_object_and_missing_handlers(
    tmp_path: Path,
) -> None:
    object_root = tmp_path / "internal/content/published_post_view"
    fake = object_root / "adapters/inbound/fake.py"
    fake.parent.mkdir(parents=True)
    fake.write_text(
        "# class PublishedPostConsumer:\n"
        "MARKER = 'def process_once(self):'\n",
        encoding="utf-8",
    )
    cross_object = tmp_path / "internal/content/other_view/adapters/consumer.py"
    cross_object.parent.mkdir(parents=True)
    cross_object.write_text(
        "class PublishedPostConsumer:\n"
        "    def process_once(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    missing_method = object_root / "adapters/inbound/missing_method.py"
    missing_method.write_text(
        "class PublishedPostConsumer:\n"
        "    def other_method(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    for sources in ([fake], [cross_object], [fake, cross_object], [missing_method]):
        binding_issues = lifecycle_handler_binding_issues(
            consumers,
            object_root,
            sources,
        )
        assert binding_issues == [
            (
                "lifecycle consumer ProjectPublishedPost must bind same-object handler "
                "PublishedPostConsumer.processOnce"
            )
        ]


def test_dec011_lifecycle_entrypoint_rejects_noncanonical_or_duplicate_source_events(
) -> None:
    invalid = lifecycle_projection_document()
    invalid["lifecycle"]["source_events"] = ["not-an-authored-edge"]
    _, issues = lifecycle_authored_consumers(invalid)
    assert issues == [
        (
            "lifecycle.source_events must use canonical domain.object.EventName refs; "
            "invalid indexes=[0]"
        )
    ]

    duplicate = lifecycle_projection_document()
    duplicate["lifecycle"]["source_events"] = [
        "content.post.PostPublished",
        "content.post.PostPublished",
    ]
    _, issues = lifecycle_authored_consumers(duplicate)
    assert issues == ["lifecycle.source_events must be unique"]


def test_dec011_lifecycle_only_entrypoint_is_projection_only() -> None:
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    for kind in (
        "aggregate_root",
        "append_only_fact",
        "external_reference",
        "runtime_session",
    ):
        assert object_entrypoint_mode(kind, [], [], consumers) == (
            None,
            [
                (
                    f"kind={kind} cannot use lifecycle consumers as its only entrypoint; "
                    "lifecycle-only entrypoints require ['projection']"
                )
            ],
        )


def test_dec011_lifecycle_entrypoint_rejects_stub_python_and_go_handlers(
    tmp_path: Path,
) -> None:
    object_root = tmp_path / "internal/content/published_post_view"
    adapters = object_root / "adapters"
    adapters.mkdir(parents=True)
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    expected = [
        (
            "lifecycle consumer ProjectPublishedPost must bind same-object handler "
            "PublishedPostConsumer.processOnce"
        )
    ]

    python_stubs = {
        "pass.py": (
            "class PublishedPostConsumer:\n"
            "    def process_once(self):\n"
            "        pass\n"
        ),
        "ellipsis.py": (
            "class PublishedPostConsumer:\n"
            "    def process_once(self):\n"
            "        ...\n"
        ),
        "abstract.py": (
            "from abc import abstractmethod\n"
            "class PublishedPostConsumer:\n"
            "    @abstractmethod\n"
            "    def process_once(self):\n"
            "        return 1\n"
        ),
        "not_implemented.py": (
            "class PublishedPostConsumer:\n"
            "    def process_once(self):\n"
            "        raise NotImplementedError()\n"
        ),
    }
    for name, source in python_stubs.items():
        path = adapters / name
        path.write_text(source, encoding="utf-8")
        assert lifecycle_handler_binding_issues(
            consumers,
            object_root,
            [path],
        ) == expected

    go_stubs = {
        "empty.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() {}\n"
        ),
        "panic.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() { panic(\"not implemented\") }\n"
        ),
        "return.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() { return }\n"
        ),
        "return_nil.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() error { return nil }\n"
        ),
        "return_zero.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() int { return 0 }\n"
        ),
        "return_false.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() bool { return false }\n"
        ),
        "return_empty_string.go": (
            "package adapters\n"
            "type PublishedPostConsumer struct{}\n"
            "func (*PublishedPostConsumer) ProcessOnce() string { return \"\" }\n"
        ),
    }
    for name, source in go_stubs.items():
        path = adapters / name
        path.write_text(source, encoding="utf-8")
        assert lifecycle_handler_binding_issues(
            consumers,
            object_root,
            [path],
        ) == expected

    real_go_handler = adapters / "real.go"
    real_go_handler.write_text(
        "package adapters\n"
        "type PublishedPostConsumer struct{}\n"
        "func (*PublishedPostConsumer) ProcessOnce() int {\n"
        "    processed := 1\n"
        "    return processed\n"
        "}\n",
        encoding="utf-8",
    )
    assert lifecycle_handler_binding_issues(
        consumers,
        object_root,
        [real_go_handler],
    ) == []


def test_dec011_http_and_runtime_entrypoints_remain_mutually_exclusive() -> None:
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    http_route = {"method": "GET", "path": "/published-posts"}
    runtime_entrypoint = {"kind": "projector"}
    assert object_entrypoint_mode(
        "projection",
        [http_route],
        [runtime_entrypoint],
        consumers,
    ) == (
        None,
        [
            (
                "canonical object must not own both HTTP api_routes and "
                "runtime_entrypoints"
            )
        ],
    )
    assert object_entrypoint_mode(
        "projection",
        [http_route],
        [],
        consumers,
    ) == ("http", [])


def test_dec011_legacy_runtime_entrypoint_remains_the_entry_owner() -> None:
    consumers, issues = lifecycle_authored_consumers(lifecycle_projection_document())
    assert issues == []
    assert object_entrypoint_mode(
        "projection",
        [],
        [{"kind": "projector"}],
        consumers,
    ) == (
        "runtime",
        [],
    )
