#!/usr/bin/env python3
"""Execute one Review plan's named evidence once and emit canonical receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
import sys
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
    snapshot_path,
    validate_evidence_fingerprint,
    validate_ref,
    workspace_digests,
)
import review_dispatch as review_dispatch_module  # noqa: E402

OUTPUT_ROOT = ROOT / ".qwq_output/env/repo/runs/review-evidence"


class EvidenceRunnerError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _command_digest(command: str) -> str:
    return _sha256_bytes(command.encode("utf-8"))


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise EvidenceRunnerError("无法读取 source HEAD")
    return result.stdout.strip()


def _managed_paths(plan: dict[str, Any]) -> list[str]:
    paths = list(plan.get("changed_paths") or [])
    paths.extend(
        str(item.get("path") or "")
        for item in (plan.get("contexts") or [])
        if isinstance(item, dict) and item.get("path")
    )
    return sorted(set(paths))


def _fingerprint(
    *,
    plan: dict[str, Any],
    evidence: list[dict[str, Any]],
    results: list[dict[str, Any]],
    phase: str,
    registry: dict[str, Any],
) -> dict[str, Any]:
    current_plan = review_dispatch_module.recompute_plan_fingerprint(plan, registry)
    payload = current_plan["digest_payload"]
    generator = snapshot_path(Path(__file__).relative_to(ROOT), repo_root=ROOT)
    return build_evidence_fingerprint(
        {
            "git": dict(payload["git"]),
            "workspace": workspace_digests(_managed_paths(plan), repo_root=ROOT),
            "assets": {
                "canonical_assets_digest": canonical_digest(
                    {
                        "plan_ref": current_plan["ref"],
                        "evidence": [
                            {
                                "id": item["id"],
                                "command_digest": item["command_digest"],
                                "required": item["required"],
                            }
                            for item in evidence
                        ],
                    }
                ),
                "review_assets_digest": canonical_digest(
                    {
                        "plan_assets": payload["assets"],
                        "results": results,
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
                        "runner": "subprocess.run-shell-false",
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
        captured_metadata={"phase": phase},
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


def run_plan(
    plan: dict[str, Any],
    *,
    run_id: str | None = None,
    captured_by: str = "evidence_runner",
    cwd: Path = ROOT,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if registry is None:
        raise EvidenceRunnerError("registry 为 canonical evidence 执行必填输入")
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
        if registry is not None:
            registered = (registry.get("evidence") or {}).get(evidence_id)
            if not isinstance(registered, dict):
                raise EvidenceRunnerError(f"evidence={evidence_id} 不在 registry")
            registered_command = registered.get("command")
            if registered_command != command:
                raise EvidenceRunnerError(
                    f"evidence={evidence_id} command 与 registry 解析结果不一致"
                )
            registered_digest = _command_digest(str(registered_command))
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
            }
        )

    started_at = _now()
    execution_fingerprint = _fingerprint(
        plan=plan,
        evidence=evidence,
        results=[],
        phase="execution_input",
        registry=registry,
    )
    results: list[dict[str, Any]] = []
    failed_required: str | None = None
    for item in evidence:
        item_started = _now()
        # The exact registry-resolved command string is passed as one /bin/sh -c
        # argument only after its digest has been verified; no interpolation occurs here.
        completed = subprocess.run(
            ["/bin/sh", "-c", item["command"]],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
        item_finished = _now()
        results.append(
            declared_object(
                {
                    "id": item["id"],
                    "command": item["command"],
                    "command_digest": item["command_digest"],
                    "exit_code": completed.returncode,
                    "stdout_digest": _sha256_bytes(completed.stdout),
                    "stderr_digest": _sha256_bytes(completed.stderr),
                    "started_at": item_started,
                    "finished_at": item_finished,
                    "captured_by": captured_by,
                    "required": item["required"],
                },
                "named_evidence_receipt",
                "evidence_result_fields",
            )
        )
        post_command = _fingerprint(
            plan=plan,
            evidence=evidence,
            results=[],
            phase="post_command",
            registry=registry,
        )
        _assert_same_fingerprint(
            execution_fingerprint, post_command, phase=f"after {item['id']}"
        )
        if completed.returncode != 0 and item["required"]:
            failed_required = item["id"]
            break

    finished_at = _now()
    final_input = _fingerprint(
        plan=plan,
        evidence=evidence,
        results=[],
        phase="final_input",
        registry=registry,
    )
    _assert_same_fingerprint(execution_fingerprint, final_input, phase="final")
    result_fingerprint = _fingerprint(
        plan=plan,
        evidence=evidence,
        results=results,
        phase="execution_result",
        registry=registry,
    )
    terminal = declared_object(
        {
            "status": "GATE_BLOCK" if failed_required else "PASS",
            "code": "REVIEW.EVIDENCE_FAILED" if failed_required else "EVIDENCE.PASSED",
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
    validate_required_fields(receipt, "named_evidence_receipt")
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
    if execution["digest_payload"]["workspace"] != result["digest_payload"]["workspace"]:
        raise EvidenceRunnerError("REVIEW.FINGERPRINT_CHANGED: evidence receipt workspace stale")
    return receipt


def _output_path(run_id: str) -> Path:
    if not run_id or "/" in run_id or run_id in {".", ".."}:
        raise EvidenceRunnerError("run-id 必须为单一安全 path segment")
    return OUTPUT_ROOT / run_id / "receipt.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise EvidenceRunnerError("plan 必须为 JSON object")
        import yaml

        registry_path = ROOT / ".agents/skills/review/references/registry.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        receipt = run_plan(plan, registry=registry, run_id=args.run_id)
        path = _output_path(args.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, EvidenceRunnerError, TypeError, ValueError) as exc:
        print(f"[evidence_runner] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(path.relative_to(ROOT))
    return 1 if receipt["terminal"]["status"] == "GATE_BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
