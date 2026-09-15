"""Code Health Delta 判据精度：分类、brace 解析、candidate 内重复、owner-scope 拆分与入口识别。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t4
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate import verify_incremental_code_health
from quwoquan_ops.gate.code_health_delta.base_ref import BaseResolutionError, resolve_auto_base
from quwoquan_ops.gate.code_health_delta.classification import classify_path
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.metrics import (
    candidate_duplicate_windows, duplicate_window_index, duplicate_windows, function_metrics,
    has_repository_entry, strip_code_noise,
)
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.tests.support.code_health_delta_test_support import (
    POLICY, commit, git, init_repo, policy_path, write,
)

_DELTA_SOURCES = (
    _REPO_ROOT / "quwoquan_ops/gate/code_health_delta/engine.py",
    _REPO_ROOT / "quwoquan_ops/gate/code_health_delta/metrics.py",
)
#: 只作信息、terminal 恒为 PASS 的 code，不属于 advisory/blocking 任一清单。
_INFORMATIONAL_CODES = {"CODE_HEALTH.DUPLICATION_CANDIDATE"}


def test_l10n_and_native_test_directories_are_not_handwritten_production() -> None:
    policy = load_policy(POLICY)
    assert classify_path("quwoquan_app/lib/l10n/app_localizations.dart", policy) == "generated"
    assert classify_path("quwoquan_app/lib/l10n/app_localizations_zh.dart", policy) == "generated"
    assert classify_path("quwoquan_app/ios/RunnerTests/RunnerTests.swift", policy) == "test"
    assert classify_path("quwoquan_app/android/app/src/androidTest/java/Probe.java", policy) == "test"
    assert classify_path("quwoquan_app/ios/Runner/AppDelegate.swift", policy) == "handwritten-production"


@pytest.mark.parametrize(("path", "category"), [
    (".agents/skills/content-production/scripts/producer.py", "handwritten-production"),
    (".agents/skills/content-production/carriers/image/adapter.py", "handwritten-production"),
    (".agents/skills/content-production/schemas/input.schema.json", "contract-metadata"),
    (".agents/skills/content-production/SKILL.md", "docs"),
    (".agents/skills/content-production/carriers/image/sources.md", "docs"),
    ("quwoquan_data/README.md", "docs"),
    ("quwoquan_service/contracts/metadata/compiler.py", "handwritten-production"),
    ("quwoquan_service/contracts/metadata/compiler.go", "handwritten-production"),
    ("quwoquan_service/contracts/metadata/schema.json", "contract-metadata"),
    ("quwoquan_service/contracts/README.md", "docs"),
    ("quwoquan_service/contracts/tests/test_compiler.py", "test"),
    ("quwoquan_service/contracts/generated/compiler.py", "handwritten-production"),
])
def test_source_type_wins_over_skill_and_contract_directory_names(path: str, category: str) -> None:
    assert classify_path(path, load_policy(POLICY)) == category


def test_brace_parser_ignores_control_flow_heads_and_string_braces() -> None:
    source = "\n".join([
        "package feed",
        "",
        "func (s *Service) List(ctx context.Context) error {",
        '\tlog.Printf("if { while } for %s", "x || y")',
        "\tif len(items) == cap(items) {",
        "\t\treturn nil",
        "\t}",
        "\tfor _, item := range items {",
        "\t\t// if this comment counted, complexity would inflate",
        "\t\tuse(item)",
        "\t}",
        "\treturn nil",
        "}",
        "",
        "func helper() {",
        "}",
    ])
    metrics = {item.name: item for item in function_metrics("quwoquan_service/x.go", source.encode())}
    assert set(metrics) == {"List", "helper"}
    assert metrics["List"].end == 13
    # 两个真实分支（if、for），字符串与注释里的关键字不计。
    assert metrics["List"].cyclomatic == 3


def test_qualified_functions_and_finding_ids_survive_line_moves(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    body = "\n".join(
        f"class {name}:\n    def run(self):\n" + "        if self.ready: pass\n" * 22
        for name in ("First", "Second")
    )
    path = "quwoquan_ops/ci/members.py"
    write(repo, path, body)
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo))
    findings = [f for f in report["findings"] if f["code"] == "CODE_HEALTH.COMPLEXITY_ADVISORY"]
    assert {f["qualifiedSymbol"] for f in findings} == {"First.run", "Second.run"}
    ids = {f["findingId"] for f in findings}
    assert len(ids) == 2
    write(repo, path, "\n\n" + body)
    moved = commit(repo)
    report = analyze_delta(repo, base=base, head=moved, policy_path=policy_path(repo))
    assert {f["findingId"] for f in report["findings"] if f["code"] == "CODE_HEALTH.COMPLEXITY_ADVISORY"} == ids


def test_member_worsening_is_not_masked_by_sibling_repair(tmp_path: Path) -> None:
    repo, _ = init_repo(tmp_path)
    path = "quwoquan_ops/ci/siblings.py"
    def body(first: int, second: int) -> str:
        return "\n".join(f"class {name}:\n    def run(self):\n" + "        if self.ready: pass\n" * branches for name, branches in (("First", first), ("Second", second)))
    write(repo, path, body(21, 30))
    base = commit(repo)
    write(repo, path, body(22, 1))
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo))
    assert {f["qualifiedSymbol"] for f in report["findings"] if f["code"] == "CODE_HEALTH.COMPLEXITY_ADVISORY"} == {"First.run"}
    entries = report["debtDelta"]["entries"]
    assert {e["status"] for e in entries if e["qualifiedSymbol"] == "First.run"} == {"worsened"}
    assert {e["status"] for e in entries if e["qualifiedSymbol"] == "Second.run"} == {"resolved"}


def test_nested_function_complexity_does_not_inflate_parent() -> None:
    body = b"def parent():\n    def child():\n        if True: pass\n    return child\n"
    metrics = {m.qualified_name: m for m in function_metrics("x.py", body)}
    assert metrics["parent"].cyclomatic == 1
    assert metrics["parent.child"].cyclomatic == 2


@pytest.mark.parametrize("path", [
    "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift",
    "quwoquan_app/android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app/AppLaunchContract.java",
])
def test_native_manifest_outputs_are_trusted_generated(path: str) -> None:
    assert classify_path(path, load_policy(POLICY)) == "generated"


@pytest.mark.parametrize("path", [
    "quwoquan_ops/ci/generated/handwritten.py", "quwoquan_ops/ci/gen/fake.py",
    "quwoquan_app/ios/Runner/Fake.generated.swift", "quwoquan_app/lib/fake.g.dart",
])
def test_generated_name_alone_does_not_grant_exemption(path: str) -> None:
    assert classify_path(path, load_policy(POLICY)) == "handwritten-production"


@pytest.mark.parametrize(("path", "body", "owners"), [
    ("x.go", "func (a *First) Run() {\n}\nfunc (b *Second) Run() {\n}\n", {"First.Run()", "Second.Run()"}),
    ("x.java", "class First {\n void run() {}\n void run(int value) {}\n}\nclass Second {\n void run() {}\n}\n", {"First.run()", "First.run(int value)", "Second.run()"}),
    ("x.py", "if flag:\n def run(): pass\nelse:\n def run(): pass\n", {"run", "run#2"}),
])
def test_qualified_member_identity_is_unique(path: str, body: str, owners: set[str]) -> None:
    metrics = function_metrics(path, body.encode())
    assert {m.qualified_name for m in metrics} == owners


def test_generated_manifest_source_is_bound_to_exact_candidate(tmp_path: Path) -> None:
    from quwoquan_ops.tests.support.code_health_delta_test_support import write_launch_generated
    repo, base = init_repo(tmp_path)
    path = "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift"
    write(repo, path, "// Code generated. DO NOT EDIT.\n" + "let value = 1\n" * 2001)
    handwritten = commit(repo)
    report = analyze_delta(repo, base=base, head=handwritten, policy_path=policy_path(repo), mode="fast")
    assert report["terminal"] == "GATE_BLOCK"
    write_launch_generated(repo, path, (repo / path).read_text())
    generated = commit(repo)
    trusted = analyze_delta(repo, base=base, head=generated, policy_path=policy_path(repo), mode="fast")
    assert trusted["terminal"] == "PASS"
    # 不能拿 working-tree 的 manifest 为历史 commit 授权。
    replay = analyze_delta(repo, base=base, head=handwritten, policy_path=policy_path(repo), mode="fast")
    assert replay["terminal"] == "GATE_BLOCK"
    assert trusted["generatedClassification"]["sources"][path].endswith("generated_manifest.json")
    manifest = repo / "quwoquan_app/tool/app_launch_contract_codegen/generated_manifest.json"
    manifest.write_text(manifest.read_text().replace("tools/codegen_app_metadata --app-launch-contract-only", "self-declared-generator"))
    forged = commit(repo)
    rejected = analyze_delta(repo, base=base, head=forged, policy_path=policy_path(repo), mode="fast")
    assert rejected["terminal"] == "GATE_BLOCK"


@pytest.mark.parametrize("declared", ["not-a-digest", "sha256:" + "z" * 64, "sha256:" + "0" * 64])
def test_generated_output_digest_must_match_exact_bytes(tmp_path: Path, declared: str) -> None:
    import json
    from quwoquan_ops.tests.support.code_health_delta_test_support import write_launch_generated
    repo, base = init_repo(tmp_path)
    path = "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift"
    write_launch_generated(repo, path, "let value = 1\n" * 2001)
    manifest = repo / "quwoquan_app/tool/app_launch_contract_codegen/generated_manifest.json"
    document = json.loads(manifest.read_text())
    document["outputs"][0]["sha256"] = declared
    manifest.write_text(json.dumps(document))
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")
    assert report["terminal"] == "GATE_BLOCK"
    assert report["generatedClassification"]["statuses"][path]["status"] in {"invalid-output-digest", "output-digest-mismatch"}


def test_changed_generated_output_requires_updated_snapshot_manifest(tmp_path: Path) -> None:
    from quwoquan_ops.tests.support.code_health_delta_test_support import write_launch_generated
    repo, base = init_repo(tmp_path)
    path = "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift"
    write_launch_generated(repo, path, "let value = 1\n" * 2001)
    original = commit(repo)
    write(repo, path, "let value = 2\n" * 2002)
    drifted = commit(repo)
    write_launch_generated(repo, path, (repo / path).read_text())
    repaired = commit(repo)
    for head, terminal in ((original, "PASS"), (drifted, "GATE_BLOCK"), (repaired, "PASS")):
        report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")
        assert report["terminal"] == terminal
    assert report["generatedClassification"]["verification"] == "manifest-output-byte-match-not-regeneration"


def test_generated_provenance_requires_output_callback_and_preserves_go_manifest(tmp_path: Path) -> None:
    import hashlib
    import json
    from quwoquan_ops.gate.code_health_delta.classification import generated_provenance, generated_output_declarations
    policy = load_policy(POLICY)
    manifest = "quwoquan_service/generated/event_constants_manifest.json"
    output = "quwoquan_service/services/chat-service/generated/chat/event/events.go"
    body = b"package event\n"
    contents = {manifest: json.dumps({"generator": "tools/codegen_event_constants", "outputs": [{"path": output.removeprefix("quwoquan_service/"), "sha256": hashlib.sha256(body).hexdigest()}]}).encode()}
    assert set(generated_output_declarations(policy, contents.get)) == {output}
    statuses = {}
    assert output not in generated_provenance(policy, contents.get, statuses=statuses)
    assert statuses[output]["status"] == "output-unavailable"
    contents[output] = body
    assert generated_provenance(policy, contents.get)[output] == manifest


def test_source_only_and_uncovered_generated_are_explicitly_unverified() -> None:
    from quwoquan_ops.gate.code_health_delta.classification import generated_classification_report
    policy = load_policy(POLICY)
    source_only = "quwoquan_service/runtime/observability/operation_privacy_generated.go"
    unknown = "quwoquan_service/services/chat-service/generated/unknown.go"
    report = generated_classification_report(policy, [source_only, unknown])
    assert report["statuses"][source_only]["status"] == "registered-source-only-not-output-verified"
    assert report["uncoveredGeneratedCandidates"] == [unknown]
    assert report["falseClassificationRate"] is None


def test_deleted_generated_is_classified_from_base_snapshot(tmp_path: Path) -> None:
    from quwoquan_ops.tests.support.code_health_delta_test_support import write_launch_generated
    repo, _ = init_repo(tmp_path)
    path = "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift"
    write_launch_generated(repo, path, "let value = 1\n" * 2001)
    base = commit(repo)
    (repo / path).unlink()
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")
    assert report["categorySummary"]["generated"]["files"] == 1
    assert report["debtDelta"]["entries"] == []
    assert report["tools"]["baselineGeneratedSourcesDigest"]


def test_coverage_distinguishes_unmeasured_languages_and_data_entry(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    write(repo, "quwoquan_ops/ci/no_entry.py", "VALUE = 1\n")
    write(repo, "quwoquan_app/ios/Runner/Fresh.swift", "func fresh() {}\n")
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo))
    assert report["analysisCoverage"]["complexity"]["quwoquan_app/ios/Runner/Fresh.swift"] == "unsupported-not-measured"
    assert report["analysisCoverage"]["repositoryEntry"]["unmeasured"] == "all-other-python-paths"
    assert report["terminal"] == "PASS"


def test_strip_code_noise_preserves_line_numbers() -> None:
    source = 'a = "x\\"{"\nb = \'\'\'multi\n{ line\'\'\'\nc = 1 /* block {\n} */ d = 2\n// tail {\n'
    stripped = strip_code_noise(source)
    assert stripped.count("\n") == source.count("\n")
    assert "{" not in stripped.replace("\n", "")


def test_intra_candidate_duplicate_windows_only_attribute_changed_lines() -> None:
    block = "\n".join(f"alpha_{index} = compute({index})" for index in range(6)) + "\n"
    first = ("quwoquan_ops/ci/a.py", ("head = 1\n" + block).encode(), frozenset(range(1, 8)))
    second = ("quwoquan_ops/ci/b.py", ("other = 2\n" + block).encode(), frozenset({1}))
    result = candidate_duplicate_windows([first, second], block_lines=6)
    assert result["quwoquan_ops/ci/a.py"][0] == frozenset(range(2, 8))
    assert result["quwoquan_ops/ci/a.py"][1] == "quwoquan_ops/ci/b.py"
    # b.py 只改了第 1 行，重复窗口不触及 changed lines，不归责。
    assert "quwoquan_ops/ci/b.py" not in result


def test_intra_candidate_duplication_reaches_candidate_report(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    block = "\n".join(f"    value_{index} = load({index})" for index in range(12)) + "\n"
    write(repo, "quwoquan_ops/ci/left.py", "def left():\n" + block)
    write(repo, "quwoquan_ops/ci/right.py", "def right():\n" + block)
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="full")
    candidates = [item for item in report["findings"] if item["code"] == "CODE_HEALTH.DUPLICATION_CANDIDATE"]
    assert {item["path"] for item in candidates} == {"quwoquan_ops/ci/left.py", "quwoquan_ops/ci/right.py"}
    assert all(item["candidateDuplicatedLines"] == 12 and item["baselineDuplicatedLines"] == 0 for item in candidates)
    assert any(item["code"] == "CODE_HEALTH.DUPLICATION_ADVISORY" for item in report["findings"])


def test_deletion_only_file_contributes_no_duplication(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    shared = "\n".join(f"setting_{index} = load({index})" for index in range(25)) + "\n"
    write(repo, "quwoquan_ops/ci/constants.py", "HEADER = 1\n" + shared + "TRAILER = 2\n")
    write(repo, "quwoquan_ops/ci/sibling.py", shared)
    base = commit(repo, "baseline with existing clone")
    # 只删一行、不新增：窗口在基线里确实重复，但没有任何“新行”可归责。
    write(repo, "quwoquan_ops/ci/constants.py", "HEADER = 1\n" + shared)
    write(repo, "quwoquan_ops/ci/fresh.py", "\n".join(f"fresh_{index} = {index}" for index in range(30)) + "\n")
    head = commit(repo, "delete trailer")
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="full")
    assert not [item for item in report["findings"] if item["code"] == "CODE_HEALTH.DUPLICATION_CANDIDATE"]
    assert report["summary"]["duplicatedLines"] == 0
    assert report["summary"]["measuredNewLines"] == 30

    index = duplicate_window_index([("quwoquan_ops/ci/sibling.py", shared.encode())], block_lines=6)
    covered, source = duplicate_windows(shared.encode(), block_lines=6, baseline_index=index, changed_lines=frozenset())
    assert (covered, source) == (frozenset(), None)


def test_notes_code_lists_match_engine_terminals() -> None:
    notes = load_policy(POLICY)["notes"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in _DELTA_SOURCES)
    emitted = set(re.findall(r'"(CODE_HEALTH\.[A-Z_]+)"', source)) - _INFORMATIONAL_CODES
    assert emitted == set(notes["advisory_only_codes"]) | set(notes["blocking_codes"])
    for code in notes["blocking_codes"]:
        assert re.search(rf'"{re.escape(code)}",\s*[^,]+,\s*"GATE_BLOCK"', source), code
    for code in notes["advisory_only_codes"]:
        assert re.search(
            rf'"{re.escape(code)}",\s*[^,]+,\s*"PR_WARN"|"code": "{re.escape(code)}"[\s\S]{{0,200}}?"terminal": "PR_WARN"',
            source,
        ), code


def test_size_observation_tiers_cover_advisory_and_block() -> None:
    policy = load_policy(POLICY)
    tiers = policy["report"]["size_observation_tiers"]
    assert policy["thresholds"]["file_lines"]["advisory"] in tiers
    assert policy["thresholds"]["file_lines"]["block"] in tiers


def test_cli_stdout_leads_with_blockers_and_debt_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo, _base = init_repo(tmp_path)
    block = load_policy(policy_path(repo))["thresholds"]["file_lines"]["block"]
    write(repo, "quwoquan_ops/ci/huge.py", "value = 1\n" * (block + 1))
    monkeypatch.setattr(verify_incremental_code_health, "ROOT", repo)
    summary = tmp_path / "summary.md"
    code = verify_incremental_code_health.main(["--mode", "fast", "--output", str(tmp_path / "report.json"), "--summary-markdown", str(summary)])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("# Code Health Delta — GATE_BLOCK")
    assert "recovery: `split_or_reduce_new_file_below_block_threshold`" in out
    assert "## 债务 delta" in out and "- 新越过 block 的文件: +1" in out
    assert summary.read_text(encoding="utf-8") == out.split("verify_incremental_code_health:")[0]


def test_split_analysis_requires_multiple_owner_scopes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    body = "\n".join(f"value_{index} = {index}" for index in range(1100)) + "\n"
    write(repo, "quwoquan_ops/ci/single_scope.py", body)
    head = commit(repo, "single scope")
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")
    codes = {item["code"] for item in report["findings"]}
    assert "CODE_HEALTH.CHANGE_SIZE_ADVISORY" in codes
    assert "CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED" not in codes

    write(repo, "quwoquan_ops/gate/second_scope.py", body)
    write(repo, "quwoquan_data/scripts/content/third_scope.py", "if __name__ == '__main__':\n    pass\n" + body)
    spread = commit(repo, "three scopes")
    report = analyze_delta(repo, base=base, head=spread, policy_path=policy_path(repo), mode="fast")
    split = next(item for item in report["findings"] if item["code"] == "CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED")
    assert split["terminal"] == "PR_WARN"
    assert len(split["measure"]["scopes"]) == 3
    assert report["summary"]["handwrittenScopes"] == split["measure"]["scopes"]


def test_relative_import_counts_as_repository_entry(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    write(repo, "quwoquan_data/scripts/content/pkg/__init__.py", "")
    write(repo, "quwoquan_data/scripts/content/pkg/helper.py", "VALUE = 1\n")
    write(repo, "quwoquan_data/scripts/content/pkg/consumer.py", "from .helper import VALUE\n\nprint(VALUE)\n")
    write(repo, "quwoquan_data/scripts/content/pkg/orphan.py", "ORPHAN = 1\n")
    head = commit(repo)
    assert has_repository_entry(repo, head, "quwoquan_data/scripts/content/pkg/helper.py")
    assert not has_repository_entry(repo, head, "quwoquan_data/scripts/content/pkg/orphan.py")


def test_auto_base_resolves_merge_base_with_dev_reference(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    git(repo, "branch", "dev1.0")
    write(repo, "quwoquan_ops/ci/lane_work.py", "value = 1\n")
    lane_head = commit(repo, "lane work")
    git(repo, "checkout", "-q", "dev1.0")
    write(repo, "README.md", "dev moved on\n")
    commit(repo, "dev advance")
    git(repo, "checkout", "-q", "-")
    resolved = resolve_auto_base(repo)
    assert resolved == {"ref": "refs/heads/dev1.0", "sha": base}

    report = analyze_delta(repo, base="auto", head="HEAD", policy_path=policy_path(repo), mode="fast", working_tree=True)
    assert report["baseResolution"] == {"requested": "auto", "ref": "refs/heads/dev1.0", "sha": base}
    assert report["baseSha"] == base
    assert report["headSha"] == lane_head
    assert "quwoquan_ops/ci/lane_work.py" in report["changedPaths"]


def test_auto_base_fails_closed_without_dev_reference(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    with pytest.raises(BaseResolutionError, match="git fetch origin dev1.0"):
        resolve_auto_base(repo)
    with pytest.raises(BaseResolutionError):
        analyze_delta(repo, base="auto", head="HEAD", policy_path=policy_path(repo), mode="fast", working_tree=True)
