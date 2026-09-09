#!/usr/bin/env python3
"""「lane 验收 → integration 发布 dev1.0」的 canonical 编排，分两种运行位置：

- `--mode acceptance`：在 lane 工作树（当前分支为该 lane，head 即 candidate）对 exact candidate
  跑本地 readiness、Alpha（Beta 仅 `--beta` 显式 opt-in，否则以 typed `not_required` 闭合）并签发
  `EnvironmentAcceptanceFact`，终态 `accepted`，不 admit、不 publish；同时把 candidate/claim/
  source fact/EAF 及其全部 exact 证据打成 portable acceptance bundle。Data release 的
  `ship --handoff-ref` admission 会用当前工作树重算 candidate evidence，因此只能在产出 handoff
  的 lane 工作树完成；`--baseline` 指定 ImpactPlan/readiness 的 exact parent（默认远端 dev1.0）；
  用户显式合并多个 lane head 后验收时用 `--merged-lanes` 记录来源。
- `--mode integrate`（默认）：在唯一 integration 工作区（分支 dev1.0，HEAD 即 candidate）只消费
  `--acceptance-bundle`：exact bytes 导入本工作树 store（create-once）、验签并复核 candidate 绑定与
  expected parent == 远端 before，然后 admit → publish（可选）。不启动任何环境、不需要 Data release
  输入；Gamma 与 prod canary 只在 integration 工作区、在 publish 之后推进。

只编排、不解释结论：环境动作一律经 `stackctl` 子进程，事实一律经
`quwoquan_ops.ci.scoped_candidate` / `environment_scheduler` 既有 create-once 入口。
任一步失败即保留首个 typed blocker 并把已启动的本地 runtime 放倒（finally down）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
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
    validate_environment_acceptance_fact,
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
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    BETA_OPTIONAL_BY_POLICY,
    NO_LIVE_ENVIRONMENT_REQUIRED,
)
from quwoquan_ops.cli.lib.evidence_signing import (
    DEFAULT_KEYRING_PATH,
    EvidenceSigningError,
    ed25519_environment_verifier,
    ed25519_signer,
    key_root,
    load_keyring,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    validate_readiness_case_result,
)

POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
LOCAL_READINESS = ROOT / "quwoquan_ops/cli/local_readiness.py"
OUTPUT_ROOT = ROOT / ".qwq_output"
RUNS_ROOT = OUTPUT_ROOT / "env/repo/runs/integrate"
DEV_REF = "refs/heads/dev1.0"
NO_LIVE = NO_LIVE_ENVIRONMENT_REQUIRED
ENVIRONMENT_SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
DEFAULT_SIGNER = "quwoquan-environment-ops-local"
ACCEPTANCE_BUNDLE_SCHEMA = "quwoquan_ops.acceptance_bundle.v1"
BUNDLE_MANIFEST = "bundle.json"
BUNDLE_STORE_DIR = "store"
_EAF_NAMED_FIELDS = (
    "runtimeIdentity", "dataLifecycle", "providerReadiness", "observabilityReadiness",
    "inspectEvidence", "doctorEvidence", "cleanupEvidence", "leaseClosureEvidence",
)


class IntegrationRunError(RuntimeError):
    """Typed blocker; the summary keeps the first one."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    # canonical publish 对象含中文路径；关闭 quotePath 才能把 diff-tree 输出原样交给 ImpactPlanner。
    completed = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ROOT, text=True, capture_output=True, check=False)
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


# DEC-041：release 不携带类别；acceptance 只消费显式 immutable 身份。
HANDOFF_REF_RE = re.compile(r"^handoff-ref-v1:sha256:[0-9a-f]{64}:sha256:[0-9a-f]{64}$")


def _release_id(attestation: Path) -> str:
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import _release_binding

    try:
        binding = _release_binding(str(attestation), label="acceptance")
    except (OSError, TypeError, ValueError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", str(exc)) from exc
    release_id = binding["releaseId"]
    local = OUTPUT_ROOT / "data/releases" / release_id / "attestations/release.json"
    if not local.is_file() or local.read_bytes() != attestation.read_bytes():
        raise IntegrationRunError(
            "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE",
            f"immutable release {release_id} is absent from {OUTPUT_ROOT / 'data/releases'} or its attestation differs; "
            "ship apply only executes releases present in this worktree's Data root",
        )
    return release_id


def _handoff_ref(value: str, *, label: str) -> str:
    """现役 `qwq-data ship` 只接受 authoritative handoff-ref-v1 准入；release id 不再是隐式选择器。"""

    ref = str(value or "").strip()
    if not HANDOFF_REF_RE.fullmatch(ref):
        raise IntegrationRunError(
            "INTEGRATION_RUN.INPUT_INVALID",
            f"{label} must be a canonical handoff-ref-v1 (got {ref[:48] or '-'}); "
            "obtain it from the Data producer release handoff (qwq-state/handoffs)",
        )
    return ref


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
    """candidate release 进入环境：`ship apply --handoff-ref … --import --full-sync` → `ship activate` → `ship verify`。

    handoff-ref 是现役 Data CLI 唯一的 release 准入身份；attestation 只用于 stackctl package 的候选绑定，
    两者必须指向同一 releaseId（由 ship 侧对 handoff 做 exact 校验）。返回 release-readiness 回执路径。
    """

    release_id = _release_id(args.release_attestation)
    handoff_ref = _handoff_ref(args.release_handoff_ref, label="--release-handoff-ref")
    import_run, activate_run, verify_run = f"{run_id}-import", f"{run_id}-activate", f"{run_id}-verify"
    _data_ship("apply", "--handoff-ref", handoff_ref, "--env", environment, "--run-id", import_run,
               "--import", "--full-sync", log_dir=log_dir, label=f"{environment}-apply")
    _data_ship("activate", "--handoff-ref", handoff_ref, "--env", environment, "--import-run-id", import_run,
               "--run-id", activate_run, log_dir=log_dir, label=f"{environment}-activate")
    _bootstrap_premium_pool(environment=environment, release_id=release_id, import_run=import_run,
                            attestation=args.release_attestation, log_dir=log_dir)
    # ship verify 的 --import-run-id 指向 completed 的 activate run（其 result.importRunId 再指回 apply run）；
    # 传 apply run 会因 result status=prepared 被拒（"completed activation predecessor result status 不一致"）。
    verify_args = ["verify", "--handoff-ref", handoff_ref, "--env", environment, "--import-run-id", activate_run,
                   "--run-id", verify_run]
    if previous_readiness is not None:
        verify_args.extend(["--previous-environment-readiness", _output_ref(previous_readiness)])
    _data_ship(*verify_args, log_dir=log_dir, label=f"{environment}-verify")
    readiness = OUTPUT_ROOT / "env" / environment / "runs/data-release" / release_id / verify_run / "release-readiness.json"
    if not readiness.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.DATA_RELEASE_FAILED", f"release readiness receipt missing: {readiness}")
    return readiness


PREMIUM_POOL_BOOTSTRAP_QUALITY_SCORE = "1.0"
PREMIUM_POOL_BOOTSTRAP_TTL_DAYS = 30


def _bootstrap_premium_pool(*, environment: str, release_id: str, import_run: str, attestation: Path, log_dir: Path) -> None:
    """fresh 环境的精选池首次激活：`ship verify` 要求 premium_stream 读回 release 视频，
    而精选池只能经 canonical `stackctl premium-pool --launch-policy release-import` 自举（OPEN-023）。
    样本来自派生 ReleaseUatSamplePlan 的 video objectId，经导入报告 contentId → postId 绑定；池非空时该路径按设计关闭，视为已激活。"""

    from quwoquan_ops.cli.lib.app_content_uat_plan import load_release_uat_sample_plan

    import_report = OUTPUT_ROOT / "env" / environment / "runs/data-release" / release_id / import_run / "import.json"
    try:
        report = json.loads(import_report.read_text(encoding="utf-8"))
        header = json.loads((attestation.parent.parent / "payload/release.json").read_text(encoding="utf-8"))
        plan, _ref, _digest = load_release_uat_sample_plan(
            release_root=attestation.parent.parent / "payload", release_header=header,
            manifest_digest=str(report.get("manifestDigest") or ""),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.DATA_RELEASE_FAILED", f"premium pool bootstrap inputs unavailable: {exc}") from exc
    video_object_ids = {str(s.get("objectId") or "") for s in plan.get("samples") or [] if isinstance(s, Mapping) and s.get("carrier") == "video"}
    post_ids = sorted(
        str(row.get("postId") or "")
        for row in report.get("postBindings") or []
        if isinstance(row, Mapping) and row.get("contentType") == "video" and str(row.get("contentId") or "") in video_object_ids
    )
    if not post_ids:
        raise IntegrationRunError("INTEGRATION_RUN.DATA_RELEASE_FAILED", "ReleaseUatSamplePlan video sample has no postId binding in the import report")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=PREMIUM_POOL_BOOTSTRAP_TTL_DAYS)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = _stackctl(
        "premium-pool", "--target", f"{environment}-local", "--action", "upsert-and-verify", "--launch-policy", "release-import",
        "--readiness-receipt", str(import_report), "--content-id", post_ids[0],
        "--quality-score", PREMIUM_POOL_BOOTSTRAP_QUALITY_SCORE, "--expires-at", expires_at, log_dir=log_dir,
    )
    if result.exit_code == 0:
        return
    details = " ".join(str(item) for item in (result.payload.get("details") or []))
    if "already has premium pool entries" in details:
        return
    _require_ok(result, "INTEGRATION_RUN.DATA_RELEASE_FAILED")


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


def _readiness_local_ref(*, args: argparse.Namespace, commit: str) -> str:
    """readiness 的 push identity 要求 local ref 精确解析到 candidate。

    integrate 在 integration 工作区，本地 `refs/heads/dev1.0` 就是 candidate；acceptance 在 lane
    工作树，candidate 是 lane 自己的 branch ref（当前分支且解析到 candidate），不得借用 dev1.0。
    """
    if args.mode != "acceptance":
        return DEV_REF
    branch_ref = _git("symbolic-ref", "--quiet", "HEAD")
    if not branch_ref.startswith("refs/heads/lane/") or _git("rev-parse", branch_ref) != commit:
        raise IntegrationRunError(
            "INTEGRATION_RUN.LANE_IDENTITY_INVALID",
            f"acceptance must run on a lane branch whose head is the candidate (branch={branch_ref or 'detached'})",
        )
    return branch_ref


def _local_readiness(*, level: str, parent: str, commit: str, run_dir: Path, args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    # `run` 会读取 push updates 两次（plan + run），stdin 只能读一次，所以落成文件再传路径。
    local_ref = _readiness_local_ref(args=args, commit=commit)
    updates_path = run_dir / f"push-updates-{level}.txt"
    updates_path.write_text(f"{local_ref} {commit} {DEV_REF} {parent}\n", encoding="utf-8")
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
        _write_canonical(case_path, validate_readiness_case_result(result, generated_at=completed))
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


PACKAGE_REUSE_SUMMARY_MARKER = "reused immutable candidate"


def _assert_package_identity(*, packaged_revision: str, candidate_commit: str, package: StackctlResult) -> None:
    """候选身份是内容寻址的：baselineId 由当前树的打包输入派生，`stackctl package` 只在输入字节同一时复用既有
    不可变候选，其 manifest.sourceRevision 保留首次打包的 commit。因此 sourceRevision 与 candidate 不等只在
    「本次是复用」且「该 commit 是 candidate 祖先」时合法（例如只改 quwoquan_data/specs 的候选）。"""

    if packaged_revision == candidate_commit:
        return
    reused = PACKAGE_REUSE_SUMMARY_MARKER in str(package.payload.get("summary") or "")
    ancestor = bool(packaged_revision) and subprocess.run(
        ["git", "merge-base", "--is-ancestor", packaged_revision, candidate_commit], cwd=ROOT, check=False,
    ).returncode == 0
    if not (reused and ancestor):
        raise IntegrationRunError(
            "INTEGRATION_RUN.PACKAGE_IDENTITY_INVALID",
            f"packaged sourceRevision {packaged_revision} != candidate {candidate_commit} (reused={reused}, ancestor={ancestor})",
        )


def _package_with_dependency_recovery(*, environment: str, args: argparse.Namespace, log_dir: Path, phases: Phases) -> StackctlResult:
    """打包；App 依赖 bundle 缺失/过期时执行一次有界 canonical `app-dependency-sync` 再重试，其余失败原样阻断。"""

    def package() -> StackctlResult:
        return _stackctl(
            "package", "--env", environment, "--include-services",
            "--release-attestation", str(args.release_attestation),
            "--rollback-release-attestation", str(args.rollback_release_attestation), log_dir=log_dir,
        )

    result = package()
    details = " ".join(str(item) for item in (result.payload.get("details") or []))
    if result.exit_code != 0 and "App dependency bundle" in details:
        phases.run(f"{environment}.app-dependency-sync", lambda: _require_ok(
            _stackctl("app-dependency-sync", log_dir=log_dir / "app-dependency-sync"), "INTEGRATION_RUN.APP_DEPENDENCY_SYNC_FAILED",
        ))
        result = package()
    return _require_ok(result, "INTEGRATION_RUN.PACKAGE_FAILED")


def _alpha_app_launch_cases(*, candidate: Mapping[str, str], runtime: Mapping[str, str], evidence_dir: Path,
                            log_dir: Path, args: argparse.Namespace, env_summary: dict[str, Any]) -> list[dict[str, str]]:
    """Alpha 的 App 启动 + 首页/视频书 readback：两份 raw ReadinessCaseResult，任一失败即 typed blocker。

    服务 health 不等于 App 能启动；candidate 影响面含 `app` 时这是 Alpha 准入的必需证据，
    没有可用模拟器同样阻断，不得降级为 PASS（environment-topology-and-packaging REQ-003、
    local-continuous-integration REQ-004）。
    """

    from quwoquan_ops.cli.lib.integration_app_launch import (
        APP_LAUNCH_SPEC_REF, CONTENT_READBACK_SPEC_REF, IntegrationAppLaunchError,
        case_result, content_readback, launch_and_observe, select_ios_simulator,
    )

    try:
        device = select_ios_simulator(preferred_udid=str(getattr(args, "app_launch_device", "") or ""))
        observation = launch_and_observe(
            repo_root=ROOT, device=device, log_dir=log_dir,
            timeout_seconds=float(getattr(args, "app_launch_timeout_seconds", 900)),
        )
    except IntegrationAppLaunchError as exc:
        raise IntegrationRunError(exc.code, exc.detail) from exc
    launch_receipt = log_dir / "app-launch-alpha.json"
    launch_receipt.write_text(json.dumps({
        "device": {"udid": device.udid, "name": device.name},
        "phases": observation.phases,
        "launched": observation.launched,
        "routerShell": observation.router_shell,
        "configurationComplete": observation.configuration_complete,
        "exitCode": observation.exit_code,
        "firstBlocker": observation.first_blocker,
        "logRef": _output_ref(observation.log_path) if observation.log_path else "",
        "startedAt": observation.started_at,
        "completedAt": observation.completed_at,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    env_summary["appLaunch"] = {"device": device.name, "passed": observation.passed, "receipt": _output_ref(launch_receipt)}
    if not observation.passed:
        raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", observation.first_blocker or "App launch did not reach launched/router_shell/complete")

    readback_started = _now()
    readback = content_readback(target="alpha-local")
    readback_receipt = log_dir / "content-readback-alpha.json"
    readback_receipt.write_text(json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    env_summary["contentReadback"] = {"passed": readback["passed"], "receipt": _output_ref(readback_receipt), "failures": readback["failures"]}
    if not readback["passed"]:
        raise IntegrationRunError("INTEGRATION_RUN.CONTENT_READBACK_FAILED", "; ".join(readback["failures"]))
    readback_completed = _now()

    refs: list[dict[str, str]] = []
    for index, (case_id, object_id, spec_ref, target_id, receipt, started, completed) in enumerate((
        ("app-launch:ios-simulator", "app-launch:alpha:ios-simulator", APP_LAUNCH_SPEC_REF, "app.launch.ios_simulator",
         launch_receipt, observation.started_at, observation.completed_at),
        ("content-readback:home-feed+video-book", "content-readback:alpha:home-feed+video-book", CONTENT_READBACK_SPEC_REF,
         "content.feed.list", readback_receipt, readback_started, readback_completed),
    )):
        result = case_result(
            case_id=case_id, object_id=object_id, spec_ref=spec_ref, target_id=target_id, environment="alpha",
            candidate=candidate, runtime=runtime, started_at=started, completed_at=completed,
            artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(), receipt_ref=_output_ref(receipt),
        )
        case_path = evidence_dir / "cases" / f"app-{index:03d}.json"
        case_path.parent.mkdir(parents=True, exist_ok=True)
        _write_canonical(case_path, validate_readiness_case_result(result, generated_at=completed))
        refs.append({"ref": case_path.relative_to(_store()).as_posix(), "digest": exact_file_digest(case_path)})
    return refs


def _run_environment(*, environment: str, profile: str, candidate: Mapping[str, str], impact_plan_digest: str,
                     args: argparse.Namespace, run_dir: Path, phases: Phases, summary: dict[str, Any],
                     previous_readiness: Path | None = None, scopes: Sequence[str] = ()) -> dict[str, Any]:
    target = f"{environment}-local"
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / environment
    log_dir = run_dir / environment
    env_summary: dict[str, Any] = {"environment": environment, "target": target, "reports": {}}
    summary["environments"][environment] = env_summary
    started_up = False
    app_cases: list[dict[str, str]] = []
    try:
        package = phases.run(f"{environment}.package", lambda: _package_with_dependency_recovery(
            environment=environment, args=args, log_dir=log_dir, phases=phases,
        ))
        env_summary["reports"]["package"] = _report_source(package)
        active_path = Path(os.environ.get("QWQ_DEPLOY_WORK_ROOT", str(Path.home() / ".cache/quwoquan/deploy"))) / target / "active-runtime-candidate.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        baseline = str(active.get("baselineId") or "")
        manifest = json.loads((Path(str(active["candidateDir"])) / "manifest.json").read_text(encoding="utf-8"))
        packaged_revision = str(manifest.get("sourceRevision") or "")
        _assert_package_identity(packaged_revision=packaged_revision, candidate_commit=candidate["commit"], package=package)
        env_summary["package"] = {"baselineId": baseline, "sourceRevision": packaged_revision, "packageDigest": manifest.get("packageDigest"), "imageDigest": manifest.get("imageDigest"),
                                  "reusedFromAncestor": packaged_revision != candidate["commit"]}

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
        if environment == "alpha" and "app" in scopes:
            # App 可启动、首页与视频书可访问是 Alpha 准入的必需事实，在服务 health 之后、
            # runtime 仍在线时执行；模拟器缺失或任一 readback 失败都在这里 typed 阻断。
            app_cases = phases.run(f"{environment}.app-launch", lambda: _alpha_app_launch_cases(
                candidate=candidate, runtime=runtime, evidence_dir=evidence_dir, log_dir=log_dir, args=args, env_summary=env_summary,
            ))
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
    cases.extend(app_cases)
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


def _not_required_beta(*, candidate: Mapping[str, str], impact_plan_digest: str, impact_plan_path: Path, profile: str,
                       reason_code: str = NO_LIVE) -> dict[str, Any]:
    """Beta 不真跑时的 typed not_required 证据：`reason_code` 记录真实原因——ImpactPlan 判定无需 live
    Beta（`IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED`），或 ImpactPlan 判定敏感但用户未 `--beta` opt-in
    （`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`）。两者都绑定 candidate 与 ImpactPlan，不从 skipped 推导。"""
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / "beta"
    plan_sha = hashlib.sha256(impact_plan_path.read_bytes()).hexdigest()
    source = {"basis": reason_code, "executed": False, "impactPlanRef": _output_ref(impact_plan_path), "impactPlanSha256": plan_sha}

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
        # ReadinessCaseResult 合同：passed 结果不得携带 reasonCode；不真跑的原因记录在 EAF.reasonCode 与 named evidence source.basis。
    }
    case_path = evidence_dir / "cases" / "000.json"
    case_path.parent.mkdir(parents=True, exist_ok=True)
    _write_canonical(case_path, validate_readiness_case_result(case, generated_at=now))
    return {"named": named, "cases": [{"ref": case_path.relative_to(store).as_posix(), "digest": exact_file_digest(case_path)}],
            "reasonCode": reason_code}


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
        non_promotable=False, reason_code=str(evidence.get("reasonCode") or NO_LIVE) if status == "not_required" else None,
        **evidence["named"],
    )
    acceptance = {"ref": path.relative_to(store).as_posix(), "digest": exact_file_digest(path)}
    # scheduler 签发入口已追加 acceptance_issued；编排不得重复追加终态。
    return acceptance


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _bundle_path(root: Path, ref: str) -> Path:
    """exact ref 只允许物理根内 canonical POSIX 整文件，任何 symlink 分量拒绝。"""
    if not ref or ref == "." or any(char in ref for char in "\x00\n\r\\") or Path(ref).is_absolute() or Path(ref).as_posix() != ref or ".." in Path(ref).parts:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"unsafe bundle ref: {ref!r}")
    path = root / ref
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"linked bundle ref: {ref}")
    return path


def _bundle_bytes(root: Path, exact: Mapping[str, str]) -> bytes:
    if not isinstance(exact, Mapping) or set(exact) != {"ref", "digest"}:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "bundle exact ref must contain ref and digest")
    if not isinstance(exact["ref"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(exact["digest"])):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "bundle exact ref has invalid types or digest")
    path = _bundle_path(root, exact["ref"])
    if not path.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INCOMPLETE", f"bundle file is absent: {exact['ref']}")
    raw = path.read_bytes()
    if _sha256_hex(raw) != exact["digest"]:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", f"bundle exact bytes drifted: {exact['ref']}")
    return raw


def _bundle_put(root: Path, ref: str, raw: bytes) -> bool:
    """先 fsync 私有临时文件，再 link 原子 create-once；竞争失败只接受 exact-byte replay。"""
    path = _bundle_path(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".bundle-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _bundle_path(root, ref)
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            _bundle_path(root, ref)
            if not path.is_file() or path.read_bytes() != raw:
                raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", f"create-once slot differs: {ref}")
            return False
    finally:
        temporary.unlink(missing_ok=True)


def _read_store_object(store: Path, exact: Mapping[str, str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(_bundle_bytes(store, exact))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"{label} is not JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"{label} is not an object")
    return payload


def _source_receipt(source: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    exact = source.get("receipt")
    if not isinstance(exact, Mapping) or not str(exact.get("ref", "")).startswith(".qwq_output/env/repo/"):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "source receipt must be an exact repo output ref")
    return dict(exact), str(exact["ref"]).removeprefix(".qwq_output/")


def _fact_evidence_refs(fact: Mapping[str, Any]) -> list[dict[str, str]]:
    """EAF 的全部 store 内 exact 引用：caseResultRefs + 八类 named evidence（predecessor 单独打包）。"""
    refs: list[dict[str, str]] = [dict(item) for item in (fact.get("caseResultRefs") or [])]
    for field in _EAF_NAMED_FIELDS:
        value = fact.get(field)
        if not isinstance(value, Mapping):
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"acceptance fact lacks {field}")
        refs.append(dict(value))
    return refs


def _merged_lanes(*, values: Sequence[str], lane_branch: str, commit: str, remote: str) -> list[dict[str, str]]:
    """记录本次验收 candidate 合并了哪些 lane head：每个 lane 解析为 exact commit 且必须是 candidate 的祖先。

    这是多工作树合并验收的显式来源记录（用户明确指定），不是自动发现；缺省只记录 lane 自身。
    """
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in [lane_branch, *values]:
        name = str(raw or "").strip().removeprefix("refs/heads/")
        if not name.startswith("lane/"):
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes expects lane/<name> (got {name or '-'})")
        if name in seen:
            continue
        resolved = ""
        for ref in (f"refs/heads/{name}", f"refs/remotes/{remote}/{name}"):
            probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=ROOT, text=True, capture_output=True, check=False)
            if probe.returncode == 0 and probe.stdout.strip():
                resolved = probe.stdout.strip()
                break
        if not resolved:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes {name} does not resolve to a local or {remote} lane head")
        if subprocess.run(["git", "merge-base", "--is-ancestor", resolved, commit], cwd=ROOT, check=False).returncode != 0:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes {name}@{resolved[:12]} is not an ancestor of the candidate")
        seen.add(name)
        entries.append({"branch": f"refs/heads/{name}", "commit": resolved})
    return entries


def _write_acceptance_bundle(*, run_dir: Path, candidate_ref: Mapping[str, str], source_ref: Mapping[str, str],
                             alpha_ref: Mapping[str, str], beta_ref: Mapping[str, str], identity: Mapping[str, str],
                             plan_path: Path, summary: Mapping[str, Any], beta_status: str, beta_reason: str | None,
                             lane_branch: str, merged_lanes: Sequence[Mapping[str, str]], args: argparse.Namespace) -> Path:
    """把 accepted 终态的全部 exact 事实按 store 相对路径复制成 portable bundle，供 integration 工作区导入。

    bundle 只复制字节、不改写任何事实；`bundle.json` 记录 candidate 身份、baseline、lane 来源与每个文件的
    exact digest，`bundleId` 是 manifest 自身的 canonical digest。integration 侧按同一 digest 逐字节复核。
    """
    store = _store()
    bundle_dir = run_dir / "acceptance-bundle"
    if bundle_dir.exists():
        raise IntegrationRunError("INTEGRATION_RUN.CREATE_CONFLICT", f"acceptance bundle already exists: {bundle_dir}")
    store_dir = bundle_dir / BUNDLE_STORE_DIR
    candidate = _read_store_object(store, candidate_ref, "candidate")
    claim_ref = {"ref": str(candidate["claimRef"]), "digest": str(candidate["claimDigest"])}
    files: dict[str, str] = {}

    def add(exact: Mapping[str, str], label: str) -> None:
        ref, digest = str(exact["ref"]), str(exact["digest"])
        raw = _bundle_bytes(store, exact)
        if files.get(ref, digest) != digest:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", f"{label} {ref} is referenced with two digests")
        if ref in files:
            return
        files[ref] = digest
        _bundle_put(store_dir, ref, raw)

    add(candidate_ref, "candidate")
    add(claim_ref, "claim")
    add(source_ref, "sourceFact")
    receipt, output_ref = _source_receipt(_read_store_object(store, source_ref, "sourceFact"))
    receipt_raw = _bundle_bytes(OUTPUT_ROOT, {"ref": output_ref, "digest": receipt["digest"]})
    _bundle_put(bundle_dir / "repository", receipt["ref"], receipt_raw)
    for environment, fact_ref in (("alpha", alpha_ref), ("beta", beta_ref)):
        add(fact_ref, f"{environment}Fact")
        fact = _read_store_object(store, fact_ref, f"{environment}Fact")
        for exact in _fact_evidence_refs(fact):
            add(exact, f"{environment} evidence")
    plan_bytes = plan_path.read_bytes()
    _bundle_put(bundle_dir, "impact-plan.json", plan_bytes)
    manifest: dict[str, Any] = {
        "schema": ACCEPTANCE_BUNDLE_SCHEMA, "runId": summary["runId"], "createdAt": _now(),
        "candidateId": candidate["candidateId"], "commit": candidate["commit"], "tree": candidate["tree"],
        "expectedParent": candidate["expectedParent"],
        "baseline": identity["parent"], "remoteHeadAtAcceptance": identity.get("remoteHead", ""),
        "laneBranch": lane_branch, "mergedLanes": [dict(item) for item in merged_lanes],
        "impactPlan": {**dict(summary["impactPlan"]), "fileSha256": _sha256_hex(plan_bytes)},
        "dataReleases": list(summary.get("dataReleases") or []),
        "dataReleaseHandoffRef": str(summary.get("dataReleaseHandoffRef") or ""),
        "signerIdentity": args.signer_identity, "profile": args.profile,
        "beta": {"status": beta_status, "executed": beta_status == "passed", "reasonCode": beta_reason},
        "candidate": dict(candidate_ref), "claim": claim_ref, "sourceFact": dict(source_ref), "sourceReceipt": receipt,
        "alphaFact": dict(alpha_ref), "betaFact": dict(beta_ref),
        "storeFiles": [{"ref": ref, "digest": digest} for ref, digest in sorted(files.items())],
    }
    manifest["bundleId"] = _sha256_hex(_canonical_bytes(manifest))
    _bundle_put(bundle_dir, BUNDLE_MANIFEST, _canonical_bytes(manifest) + b"\n")
    return bundle_dir


def _load_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = _bundle_path(bundle_dir, BUNDLE_MANIFEST)
    if not bundle_dir.is_dir() or not manifest_path.is_file():
        raise IntegrationRunError(
            "INTEGRATION_RUN.ACCEPTANCE_REQUIRED",
            f"integrate consumes a lane acceptance bundle; {manifest_path} is missing (run make accept in the lane worktree first)",
        )
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest is not JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != ACCEPTANCE_BUNDLE_SCHEMA:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest schema must be {ACCEPTANCE_BUNDLE_SCHEMA}")
    material = {key: value for key, value in manifest.items() if key != "bundleId"}
    if manifest.get("bundleId") != _sha256_hex(_canonical_bytes(material)):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", "bundle manifest bytes do not match bundleId")
    for key in ("candidateId", "commit", "tree", "expectedParent", "candidate", "claim", "sourceFact", "alphaFact", "betaFact", "storeFiles", "signerIdentity", "sourceReceipt", "impactPlan", "beta", "profile"):
        if key not in manifest:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest lacks {key}")
    return manifest


def _import_acceptance_bundle(*, bundle_dir: Path, commit: str, tree: str, parent: str, args: argparse.Namespace,
                              keyring: Any) -> dict[str, Any]:
    """integrate 模式唯一的事实来源：逐字节导入 lane bundle 并复核绑定。

    - 每个 store 文件按 manifest digest 复核后 create-once 写入本工作树 store；已存在且字节不同即 `BUNDLE_DRIFT`。
    - candidate.commit/tree 必须等于本工作区 HEAD candidate；expectedParent 必须等于当前远端 dev1.0（否则
      `BUNDLE_STALE`：dev1.0 已前移，需在合入新 dev1.0 的 head 上重新 `make accept`）。
    - Alpha/Beta EAF 以仓内 keyring 验签、复核全部引用与 candidate 绑定；source fact 必须 passed 且绑定同一 candidateId。
    """
    manifest = _load_bundle_manifest(bundle_dir)
    if manifest["commit"] != commit or manifest["tree"] != tree:
        raise IntegrationRunError(
            "INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH",
            f"bundle was accepted for {str(manifest['commit'])[:12]} but the integration candidate is {commit[:12]}",
        )
    if manifest["expectedParent"] != parent:
        raise IntegrationRunError(
            "INTEGRATION_RUN.BUNDLE_STALE",
            f"bundle expectedParent {str(manifest['expectedParent'])[:12]} != remote dev1.0 {parent[:12]}; "
            "dev1.0 moved since acceptance, re-run make accept on a head that includes the current dev1.0",
        )
    # 先在 bundle 内验证完整闭包，不让目标 store 的残留文件补齐不完整输入。
    store = bundle_dir / BUNDLE_STORE_DIR
    if not isinstance(manifest["storeFiles"], list) or not isinstance(manifest["impactPlan"], dict):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "invalid storeFiles or impactPlan")
    files: dict[str, bytes] = {}
    for exact in manifest["storeFiles"]:
        raw = _bundle_bytes(store, exact)
        if exact["ref"] in files:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "duplicate storeFiles ref")
        files[exact["ref"]] = raw
    _bundle_bytes(bundle_dir, {"ref": "impact-plan.json", "digest": manifest["impactPlan"].get("fileSha256")})
    candidate = _read_store_object(store, manifest["candidate"], "candidate")
    if (
        candidate.get("candidateId") != manifest["candidateId"] or candidate.get("commit") != commit
        or candidate.get("tree") != tree or candidate.get("expectedParent") != parent
        or candidate.get("claimRef") != manifest["claim"].get("ref") or candidate.get("claimDigest") != manifest["claim"].get("digest")
    ):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "imported candidate does not bind the bundle identity")
    _read_store_object(store, manifest["claim"], "claim")
    source_fact = _read_store_object(store, manifest["sourceFact"], "sourceFact")
    if (source_fact.get("status") != "passed" or source_fact.get("candidateId") != candidate["candidateId"]
            or source_fact.get("commit") != commit or source_fact.get("tree") != tree
            or source_fact.get("candidate") != manifest["candidate"]):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "imported source fact is not passed for this candidate")
    receipt, output_ref = _source_receipt(source_fact)
    if receipt != manifest["sourceReceipt"]:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", "source receipt differs from manifest")
    receipt_raw = _bundle_bytes(bundle_dir / "repository", receipt)
    required = [manifest[key] for key in ("candidate", "claim", "sourceFact", "alphaFact", "betaFact")]
    signer_identity = str(manifest["signerIdentity"])
    if signer_identity != args.signer_identity:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle signer {signer_identity} != expected {args.signer_identity}")
    try:
        verifier = ed25519_environment_verifier(keyring, [signer_identity])
    except EvidenceSigningError as exc:
        raise IntegrationRunError("INTEGRATION_RUN.SIGNER_UNREGISTERED", exc.detail) from exc
    for environment, fact_ref in (("alpha", manifest["alphaFact"]), ("beta", manifest["betaFact"])):
        fact = _read_store_object(store, fact_ref, f"{environment}Fact")
        validated = validate_environment_acceptance_fact(
            fact, store_root=store, verify_references=True, accepted_at=datetime.now(timezone.utc),
            signature_verifier=verifier, expected_signer_identity=signer_identity,
        )
        required.extend(_fact_evidence_refs(validated))
        if (validated.get("profile") != manifest["profile"] or validated.get("nonPromotable") is not False
                or validated.get("impactPlanDigest") != manifest["impactPlan"].get("digest")
                or candidate.get("impactPlanDigest") != manifest["impactPlan"].get("digest")
                or (environment == "alpha" and validated.get("status") != "passed")
                or (environment == "beta" and (validated.get("predecessor") != manifest["alphaFact"] or manifest["beta"] != {
                    "status": validated.get("status"), "executed": validated.get("status") == "passed",
                    "reasonCode": validated.get("reasonCode")}))):
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", f"{environment} signed fact differs from manifest")
        binding = validated.get("candidate") or {}
        if validated.get("environment") != environment or binding.get("candidateId") != candidate["candidateId"] \
                or binding.get("commit") != commit or binding.get("tree") != tree:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", f"{environment} fact does not bind the imported candidate")
    if {item["ref"]: item["digest"] for item in required} != {ref: _sha256_hex(raw) for ref, raw in files.items()}:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INCOMPLETE", "storeFiles is not the exact evidence closure")
    destination = _store()
    imported = sum(_bundle_put(destination, ref, raw) for ref, raw in files.items())
    _bundle_put(OUTPUT_ROOT, output_ref, receipt_raw)
    return {"manifest": manifest, "candidate": candidate, "importedFiles": imported, "storeFiles": len(files)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", default="HEAD", help="exact commit（HEAD 或 lane head sha）")
    parser.add_argument("--mode", choices=("integrate", "acceptance"), default="integrate",
                        help="integrate=integration 工作区消费 acceptance bundle 并 admit/publish；"
                             "acceptance=lane 工作树跑 readiness + Alpha（--beta 时含 Beta）并签发事实与 bundle")
    parser.add_argument("--baseline", default="",
                        help="acceptance 专用：ImpactPlan/readiness 的 exact parent commit；缺省取远端 dev1.0 head，"
                             "candidate 已等于远端 dev1.0 时必须显式给出上一个已验收基线")
    parser.add_argument("--beta", action="store_true",
                        help="acceptance 专用：显式 opt-in 真跑 Beta；缺省不按集成深度分流，"
                             "以 typed not_required(reason=ACCEPTANCE.BETA_OPTIONAL_BY_POLICY) 闭合")
    parser.add_argument("--merged-lanes", action="append", default=[],
                        help="acceptance 专用：candidate 显式合并的其他 lane（lane/<name>，可重复）；每个都必须是 candidate 的祖先")
    parser.add_argument("--acceptance-bundle", type=Path, default=None,
                        help="integrate 专用：lane `make accept` 产出的 acceptance-bundle 目录；缺失即 INTEGRATION_RUN.ACCEPTANCE_REQUIRED")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--owner-identity", default="", help="PRE owner identity manifest ref（make feature-context 输出）")
    parser.add_argument("--candidate-evidence", default="")
    parser.add_argument("--review-consolidation", default="")
    parser.add_argument("--required-evidence", action="append", default=[])
    parser.add_argument("--readiness-level", choices=("fast", "scope"), default="fast",
                        help="fast=exact delta 静态+聚焦（deferred 允许，L2 在 Gamma 前补齐）；scope 需 Review consolidation 输入")
    parser.add_argument("--release-attestation", type=Path, default=None,
                        help="acceptance 必填：candidate production Data release attestation（stackctl package 候选绑定）")
    parser.add_argument("--rollback-release-attestation", type=Path, default=None,
                        help="acceptance 必填：rollback production Data release attestation（只参与候选绑定，不执行 rollback）")
    parser.add_argument("--release-handoff-ref", default="",
                        help="acceptance 必填：candidate production release 的 authoritative handoff-ref-v1（现役 qwq-data ship 唯一准入身份）；"
                             "rollback release 只参与 stackctl package 候选绑定，因此不需要其 handoff-ref")
    parser.add_argument("--workload", default="full", choices=("content-release", "content-commercial", "full"))
    parser.add_argument("--profile", default="integration", choices=("smoke", "integration"))
    parser.add_argument("--signer-identity", default=DEFAULT_SIGNER)
    parser.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH,
                        help="仓内 Ed25519 公钥 keyring；私钥来自仓外 QWQ_EVIDENCE_SIGNING_KEY_ROOT")
    parser.add_argument("--fact-ttl-hours", type=int, default=72)
    parser.add_argument("--writer", default="integration")
    parser.add_argument("--publish", action="store_true", help="admit 后以 local-git CAS 发布到远端 dev1.0")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--app-launch-device", default="",
                        help="Alpha App 启动证据使用的 iOS 模拟器 udid；缺省选已 Booted 或第一台可用 iPhone")
    parser.add_argument("--app-launch-timeout-seconds", type=int, default=900)
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
        summary["mode"] = args.mode
        try:
            keyring = load_keyring(args.signing_keyring)
        except EvidenceSigningError as exc:
            raise IntegrationRunError("INTEGRATION_RUN.SIGNER_UNAVAILABLE", exc.detail) from exc
        if args.mode == "integrate":
            # integrate 只消费 lane 事实：不签发、不跑环境，因此不需要私钥与 Data release 输入。
            for flag, value in (("--baseline", args.baseline), ("--beta", args.beta), ("--merged-lanes", args.merged_lanes),
                                ("--release-attestation", args.release_attestation),
                                ("--rollback-release-attestation", args.rollback_release_attestation),
                                ("--release-handoff-ref", args.release_handoff_ref)):
                if value:
                    raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"{flag} is acceptance-only; integrate consumes --acceptance-bundle")
            if args.acceptance_bundle is None:
                raise IntegrationRunError(
                    "INTEGRATION_RUN.ACCEPTANCE_REQUIRED",
                    "integrate requires --acceptance-bundle produced by make accept in the lane worktree; no environment runs here",
                )
            signer = None
        else:
            if args.publish:
                raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "acceptance mode issues environment facts only; publish belongs to the integration worktree")
            if args.acceptance_bundle is not None:
                raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "--acceptance-bundle is integrate-only; acceptance produces the bundle")
            try:
                signer = ed25519_signer(args.signer_identity, root=key_root(), keyring=keyring)
            except EvidenceSigningError as exc:
                raise IntegrationRunError(
                    "INTEGRATION_RUN.SIGNER_UNREGISTERED" if exc.code == "EVIDENCE_SIGNING.SIGNER_UNREGISTERED" else "INTEGRATION_RUN.SIGNER_UNAVAILABLE",
                    exc.detail,
                ) from exc
            for label, path in (("release", args.release_attestation), ("rollback", args.rollback_release_attestation)):
                if path is None or not path.is_file():
                    raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"{label} attestation is required in acceptance mode and must be a file: {path}")
            release_ids = {_release_id(args.release_attestation), _release_id(args.rollback_release_attestation)}
            if len(release_ids) != 2:
                raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "release and rollback attestations must name two different releases")
            summary["dataReleases"] = sorted(release_ids)
            summary["dataReleaseHandoffRef"] = _handoff_ref(args.release_handoff_ref, label="--release-handoff-ref")

        def preflight() -> dict[str, str]:
            if _git("status", "--porcelain", "--untracked-files=no"):
                raise IntegrationRunError("INTEGRATION_RUN.DIRTY_WORKTREE", "worktree must be clean")
            commit = _git("rev-parse", f"{args.candidate}^{{commit}}")
            remote_head = _git("ls-remote", args.remote, DEV_REF).split()[0]
            if args.mode == "acceptance":
                # lane 工作树只签发环境事实：parent 是显式基线（或远端 dev1.0），不要求 candidate 领先远端。
                parent = _git("rev-parse", f"{args.baseline}^{{commit}}") if args.baseline else remote_head
                if commit == parent:
                    raise IntegrationRunError(
                        "INTEGRATION_RUN.NOTHING_TO_ACCEPT",
                        "candidate equals its baseline; pass --baseline <previous accepted commit> to accept an already-landed head",
                    )
                if subprocess.run(["git", "merge-base", "--is-ancestor", parent, commit], cwd=ROOT, check=False).returncode != 0:
                    raise IntegrationRunError("INTEGRATION_RUN.NOT_FAST_FORWARD", "baseline is not an ancestor of the candidate")
                return {"commit": commit, "parent": parent, "remoteHead": remote_head, "tree": _git("show", "-s", "--format=%T", commit)}
            parent = remote_head
            if commit == parent:
                raise IntegrationRunError("INTEGRATION_RUN.NOTHING_TO_INTEGRATE", "candidate equals remote dev1.0 head")
            if subprocess.run(["git", "merge-base", "--is-ancestor", parent, commit], cwd=ROOT, check=False).returncode != 0:
                raise IntegrationRunError("INTEGRATION_RUN.NOT_FAST_FORWARD", "remote dev1.0 is not an ancestor of the candidate")
            # publish 在 dev1.0 分支上 ff 到 candidate；要求 HEAD 已是 candidate，避免导入后再移动本地分支。
            if _git("symbolic-ref", "--quiet", "HEAD") != DEV_REF or _git("rev-parse", "HEAD") != commit:
                raise IntegrationRunError(
                    "INTEGRATION_RUN.INTEGRATION_IDENTITY_INVALID",
                    "integrate must run on refs/heads/dev1.0 with HEAD == candidate (git merge --ff-only <lane head> first)",
                )
            return {"commit": commit, "parent": parent, "remoteHead": remote_head, "tree": _git("show", "-s", "--format=%T", commit)}

        identity = phases.run("preflight", preflight)
        summary["candidate"] = identity

        if args.mode == "integrate":
            imported = phases.run("import-bundle", lambda: _import_acceptance_bundle(
                bundle_dir=args.acceptance_bundle, commit=identity["commit"], tree=identity["tree"], parent=identity["parent"],
                args=args, keyring=keyring,
            ))
            manifest = imported["manifest"]
            candidate = imported["candidate"]
            claim_path = _store() / candidate["claimRef"]
            summary["candidate"].update({"candidateId": candidate["candidateId"], "candidateRef": dict(manifest["candidate"]), "claimRef": candidate["claimRef"]})
            summary["acceptanceBundle"] = {
                "path": str(args.acceptance_bundle), "bundleId": manifest["bundleId"], "runId": manifest.get("runId"),
                "laneBranch": manifest.get("laneBranch"), "mergedLanes": manifest.get("mergedLanes"),
                "baseline": manifest.get("baseline"), "beta": manifest.get("beta"),
                "importedFiles": imported["importedFiles"], "storeFiles": imported["storeFiles"],
            }
            summary["impactPlan"] = dict(manifest.get("impactPlan") or {})
            summary["dataReleases"] = manifest.get("dataReleases")
            summary["dataReleaseHandoffRef"] = manifest.get("dataReleaseHandoffRef")
            summary["sourceFact"] = dict(manifest["sourceFact"])
            summary["environments"] = {
                "alpha": {"environment": "alpha", "executed": True, "imported": True, "acceptance": dict(manifest["alphaFact"])},
                "beta": {"environment": "beta", "executed": bool((manifest.get("beta") or {}).get("executed")), "imported": True,
                         "reasonCode": (manifest.get("beta") or {}).get("reasonCode"), "acceptance": dict(manifest["betaFact"])},
            }
            admission_path = phases.run("admit", lambda: create_publish_admission(
                repository=ROOT, policy_path=POLICY, candidate_ref=manifest["candidate"], source_fact_refs=[manifest["sourceFact"]],
                alpha_fact_ref=manifest["alphaFact"], beta_fact_ref=manifest["betaFact"], expected_remote_oid=identity["parent"],
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

        lane_branch = _readiness_local_ref(args=args, commit=identity["commit"])
        merged_lanes = _merged_lanes(values=args.merged_lanes, lane_branch=lane_branch, commit=identity["commit"], remote=args.remote)
        summary["laneBranch"] = lane_branch
        summary["mergedLanes"] = merged_lanes
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
                                          impact_plan_digest=impact_digest, args=args, run_dir=run_dir, phases=phases, summary=summary,
                                          scopes=tuple(str(scope) for scope in plan["scopes"]))
        alpha_ref = phases.run("alpha.issue", lambda: _issue(
            environment="alpha", candidate_ref=candidate_ref, impact_plan_digest=impact_digest, evidence=alpha_evidence,
            status="passed", predecessor=None, profile=args.profile, args=args, signer=signer,
        ))
        summary["environments"]["alpha"]["acceptance"] = alpha_ref

        # Beta 只在用户显式 --beta 时真跑；未 opt-in 是政策选择，不由 ImpactPlan 深度改写原因码。
        beta_reason: str | None
        if args.beta:
            beta_evidence = _run_environment(environment="beta", profile=args.profile, candidate=candidate_identity,
                                             impact_plan_digest=impact_digest, args=args, run_dir=run_dir, phases=phases, summary=summary,
                                             previous_readiness=alpha_evidence["readiness"])
            beta_status, beta_reason = "passed", None
        else:
            beta_reason = BETA_OPTIONAL_BY_POLICY
            beta_evidence = _not_required_beta(candidate=candidate_identity, impact_plan_digest=impact_digest, impact_plan_path=plan_path,
                                               profile=args.profile, reason_code=beta_reason)
            beta_status = "not_required"
            summary["environments"]["beta"] = {"environment": "beta", "executed": False, "reasonCode": beta_reason, "integrationDepth": depth}
        beta_ref = phases.run("beta.issue", lambda: _issue(
            environment="beta", candidate_ref=candidate_ref, impact_plan_digest=impact_digest, evidence=beta_evidence,
            status=beta_status, predecessor=alpha_ref, profile=args.profile, args=args, signer=signer,
        ))
        summary["environments"]["beta"]["acceptance"] = beta_ref

        if detached:
            _git("checkout", "--quiet", original_branch.removeprefix("refs/heads/"))
            detached = False

        # 环境事实已 create-once 落盘；admission/publish 只属于 integration 工作区（gamma/prod 亦然）。
        # bundle 把全部 exact 事实按 store 相对路径复制出去，供 integration 逐字节导入。
        bundle_dir = phases.run("bundle", lambda: _write_acceptance_bundle(
            run_dir=run_dir, candidate_ref=candidate_ref, source_ref=source_ref, alpha_ref=alpha_ref, beta_ref=beta_ref,
            identity=identity, plan_path=plan_path, summary=summary, beta_status=beta_status, beta_reason=beta_reason,
            lane_branch=lane_branch, merged_lanes=merged_lanes, args=args,
        ))
        manifest = json.loads((bundle_dir / BUNDLE_MANIFEST).read_bytes())
        summary["terminal"] = "accepted"
        summary["acceptance"] = {"alphaFactRef": alpha_ref, "betaFactRef": beta_ref, "betaStatus": beta_status, "betaReasonCode": beta_reason,
                                 "bundle": {"path": str(bundle_dir), "ref": _output_ref(bundle_dir), "bundleId": manifest["bundleId"],
                                            "storeFiles": len(manifest["storeFiles"])},
                                 "note": "lane acceptance only: no publish admission, no dev1.0 write; integrate consumes the bundle"}
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
        bundle = (summary.get("acceptance") or {}).get("bundle") or {}
        print(json.dumps({"terminal": summary["terminal"], "runId": run_id, "summary": _output_ref(run_dir / "summary.json"),
                          **({"acceptanceBundle": bundle["path"]} if bundle else {}),
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
    if summary.get("mergedLanes"):
        lines.append("- mergedLanes: " + ", ".join(f"`{item['branch']}@{item['commit'][:12]}`" for item in summary["mergedLanes"]))
    for name, env in (summary.get("environments") or {}).items():
        package = env.get("package") or {}
        lines.append(f"- {name}: executed={env.get('executed', True)} imported={env.get('imported', False)} reason `{env.get('reasonCode') or '-'}` baseline `{package.get('baselineId', '-')}` sourceRevision `{package.get('sourceRevision', '-')}` acceptance `{(env.get('acceptance') or {}).get('ref', '-')}`")
    bundle = (summary.get("acceptance") or {}).get("bundle") or summary.get("acceptanceBundle")
    if bundle:
        lines.append(f"- acceptanceBundle: `{bundle.get('path')}` bundleId `{bundle.get('bundleId')}` storeFiles {bundle.get('storeFiles')}")
    if "admission" in summary:
        lines.append(f"- admission: `{summary['admission']['ref']}`")
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
