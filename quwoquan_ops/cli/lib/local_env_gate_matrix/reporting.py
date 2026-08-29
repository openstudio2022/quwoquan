"""矩阵结果 CaseResult / Markdown 落盘与 claim 计算（自原单文件逐字搬移）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 测试通过 mock.patch.object(matrix_mod, "write_timing_bundle") 拦截 timing 写出；
# 保持包属性延迟访问以兼容 monkeypatch。
import quwoquan_ops.cli.lib.local_env_gate_matrix as _matrix_pkg
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    CANONICAL_TARGETS,
    DEVICE_PROFILE_EMULATOR_ONLY,
    EMULATOR_ONLY_CLAIM,
    PROFILE_LOCAL_ENV_GATE,
    SPEC_REFS,
    _SHA256,
    _evidence_path,
)
from quwoquan_ops.cli.lib.local_env_gate_timing import utc_now


def _write_matrix_result(
    *,
    matrix_dir: Path,
    phases: list[dict[str, Any]],
    environments: dict[str, Any],
    budgets: dict[str, Any],
    wall_seconds: float,
    exit_code: int,
    failure_category: str,
    release_train_id: str,
    package_baselines: dict[str, str],
    release: dict[str, str],
    matrix_run_id: str,
    execution_class: str,
    device_profile: str,
) -> dict[str, Any]:
    identity_complete = (
        _SHA256.fullmatch(release_train_id) is not None
        and set(package_baselines) == set(CANONICAL_TARGETS)
        and all(
            _SHA256.fullmatch(str(package_baselines[target] or "")) is not None
            for target in CANONICAL_TARGETS
        )
    )
    passed = (
        exit_code == 0
        and tuple(environments) == CANONICAL_TARGETS
        and identity_complete
    )
    effective_failure_category = failure_category or (
        "" if identity_complete else "receipt_identity"
    )
    live_evidence = execution_class == "live"
    claim = (
        EMULATOR_ONLY_CLAIM
        if passed and live_evidence and device_profile == DEVICE_PROFILE_EMULATOR_ONLY
        else "ALPHA_BETA_GAMMA_LOCAL_GREEN"
        if passed and live_evidence
        else "CONTRACT_SIMULATION_PASSED"
        if passed
        else "GATE_BLOCK"
    )
    status = "passed" if passed else "gate_block"
    executed = len(phases)
    skipped = 0
    timing_path = _matrix_pkg.write_timing_bundle(
        matrix_dir,
        phases=phases,
        wall_clock_seconds=wall_seconds,
        budgets=budgets,
        claim=claim,
        cache_mode="package-bound",
        extras={
            "failureCategory": effective_failure_category,
            "targets": list(CANONICAL_TARGETS),
            "executed": executed,
            "skipped": skipped,
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
            "deviceProfile": device_profile,
            "nonPromotable": device_profile == DEVICE_PROFILE_EMULATOR_ONLY,
        },
    )
    payload = {
        "schema": "quwoquan.test.case-result",
        "generatedAt": utc_now(),
        "caseId": "stackctl.local-env-gate.alpha-beta-gamma",
        "status": status,
        "claim": claim,
        "executed": executed,
        "skipped": skipped,
        "specRefs": list(SPEC_REFS),
        "targets": list(CANONICAL_TARGETS),
        "wallClockSeconds": round(wall_seconds, 3),
        "softBudgetSeconds": budgets["softBudgetSeconds"],
        "hardBudgetSeconds": budgets["hardBudgetSeconds"],
        "failureCategory": effective_failure_category,
        "matrixRunId": matrix_run_id,
        "executionClass": execution_class,
        "deviceProfile": device_profile,
        "releaseTrainId": release_train_id,
        "packageBaselines": {
            target: str(package_baselines.get(target) or "")
            for target in CANONICAL_TARGETS
            if str(package_baselines.get(target) or "")
        },
        "releaseId": release.get("releaseId", ""),
        "releaseDigest": release.get("releaseDigest", ""),
        "timingPath": _evidence_path(timing_path),
        "phases": phases,
        "environments": environments,
    }
    if device_profile == DEVICE_PROFILE_EMULATOR_ONLY:
        payload["nonPromotable"] = True
        payload["deviceCoverage"] = [
            "ios-simulator",
            "android-emulator",
        ]
        payload["waivers"] = [
            {
                "scope": "android-physical-device",
                "effect": "release-promotion-blocked",
                "reason": "emulator_only execution profile",
            }
        ]
    (matrix_dir / "matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (matrix_dir / "matrix.md").write_text(
        "\n".join(
            [
                "# Alpha / Beta / Gamma local gate",
                "",
                f"- status: `{status}`",
                f"- claim: `{claim}`",
                f"- executed/skipped: `{executed}/{skipped}`",
                f"- failureCategory: `{effective_failure_category or 'none'}`",
                f"- releaseTrainId: `{release_train_id or 'missing'}`",
                "- packageBaselines: `"
                + json.dumps(
                    payload["packageBaselines"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                f"- timing: `{_evidence_path(timing_path)}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "exitCode": 0 if passed else (exit_code or 2),
        "summary": f"stackctl matrix {PROFILE_LOCAL_ENV_GATE}: {claim}",
        "details": [
            f"status={status}",
            f"executed={executed}",
            f"skipped={skipped}",
            f"timing={_evidence_path(timing_path)}",
            f"failureCategory={effective_failure_category or 'none'}",
            f"deviceProfile={device_profile}",
        ],
        "reportDir": _evidence_path(matrix_dir),
        "claim": claim,
        "status": status,
        "executed": executed,
        "skipped": skipped,
        "wallClockSeconds": round(wall_seconds, 3),
        "releaseTrainId": release_train_id,
        "packageBaselines": dict(payload["packageBaselines"]),
    }
