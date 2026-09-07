#!/usr/bin/env python3
"""Execute one Review plan's named evidence once and emit canonical receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    declared_object,
    validate_declared_fields,
    validate_required_fields,
)
from lib.evidence_fingerprint import (  # noqa: E402
    build_evidence_fingerprint,
    canonical_digest,
    normalize_repo_relative_path,
    snapshot_path,
    validate_evidence_fingerprint,
    validate_ref,
    workspace_digests,
)
import review_dispatch as review_dispatch_module  # noqa: E402
from lib.descriptor_safe_io import (  # noqa: E402
    read_repo_relative_regular_single_link,
)
from lib.readiness_case_result import (  # noqa: E402
    ReadinessCaseResultError,
    write_create_once_json,
)
from lib.named_evidence_artifact import (  # noqa: E402
    NamedEvidenceArtifactError,
    read_result_artifact,
)

sys.path.insert(0, str(ROOT / "quwoquan_ops/gate/lib"))
from process_group_deadline import run_command  # noqa: E402

OUTPUT_ROOT = ROOT / ".qwq_output/env/repo/runs/review-evidence"
BASELINE_PLAN_ENV = "QWQ_REVIEW_BASELINE_PLAN_PATH"
BASELINE_PLAN_SHA_ENV = "QWQ_REVIEW_BASELINE_PLAN_SHA256"
BASELINE_PLAN_REF_ENV = "QWQ_REVIEW_BASELINE_PLAN_REF"
RESULT_PATH_ENV = "QWQ_NAMED_EVIDENCE_RESULT_PATH"
SOURCE_HEAD_ENV = "QWQ_REVIEW_EVIDENCE_HEAD_SHA"
SOURCE_MERGE_BASE_ENV = "QWQ_REVIEW_EVIDENCE_MERGE_BASE_SHA"


class EvidenceRunnerError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _command_digest(command: str) -> str:
    return _sha256_bytes(command.encode("utf-8"))


def _git_text(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"git {' '.join(args)} failed"
        raise EvidenceRunnerError(detail)
    return result.stdout.strip()


def _workspace_source_classification(repo_root: Path = ROOT) -> dict[str, Any]:
    """Classify the exact current workspace without overstating immutability."""

    head_sha = _git_text(repo_root, "rev-parse", "HEAD")
    if not head_sha:
        raise EvidenceRunnerError("无法读取 source HEAD")
    merge_base_sha = head_sha
    for base in ("origin/dev1.0", "dev1.0", "main"):
        result = subprocess.run(
            ["git", "merge-base", head_sha, base],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            merge_base_sha = result.stdout.strip()
            break
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise EvidenceRunnerError(
            status.stderr.decode("utf-8", errors="replace").strip()
            or "无法读取 source workspace status"
        )
    repository_clean = status.stdout == b""
    return {
        "mode": "workspace",
        "head_sha": head_sha,
        "merge_base_sha": merge_base_sha,
        "repository_clean": repository_clean,
        "immutable": False,
    }


def _evidence_classification(source: dict[str, Any]) -> tuple[str, bool]:
    eligible = (
        source.get("mode") == "workspace"
        and source.get("repository_clean") is True
        and source.get("immutable") is False
    )
    return ("reusable", True) if eligible else ("feedback_only", False)


def _validate_source(source: dict[str, Any]) -> None:
    validate_declared_fields(source, "named_evidence_receipt", "source_fields")
    if source["mode"] != "workspace" or source["immutable"] is not False:
        raise EvidenceRunnerError("named evidence source 仅支持 mutable workspace")
    if type(source["repository_clean"]) is not bool:
        raise EvidenceRunnerError("named evidence source.repository_clean 必须为 bool")
    import re

    for field in ("head_sha", "merge_base_sha"):
        if not isinstance(source[field], str) or re.fullmatch(r"[0-9a-f]{40,64}", source[field]) is None:
            raise EvidenceRunnerError(f"named evidence source.{field} 非 exact Git SHA")


def _assert_source_head(source: dict[str, Any], repo_root: Path) -> None:
    current = _workspace_source_classification(repo_root)
    if current["head_sha"] != source["head_sha"]:
        raise EvidenceRunnerError(
            "REVIEW.FINGERPRINT_CHANGED: evidence source exact Git SHA 已 stale"
        )
    if source["repository_clean"] is True and current["repository_clean"] is not True:
        raise EvidenceRunnerError(
            "REVIEW.FINGERPRINT_CHANGED: clean exact Git SHA workspace 在命令后变脏"
        )


def require_admission_eligible(
    receipt: dict[str, Any], *, label: str = "named evidence receipt"
) -> dict[str, Any]:
    """Reject development feedback at any formal admission/reuse boundary."""

    validate_named_evidence_receipt(receipt)
    if (
        receipt.get("evidence_class") != "reusable"
        or receipt.get("admission_eligible") is not True
    ):
        source = receipt.get("source") or {}
        reason = (
            "dirty mutable workspace"
            if source.get("mode") == "workspace"
            and source.get("repository_clean") is False
            else "non-admission evidence source"
        )
        raise EvidenceRunnerError(
            "REVIEW.EVIDENCE_FEEDBACK_ONLY: "
            f"{label} 来自 {reason}，仅可用于开发反馈，不得用于正式准出或复用"
        )
    return receipt


def _managed_paths(plan: dict[str, Any]) -> list[str]:
    paths = list(plan.get("changed_paths") or [])
    paths.extend(
        str(item.get("path") or "")
        for item in (plan.get("contexts") or [])
        if isinstance(item, dict) and item.get("path")
    )
    return sorted(set(paths))


def _fingerprint_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind artifact reports by exact bytes without re-encoding metric numbers."""

    projected: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        artifact = item.get("artifact")
        if isinstance(artifact, dict):
            # summary/findings may contain finite decimal metrics. EvidenceFingerprint's
            # cross-runtime canonical subset is integer-only, while the report's exact
            # byte digest already binds those projections after fail-closed validation.
            item["artifact"] = {
                key: value
                for key, value in artifact.items()
                if key not in {"summary", "findings"}
            }
        projected.append(item)
    return projected


def _fingerprint(
    *,
    plan: dict[str, Any],
    evidence: list[dict[str, Any]],
    results: list[dict[str, Any]],
    phase: str,
    registry: dict[str, Any],
    source: dict[str, Any],
    repo_root: Path = ROOT,
    plan_bytes_sha256: str | None = None,
    plan_input_ref: str | None = None,
) -> dict[str, Any]:
    if plan_bytes_sha256 is None or plan_input_ref is None:
        raise EvidenceRunnerError(
            "exact plan bytes identity 为 evidence fingerprint 重算必填输入"
        )
    current_plan = review_dispatch_module.recompute_plan_fingerprint(plan, registry)
    payload = current_plan["digest_payload"]
    generator_path = Path(__file__).resolve()
    try:
        generator_ref = generator_path.relative_to(repo_root.resolve())
    except ValueError:
        generator_ref = None
    generator = (
        snapshot_path(generator_ref, repo_root=repo_root)
        if generator_ref is not None
        else {"path": str(generator_path), "content_digest": _sha256_bytes(generator_path.read_bytes())}
    )
    return build_evidence_fingerprint(
        {
            "git": {
                "head_sha": source["head_sha"],
                "merge_base_sha": source["merge_base_sha"],
            },
            "workspace": workspace_digests(_managed_paths(plan), repo_root=repo_root),
            "assets": {
                "canonical_assets_digest": canonical_digest(
                    {
                        "plan_fingerprint_ref": current_plan["ref"],
                        "plan_input_ref": plan_input_ref,
                        "plan_bytes_sha256": plan_bytes_sha256,
                        "evidence": [
                            {
                                "id": item["id"],
                                "command_digest": item["command_digest"],
                                "required": item["required"],
                                "timeout_seconds": item["timeout_seconds"],
                            }
                            for item in evidence
                        ],
                    }
                ),
                "review_assets_digest": canonical_digest(
                    {
                        "plan_assets": payload["assets"],
                        "source": source,
                        "results": _fingerprint_results(results),
                    }
                ),
            },
            "execution": {
                "commands_digest": payload["execution"]["commands_digest"],
                "toolchain_digest": canonical_digest(
                    {
                        "python": list(sys.version_info[:3]),
                        "shell": "/bin/sh",
                        "plan_toolchain": payload["execution"]["toolchain_digest"],
                    }
                ),
                "provider_digest": canonical_digest(
                    {
                        "runner": "process-group-deadline-shell-false",
                        "plan_provider": payload["execution"]["provider_digest"],
                    }
                ),
                "generator_digest": canonical_digest(
                    {
                        "runner": generator,
                        "plan_generator": payload["execution"]["generator_digest"],
                    }
                ),
            },
        },
        captured_by="evidence_runner",
        captured_metadata={
            "phase": phase,
            "source": source,
            "plan_input_ref": plan_input_ref,
            "plan_bytes_sha256": plan_bytes_sha256,
        },
    )


def _assert_same_fingerprint(
    expected: dict[str, Any],
    current: dict[str, Any],
    *,
    phase: str,
) -> None:
    for field in ("ref", "digest", "digest_payload"):
        if current[field] != expected[field]:
            raise EvidenceRunnerError(
                f"REVIEW.FINGERPRINT_CHANGED: evidence {phase} {field} 已 stale"
            )


def _assert_plan_source_range(
    plan: dict[str, Any], source: dict[str, Any]
) -> None:
    if (
        source["head_sha"] != plan["head_sha"]
        or source["merge_base_sha"] != plan["merge_base_sha"]
    ):
        raise EvidenceRunnerError(
            "REVIEW.FINGERPRINT_CHANGED: evidence source exact Git range 与 plan 漂移"
        )


def run_plan(
    plan: dict[str, Any],
    *,
    run_id: str | None = None,
    captured_by: str = "evidence_runner",
    cwd: Path = ROOT,
    registry: dict[str, Any] | None = None,
    plan_bytes: bytes | None = None,
    plan_ref: str | None = None,
) -> dict[str, Any]:
    if registry is None:
        raise EvidenceRunnerError("registry 为 canonical evidence 执行必填输入")
    if plan_bytes is None or plan_ref is None:
        raise EvidenceRunnerError(
            "exact plan bytes/ref 为 canonical evidence 执行必填输入"
        )
    exact_plan_bytes = plan_bytes
    try:
        exact_plan = json.loads(exact_plan_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceRunnerError(f"exact plan bytes 非法: {exc}") from exc
    if not isinstance(exact_plan, dict) or exact_plan != plan:
        raise EvidenceRunnerError("REVIEW.FINGERPRINT_CHANGED: exact plan bytes 与已验证 plan 不一致")
    exact_plan_sha256 = _sha256_bytes(exact_plan_bytes)
    resolved_plan_ref = plan_ref or f"in-memory:{exact_plan_sha256}"

    try:
        plan_receipt = review_dispatch_module.validate_current_review_plan(
            plan, registry, phase="evidence"
        )
    except review_dispatch_module.ReviewDispatchError as exc:
        raise EvidenceRunnerError(f"{exc.code}: {exc.message}") from exc
    if plan.get("fingerprint") != plan_receipt["digest"]:
        raise EvidenceRunnerError("REVIEW.FINGERPRINT_CHANGED: plan fingerprint 已 stale")
    validate_ref(plan_receipt["ref"], digest=plan_receipt["digest"])
    raw_evidence = plan.get("evidence")
    if not isinstance(raw_evidence, list):
        raise EvidenceRunnerError("plan.evidence 必须为列表")

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            raise EvidenceRunnerError("plan.evidence 项必须为 mapping")
        evidence_id = str(raw.get("id") or "")
        if not evidence_id:
            raise EvidenceRunnerError("evidence id 不能为空")
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        command = raw.get("command")
        command_digest = raw.get("command_digest")
        if not isinstance(command, str) or not command:
            raise EvidenceRunnerError(f"evidence={evidence_id} command 不能为空")
        exact = _command_digest(command)
        registered = (registry.get("evidence") or {}).get(evidence_id)
        if not isinstance(registered, dict):
            raise EvidenceRunnerError(f"evidence={evidence_id} 不在 registry")
        registered_command = registered.get("command")
        if registered_command != command:
            raise EvidenceRunnerError(
                f"evidence={evidence_id} command 与 registry 解析结果不一致"
            )
        registered_digest = _command_digest(str(registered_command))
        timeout_seconds = registered.get("timeout_seconds")
        max_evidence_timeout = (registry.get("limits") or {}).get(
            "max_evidence_timeout_seconds"
        )
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
            or not isinstance(max_evidence_timeout, int)
            or timeout_seconds > max_evidence_timeout
        ):
            raise EvidenceRunnerError(
                f"evidence={evidence_id} timeout_seconds 必须为 registry 正数上限内的整数"
            )
        if raw.get("timeout_seconds") != timeout_seconds:
            raise EvidenceRunnerError(
                f"evidence={evidence_id} timeout_seconds 与 registry 漂移"
            )
        if command_digest != registered_digest:
            raise EvidenceRunnerError(
                f"evidence={evidence_id} command_digest 与 registry 漂移"
            )
        if command_digest != exact:
            raise EvidenceRunnerError(
                f"evidence={evidence_id} command digest 漂移：expected={exact} actual={command_digest}"
            )
        evidence.append(
            {
                "id": evidence_id,
                "command": command,
                "command_digest": exact,
                "required": bool(raw.get("required", True)),
                "timeout_seconds": timeout_seconds,
                "result_artifact": registered.get("result_artifact"),
            }
        )

    if not evidence:
        raise EvidenceRunnerError("plan.evidence 不得为空")

    started_at = _now()
    repo_root = cwd.resolve()
    source = _workspace_source_classification(repo_root)
    _assert_plan_source_range(plan, source)
    evidence_class, admission_eligible = _evidence_classification(source)
    execution_fingerprint = _fingerprint(
        plan=plan, evidence=evidence, results=[], phase="execution_input", registry=registry,
        source=source, repo_root=repo_root, plan_bytes_sha256=exact_plan_sha256, plan_input_ref=resolved_plan_ref,
    )
    results: list[dict[str, Any]] = []
    failed_required: str | None = None
    failed_required_timed_out = False
    with tempfile.TemporaryDirectory(prefix="qwq-review-evidence-plan-") as directory:
        plan_input = Path(directory) / "exact-plan.json"
        plan_input.write_bytes(exact_plan_bytes)
        plan_input.chmod(0o400)
        command_env = os.environ.copy()
        for reserved in (
            BASELINE_PLAN_ENV,
            BASELINE_PLAN_SHA_ENV,
            BASELINE_PLAN_REF_ENV,
            RESULT_PATH_ENV,
            SOURCE_HEAD_ENV,
            SOURCE_MERGE_BASE_ENV,
        ):
            command_env.pop(reserved, None)
        command_env.update(
            {
                BASELINE_PLAN_ENV: str(plan_input),
                BASELINE_PLAN_SHA_ENV: exact_plan_sha256,
                BASELINE_PLAN_REF_ENV: resolved_plan_ref,
                SOURCE_HEAD_ENV: source["head_sha"],
                SOURCE_MERGE_BASE_ENV: source["merge_base_sha"],
            }
        )
        for item in evidence:
            item_started = _now()
            descriptor_path = Path(directory) / f"{item['id']}.json"
            item_env = dict(command_env)
            item_env[RESULT_PATH_ENV] = str(descriptor_path)
            completed = run_command(
                ["/bin/sh", "-c", item["command"]],
                cwd=cwd,
                timeout_seconds=float(item["timeout_seconds"]),
                capture_output=True,
                env=item_env,
            )
            item_finished = _now()
            # 声明了 result_artifact 的证据命令若自身失败且未写描述符，这是该证据的
            # 失败事实，应记入回执让 terminal 走 failed（如脏工作树下的 Code Health）；
            # 只有命令成功却没有描述符、或描述符存在但身份漂移，才是合同违规。
            descriptor_absent = not (descriptor_path.exists() or descriptor_path.is_symlink())
            try:
                if item["result_artifact"] is not None and descriptor_absent and completed.returncode != 0:
                    artifact = None
                else:
                    artifact = read_result_artifact(
                        kind=item["result_artifact"], descriptor_path=descriptor_path,
                        evidence_id=item["id"], plan=plan, plan_ref=resolved_plan_ref,
                        plan_sha256=exact_plan_sha256, source=source, repo_root=repo_root,
                    )
            except NamedEvidenceArtifactError as exc:
                raise EvidenceRunnerError(str(exc)) from exc
            results.append(
                declared_object(
                    {
                        "id": item["id"],
                        "command": item["command"],
                        "command_digest": item["command_digest"],
                        "timeout_seconds": item["timeout_seconds"],
                        "exit_code": completed.returncode,
                        "outcome": "timeout" if completed.timed_out else "exited",
                        "timed_out": completed.timed_out,
                        "termination_signal": completed.termination_signal,
                        "stdout_digest": _sha256_bytes(completed.stdout),
                        "stderr_digest": _sha256_bytes(completed.stderr),
                        "started_at": item_started,
                        "finished_at": item_finished,
                        "captured_by": captured_by,
                        "required": item["required"],
                        "artifact": artifact,
                    },
                    "named_evidence_receipt",
                    "evidence_result_fields",
                )
            )
            _assert_source_head(source, repo_root)
            post_command = _fingerprint(
                plan=plan, evidence=evidence, results=[], phase="post_command", registry=registry,
                source=source, repo_root=repo_root,
                plan_bytes_sha256=exact_plan_sha256, plan_input_ref=resolved_plan_ref,
            )
            _assert_same_fingerprint(
                execution_fingerprint, post_command, phase=f"after {item['id']}"
            )
            if completed.returncode != 0 and item["required"]:
                failed_required = item["id"]
                failed_required_timed_out = completed.timed_out
                break

    finished_at = _now()
    _assert_source_head(source, repo_root)
    final_input = _fingerprint(
        plan=plan, evidence=evidence, results=[], phase="final_input", registry=registry,
        source=source, repo_root=repo_root,
        plan_bytes_sha256=exact_plan_sha256, plan_input_ref=resolved_plan_ref,
    )
    _assert_same_fingerprint(execution_fingerprint, final_input, phase="final")
    result_fingerprint = _fingerprint(
        plan=plan, evidence=evidence, results=results, phase="execution_result", registry=registry,
        source=source, repo_root=repo_root, plan_bytes_sha256=exact_plan_sha256, plan_input_ref=resolved_plan_ref,
    )
    terminal = declared_object(
        {
            "status": "GATE_BLOCK" if failed_required else "PASS",
            "code": (
                "REVIEW.EVIDENCE_TIMEOUT"
                if failed_required_timed_out
                else "REVIEW.EVIDENCE_FAILED"
                if failed_required
                else "EVIDENCE.PASSED"
            ),
            "failed_evidence": failed_required,
        },
        "named_evidence_receipt",
        "terminal_fields",
    )
    resolved_run_id = run_id or uuid.uuid4().hex
    if not resolved_run_id or "/" in resolved_run_id or resolved_run_id in {".", ".."}:
        raise EvidenceRunnerError("run_id 必须为单一安全 path segment")
    receipt = {
        "schema_version": contract_schema_version("named_evidence_receipt"),
        "run_id": resolved_run_id,
        "generation_id": result_fingerprint["digest"],
        "plan_fingerprint_ref": plan_receipt["ref"],
        "plan_fingerprint_digest": plan_receipt["digest"],
        "source": source,
        "evidence_class": evidence_class,
        "admission_eligible": admission_eligible,
        "execution_fingerprint": execution_fingerprint,
        "result_fingerprint": result_fingerprint,
        "evidence": results,
        "terminal": terminal,
        "captured_by": captured_by,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    validate_named_evidence_receipt(receipt)
    return receipt


def validate_named_evidence_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    if receipt.get("schema_version") != contract_schema_version(
        "named_evidence_receipt"
    ):
        raise EvidenceRunnerError(
            "IDENTITY.MIGRATION_REQUIRED: named evidence receipt schema_version 非法"
        )
    try:
        validate_required_fields(receipt, "named_evidence_receipt")
    except ValueError as exc:
        raise EvidenceRunnerError(
            f"IDENTITY.MIGRATION_REQUIRED: named evidence receipt 字段非法: {exc}"
        ) from exc
    source = receipt["source"]
    if not isinstance(source, dict):
        raise EvidenceRunnerError("named evidence source 必须为 mapping")
    _validate_source(source)
    evidence_class, admission_eligible = _evidence_classification(source)
    if receipt["evidence_class"] != evidence_class or receipt["admission_eligible"] is not admission_eligible:
        raise EvidenceRunnerError("named evidence evidence_class/admission_eligible 与 source classification 不一致")
    if receipt["evidence_class"] not in {"feedback_only", "reusable"}:
        raise EvidenceRunnerError("named evidence evidence_class 非法")
    for item in receipt["evidence"]:
        if not isinstance(item, dict):
            raise EvidenceRunnerError("named evidence result 必须为 mapping")
        validate_declared_fields(
            item, "named_evidence_receipt", "evidence_result_fields"
        )
    terminal = receipt["terminal"]
    if not isinstance(terminal, dict):
        raise EvidenceRunnerError("named evidence terminal 必须为 mapping")
    validate_declared_fields(
        terminal, "named_evidence_receipt", "terminal_fields"
    )
    execution = validate_evidence_fingerprint(receipt["execution_fingerprint"])
    result = validate_evidence_fingerprint(receipt["result_fingerprint"])
    if receipt.get("generation_id") != result["digest"]:
        raise EvidenceRunnerError(
            "named evidence generation_id 与 result fingerprint digest 不一致"
        )
    if execution["digest_payload"]["workspace"] != result["digest_payload"]["workspace"]:
        raise EvidenceRunnerError("REVIEW.FINGERPRINT_CHANGED: evidence receipt workspace stale")
    expected_git = {"head_sha": source["head_sha"], "merge_base_sha": source["merge_base_sha"]}
    if execution["digest_payload"]["git"] != expected_git or result["digest_payload"]["git"] != expected_git:
        raise EvidenceRunnerError("named evidence source Git identity 与 fingerprint 不一致")
    return receipt


def _output_path(run_id: str) -> Path:
    if not run_id or "/" in run_id or run_id in {".", ".."}:
        raise EvidenceRunnerError("run-id 必须为单一安全 path segment")
    return OUTPUT_ROOT / run_id / "receipt.json"


def _write_receipt_create_once(run_id: str, receipt: dict[str, Any]) -> Path:
    path = _output_path(run_id)
    try:
        return write_create_once_json(path, receipt)
    except ReadinessCaseResultError as exc:
        raise EvidenceRunnerError(
            f"run-id={run_id} evidence receipt create-once conflict: {exc}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-mode", choices=("workspace",), default="workspace")
    args = parser.parse_args(argv)
    try:
        try:
            plan_ref = normalize_repo_relative_path(args.plan, ROOT)
            plan_bytes = read_repo_relative_regular_single_link(ROOT, plan_ref)
        except (OSError, ValueError) as exc:
            raise EvidenceRunnerError(
                f"--plan 必须为仓内非 symlink、single-link regular file: {exc}"
            ) from exc
        plan = json.loads(plan_bytes.decode("utf-8"))
        if not isinstance(plan, dict):
            raise EvidenceRunnerError("plan 必须为 JSON object")
        import yaml

        registry_path = ROOT / ".agents/skills/review/references/registry.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        receipt = run_plan(
            plan, registry=registry, run_id=args.run_id,
            plan_bytes=plan_bytes, plan_ref=plan_ref,
        )
        path = _write_receipt_create_once(args.run_id, receipt)
    except (OSError, json.JSONDecodeError, EvidenceRunnerError, ReadinessCaseResultError, TypeError, ValueError) as exc:
        print(f"[evidence_runner] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(path.relative_to(ROOT))
    return 1 if receipt["terminal"]["status"] == "GATE_BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
