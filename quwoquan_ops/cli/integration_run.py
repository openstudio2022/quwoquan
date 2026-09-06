#!/usr/bin/env python3
"""integration 工作区「集成验证 → 发布 dev1.0」的 canonical 编排（模式二）。

固定顺序：前置校验 → 本地 readiness（exact delta）→ build-head candidate → ImpactPlan 深度
→ environment request → Alpha（条件 Beta）package/up/health/verify/inspect/doctor/down
→ 证据 canonical 化 → EnvironmentAcceptanceFact → admit → publish（可选）→ summary。

只编排、不解释结论：环境动作一律经 `stackctl` 子进程，事实一律经
`quwoquan_ops.ci.scoped_candidate` / `environment_scheduler` 既有 create-once 入口。
任一步失败即保留首个 typed blocker 并把已启动的本地 runtime 放倒（finally down）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from quwoquan_ops.ci.environment_scheduler import (
    EnvironmentSchedulerError,
    append_task_state,
    create_execution_request,
    exact_file_digest,
    issue_environment_acceptance_fact,
    request_exact_ref,
)
from quwoquan_ops.ci.impact_planner_core import (
    build_delivery_impact_plan,
    classify_impacts,
)
from quwoquan_ops.ci.scoped_candidate import (
    ScopedCandidateError,
    build_head_candidate,
    create_publish_admission,
    create_source_fact,
    local_git_cas_publish,
    release_claim,
    store_ref,
    store_root,
)
from quwoquan_ops.cli.lib.content_api_consumer_authority import (
    _runtime_authority,
)
from quwoquan_ops.cli.lib.evidence_signing import (
    DEFAULT_KEYRING_PATH,
    EvidenceSigningError,
    ed25519_signer,
    key_root,
    load_keyring,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    write_readiness_case_result,
)

POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
LOCAL_READINESS = ROOT / "quwoquan_ops/cli/local_readiness.py"
OUTPUT_ROOT = ROOT / ".qwq_output"
RUNS_ROOT = OUTPUT_ROOT / "env/repo/runs/integrate"
DEV_REF = "refs/heads/dev1.0"
NO_LIVE = "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED"
ENVIRONMENT_SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
DEFAULT_SIGNER = "quwoquan-environment-ops-local"


class IntegrationRunError(RuntimeError):
    """Typed blocker; the summary keeps the first one."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise IntegrationRunError("INTEGRATION_RUN.GIT", f"git {' '.join(args)}: {' '.join((completed.stderr or completed.stdout).split())}")
    return completed.stdout.strip()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _write_canonical(path: Path, value: Mapping[str, Any]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise IntegrationRunError("INTEGRATION_RUN.CREATE_CONFLICT", f"evidence slot already exists: {path}")
    path.write_bytes(_canonical_bytes(value) + b"\n")
    return {"ref": path.relative_to(_store()).as_posix(), "digest": exact_file_digest(path)}


def _store() -> Path:
    return store_root(repository=ROOT, policy_path=POLICY)


def _output_ref(path: Path) -> str:
    return path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()


class Phases:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def run(self, name: str, fn: Any) -> Any:
        started = time.monotonic()
        started_at = _now()
        status = "passed"
        try:
            return fn()
        except BaseException:
            status = "failed"
            raise
        finally:
            self.items.append({
                "name": name, "status": status, "startedAt": started_at, "endedAt": _now(),
                "durationSeconds": round(time.monotonic() - started, 3),
            })


class StackctlResult:
    def __init__(self, command: str, payload: Mapping[str, Any], stderr: str) -> None:
        self.command = command
        self.payload = dict(payload)
        self.stderr = stderr

    @property
    def exit_code(self) -> int:
        value = self.payload.get("exitCode")
        return int(value) if isinstance(value, int) else 1

    @property
    def report_dir(self) -> Path | None:
        value = self.payload.get("reportDir")
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else ROOT / path

    def report_json(self) -> tuple[Path, dict[str, Any]] | None:
        report_dir = self.report_dir
        if report_dir is None:
            return None
        report = report_dir / "report.json"
        if not report.is_file():
            return None
        return report, json.loads(report.read_text(encoding="utf-8"))


def _stackctl(*args: str, env: Mapping[str, str] | None = None, log_dir: Path) -> StackctlResult:
    command = " ".join(args)
    process_env = dict(os.environ)
    process_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        process_env.update(env)
    completed = subprocess.run(
        [sys.executable, "-B", str(STACKCTL), "--output-format", "json", *args],
        cwd=ROOT, env=process_env, text=True, capture_output=True, check=False,
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    slug = "-".join(part.strip("-") for part in args[:3]).replace("/", "_")
    (log_dir / f"stackctl-{slug}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    (log_dir / f"stackctl-{slug}.stdout.json").write_text(completed.stdout, encoding="utf-8")
    payload: dict[str, Any]
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if "exitCode" not in payload:
        payload["exitCode"] = completed.returncode
    return StackctlResult(command, payload, completed.stderr)


DATA_CLI = ROOT / "quwoquan_data/scripts/cli.py"


def _release_id(attestation: Path) -> tuple[str, str]:
    payload = json.loads(attestation.read_text(encoding="utf-8"))
    release_id, release_class = str(payload.get("releaseId") or ""), str(payload.get("releaseClass") or "")
    if not release_id or release_class not in {"research", "commercial"}:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"{attestation} is not a canonical release attestation")
    local = OUTPUT_ROOT / "data/releases" / release_id / "attestations/release.json"
    if not local.is_file() or local.read_bytes() != attestation.read_bytes():
        raise IntegrationRunError(
            "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE",
            f"immutable release {release_id} is absent from {OUTPUT_ROOT / 'data/releases'} or its attestation differs; "
            "ship apply only executes releases present in this worktree's Data root",
        )
    return release_id, release_class


def _data_ship(*args: str, log_dir: Path, label: str) -> None:
    """Data release 进入环境只经 canonical `qwq-data ship`；失败保留 stdout/stderr 作为 typed blocker。"""

    process_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(DATA_CLI), "ship", *args],
        cwd=ROOT, env=process_env, text=True, capture_output=True, check=False,
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"data-ship-{label}.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (log_dir / f"data-ship-{label}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        tail = " ".join((completed.stderr or completed.stdout).split())[-400:]
        raise IntegrationRunError("INTEGRATION_RUN.DATA_RELEASE_FAILED", f"qwq-data ship {label} failed: {tail}")


def _apply_data_release(*, environment: str, run_id: str, args: argparse.Namespace, log_dir: Path,
                        previous_readiness: Path | None) -> Path:
    """candidate release：apply --import --full-sync → verify（research/commercial 按 attestation）；返回 readiness 回执。"""

    release_id, release_class = _release_id(args.release_attestation)
    import_run, verify_run = f"{run_id}-import", f"{run_id}-verify"
    _data_ship("apply", "--release-id", release_id, "--env", environment, "--run-id", import_run,
               "--import", "--full-sync", log_dir=log_dir, label=f"{environment}-apply")
    verify_args = ["verify", "--release-id", release_id, "--env", environment, "--import-run-id", import_run,
                   "--run-id", verify_run, "--readiness-phase", release_class]
    if previous_readiness is not None:
        verify_args.extend(["--previous-environment-readiness", _output_ref(previous_readiness)])
    _data_ship(*verify_args, log_dir=log_dir, label=f"{environment}-verify")
    readiness = OUTPUT_ROOT / "env" / environment / "runs/data-release" / release_id / verify_run / "release-readiness.json"
    if not readiness.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.DATA_RELEASE_FAILED", f"release readiness receipt missing: {readiness}")
    return readiness


def _require_ok(result: StackctlResult, code: str) -> StackctlResult:
    if result.exit_code != 0:
        summary = str(result.payload.get("summary") or "").strip()
        details = result.payload.get("details")
        first = ""
        if isinstance(details, list) and details:
            first = str(details[0])
        raise IntegrationRunError(code, f"stackctl {result.command}: {summary or first or result.stderr[-400:]}")
    return result


def _impact_plan(*, parent: str, commit: str, run_dir: Path) -> tuple[dict[str, Any], Path]:
    changed = [line for line in _git("diff-tree", "--no-commit-id", "--name-only", "-r", parent, commit).splitlines() if line]
    classified = classify_impacts(changed, fail_closed_empty=True)
    tree = _git("show", "-s", "--format=%T", commit)
    plan = build_delivery_impact_plan(
        classified["paths"], source_sha=commit, base_sha=parent, head_sha=commit, synthetic_sha=commit,
        source_tree_digest=f"sha1:{tree}",
        execution_profile="manual", force_device=False, fail_closed_empty=True, required_scopes=[],
    )
    path = run_dir / "impact-plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan, path


def _local_readiness(*, level: str, parent: str, commit: str, run_dir: Path, args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    # `run` 会读取 push updates 两次（plan + run），stdin 只能读一次，所以落成文件再传路径。
    updates_path = run_dir / f"push-updates-{level}.txt"
    updates_path.write_text(f"{DEV_REF} {commit} {DEV_REF} {parent}\n", encoding="utf-8")
    command = [sys.executable, "-B", str(LOCAL_READINESS), "run", "--level", level, "--push-updates", str(updates_path)]
    if args.owner_identity:
        command += ["--owner-identity", args.owner_identity]
    if args.candidate_evidence:
        command += ["--candidate-evidence", args.candidate_evidence]
    if args.review_consolidation:
        command += ["--review-consolidation", args.review_consolidation]
    for item in args.required_evidence or []:
        command += ["--required-evidence", item]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    (run_dir / f"local-readiness-{level}.stdout.json").write_text(completed.stdout, encoding="utf-8")
    (run_dir / f"local-readiness-{level}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise IntegrationRunError("INTEGRATION_RUN.L1_UNAVAILABLE", f"local readiness produced no receipt: {completed.stderr[-400:]}") from exc
    if completed.returncode != 0 or receipt.get("status") != "PASS":
        failed = [item.get("id") for item in receipt.get("results", []) if item.get("status") != "PASS"]
        raise IntegrationRunError("INTEGRATION_RUN.L1_FAILED", f"local readiness {level} did not pass: {failed[:5] or completed.stderr[-300:]}")
    digest = str(receipt.get("fingerprint", {}).get("digest", "")).removeprefix("sha256:")
    receipt_path = OUTPUT_ROOT / "env/repo/local/local-readiness/process/receipts/by-fingerprint" / f"{digest}.json"
    if not receipt_path.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.L1_UNAVAILABLE", f"readiness receipt is missing: {receipt_path}")
    return receipt_path, receipt


def _evidence_object(*, role: str, status: str, environment: str, profile: str, candidate: Mapping[str, str],
                     impact_plan_digest: str, source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"quwoquan_ops.environment_{role}.v1", "role": role, "status": status,
        "environment": environment, "profile": profile,
        "candidateId": candidate["candidateId"], "commit": candidate["commit"], "tree": candidate["tree"],
        "impactPlanDigest": impact_plan_digest, "source": dict(source), "recordedAt": _now(),
    }


def _report_source(result: StackctlResult) -> dict[str, Any]:
    report = result.report_json()
    if report is None:
        return {"command": result.command, "exitCode": result.exit_code}
    path, _ = report
    return {"command": result.command, "exitCode": result.exit_code, "reportRef": _output_ref(path), "reportDigest": exact_file_digest(path)}


def _case_results_from_verify(*, verify: StackctlResult, environment: str, profile: str, candidate: Mapping[str, str],
                              runtime: Mapping[str, str], evidence_dir: Path) -> list[dict[str, str]]:
    report = verify.report_json()
    if report is None:
        raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_MISSING", "stackctl verify produced no report.json")
    path, payload = report
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_MISSING", "stackctl verify report has no checks")
    report_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    started = str(payload.get("startedAt") or _now())
    completed = str(payload.get("endedAt") or _now())
    refs: list[dict[str, str]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, Mapping):
            raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_INVALID", f"check[{index}] is not an object")
        name = str(check.get("name") or check.get("id") or f"check-{index}")
        if check.get("skipped") is True:
            continue
        if check.get("ok") is not True:
            raise IntegrationRunError("INTEGRATION_RUN.VERIFY_FAILED", f"{environment} verify check failed: {name}: {str(check.get('bodyPreview') or '')[:200]}")
        result = {
            "objectId": f"stackctl-verify:{environment}:{name}",
            "specRef": str(check.get("specRef") or ENVIRONMENT_SPEC_REF),
            "caseId": f"verify:{profile}:{environment}:{name}",
            "producer": "ops",
            "layer": "environment_acceptance",
            "status": "passed",
            "target": {"kind": "operation", "id": name},
            "commitSha": runtime["commitSha"],
            "contractGraphSourceHash": runtime["contractGraphSourceHash"],
            "deploymentTarget": f"{environment}-local",
            "baselineId": runtime["baselineId"],
            "packageDigest": runtime["packageDigest"],
            "configurationDigest": runtime["configurationDigest"],
            "candidateManifestSha256": runtime["candidateManifestSha256"],
            "candidateDigest": candidate["candidateId"],
            "environment": environment,
            "provider": "first-party-https",
            "startedAt": started,
            "completedAt": completed,
            "runnerIdentity": "integration-run",
            "artifactSha256": report_sha,
            "receiptRef": _output_ref(path),
        }
        case_path = evidence_dir / "cases" / f"{index:03d}.json"
        case_path.parent.mkdir(parents=True, exist_ok=True)
        write_readiness_case_result(case_path, result, generated_at=completed)
        refs.append({"ref": case_path.relative_to(_store()).as_posix(), "digest": exact_file_digest(case_path)})
    if not refs:
        raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_INVALID", "verify report contains only skipped checks")
    return refs


def _health_runtime(*, health: StackctlResult, environment: str, candidate: Mapping[str, str], expected_baseline: str) -> dict[str, str]:
    report = health.report_json()
    if report is None:
        raise IntegrationRunError("INTEGRATION_RUN.HEALTH_REPORT_MISSING", "stackctl health produced no report.json")
    _, payload = report
    try:
        runtime = _runtime_authority(payload, target=f"{environment}-local")
    except Exception as exc:
        raise IntegrationRunError("INTEGRATION_RUN.RUNTIME_IDENTITY_INVALID", str(exc)) from exc
    if runtime["commitSha"] != candidate["commit"]:
        raise IntegrationRunError(
            "INTEGRATION_RUN.RUNTIME_IDENTITY_INVALID",
            f"{environment} runtime sourceRevision {runtime['commitSha']} != candidate {candidate['commit']}",
        )
    if runtime["baselineId"] != expected_baseline.removeprefix("sha256:"):
        raise IntegrationRunError("INTEGRATION_RUN.RUNTIME_IDENTITY_INVALID", f"{environment} active baseline drifted from freshly packaged candidate")
    return runtime


def _run_environment(*, environment: str, profile: str, candidate: Mapping[str, str], impact_plan_digest: str,
                     args: argparse.Namespace, run_dir: Path, phases: Phases, summary: dict[str, Any],
                     previous_readiness: Path | None = None) -> dict[str, Any]:
    target = f"{environment}-local"
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / environment
    log_dir = run_dir / environment
    env_summary: dict[str, Any] = {"environment": environment, "target": target, "reports": {}}
    summary["environments"][environment] = env_summary
    started_up = False
    try:
        package = phases.run(f"{environment}.package", lambda: _require_ok(_stackctl(
            "package", "--env", environment, "--include-services",
            "--release-attestation", str(args.release_attestation),
            "--rollback-release-attestation", str(args.rollback_release_attestation), log_dir=log_dir,
        ), "INTEGRATION_RUN.PACKAGE_FAILED"))
        env_summary["reports"]["package"] = _report_source(package)
        active_path = Path(os.environ.get("QWQ_DEPLOY_WORK_ROOT", str(Path.home() / ".cache/quwoquan/deploy"))) / target / "active-runtime-candidate.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        baseline = str(active.get("baselineId") or "")
        manifest = json.loads((Path(str(active["candidateDir"])) / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("sourceRevision") != candidate["commit"]:
            raise IntegrationRunError("INTEGRATION_RUN.PACKAGE_IDENTITY_INVALID", f"packaged sourceRevision {manifest.get('sourceRevision')} != candidate {candidate['commit']}")
        env_summary["package"] = {"baselineId": baseline, "sourceRevision": manifest.get("sourceRevision"), "packageDigest": manifest.get("packageDigest"), "imageDigest": manifest.get("imageDigest")}

        up = phases.run(f"{environment}.up", lambda: _stackctl("up", "--target", target, "--skip-app", "--workload", args.workload, log_dir=log_dir))
        started_up = True
        _require_ok(up, "INTEGRATION_RUN.UP_FAILED")
        env_summary["reports"]["up"] = _report_source(up)
        # health 的 release_active 层要求该环境已导入并验证 candidate Data release（release-readiness 回执）。
        readiness = phases.run(f"{environment}.data-release", lambda: _apply_data_release(
            environment=environment, run_id=summary["runId"], args=args, log_dir=log_dir, previous_readiness=previous_readiness,
        ))
        env_summary["dataRelease"] = {"readiness": _output_ref(readiness), "digest": exact_file_digest(readiness)}
        health = phases.run(f"{environment}.health", lambda: _require_ok(_stackctl("health", "--target", target, "--scope", "full", log_dir=log_dir), "INTEGRATION_RUN.HEALTH_FAILED"))
        env_summary["reports"]["health"] = _report_source(health)
        runtime = _health_runtime(health=health, environment=environment, candidate=candidate, expected_baseline=baseline)
        env_summary["runtimeIdentity"] = runtime
        verify = phases.run(f"{environment}.verify", lambda: _require_ok(_stackctl("verify", "--env", environment, "--target", target, "--kind", "all", "--profile", profile, log_dir=log_dir), "INTEGRATION_RUN.VERIFY_FAILED"))
        env_summary["reports"]["verify"] = _report_source(verify)
        inspect = phases.run(f"{environment}.inspect", lambda: _require_ok(_stackctl("inspect", "--target", target, "--scope", "all", log_dir=log_dir), "INTEGRATION_RUN.INSPECT_FAILED"))
        env_summary["reports"]["inspect"] = _report_source(inspect)
        doctor = phases.run(f"{environment}.doctor", lambda: _require_ok(_stackctl("doctor", "--target", target, log_dir=log_dir), "INTEGRATION_RUN.DOCTOR_FAILED"))
        env_summary["reports"]["doctor"] = _report_source(doctor)
        health_payload = health.report_json()[1]  # type: ignore[index]
        provider_ok = _provider_ready(health_payload)
    finally:
        if started_up:
            down = phases.run(f"{environment}.down", lambda: _stackctl("down", "--target", target, "--workload", args.workload, log_dir=log_dir))
            env_summary["reports"]["down"] = _report_source(down)
            if down.exit_code != 0:
                raise IntegrationRunError("INTEGRATION_RUN.DOWN_FAILED", f"stackctl down {target} failed: {down.payload.get('summary')}")
    status_after = phases.run(f"{environment}.lease-readback", lambda: _stackctl("status", "--target", target, log_dir=log_dir))
    locks = status_after.payload.get("localRuntimeLocks")
    if locks not in ([], None):
        raise IntegrationRunError("INTEGRATION_RUN.LEASE_OPEN", f"{target} still holds runtime locks after down: {locks}")
    env_summary["reports"]["leaseReadback"] = _report_source(status_after)
    if not provider_ok:
        raise IntegrationRunError("INTEGRATION_RUN.PROVIDER_NOT_READY", f"{environment} provider composition is not ready in health evidence")

    def evidence(role: str, status: str, source: StackctlResult) -> dict[str, str]:
        return _write_canonical(evidence_dir / f"{role}.json", _evidence_object(
            role=role, status=status, environment=environment, profile=profile, candidate=candidate,
            impact_plan_digest=impact_plan_digest, source=_report_source(source),
        ))

    named = {
        "runtime_identity": evidence("runtime-identity", "ready", health),
        "data_lifecycle": evidence("data-lifecycle", "closed", down),
        "provider_readiness": evidence("provider-readiness", "ready", health),
        "observability_readiness": evidence("observability-readiness", "ready", inspect),
        "inspect_evidence": evidence("inspect", "passed", inspect),
        "doctor_evidence": evidence("doctor", "passed", doctor),
        "cleanup_evidence": evidence("cleanup", "closed", down),
        "lease_closure_evidence": evidence("lease-closure", "released", status_after),
    }
    cases = _case_results_from_verify(verify=verify, environment=environment, profile=profile, candidate=candidate, runtime=runtime, evidence_dir=evidence_dir)
    env_summary["caseResults"] = len(cases)
    return {"named": named, "cases": cases, "readiness": readiness}


def _provider_ready(health_payload: Mapping[str, Any]) -> bool:
    report = health_payload.get("userAvailabilityReport")
    if not isinstance(report, Mapping):
        return False
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    provider = evidence.get("providerComposition")
    if isinstance(provider, Mapping):
        return provider.get("status") in {"ready", "ok", "passed", "healthy", "available"} or not provider.get("issues")
    return True


def _not_required_beta(*, candidate: Mapping[str, str], impact_plan_digest: str, impact_plan_path: Path, profile: str) -> dict[str, Any]:
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / "beta"
    plan_sha = hashlib.sha256(impact_plan_path.read_bytes()).hexdigest()
    source = {"basis": NO_LIVE, "executed": False, "impactPlanRef": _output_ref(impact_plan_path), "impactPlanSha256": plan_sha}

    def evidence(role: str, status: str) -> dict[str, str]:
        return _write_canonical(evidence_dir / f"{role}.json", _evidence_object(
            role=role, status=status, environment="beta", profile=profile, candidate=candidate,
            impact_plan_digest=impact_plan_digest, source=source,
        ))

    named = {
        "runtime_identity": evidence("runtime-identity", "ready"),
        "data_lifecycle": evidence("data-lifecycle", "closed"),
        "provider_readiness": evidence("provider-readiness", "ready"),
        "observability_readiness": evidence("observability-readiness", "ready"),
        "inspect_evidence": evidence("inspect", "passed"),
        "doctor_evidence": evidence("doctor", "passed"),
        "cleanup_evidence": evidence("cleanup", "closed"),
        "lease_closure_evidence": evidence("lease-closure", "released"),
    }
    now = _now()
    case = {
        "objectId": "impact-plan:integration-depth",
        "specRef": ENVIRONMENT_SPEC_REF,
        "caseId": "beta-depth-evaluation",
        "producer": "ops",
        "layer": "environment_acceptance",
        "status": "passed",
        "target": {"kind": "operation", "id": "derive_integration_depth"},
        "commitSha": candidate["commit"],
        "contractGraphSourceHash": plan_sha,
        "deploymentTarget": "beta-local",
        "baselineId": "impact-plan-not-required",
        "packageDigest": "sha256:" + plan_sha,
        "configurationDigest": "sha256:" + plan_sha,
        "candidateManifestSha256": plan_sha,
        "candidateDigest": candidate["candidateId"],
        "environment": "beta",
        "provider": "impact-planner",
        "startedAt": now,
        "completedAt": now,
        "runnerIdentity": "integration-run",
        "artifactSha256": plan_sha,
        "receiptRef": _output_ref(impact_plan_path),
        "reasonCode": NO_LIVE,
    }
    case_path = evidence_dir / "cases" / "000.json"
    case_path.parent.mkdir(parents=True, exist_ok=True)
    write_readiness_case_result(case_path, case, generated_at=now)
    return {"named": named, "cases": [{"ref": case_path.relative_to(store).as_posix(), "digest": exact_file_digest(case_path)}]}


def _issue(*, environment: str, candidate_ref: Mapping[str, str], impact_plan_digest: str, evidence: Mapping[str, Any],
           status: str, predecessor: Mapping[str, str] | None, profile: str, args: argparse.Namespace, signer: Any) -> dict[str, str]:
    store = _store()
    request_path = create_execution_request(
        store_root=store, candidate_ref=candidate_ref, environment=environment,
        impact_plan_digest=impact_plan_digest, priority=1,
    )
    request_ref = request_exact_ref(store, request_path)
    append_task_state(store_root=store, request_ref=request_ref, state="queued")
    if status == "passed":
        append_task_state(store_root=store, request_ref=request_ref, state="mutation_started")
    expires = (datetime.now(timezone.utc) + timedelta(hours=args.fact_ttl_hours)).isoformat().replace("+00:00", "Z")
    path = issue_environment_acceptance_fact(
        store_root=store, request_ref=request_ref, profile=profile, status=status,
        case_result_refs=evidence["cases"], predecessor=predecessor,
        signer_identity=args.signer_identity, signer=signer, expires_at=expires,
        non_promotable=False, reason_code=NO_LIVE if status == "not_required" else None,
        **evidence["named"],
    )
    acceptance = {"ref": path.relative_to(store).as_posix(), "digest": exact_file_digest(path)}
    append_task_state(store_root=store, request_ref=request_ref, state="acceptance_issued", acceptance_ref=acceptance)
    return acceptance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", default="HEAD", help="exact commit（HEAD 或 lane head sha）")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--owner-identity", default="", help="PRE owner identity manifest ref（make feature-context 输出）")
    parser.add_argument("--candidate-evidence", default="")
    parser.add_argument("--review-consolidation", default="")
    parser.add_argument("--required-evidence", action="append", default=[])
    parser.add_argument("--readiness-level", choices=("fast", "scope"), default="fast",
                        help="fast=exact delta 静态+聚焦（deferred 允许，L2 在 Gamma 前补齐）；scope 需 Review consolidation 输入")
    parser.add_argument("--release-attestation", type=Path, required=True)
    parser.add_argument("--rollback-release-attestation", type=Path, required=True)
    parser.add_argument("--workload", default="full", choices=("content-release", "content-commercial", "full"))
    parser.add_argument("--profile", default="integration", choices=("smoke", "integration"))
    parser.add_argument("--signer-identity", default=DEFAULT_SIGNER)
    parser.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH,
                        help="仓内 Ed25519 公钥 keyring；私钥来自仓外 QWQ_EVIDENCE_SIGNING_KEY_ROOT")
    parser.add_argument("--fact-ttl-hours", type=int, default=72)
    parser.add_argument("--writer", default="integration")
    parser.add_argument("--publish", action="store_true", help="admit 后以 local-git CAS 发布到远端 dev1.0")
    parser.add_argument("--run-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    phases = Phases()
    summary: dict[str, Any] = {
        "schema": "quwoquan_ops.integration_run_summary.v1", "runId": run_id, "startedAt": _now(),
        "terminal": "running", "environments": {}, "phases": phases.items,
    }
    detached = False
    original_branch = None
    claim_path: Path | None = None
    try:
        try:
            signer = ed25519_signer(args.signer_identity, root=key_root(), keyring=load_keyring(args.signing_keyring))
        except EvidenceSigningError as exc:
            raise IntegrationRunError(
                "INTEGRATION_RUN.SIGNER_UNREGISTERED" if exc.code == "EVIDENCE_SIGNING.SIGNER_UNREGISTERED" else "INTEGRATION_RUN.SIGNER_UNAVAILABLE",
                exc.detail,
            ) from exc
        for label, path in (("release", args.release_attestation), ("rollback", args.rollback_release_attestation)):
            if not path.is_file():
                raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"{label} attestation is not a file: {path}")
        release_ids = {_release_id(args.release_attestation)[0], _release_id(args.rollback_release_attestation)[0]}
        if len(release_ids) != 2:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "release and rollback attestations must name two different releases")
        summary["dataReleases"] = sorted(release_ids)

        def preflight() -> dict[str, str]:
            if _git("status", "--porcelain", "--untracked-files=no"):
                raise IntegrationRunError("INTEGRATION_RUN.DIRTY_WORKTREE", "worktree must be clean")
            commit = _git("rev-parse", f"{args.candidate}^{{commit}}")
            parent = _git("ls-remote", args.remote, DEV_REF).split()[0]
            if commit == parent:
                raise IntegrationRunError("INTEGRATION_RUN.NOTHING_TO_INTEGRATE", "candidate equals remote dev1.0 head")
            if subprocess.run(["git", "merge-base", "--is-ancestor", parent, commit], cwd=ROOT, check=False).returncode != 0:
                raise IntegrationRunError("INTEGRATION_RUN.NOT_FAST_FORWARD", "remote dev1.0 is not an ancestor of the candidate")
            return {"commit": commit, "parent": parent, "tree": _git("show", "-s", "--format=%T", commit)}

        identity = phases.run("preflight", preflight)
        summary["candidate"] = identity
        plan, plan_path = phases.run("impact-plan", lambda: _impact_plan(parent=identity["parent"], commit=identity["commit"], run_dir=run_dir))
        depth = str(plan["integration_depth"])
        impact_digest = str(plan["plan_digest"])
        summary["impactPlan"] = {"digest": impact_digest, "integrationDepth": depth, "ref": _output_ref(plan_path), "scopes": plan["scopes"]}
        if depth == "no_live":
            summary["terminal"] = "no_live"
            summary["note"] = "ImpactPlan 判定无 runtime 影响；不产生环境事实，也不发布。"
            return 0

        receipt_path, receipt = phases.run(f"readiness-{args.readiness_level}", lambda: _local_readiness(
            level=args.readiness_level, parent=identity["parent"], commit=identity["commit"], run_dir=run_dir, args=args,
        ))
        summary["readiness"] = {"level": args.readiness_level, "receiptRef": _output_ref(receipt_path), "deferred": len(receipt.get("plan", {}).get("deferred", []))}

        expires = (datetime.now(timezone.utc) + timedelta(hours=args.fact_ttl_hours)).isoformat().replace("+00:00", "Z")
        candidate_path = phases.run("build-head", lambda: build_head_candidate(
            repository=ROOT, policy_path=POLICY, commit=identity["commit"], expected_parent=identity["parent"],
            owner_identity_ref=args.owner_identity or f"integration-run:{run_id}", impact_plan_digest=impact_digest,
            writer_id=args.writer, expires_at=expires,
        ))
        candidate_ref = store_ref(repository=ROOT, policy_path=POLICY, path=candidate_path)
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate_identity = {"candidateId": candidate["candidateId"], "commit": candidate["commit"], "tree": candidate["tree"]}
        claim_path = _store() / candidate["claimRef"]
        summary["candidate"].update({"candidateId": candidate["candidateId"], "candidateRef": candidate_ref, "claimRef": candidate["claimRef"]})

        source_path = create_source_fact(
            repository=ROOT, policy_path=POLICY, candidate_ref=candidate_ref,
            kind=f"local_readiness_{args.readiness_level}", receipt_path=receipt_path, status="passed",
        )
        source_ref = store_ref(repository=ROOT, policy_path=POLICY, path=source_path)
        summary["sourceFact"] = source_ref

        head = _git("rev-parse", "HEAD")
        if head != identity["commit"]:
            original_branch = _git("symbolic-ref", "--quiet", "HEAD")
            _git("checkout", "--quiet", "--detach", identity["commit"])
            detached = True

        alpha_evidence = _run_environment(environment="alpha", profile=args.profile, candidate=candidate_identity,
                                          impact_plan_digest=impact_digest, args=args, run_dir=run_dir, phases=phases, summary=summary)
        alpha_ref = phases.run("alpha.issue", lambda: _issue(
            environment="alpha", candidate_ref=candidate_ref, impact_plan_digest=impact_digest, evidence=alpha_evidence,
            status="passed", predecessor=None, profile=args.profile, args=args, signer=signer,
        ))
        summary["environments"]["alpha"]["acceptance"] = alpha_ref

        if depth == "abg_release_sensitive":
            beta_evidence = _run_environment(environment="beta", profile=args.profile, candidate=candidate_identity,
                                             impact_plan_digest=impact_digest, args=args, run_dir=run_dir, phases=phases, summary=summary,
                                             previous_readiness=alpha_evidence["readiness"])
            beta_status = "passed"
        else:
            beta_evidence = _not_required_beta(candidate=candidate_identity, impact_plan_digest=impact_digest, impact_plan_path=plan_path, profile=args.profile)
            beta_status = "not_required"
            summary["environments"]["beta"] = {"environment": "beta", "executed": False, "reasonCode": NO_LIVE}
        beta_ref = phases.run("beta.issue", lambda: _issue(
            environment="beta", candidate_ref=candidate_ref, impact_plan_digest=impact_digest, evidence=beta_evidence,
            status=beta_status, predecessor=alpha_ref, profile=args.profile, args=args, signer=signer,
        ))
        summary["environments"]["beta"]["acceptance"] = beta_ref

        if detached:
            _git("checkout", "--quiet", original_branch.removeprefix("refs/heads/"))
            detached = False

        admission_path = phases.run("admit", lambda: create_publish_admission(
            repository=ROOT, policy_path=POLICY, candidate_ref=candidate_ref, source_fact_refs=[source_ref],
            alpha_fact_ref=alpha_ref, beta_fact_ref=beta_ref, expected_remote_oid=identity["parent"],
        ))
        summary["admission"] = store_ref(repository=ROOT, policy_path=POLICY, path=admission_path)

        if args.publish:
            result_path = phases.run("publish", lambda: local_git_cas_publish(
                repository=ROOT, policy_path=POLICY, admission_ref=admission_path, remote=args.remote,
            ))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            summary["publish"] = {**store_ref(repository=ROOT, policy_path=POLICY, path=result_path),
                                  "beforeOid": result["beforeOid"], "afterOid": result["afterOid"], "readbackOid": result["readbackOid"]}
            summary["terminal"] = "published"
        else:
            summary["terminal"] = "admitted"
        return 0
    except (IntegrationRunError, ScopedCandidateError, EnvironmentSchedulerError) as exc:
        code = getattr(exc, "code", "INTEGRATION_RUN.BLOCKED")
        detail = getattr(exc, "detail", str(exc))
        summary["terminal"] = "GATE_BLOCK"
        summary["blocker"] = {"code": code, "detail": detail}
        return 1
    except Exception as exc:  # noqa: BLE001 - 保留首个阻断而不是伪装成功
        summary["terminal"] = "GATE_BLOCK"
        summary["blocker"] = {"code": "INTEGRATION_RUN.UNEXPECTED", "detail": f"{type(exc).__name__}: {exc}"}
        return 1
    finally:
        if detached and original_branch:
            subprocess.run(["git", "checkout", "--quiet", original_branch.removeprefix("refs/heads/")], cwd=ROOT, check=False)
        if claim_path is not None:
            # claim 只保护候选构造期；run 终态后显式释放，避免下一轮同 scope 候选被过期 claim 卡住。
            try:
                release_claim(repository=ROOT, policy_path=POLICY, claim_ref=claim_path, reason=f"integration-run {run_id} terminal {summary['terminal']}")
            except ScopedCandidateError as exc:
                summary.setdefault("warnings", []).append(f"claim release failed: {exc}")
        summary["endedAt"] = _now()
        summary["wallClockSeconds"] = round(sum(item["durationSeconds"] for item in phases.items), 3)
        (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (run_dir / "summary.md").write_text(_render_summary(summary), encoding="utf-8")
        print(json.dumps({"terminal": summary["terminal"], "runId": run_id, "summary": _output_ref(run_dir / "summary.json"),
                          **({"blocker": summary["blocker"]} if "blocker" in summary else {})}, ensure_ascii=False, sort_keys=True))


def _render_summary(summary: Mapping[str, Any]) -> str:
    lines = [f"# integrate {summary['runId']}", "", f"- terminal: `{summary['terminal']}`"]
    candidate = summary.get("candidate") or {}
    if candidate:
        lines.append(f"- candidate: `{candidate.get('commit')}` parent `{candidate.get('parent')}` candidateId `{candidate.get('candidateId', '-')}`")
    plan = summary.get("impactPlan") or {}
    if plan:
        lines.append(f"- integrationDepth: `{plan.get('integrationDepth')}` impactPlanDigest `{plan.get('digest')}`")
    if "readiness" in summary:
        lines.append(f"- readiness: level `{summary['readiness']['level']}` deferred {summary['readiness']['deferred']} receipt `{summary['readiness']['receiptRef']}`")
    for name, env in (summary.get("environments") or {}).items():
        package = env.get("package") or {}
        lines.append(f"- {name}: executed={env.get('executed', True)} baseline `{package.get('baselineId', '-')}` sourceRevision `{package.get('sourceRevision', '-')}` acceptance `{(env.get('acceptance') or {}).get('ref', '-')}`")
    if "publish" in summary:
        lines.append(f"- publish: `{summary['publish']['beforeOid']}` -> `{summary['publish']['afterOid']}` readback `{summary['publish']['readbackOid']}`")
    if "blocker" in summary:
        lines.append(f"- blocker: `{summary['blocker']['code']}` {summary['blocker']['detail']}")
    lines += ["", f"- wallClockSeconds: {summary.get('wallClockSeconds', 0)}", "", "| phase | status | seconds |", "|---|---|---|"]
    for item in summary.get("phases") or []:
        lines.append(f"| {item['name']} | {item['status']} | {item['durationSeconds']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
