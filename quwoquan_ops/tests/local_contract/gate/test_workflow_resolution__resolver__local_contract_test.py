from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.workflow_resolution import ResolutionError, load_contract, resolve, verify_receipt  # noqa: E402
from lib.workflow_resolution.resolver import _receipt_digest  # noqa: E402

SPEC = "specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md"
MANIFEST = ".qwq_output/env/repo/runs/feature-tree/context-manifest.json"


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def regenerate_manifest(target: str = SPEC) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_ops/cli/feature_tree.py"), "context", "--target", target, "--format", "manifest"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def owner(*, ref: str = MANIFEST, target: str = SPEC, scope: str | None = None) -> dict[str, object]:
    return {"ref": ref, "expected_target": target, "expected_scope": scope}


def explicit(
    workflow: str,
    *,
    host: str = "cursor",
    adapter: str = "cursor-command-shell",
    manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    return resolve({
        "input_mode": "explicit",
        "command": f"/{workflow}",
        "host_label": host,
        "host_adapter": adapter,
        "owner_manifest": owner() if manifest is None else manifest,
    })


def natural(
    workflow: str,
    *,
    host: str = "codex",
    adapter: str = "codex-repository-adapter",
    manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    return resolve({
        "input_mode": "natural_structured",
        "text": "",
        "candidates": [{
            "workflow": workflow,
            "evidence": {"kind": "user_selection", "digest": sha(f"selected:{workflow}"), "reference": "user_explicit_workflow_selection"},
        }],
        "host_label": host,
        "host_adapter": adapter,
        "owner_manifest": owner() if manifest is None else manifest,
    })


@pytest.fixture(autouse=True)
def current_manifest() -> None:
    regenerate_manifest()


@pytest.mark.parametrize("workflow", list(load_contract()["workflows"]))
def test_explicit_and_structured_natural_have_semantic_parity(workflow: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-001.t1
    for _ in range(3):
        regenerate_manifest()
        left = explicit(workflow)
        right = natural(workflow)
        if left["result"] == right["result"] == "selected":
            break
    assert left["result"] == right["result"] == "selected"
    for field in ("selected_workflow", "skill_digest", "readiness_profile", "next_segment", "semantic_identity", "authorization_effect"):
        assert left[field] == right[field]
    assert left["receipt_digest"] != right["receipt_digest"]
    assert left["input_digest"] != right["input_digest"]


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-001.t3
def test_host_audit_changes_receipt_but_not_semantic_identity() -> None:
    cursor = explicit("review", host="cursor", adapter="cursor-command-shell")
    codex = explicit("review", host="codex", adapter="codex-repository-adapter")
    for field in ("selected_workflow", "skill_digest", "readiness_profile", "next_segment", "semantic_identity"):
        assert cursor[field] == codex[field]
    assert cursor["host_audit"] != codex["host_audit"]
    assert cursor["receipt_digest"] != codex["receipt_digest"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("继续做并进行 code review", {"continue", "review"}),
        ("继续部署到 gamma-local", {"continue", "environment-ops"}),
        ("验证后创建提交", {"review", "commit"}),
    ],
)
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-002.t1
def test_true_overlap_returns_typed_ask(text: str, expected: set[str]) -> None:
    receipt = resolve({"input_mode": "natural_structured", "text": text, "candidates": [], "owner_manifest": owner()})
    assert receipt["result"] == "ask"
    assert receipt["terminal_code"] == "WFR.AMBIGUOUS"
    assert receipt["recovery"] == "ask_user_to_select_one_listed_candidate"
    assert {item["workflow"] for item in receipt["candidates"]} == expected


@pytest.mark.parametrize(
    "text",
    [
        "请不要提交这次改动",
        "这句话是‘请创建提交’的引用示例",
        "讨论 git commit 的意图识别，不要执行",
        "请勿部署到 prod-hosted",
        "文案示例：内容生产",
    ],
)
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-002.t2
def test_negated_quoted_or_meta_mutation_never_selects_mutation(text: str) -> None:
    receipt = resolve({"input_mode": "natural_structured", "text": text, "candidates": [], "owner_manifest": owner()})
    assert receipt["result"] in {"ask", "hold"}
    assert receipt["selected_workflow"] is None
    assert receipt["terminal_code"] in {"WFR.MUTATION_INTENT_UNCERTAIN", "WFR.LOW_CONFIDENCE"}


def test_legal_plus_unknown_candidate_has_hold_precedence() -> None:
    receipt = resolve({
        "input_mode": "natural_structured", "text": "", "owner_manifest": owner(),
        "candidates": [
            {"workflow": "review", "evidence": {"kind": "user_selection", "digest": sha("review"), "reference": "user_explicit_workflow_selection"}},
            {"workflow": "invented", "evidence": {"kind": "host_classification", "digest": sha("invented"), "reference": "host_classifier"}},
        ],
    })
    assert receipt["result"] == "hold"
    assert receipt["terminal_code"] == "WFR.UNKNOWN_CANDIDATE"
    assert receipt["selected_workflow"] is None


def test_structured_candidate_rejects_raw_free_text_evidence() -> None:
    with pytest.raises(ResolutionError, match="must be an object"):
        resolve({
            "input_mode": "natural_structured", "text": "", "owner_manifest": owner(),
            "candidates": [{"workflow": "review", "evidence": "raw reason contains secret"}],
        })


def test_serialized_receipt_never_contains_natural_text_secret_email_or_pii() -> None:
    secret = "TOKEN-ghp_supersecret user@example.com 身份证11010519491231002X"
    receipt = resolve({
        "input_mode": "natural_structured", "text": f"请评审 {secret}", "candidates": [], "owner_manifest": owner(),
    })
    serialized = json.dumps(receipt, ensure_ascii=False)
    for forbidden in ("ghp_supersecret", "user@example.com", "11010519491231002X", secret):
        assert forbidden not in serialized
    assert receipt["candidates"][0]["confidence_basis"] == "contract_rule_match"


def test_real_manifest_is_opened_and_caller_cannot_assert_status() -> None:
    selected = explicit("continue")
    assert selected["result"] == "selected"
    assert selected["owner_manifest_status"] == "fresh"
    with pytest.raises(ResolutionError, match="fields drifted"):
        explicit("continue", manifest={**owner(), "status": "fresh"})


@pytest.mark.parametrize(
    ("manifest", "code", "status"),
    [
        (owner(ref=".qwq_output/env/repo/runs/feature-tree/no-such.json"), "WFR.OWNER_MANIFEST_REQUIRED", "missing"),
        ({"ref": "../outside.json", "expected_target": SPEC, "expected_scope": None}, "WFR.INPUT_INVALID", None),
    ],
)
def test_missing_or_traversal_manifest_fails_closed(manifest: dict[str, object], code: str, status: str | None) -> None:
    if code == "WFR.INPUT_INVALID":
        with pytest.raises(ResolutionError) as error:
            explicit("continue", manifest=manifest)
        assert error.value.code == code
        return
    receipt = explicit("continue", manifest=manifest)
    assert receipt["result"] == "hold"
    assert receipt["terminal_code"] == code
    assert receipt["owner_manifest_status"] == status
    assert receipt["next_segment"] == "hold"
    assert verify_receipt(receipt)["result"] == "valid"


def test_symlink_manifest_is_rejected(tmp_path: Path) -> None:
    link = ROOT / ".qwq_output/env/repo/runs/feature-tree/workflow-resolution-symlink.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(ROOT / MANIFEST, link)
        receipt = explicit("review", manifest=owner(ref=link.relative_to(ROOT).as_posix()))
        assert receipt["result"] == "hold"
        assert receipt["terminal_code"] == "WFR.OWNER_MANIFEST_UNSAFE"
        assert verify_receipt(receipt)["result"] == "valid"
    finally:
        if link.exists() or link.is_symlink():
            link.unlink()


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.update(schema_version=999), "WFR.OWNER_MANIFEST_INVALID"),
        (lambda value: value.update(target="specs/feature-tree/runtime/spec.md"), "WFR.OWNER_MANIFEST_TARGET_MISMATCH"),
        (lambda value: value.update(resolved_owner="specs/feature-tree/spec.md"), "WFR.OWNER_MANIFEST_OWNER_MISMATCH"),
        (lambda value: value["owner_chain"].pop(), "WFR.OWNER_MANIFEST_OWNER_MISMATCH"),
    ],
)
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-002.t3
def test_schema_target_and_owner_chain_drift_hold(mutation, code: str) -> None:
    path = ROOT / MANIFEST
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    receipt = explicit("review")
    assert receipt["result"] == "hold"
    assert receipt["terminal_code"] == code


def test_fingerprint_drift_holds_and_old_selected_receipt_becomes_invalid() -> None:
    receipt = explicit("dev")
    spec = ROOT / SPEC
    original = spec.read_text(encoding="utf-8")
    try:
        spec.write_text(original + "\n", encoding="utf-8")
        stale = explicit("dev")
        assert stale["result"] == "hold"
        assert stale["terminal_code"] == "WFR.OWNER_MANIFEST_STALE"
        with pytest.raises(ResolutionError, match="not current"):
            verify_receipt(receipt)
    finally:
        spec.write_text(original, encoding="utf-8")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result", "selected"),
        ("terminal_code", "WFR.SELECTED"),
        ("next_segment", "PRE"),
        ("ambiguity_terminal", "none"),
    ],
)
def test_rehashed_impossible_terminal_combinations_are_invalid(field: str, value: str) -> None:
    receipt = resolve({"input_mode": "natural_structured", "text": "请处理一下", "candidates": [], "owner_manifest": owner()})
    tampered = copy.deepcopy(receipt)
    tampered[field] = value
    tampered["receipt_digest"] = _receipt_digest({key: item for key, item in tampered.items() if key != "receipt_digest"})
    with pytest.raises(ResolutionError):
        verify_receipt(tampered)


def test_all_terminal_codes_project_one_recovery() -> None:
    contract = load_contract()
    recoveries = [descriptor["recovery"] for descriptor in contract["errors"].values()]
    assert len(recoveries) == len(set(recoveries))
    assert {code for entry in contract["terminal_matrix"].values() for code in entry["terminal_codes"]} == set(contract["errors"])


def test_cli_argparse_and_json_errors_are_single_typed_json(tmp_path: Path) -> None:
    cli = str(ROOT / "quwoquan_ops/cli/workflow_resolver.py")
    cases = ([sys.executable, cli], [sys.executable, cli, "resolve", "--unknown"])
    for command in cases:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        assert result.returncode == 2
        assert result.stderr == ""
        assert "usage:" not in result.stdout
        assert "Traceback" not in result.stdout
        parsed = json.loads(result.stdout)
        assert parsed["error_code"] == "WFR.INPUT_INVALID"
        assert parsed["terminal"] == "hold"


def test_control_workflow_boundary_semantics_and_authorization() -> None:
    continued = explicit("continue")
    reviewed = explicit("review")
    committed = resolve({"input_mode": "natural_structured", "text": "请提交", "candidates": [], "owner_manifest": owner()})
    assert continued["skill_ref"] == ".agents/skills/continue/SKILL.md"
    assert continued["next_segment"] == "PRE"  # resume branch remains Skill-owned
    assert reviewed["skill_ref"] == ".agents/skills/review/SKILL.md"
    assert reviewed["authorization_effect"] == "none"  # no recursive auto-review grant
    assert committed["selected_workflow"] == "commit"
    assert committed["authorization_effect"] == "none"  # resolver cannot grant external write permission


def test_real_host_discovery_remains_open_smoke_protocol() -> None:
    smoke = load_contract()["smoke_protocol"]
    assert smoke["status"] == "OPEN"
    assert smoke["open_id"] == "OPEN-001"
    assert smoke["claim_limit"] == "local_contract_does_not_prove_real_cursor_or_codex_discovery"
