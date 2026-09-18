#!/usr/bin/env python3
"""「本地验收 → integration 发布 dev1.0」的 canonical 两阶段编排：

- `--mode acceptance`：在政策允许的 lane 或 integration 分支（head 即 candidate）对 exact candidate
  跑本地 readiness，并签发 typed Alpha/Beta `EnvironmentAcceptanceFact`（默认均为 `not_required`：
  Alpha=`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`，Beta=`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`；
  仅 `--alpha`/`--beta` 才真跑 live 环境），终态 `accepted`，不 admit、不 publish；同时把 candidate/claim/
  source fact/EAF 及其全部 exact 证据打成 portable acceptance bundle。Data release 的
  `ship --handoff-ref` admission 只在 live Alpha/Beta 时验证；integration不借用他方身份；
  `--baseline` 指定 ImpactPlan/readiness 的 exact parent（默认远端 dev1.0）；
  用户显式合并多个 lane head 后验收时用 `--merged-lanes` 记录来源。
- `--mode integrate`（默认）：在唯一 integration 工作区（分支 dev1.0，HEAD 即 candidate）只消费
  `--acceptance-bundle`：exact bytes 导入本工作树 store（create-once）、验签并复核 candidate 绑定与
  expected parent == 远端 before，然后 admit → publish（可选）。不启动任何环境、不需要 Data release
  输入；Gamma 与 prod canary 只在 integration 工作区、在 publish 之后推进。

只编排、不解释结论：环境动作一律经 `stackctl` 子进程，事实一律经
`quwoquan_ops.ci.scoped_candidate` / `environment_scheduler` 既有 create-once 入口。
任一步失败保留首个 typed blocker；finally 只清理本 invocation 创建的 exact runtime generation。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
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
    ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV,
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
from quwoquan_ops.cli.lib.output_paths import env_runs_root, output_root as _output_root
from quwoquan_ops.cli.lib.descriptor_safe_io import read_repo_relative_regular_single_link

POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
LOCAL_READINESS = ROOT / "quwoquan_ops/cli/local_readiness.py"
OUTPUT_ROOT = _output_root()
RUNS_ROOT = OUTPUT_ROOT / "env/repo/runs/integrate"
DEV_REF = "refs/heads/dev1.0"
NO_LIVE = NO_LIVE_ENVIRONMENT_REQUIRED
ALPHA_LIVE_DEFERRED = ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV
ENVIRONMENT_SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
DEFAULT_SIGNER = "quwoquan-environment-ops-local"
from quwoquan_ops.cli.integration_run_acceptance import validate_mode_inputs, validate_source_inputs, preflight_identity, record_imported_bundle
from quwoquan_ops.cli.integration_run_bundle import (
    ACCEPTANCE_BUNDLE_SCHEMA, BUNDLE_MANIFEST, BUNDLE_STORE_DIR, _EAF_NAMED_FIELDS,
    IntegrationRunError, _canonical_bytes, _sha256_hex, _bundle_path, _bundle_bytes,
    _bundle_put, _read_store_object, _source_receipt, _fact_evidence_refs,
    _report_fact_refs, _load_bundle_manifest, read_bundle_files, validate_bundle_identity,
    validate_manifest_candidate, validate_manifest_source, validate_manifest_fact,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    # canonical publish 对象含中文路径；关闭 quotePath 才能把 diff-tree 输出原样交给 ImpactPlanner。
    completed = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise IntegrationRunError("INTEGRATION_RUN.GIT", f"git {' '.join(args)}: {' '.join((completed.stderr or completed.stdout).split())}")
    return completed.stdout.strip()


def _is_ancestor(parent: str, commit: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", parent, commit], cwd=ROOT, check=False).returncode == 0


def _write_canonical(path: Path, value: Mapping[str, Any]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise IntegrationRunError("INTEGRATION_RUN.CREATE_CONFLICT", f"evidence slot already exists: {path}")
    path.write_bytes(_canonical_bytes(value) + b"\n")
    return {"ref": path.relative_to(_store()).as_posix(), "digest": exact_file_digest(path)}


def _store() -> Path:
    return store_root(repository=ROOT, policy_path=POLICY)


def _output_ref(path: Path) -> str:
    ref = path.absolute().relative_to(OUTPUT_ROOT.absolute()).as_posix()
    _bundle_path(OUTPUT_ROOT, ref)
    return ref


def _evidence_location(path: Path) -> tuple[Path, str]:
    """宿主输入只接纳 canonical env/runs；不把 live 根导回 worktree。"""
    absolute = path.absolute()
    roots = [(OUTPUT_ROOT, OUTPUT_ROOT)]
    roots.extend((env_runs_root(env), env_runs_root(env).parents[2]) for env in ("alpha", "beta", "gamma"))
    for boundary, root in roots:
        if absolute.is_relative_to(boundary.absolute()):
            ref = absolute.relative_to(root.absolute()).as_posix()
            _bundle_path(root, ref)
            return root, ref
    raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "evidence is outside canonical output/runs roots")


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
        self._report_bytes: bytes | None = None

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
        root, ref = _evidence_location(report)
        if not _bundle_path(root, ref).is_file():
            if self._report_bytes is not None:
                raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", "report disappeared during acceptance")
            return None
        raw = read_repo_relative_regular_single_link(root, ref, require_current_name=True)
        if self._report_bytes is not None and self._report_bytes != raw:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", "report changed during acceptance")
        self._report_bytes = raw
        return report, json.loads(raw)


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



# DEC-041：release 不携带类别；acceptance 只消费显式 immutable 身份。
HANDOFF_REF_RE = re.compile(r"^data/releases/[^/]+/producer_release_handoff\.json=sha256:[0-9a-f]{64}$")
UNCHANGED_DATA_CHANGE = "unchanged/no_data_change"
_DATA_ENGINEERING_OUTPUT = ROOT.parent / "data-engineering" / ".qwq_output"


def _canonical_release_attestation(root: Path, release_id: str) -> Path:
    return Path(root) / "data/releases" / release_id / "attestations/release.json"


def _root_owns_attestation(root: Path, release_id: str, attestation: Path) -> bool:
    """producer 树持有与 handed attestation 逐字节相同的 canonical 文件。"""
    local = _canonical_release_attestation(root, release_id)
    try:
        return local.is_file() and local.read_bytes() == attestation.read_bytes()
    except OSError:
        return False


def _producer_data_output_candidates(release_id: str, attestation: Path) -> list[Path]:
    """只枚举只读候选根；不扫描 latest，不把他树字节拷进本树。"""
    attestation = Path(attestation).expanduser().resolve()
    candidates: list[Path] = []
    suffix = ("data", "releases", release_id, "attestations", "release.json")
    parts = attestation.parts
    if len(parts) >= 5 and parts[-5:] == suffix:
        candidates.append(Path(*parts[:-5]))
    neighbor = attestation.parent / "data/releases" / release_id / "attestations/release.json"
    if neighbor.is_file():
        candidates.append(attestation.parent)
    candidates.append(OUTPUT_ROOT)
    if _DATA_ENGINEERING_OUTPUT.is_dir():
        candidates.append(_DATA_ENGINEERING_OUTPUT)
    return candidates


def _producer_data_output_root(release_id: str, attestation: Path, *, handoff_ref: str = "") -> Path:
    """定位 producer-owned Data output root；本树 `.qwq_output/data/releases` 不是准入条件。"""
    attestation = Path(attestation).expanduser().resolve()
    seen: set[Path] = set()
    for root in _producer_data_output_candidates(release_id, attestation):
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not _root_owns_attestation(resolved, release_id, attestation):
            continue
        if handoff_ref:
            _assert_producer_handoff(resolved, handoff_ref)
        return resolved
    raise IntegrationRunError(
        "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE",
        f"immutable release {release_id} is absent from producer-owned Data roots or its attestation differs; "
        "this worktree Data root is not required and trees must not be copied to impersonate identity",
    )


def _assert_producer_handoff(output_root: Path, handoff_ref: str) -> None:
    relative, digest = handoff_ref.rsplit("=", 1)
    path = Path(output_root) / relative
    try:
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise IntegrationRunError(
            "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE",
            f"producer handoff {relative} is unreadable under {output_root}: {exc}",
        ) from exc
    if actual != digest:
        raise IntegrationRunError(
            "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE",
            f"producer handoff digest differs from {handoff_ref}",
        )


def _release_id(attestation: Path) -> str:
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import _release_binding

    try:
        binding = _release_binding(str(attestation), label="acceptance")
    except (OSError, TypeError, ValueError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", str(exc)) from exc
    release_id = binding["releaseId"]
    _producer_data_output_root(release_id, attestation)
    return release_id


def _data_release_output_ref(path: Path) -> str:
    """readiness 可落在 producer output root；不得因此复制 Data 树。"""
    try:
        return _output_ref(path)
    except ValueError:
        return str(path.resolve())


def _activated_data_release_readiness(
    *, environment: str, release_id: str, handoff_ref: str, roots: Sequence[Path],
) -> Path | None:
    """已激活且 handoff 吻合时复用既有 readiness，避免重复 apply。"""
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = Path(root).expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        base = resolved / "env" / environment / "runs/data-release" / release_id
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*/release-readiness.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or str(payload.get("releaseId") or "") != release_id:
                continue
            recorded = str(payload.get("handoffRef") or payload.get("dataReleaseHandoffRef") or "")
            if recorded and recorded != handoff_ref:
                continue
            return path
    return None


def _app_acceptance_plan(app_platform: str = "all") -> dict[str, Any]:
    """Alpha 的声明计划随 acceptanceBinding 被 EAF 签名，不以设备集合授予范围。"""
    if app_platform not in {"all", "android", "ios"}:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "invalid Alpha app platform selector")
    return {"environment": "alpha", "appPlatform": app_platform,
            "requiredPlatforms": ["android", "ios"] if app_platform == "all" else [app_platform],
            "specRef": "specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004"}


def _acceptance_release_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """只比较有角色的 exact 输入，不把路径、releaseId 集合或源码身份当作内容身份。"""
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import _release_binding

    bindings = {}
    for role, path in (("candidate", args.release_attestation), ("rollback", args.rollback_release_attestation)):
        binding = _release_binding(str(path), label=role)
        bindings[role] = {key: value for key, value in binding.items() if key != "attestationRef"}
    return {"release": bindings, "handoffRef": _handoff_ref(args.release_handoff_ref, label="--release-handoff-ref"),
            "workload": args.workload,
            "appAcceptancePlan": _app_acceptance_plan(getattr(args, "app_platform", "all"))}


def _acceptance_binds_inputs(*, store: Path, fact: Mapping[str, Any], inputs: Mapping[str, Any]) -> bool:
    """绑定来自 EAF 签名覆盖的原始 named evidence；缺失的历史证据绝不从本次参数补造。"""
    try:
        runtime = _read_store_object(store, fact["runtimeIdentity"], "runtimeIdentity")
        binding = runtime.get("source", {}).get("acceptanceBinding", {})
        if binding.get("inputs") != inputs:
            return False
        # 原始 package 与 activation/readiness 必须仍是验收时的 exact bytes；不可用就正常重跑。
        for field in ("packageManifest", "releaseReadiness"):
            _bundle_bytes(OUTPUT_ROOT, binding[field])
        return True
    except (IntegrationRunError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def _handoff_ref(value: str, *, label: str) -> str:
    """消费producer immutable exact ref；通用会话handoff不再作为Data第二准入。"""

    ref = str(value or "").strip()
    if not HANDOFF_REF_RE.fullmatch(ref):
        raise IntegrationRunError(
            "INTEGRATION_RUN.INPUT_INVALID",
            f"{label} must bind data/releases/<releaseId>/producer_release_handoff.json=sha256:<digest> "
            f"(got {ref[:48] or '-'}); use exact producer release bytes",
        )
    return ref


def _content_release(*args: str, log_dir: Path, label: str, output_root: Path | None = None) -> None:
    """环境发布仅经 Ops-owned stackctl content-release。跨树时 QWQ_OUTPUT_ROOT 指向 producer root。"""

    env = {"QWQ_OUTPUT_ROOT": str(output_root)} if output_root is not None else None
    result = _stackctl("content-release", *args, env=env, log_dir=log_dir)
    if result.exit_code != 0:
        detail = " ".join(str(item) for item in result.payload.get("details", []))[-400:]
        raise IntegrationRunError(
            "INTEGRATION_RUN.DATA_RELEASE_FAILED",
            f"stackctl content-release {label} failed: {detail}",
        )


def _release_readiness_path(output_root: Path, environment: str, release_id: str, verify_run: str) -> Path:
    return Path(output_root) / "env" / environment / "runs/data-release" / release_id / verify_run / "release-readiness.json"


def _apply_data_release(*, environment: str, run_id: str, args: argparse.Namespace, log_dir: Path,
                        previous_readiness: Path | None, candidate_root: Path | None = None) -> Path:
    """candidate release 进入环境：producer root 只读 admit；已激活且 handoff 吻合则跳过重复 apply。

    handoff-ref 是现役 Data CLI 唯一的 release 准入身份；attestation 只用于 stackctl package 的候选绑定，
    两者必须指向同一 releaseId（由 ship 侧对 handoff 做 exact 校验）。返回 release-readiness 回执路径。
    """

    release_id = _release_id(args.release_attestation)
    handoff_ref = _handoff_ref(args.release_handoff_ref, label="--release-handoff-ref")
    producer_root = _producer_data_output_root(release_id, args.release_attestation)
    handoff_path = producer_root / handoff_ref.rsplit("=", 1)[0]
    if handoff_path.is_file():
        _assert_producer_handoff(producer_root, handoff_ref)
    import_run, activate_run, verify_run = f"{run_id}-import", f"{run_id}-activate", f"{run_id}-verify"
    existing = _activated_data_release_readiness(
        environment=environment, release_id=release_id, handoff_ref=handoff_ref,
        roots=(OUTPUT_ROOT, producer_root),
    )
    if existing is not None:
        return existing
    candidate_args = ("--runtime-candidate-root", str(candidate_root)) if candidate_root is not None else ()
    _content_release("apply", "--handoff-ref", handoff_ref, "--env", environment, "--run-id", import_run,
               *candidate_args, "--import", "--full-sync", log_dir=log_dir, label=f"{environment}-apply",
               output_root=producer_root)
    _content_release("activate", "--handoff-ref", handoff_ref, "--env", environment, "--import-run-id", import_run,
               "--run-id", activate_run, *candidate_args, log_dir=log_dir, label=f"{environment}-activate",
               output_root=producer_root)
    _bootstrap_premium_pool(environment=environment, release_id=release_id, import_run=import_run,
                            attestation=args.release_attestation, log_dir=log_dir)
    # ship verify 的 --import-run-id 指向 completed 的 activate run（其 result.importRunId 再指回 apply run）；
    # 传 apply run 会因 result status=prepared 被拒（"completed activation predecessor result status 不一致"）。
    verify_args = ["verify", "--handoff-ref", handoff_ref, "--env", environment, "--import-run-id", activate_run,
                   "--run-id", verify_run, *candidate_args]
    if previous_readiness is not None:
        try:
            previous_ref = _output_ref(previous_readiness)
        except ValueError:
            previous_ref = str(previous_readiness)
        verify_args.extend(["--previous-environment-readiness", previous_ref])
    _content_release(*verify_args, log_dir=log_dir, label=f"{environment}-verify", output_root=producer_root)
    readiness = _release_readiness_path(producer_root, environment, release_id, verify_run)
    if not readiness.is_file():
        fallback = _release_readiness_path(OUTPUT_ROOT, environment, release_id, verify_run)
        if fallback.is_file():
            readiness = fallback
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

    acceptance可在政策允许的lane或integration来源执行；始终读取实际当前分支并
    验证其head等于candidate，不借用另一分支或把来源身份当作验收资格。
    """
    if args.mode != "acceptance":
        return DEV_REF
    from quwoquan_ops.cli.lib.agent_governance_contract import allowed_delivery_sources

    branch_ref = _git("symbolic-ref", "--quiet", "HEAD")
    allowed_refs = {f"refs/heads/{name}" for name in allowed_delivery_sources(ROOT)}
    if branch_ref not in allowed_refs or _git("rev-parse", branch_ref) != commit:
        raise IntegrationRunError(
            "INTEGRATION_RUN.LANE_IDENTITY_INVALID",
            f"acceptance requires a declared source branch whose head is the candidate (branch={branch_ref or 'detached'})",
        )
    return branch_ref


def _local_readiness(*, level: str, parent: str, commit: str, run_dir: Path, args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    validate_source_inputs(args, repository=ROOT)
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
    root, ref = _evidence_location(path)
    assert result._report_bytes is not None
    digest = _sha256_hex(result._report_bytes)
    raw = _bundle_bytes(root, {"ref": ref, "digest": digest})
    # 只复制被消费的整份报告，不改其内嵌路径；store 相对 ref 随 acceptance bundle 携带。
    stored_ref = f"runtime-reports/{digest.removeprefix('sha256:')}/{ref}"
    _bundle_put(_store(), stored_ref, raw)
    _bundle_bytes(root, {"ref": ref, "digest": digest})
    return {"command": result.command, "exitCode": result.exit_code, "reportRoot": "store",
            "reportRef": stored_ref, "reportDigest": digest}


def _case_results_from_verify(*, verify: StackctlResult, environment: str, profile: str, candidate: Mapping[str, str],
                              runtime: Mapping[str, str], evidence_dir: Path) -> list[dict[str, str]]:
    report = verify.report_json()
    if report is None:
        raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_MISSING", "stackctl verify produced no report.json")
    _, payload = report
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise IntegrationRunError("INTEGRATION_RUN.VERIFY_REPORT_MISSING", "stackctl verify report has no checks")
    source = _report_source(verify)
    report_sha = source["reportDigest"].removeprefix("sha256:")
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
            "receiptRef": source["reportRef"],
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

    app_platform = getattr(args, "app_platform", "all") if environment == "alpha" else "all"
    _app_acceptance_plan(app_platform)

    def package() -> StackctlResult:
        return _stackctl(
            "package", "--env", environment, "--include-services", "--app-platform", app_platform,
            "--release-attestation", str(args.release_attestation),
            "--rollback-release-attestation", str(args.rollback_release_attestation), log_dir=log_dir,
        )

    result = package()
    details = " ".join(str(item) for item in (result.payload.get("details") or []))
    if result.exit_code != 0 and "App dependency bundle" in details:
        phases.run(f"{environment}.app-dependency-sync", lambda: _require_ok(
            _stackctl("app-dependency-sync", "--platform", app_platform, log_dir=log_dir / "app-dependency-sync"), "INTEGRATION_RUN.APP_DEPENDENCY_SYNC_FAILED",
        ))
        result = package()
    return _require_ok(result, "INTEGRATION_RUN.PACKAGE_FAILED")


def _alpha_offline_pages(*, candidate: Mapping[str, Any], candidate_ref: Mapping[str, str],
                         args: argparse.Namespace, run_dir: Path, phases: Phases) -> dict[str, Any]:
    """服务启动前执行声明平台页面；证据保持 rehearsal，不补写服务 runtime identity。"""
    from quwoquan_ops.cli.lib.integration_app_launch import offline_receipt_evidence

    app_platform = getattr(args, "app_platform", "all")
    requested = tuple(_app_acceptance_plan(app_platform)["requiredPlatforms"])
    available = {"android": args.android_device_id, "ios": args.ios_device_id}
    devices = {platform: available[platform] for platform in requested}
    if not all(devices.values()) or len(set(devices.values())) != len(devices):
        raise IntegrationRunError(
            "INTEGRATION_RUN.APP_LAUNCH_DEVICE_UNAVAILABLE",
            f"explicit distinct device ids are required for app-platform={app_platform}",
        )
    receipts = {}
    evidence_root = None
    first_error = None

    def run_platform(platform: str, device: str, observed: dict[str, Any]) -> None:
        nonlocal evidence_root
        result = _stackctl(
            "app-content-uat", "--targets", "alpha-local", "--platform", "android" if platform == "android" else "ios-simulator",
            "--device-id", device, "--candidate", f"{candidate_ref['ref']}={candidate_ref['digest']}",
            log_dir=run_dir / "offline" / platform,
        )
        observed["result"] = dict(result.payload)
        command_error = None
        try:
            _require_ok(result, "INTEGRATION_RUN.APP_LAUNCH_FAILED")
        except IntegrationRunError as exc:
            # 上游 typed 首错原样保留，不被通用 summary 或后续缺报告覆盖。
            blocker = result.payload.get("firstBlocker")
            command_error = IntegrationRunError(exc.code, f"{blocker}: {exc.detail}") if blocker else exc
        try:
            if result.report_dir is None:
                raise ValueError("offline receipt directory is absent")
            path = result.report_dir / "receipt.json"
            root, ref = _evidence_location(path)
            observed["receipt"] = {"ref": ref, "digest": exact_file_digest(path)}
            if evidence_root is not None and root != evidence_root:
                raise ValueError("offline platforms use different evidence roots")
            evidence_root = root
            receipts[platform] = observed["receipt"]
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            if command_error is not None:
                raise command_error from exc
            raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", str(exc)) from exc
        if command_error is not None:
            raise command_error

    for platform, device in devices.items():
        observed: dict[str, Any] = {}
        try:
            phases.run(f"alpha.offline-{platform}", lambda: run_platform(platform, device, observed))
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            error = exc if isinstance(exc, IntegrationRunError) else IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", str(exc))
            observed["blocker"] = {"code": error.code, "detail": error.detail}
            if first_error is None:
                first_error = error
        finally:
            # phase 状态来自实际执行；保留每端 result/receipt，而非把另一端成功升级为整体通过。
            phases.items[-1].update(observed)
    if first_error is not None:
        raise first_error
    try:
        evidence = offline_receipt_evidence(root=evidence_root, receipts=receipts, candidate=candidate,
                                            devices=devices, required_platforms=requested)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", str(exc)) from exc
    # 将原始闭包 exact 复制到 store；不改 raw 路径、摘要或 nonPromotable。
    prefix = f"offline-page-evidence/{candidate['candidateId'].removeprefix('sha256:')}"
    files = [(exact, _bundle_bytes(evidence_root, exact)) for exact in evidence["files"]]
    for exact, raw in files:
        _bundle_put(_store() / prefix, exact["ref"], raw)
    # 完整复制后再验源闭包；漂移不可返回可签发的 axis，也不回写/重签任何源 receipt。
    for exact, _ in files:
        _bundle_bytes(evidence_root, exact)
    return {"root": prefix, "receipts": receipts, "devices": devices, "files": evidence["files"],
            "cases": [{"ref": prefix + "/" + exact["ref"], "digest": exact["digest"]} for exact in evidence["cases"]],
            "required": True, "nonPromotable": True, "caseCount": len(evidence["cases"])}


def _validate_offline_axis(*, store: Path, axis: Mapping[str, Any], candidate: Mapping[str, Any],
                           app_plan: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    from quwoquan_ops.cli.lib.integration_app_launch import offline_receipt_evidence
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import OFFLINE_REQUIRED_CASES

    try:
        expected_root = f"offline-page-evidence/{candidate['candidateId'].removeprefix('sha256:')}"
        plan = _app_acceptance_plan() if app_plan is None else app_plan
        if plan != _app_acceptance_plan(plan.get("appPlatform", "")):
            raise ValueError("offline acceptance platform plan is missing or drifted")
        expected_platforms = tuple(plan["requiredPlatforms"])
        if (set(axis.get("devices") or {}) != set(expected_platforms)
                or set(axis.get("receipts") or {}) != set(expected_platforms)
                or axis.get("root") != expected_root or axis.get("required") is not True
                or axis.get("nonPromotable") is not True
                or axis.get("caseCount") != len(expected_platforms) * len(OFFLINE_REQUIRED_CASES)):
            raise ValueError("required offline evidence axis is missing or drifted")
        evidence = offline_receipt_evidence(root=_bundle_path(store, expected_root), receipts=axis["receipts"],
                                            candidate=candidate, devices=axis["devices"], required_platforms=expected_platforms)
        expected_cases = [{"ref": expected_root + "/" + exact["ref"], "digest": exact["digest"]} for exact in evidence["cases"]]
        if axis["files"] != evidence["files"] or axis.get("cases") != expected_cases:
            raise ValueError("offline evidence closure drifted")
        return [{"ref": expected_root + "/" + exact["ref"], "digest": exact["digest"]} for exact in evidence["files"]]
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", str(exc)) from exc


def _alpha_content_readback_cases(*, candidate: Mapping[str, str], runtime: Mapping[str, str], evidence_dir: Path,
                                  log_dir: Path, args: argparse.Namespace, env_summary: dict[str, Any]) -> list[dict[str, str]]:
    """独立服务/API 必需轴：只消费服务 authority 和 candidate Data attestation。"""
    from quwoquan_ops.cli.lib.integration_app_launch import CONTENT_READBACK_SPEC_REF, case_result, content_readback

    started = _now()
    readback = content_readback(target="alpha-local", expected_release=_acceptance_release_inputs(args)["release"]["candidate"])
    receipt = log_dir / "content-readback-alpha.json"
    receipt.write_text(json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    env_summary["contentReadback"] = {"passed": readback["passed"], "receipt": _output_ref(receipt), "failures": readback["failures"]}
    if not readback["passed"]:
        raise IntegrationRunError("INTEGRATION_RUN.CONTENT_READBACK_FAILED", "; ".join(readback["failures"]))
    completed = _now()
    result = case_result(
        case_id="content-readback:home-feed+video-book", object_id="content-readback:alpha:home-feed+video-book",
        spec_ref=CONTENT_READBACK_SPEC_REF, target_id="content.feed.list", environment="alpha", candidate=candidate,
        runtime=runtime, started_at=started, completed_at=completed,
        artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(), receipt_ref=_output_ref(receipt),
    )
    return [_write_canonical(evidence_dir / "cases" / "content-readback.json", validate_readiness_case_result(result, generated_at=completed))]


def _run_environment(*, environment: str, profile: str, candidate: Mapping[str, str], impact_plan_digest: str,
                     args: argparse.Namespace, run_dir: Path, phases: Phases, summary: dict[str, Any],
                     previous_readiness: Path | None = None, scopes: Sequence[str] = (),
                     offline_pages: Mapping[str, Any] | None = None) -> dict[str, Any]:
    target = f"{environment}-local"
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / environment
    log_dir = run_dir / environment
    env_summary: dict[str, Any] = {"environment": environment, "target": target, "reports": {}}
    summary["environments"][environment] = env_summary
    ownership: dict[str, Any] = {}
    app_cases: list[dict[str, str]] = []
    release_inputs = _acceptance_release_inputs(args)
    if environment == "alpha" and "app" in scopes:
        _validate_offline_axis(store=store, axis=offline_pages or {}, candidate=candidate,
                               app_plan=_app_acceptance_plan(getattr(args, "app_platform", "all")))
        env_summary["offlinePages"] = dict(offline_pages or {})
    try:
        package = phases.run(f"{environment}.package", lambda: _package_with_dependency_recovery(
            environment=environment, args=args, log_dir=log_dir, phases=phases,
        ))
        env_summary["reports"]["package"] = _report_source(package)
        active_path = Path(os.environ.get("QWQ_DEPLOY_WORK_ROOT", str(Path.home() / ".cache/quwoquan/deploy"))) / target / "active-runtime-candidate.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        baseline = str(active.get("baselineId") or "")
        manifest_bytes = (Path(str(active["candidateDir"])) / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        if {role: {key: value for key, value in binding.items() if key != "attestationRef"}
                for role, binding in manifest.get("release", {}).items()} != release_inputs["release"]:
            raise IntegrationRunError("INTEGRATION_RUN.PACKAGE_IDENTITY_INVALID", "package release inputs differ from acceptance inputs")
        package_snapshot = log_dir / "package-manifest.json"
        _bundle_put(OUTPUT_ROOT, package_snapshot.relative_to(OUTPUT_ROOT).as_posix(), manifest_bytes)
        packaged_revision = str(manifest.get("sourceRevision") or "")
        _assert_package_identity(packaged_revision=packaged_revision, candidate_commit=candidate["commit"], package=package)
        env_summary["package"] = {"baselineId": baseline, "sourceRevision": packaged_revision, "packageDigest": manifest.get("packageDigest"), "imageDigest": manifest.get("imageDigest"),
                                  "reusedFromAncestor": packaged_revision != candidate["commit"]}

        up = phases.run(f"{environment}.up", lambda: _stackctl("up", "--target", target, "--skip-app", "--workload", args.workload, log_dir=log_dir))
        ownership = dict(up.payload)
        _require_ok(up, "INTEGRATION_RUN.UP_FAILED")
        if ownership.get("runtimeCreated") is not True or not ownership.get("instanceGeneration"):
            raise IntegrationRunError("INTEGRATION_RUN.UP_FAILED", "acceptance requires an owned runtime generation; reused/unknown runtime is preserved")
        env_summary["reports"]["up"] = _report_source(up)
        # health 的 release_active 层要求该环境已导入并验证 candidate Data release（release-readiness 回执）。
        readiness = phases.run(f"{environment}.data-release", lambda: _apply_data_release(
            environment=environment, run_id=summary["runId"], args=args, log_dir=log_dir, previous_readiness=previous_readiness,
            candidate_root=Path(str(active["candidateDir"])),
        ))
        env_summary["dataRelease"] = {"readiness": _data_release_output_ref(readiness), "digest": exact_file_digest(readiness)}
        health = phases.run(f"{environment}.health", lambda: _require_ok(_stackctl("health", "--target", target, "--scope", "full", log_dir=log_dir), "INTEGRATION_RUN.HEALTH_FAILED"))
        env_summary["reports"]["health"] = _report_source(health)
        runtime = _health_runtime(health=health, environment=environment, candidate=candidate, expected_baseline=baseline)
        env_summary["runtimeIdentity"] = runtime
        if environment == "alpha":
            app_cases = phases.run(f"{environment}.content-readback", lambda: _alpha_content_readback_cases(
                candidate=candidate, runtime=runtime, evidence_dir=evidence_dir, log_dir=log_dir, args=args, env_summary=env_summary,
            ))
        verify = phases.run(f"{environment}.verify", lambda: _require_ok(_stackctl("verify", "--env", environment, "--target", target, "--kind", "all", "--profile", profile, log_dir=log_dir), "INTEGRATION_RUN.VERIFY_FAILED"))
        env_summary["reports"]["verify"] = _report_source(verify)
        inspect_scope = "runtime" if profile in {"smoke", "integration"} else "all"
        inspect = phases.run(f"{environment}.inspect", lambda: _require_ok(_stackctl("inspect", "--target", target, "--scope", inspect_scope, log_dir=log_dir), "INTEGRATION_RUN.INSPECT_FAILED"))
        env_summary["reports"]["inspect"] = _report_source(inspect)
        doctor = phases.run(f"{environment}.doctor", lambda: _require_ok(_stackctl("doctor", "--target", target, log_dir=log_dir), "INTEGRATION_RUN.DOCTOR_FAILED"))
        env_summary["reports"]["doctor"] = _report_source(doctor)
        health_payload = health.report_json()[1]  # type: ignore[index]
        provider_ok = _provider_ready(health_payload)
    finally:
        primary_failure = sys.exc_info()[0] is not None
        if ownership.get("runtimeCreated") is True and ownership.get("instanceGeneration"):
            try:
                down = phases.run(f"{environment}.down", lambda: _require_ok(_stackctl(
                    "down", "--target", target, "--workload", args.workload,
                    "--expected-generation", str(ownership["instanceGeneration"]), log_dir=log_dir,
                ), "INTEGRATION_RUN.DOWN_FAILED"))
                env_summary["reports"]["down"] = _report_source(down)
            except Exception as exc:
                if not primary_failure:
                    raise
                env_summary["cleanupBlocker"] = str(exc)
        else:
            env_summary["cleanupDisposition"] = "preserved_not_owned"
    status_after = phases.run(f"{environment}.lease-readback", lambda: _stackctl("status", "--target", target, log_dir=log_dir))
    locks = status_after.payload.get("localRuntimeLocks")
    if locks not in ([], None):
        raise IntegrationRunError("INTEGRATION_RUN.LEASE_OPEN", f"{target} still holds runtime locks after down: {locks}")
    env_summary["reports"]["leaseReadback"] = _report_source(status_after)
    if not provider_ok:
        raise IntegrationRunError("INTEGRATION_RUN.PROVIDER_NOT_READY", f"{environment} provider composition is not ready in health evidence")

    if _acceptance_release_inputs(args) != release_inputs:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "release inputs changed during acceptance")
    acceptance_binding = {
        "inputs": release_inputs,
        "packageManifest": {"ref": package_snapshot.relative_to(OUTPUT_ROOT).as_posix(), "digest": exact_file_digest(package_snapshot)},
        "releaseReadiness": {"ref": _data_release_output_ref(readiness), "digest": exact_file_digest(readiness)},
    }

    def evidence(role: str, status: str, source: StackctlResult) -> dict[str, str]:
        return _write_canonical(evidence_dir / f"{role}.json", _evidence_object(
            role=role, status=status, environment=environment, profile=profile, candidate=candidate,
            impact_plan_digest=impact_plan_digest,
            source={**_report_source(source), **({"acceptanceBinding": acceptance_binding,
                    **({"offlinePages": dict(offline_pages)} if offline_pages is not None else {})} if role == "runtime-identity" else {})},
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
    if offline_pages is not None:
        cases.extend(offline_pages["cases"])
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


def _not_required_environment(*, environment: str, candidate: Mapping[str, str], impact_plan_digest: str,
                              impact_plan_path: Path, profile: str, reason_code: str) -> dict[str, Any]:
    """不真跑时的 typed not_required 证据：原因码绑定 candidate 与 ImpactPlan，不从 skipped 推导。"""
    store = _store()
    evidence_dir = store / "environment-evidence" / candidate["candidateId"].removeprefix("sha256:") / environment
    plan_sha = hashlib.sha256(impact_plan_path.read_bytes()).hexdigest()
    source = {"basis": reason_code, "executed": False, "impactPlanRef": _output_ref(impact_plan_path), "impactPlanSha256": plan_sha}

    def evidence(role: str, status: str) -> dict[str, str]:
        return _write_canonical(evidence_dir / f"{role}.json", _evidence_object(
            role=role, status=status, environment=environment, profile=profile, candidate=candidate,
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
        "caseId": f"{environment}-depth-evaluation",
        "producer": "ops",
        "layer": "environment_acceptance",
        "status": "passed",
        "target": {"kind": "operation", "id": "derive_integration_depth"},
        "commitSha": candidate["commit"],
        "contractGraphSourceHash": plan_sha,
        "deploymentTarget": f"{environment}-local",
        "baselineId": "impact-plan-not-required",
        "packageDigest": "sha256:" + plan_sha,
        "configurationDigest": "sha256:" + plan_sha,
        "candidateManifestSha256": plan_sha,
        "candidateDigest": candidate["candidateId"],
        "environment": environment,
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


def _not_required_alpha(*, candidate: Mapping[str, str], impact_plan_digest: str, impact_plan_path: Path, profile: str,
                        reason_code: str = ALPHA_LIVE_DEFERRED) -> dict[str, Any]:
    """源码合入默认不启 Alpha live；环境/UAT/Data 激活后移到已发布 SHA。"""
    return _not_required_environment(
        environment="alpha", candidate=candidate, impact_plan_digest=impact_plan_digest,
        impact_plan_path=impact_plan_path, profile=profile, reason_code=reason_code,
    )


def _not_required_beta(*, candidate: Mapping[str, str], impact_plan_digest: str, impact_plan_path: Path, profile: str,
                       reason_code: str = NO_LIVE) -> dict[str, Any]:
    """Beta 不真跑时的 typed not_required 证据：`reason_code` 记录真实原因——ImpactPlan 判定无需 live
    Beta（`IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED`），或 ImpactPlan 判定敏感但用户未 `--beta` opt-in
    （`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`）。两者都绑定 candidate 与 ImpactPlan，不从 skipped 推导。"""
    return _not_required_environment(
        environment="beta", candidate=candidate, impact_plan_digest=impact_plan_digest,
        impact_plan_path=impact_plan_path, profile=profile, reason_code=reason_code,
    )


_CANDIDATE_SCHEMA = "quwoquan_ops.exact_integration_candidate.v1"
_ACCEPTANCE_SCHEMA = "quwoquan_ops.environment_acceptance_fact.v2"


def _reusable_acceptance(*, store: Path, candidate_id: str, environment: str, profile: str,
                         commit: str, tree: str, impact_plan_digest: str, allowed_status: set[str],
                         expected_reason_code: str | None = None, predecessor: Mapping[str, str] | None = None,
                         signature_verifier: Any = None, expected_signer_identity: str | None = None,
                         release_inputs: Mapping[str, Any] | None = None) -> dict[str, str] | None:
    """同一 exact candidate 的事实必须未过期、可晋级并通过引用/签名校验，Beta 还须匹配本次政策与前驱。"""

    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_id):
        return None
    try:
        path = _bundle_path(store, f"environment-execution/acceptance/{candidate_id.removeprefix('sha256:')}/{environment}.json")
        if not path.is_file():
            return None
        raw = path.read_bytes()
        fact = validate_environment_acceptance_fact(
            json.loads(raw), store_root=store, verify_references=True, accepted_at=datetime.now(timezone.utc),
            signature_verifier=signature_verifier, expected_signer_identity=expected_signer_identity,
        )
        _report_fact_refs(store=store, fact=fact)
    except (IntegrationRunError, EnvironmentSchedulerError, OSError, ValueError, KeyError, TypeError):
        return None
    binding = fact.get("candidate") if isinstance(fact.get("candidate"), Mapping) else {}
    if (
        fact.get("schema") != _ACCEPTANCE_SCHEMA
        or fact.get("environment") != environment
        or fact.get("profile") != profile
        or fact.get("status") not in allowed_status
        or fact.get("reasonCode") != expected_reason_code
        or fact.get("predecessor") != predecessor
        or fact.get("nonPromotable") is not False
        or fact.get("impactPlanDigest") != impact_plan_digest
        or binding.get("candidateId") != candidate_id
        or binding.get("commit") != commit
        or binding.get("tree") != tree
    ):
        return None
    if release_inputs is not None and fact.get("status") == "passed" and not _acceptance_binds_inputs(store=store, fact=fact, inputs=release_inputs):
        return None
    return {"ref": path.relative_to(store).as_posix(), "digest": _sha256_hex(raw)}


def _validate_offline_fact_case_refs(*, axis: Mapping[str, Any], fact: Mapping[str, Any]) -> None:
    required = {item["ref"] for item in axis.get("cases", [])}
    present = {item["ref"] for item in fact["caseResultRefs"]}
    if not required.issubset(present):
        raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", "Alpha fact lacks required offline raw cases")


def _validate_alpha_readback_case(*, cases: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any]) -> None:
    expected = {"caseId": "content-readback:home-feed+video-book", "producer": "ops", "layer": "environment_acceptance",
                "status": "passed", "candidateDigest": candidate["candidateId"], "commitSha": candidate["commit"]}
    if not any(all(case.get(key) == value for key, value in expected.items()) for case in cases):
        raise IntegrationRunError("INTEGRATION_RUN.CONTENT_READBACK_FAILED", "offline pages cannot replace required Alpha API readback")


def _offline_fact_refs(*, store: Path, fact: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[dict[str, str]]:
    """离线轴受 Alpha EAF runtimeIdentity 的签名摘要覆盖，导出/导入/复用均重新验真。"""
    if fact.get("environment") != "alpha" or fact.get("status") != "passed":
        return []
    runtime = _read_store_object(store, fact["runtimeIdentity"], "runtimeIdentity")
    axis = (runtime.get("source") or {}).get("offlinePages")
    app_required = bool(classify_impacts(candidate.get("paths", []))["scopes"]["app"])
    if axis is None and not app_required:
        return []
    app_plan = (runtime.get("source") or {}).get("acceptanceBinding", {}).get("inputs", {}).get("appAcceptancePlan")
    if not isinstance(app_plan, Mapping):
        raise IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", "signed Alpha acceptance platform plan is missing")
    refs = _validate_offline_axis(store=store, axis=axis or {}, candidate=candidate, app_plan=app_plan)
    _validate_offline_fact_case_refs(axis=axis or {}, fact=fact)
    service_cases = [_read_store_object(store, exact, "Alpha raw case") for exact in fact["caseResultRefs"]]
    _validate_alpha_readback_case(cases=service_cases, candidate=candidate)
    return refs


def _existing_candidate(*, exact: str, identity: Mapping[str, str], impact_plan_digest: str,
                        owner_identity: str = "", store: Path | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    from quwoquan_ops.ci.scoped_candidate.core import _load_exact_ref, exact_digest

    try:
        ref, digest = exact.rsplit("=", 1)
        candidate_ref = {"ref": ref, "digest": digest}
        root = store if store is not None else _store()
        candidate, _ = _load_exact_ref(root, candidate_ref, "candidate")
        if (candidate.get("schema") != _CANDIDATE_SCHEMA
                or candidate.get("candidateId") != exact_digest({k: v for k, v in candidate.items() if k != "candidateId"})
                or any(candidate.get(key) != identity[field] for key, field in (("commit", "commit"), ("tree", "tree"), ("expectedParent", "parent")))
                or candidate.get("impactPlanDigest") != impact_plan_digest
                or (owner_identity and candidate.get("ownerIdentityRef") != owner_identity)):
            raise ValueError("existing candidate commit/tree/parent/ImpactPlan/owner drifted")
        claim, _ = _load_exact_ref(root, {"ref": candidate["claimRef"], "digest": candidate["claimDigest"]}, "claim")
        if (claim.get("paths") != candidate.get("paths") or claim.get("expectedParent") != candidate["expectedParent"]
                or claim.get("ownerIdentityRef") != candidate.get("ownerIdentityRef")):
            raise ValueError("existing candidate claim scope or owner drifted")
        return candidate_ref, candidate
    except (KeyError, TypeError, ValueError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", str(exc)) from exc


def _candidate_matches_caller(*, store: Path, path: Path, raw: bytes, identity: Mapping[str, str],
                              impact_plan_digest: str, owner_identity: str) -> bool:
    try:
        _existing_candidate(exact=f"{path.relative_to(store).as_posix()}={_sha256_hex(raw)}", identity=identity,
                            impact_plan_digest=impact_plan_digest, owner_identity=owner_identity, store=store)
        return True
    except (IntegrationRunError, ScopedCandidateError):
        return False


def _reusable_offline_evidence(store: Path, alpha: Mapping[str, str], candidate: Mapping[str, Any]) -> bool:
    try:
        _offline_fact_refs(store=store, fact=_read_store_object(store, alpha, "alpha"), candidate=candidate)
        return True
    except (IntegrationRunError, KeyError, OSError, ValueError):
        return False


def _find_reusable_candidate(*, store: Path, commit: str, tree: str, parent: str, impact_plan_digest: str,
                             profile: str, beta: bool = False, live_alpha: bool = True,
                             signature_verifier: Any = None,
                             expected_signer_identity: str | None = None,
                             release_inputs: Mapping[str, Any] | None = None,
                             owner_identity: str = "") -> dict[str, Any] | None:
    """寻找同源码及（live 时）exact release/rollback/handoff 输入、持有可复用 Alpha 的 candidate。

    live Alpha 只消费 passed；源码合入默认消费 typed deferred，若已有 passed 且 Data 绑定仍可核验则也可复用。
    Beta opt-in 只消费 passed；未 opt-in 只消费政策 not_required。后者遇到占用的旧 Beta slot 必须新建 candidate，不改写 create-once 事实。
    """

    candidates_root = store / "candidates"
    if not candidates_root.is_dir():
        return None
    if live_alpha and not release_inputs:
        return None
    matches: list[dict[str, Any]] = []
    for path in sorted(candidates_root.glob("*.json")):
        try:
            path = _bundle_path(store, path.relative_to(store).as_posix())
            raw = path.read_bytes()
            body = json.loads(raw)
        except (IntegrationRunError, OSError, ValueError):
            continue
        expected = {"schema": _CANDIDATE_SCHEMA, "commit": commit, "tree": tree,
                    "expectedParent": parent, "impactPlanDigest": impact_plan_digest}
        if not isinstance(body, Mapping) or any(body.get(key) != value for key, value in expected.items()):
            continue
        if not _candidate_matches_caller(store=store, path=path, raw=raw, identity={"commit": commit, "tree": tree, "parent": parent},
                                         impact_plan_digest=impact_plan_digest, owner_identity=owner_identity):
            continue
        candidate_id = str(body.get("candidateId") or "")
        if live_alpha:
            alpha = _reusable_acceptance(
                store=store, candidate_id=candidate_id, environment="alpha", profile=profile,
                commit=commit, tree=tree, impact_plan_digest=impact_plan_digest, allowed_status={"passed"},
                signature_verifier=signature_verifier, expected_signer_identity=expected_signer_identity,
                release_inputs=release_inputs,
            )
            if alpha is None or not _reusable_offline_evidence(store, alpha, body):
                continue
        else:
            alpha = _reusable_acceptance(
                store=store, candidate_id=candidate_id, environment="alpha", profile=profile,
                commit=commit, tree=tree, impact_plan_digest=impact_plan_digest, allowed_status={"not_required"},
                expected_reason_code=ALPHA_LIVE_DEFERRED,
                signature_verifier=signature_verifier, expected_signer_identity=expected_signer_identity,
            )
            if alpha is None and release_inputs:
                passed = _reusable_acceptance(
                    store=store, candidate_id=candidate_id, environment="alpha", profile=profile,
                    commit=commit, tree=tree, impact_plan_digest=impact_plan_digest, allowed_status={"passed"},
                    signature_verifier=signature_verifier, expected_signer_identity=expected_signer_identity,
                    release_inputs=release_inputs,
                )
                if passed is not None and _reusable_offline_evidence(store, passed, body):
                    alpha = passed
            if alpha is None:
                continue
        beta_ref = _reusable_acceptance(
            store=store, candidate_id=candidate_id, environment="beta", profile=profile,
            commit=commit, tree=tree, impact_plan_digest=impact_plan_digest,
            allowed_status={"passed"} if beta else {"not_required"},
            expected_reason_code=None if beta else BETA_OPTIONAL_BY_POLICY, predecessor=alpha,
            signature_verifier=signature_verifier, expected_signer_identity=expected_signer_identity,
            release_inputs=release_inputs,
        )
        beta_slot = store / "environment-execution/acceptance" / candidate_id.removeprefix("sha256:") / "beta.json"
        beta_evidence = store / "environment-evidence" / candidate_id.removeprefix("sha256:") / "beta"
        occupied = any(slot.exists() or slot.is_symlink() for slot in (beta_slot, beta_evidence))
        if not beta and beta_ref is None and occupied:
            # 不得把 passed/no-live/失效旧事实改称政策跳过，也不覆盖旧证据目录。
            continue
        matches.append({
            "candidatePath": path, "candidate": dict(body),
            "candidateRef": {"ref": path.relative_to(store).as_posix(), "digest": _sha256_hex(raw)},
            "alpha": alpha, "beta": beta_ref, "createdAt": str(body.get("createdAt") or ""),
        })
    if not matches:
        return None
    # 同一 exact 身份优先完整且政策匹配的 Alpha/Beta；避免较新的 Alpha-only 遮蔽可用前驱链。
    return max(matches, key=lambda item: (item["beta"] is not None, item["createdAt"]))


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


def _merged_lanes(*, values: Sequence[str], lane_branch: str, commit: str, remote: str) -> list[dict[str, str]]:
    """记录本次验收 candidate 合并了哪些 lane head：每个 lane 解析为 exact commit 且必须是 candidate 的祖先。

    这是多工作树合并验收的显式来源记录，不自动发现；lane缺省记录自身，integration单树缺省为空。
    """
    from quwoquan_ops.gate.git_branch_policy.policy import load_policy
    allowed = load_policy(POLICY.with_name("branch_policy.yaml")).allowed_local
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    local_sources = [] if lane_branch == DEV_REF else [lane_branch]
    for raw in [*local_sources, *values]:
        name = str(raw or "").strip().removeprefix("refs/heads/")
        if not name.startswith("lane/") or name not in allowed:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes expects a declared local lane (got {name or '-'})")
        if name in seen:
            continue
        probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}^{{commit}}"], cwd=ROOT, text=True, capture_output=True, check=False)
        resolved = probe.stdout.strip() if probe.returncode == 0 else ""
        if not resolved:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes {name} does not resolve to a declared local lane head")
        if subprocess.run(["git", "merge-base", "--is-ancestor", resolved, commit], cwd=ROOT, check=False).returncode != 0:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--merged-lanes {name}@{resolved[:12]} is not an ancestor of the candidate")
        seen.add(name)
        entries.append({"branch": f"refs/heads/{name}", "commit": resolved})
    return entries


def _apply_acceptance_execution_scope(args: argparse.Namespace, source_ref: str) -> None:
    """本树显式多树合并必须真跑Alpha/Beta，不把单树复用带入该模式。"""
    if source_ref == DEV_REF and args.merged_lanes:
        args.alpha = True
        args.beta = True
        args.reuse = False


def _write_acceptance_bundle(*, run_dir: Path, candidate_ref: Mapping[str, str], source_ref: Mapping[str, str],
                             alpha_ref: Mapping[str, str], beta_ref: Mapping[str, str], identity: Mapping[str, str],
                             plan_path: Path, summary: Mapping[str, Any], beta_status: str, beta_reason: str | None,
                             lane_branch: str, merged_lanes: Sequence[Mapping[str, str]], args: argparse.Namespace,
                             alpha_status: str = "passed", alpha_reason: str | None = None) -> Path:
    """把 accepted 终态的全部 exact 事实按 store 相对路径复制成 portable bundle，供 integration 工作区导入。

    bundle 只复制字节、不改写任何事实；`bundle.json` 记录 candidate 身份、baseline、lane 来源与每个文件的
    exact digest，`bundleId` 是 manifest 自身的 canonical digest。integration 侧按同一 digest 逐字节复核。
    """
    store = _store()
    if getattr(args, "release_attestation", None) is not None:
        inputs = _acceptance_release_inputs(args)
        if (summary.get("dataReleases") != sorted({binding["releaseId"] for binding in inputs["release"].values()})
                or summary.get("dataReleaseHandoffRef") != inputs["handoffRef"]):
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "reused release labels differ from exact inputs")
        for fact_ref in (alpha_ref, beta_ref):
            fact = _read_store_object(store, fact_ref, "reused acceptance")
            if fact.get("status") == "passed" and not _acceptance_binds_inputs(store=store, fact=fact, inputs=inputs):
                raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "cannot relabel old acceptance with new release inputs")
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
        for exact in [*_fact_evidence_refs(fact), *_report_fact_refs(store=store, fact=fact),
                      *_offline_fact_refs(store=store, fact=fact, candidate=candidate)]:
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
        "alpha": {"status": alpha_status, "executed": alpha_status == "passed", "reasonCode": alpha_reason},
        "beta": {"status": beta_status, "executed": beta_status == "passed", "reasonCode": beta_reason},
        "candidate": dict(candidate_ref), "claim": claim_ref, "sourceFact": dict(source_ref), "sourceReceipt": receipt,
        "alphaFact": dict(alpha_ref), "betaFact": dict(beta_ref),
        "storeFiles": [{"ref": ref, "digest": digest} for ref, digest in sorted(files.items())],
    }
    manifest["bundleId"] = _sha256_hex(_canonical_bytes(manifest))
    _bundle_put(bundle_dir, BUNDLE_MANIFEST, _canonical_bytes(manifest) + b"\n")
    return bundle_dir


def _import_acceptance_bundle(*, bundle_dir: Path, commit: str, tree: str, parent: str, args: argparse.Namespace,
                              keyring: Any, validate_only: bool = False) -> dict[str, Any]:
    """integrate 模式唯一的事实来源：逐字节导入 lane bundle 并复核绑定。

    - 每个 store 文件按 manifest digest 复核后 create-once 写入本工作树 store；已存在且字节不同即 `BUNDLE_DRIFT`。
    - candidate.commit/tree 必须等于本工作区 HEAD candidate；expectedParent 必须等于当前远端 dev1.0（否则
      `BUNDLE_STALE`：dev1.0 已前移，需在合入新 dev1.0 的 head 上重新 `make accept`）。
    - Alpha/Beta EAF 以仓内 keyring 验签、复核全部引用与 candidate 绑定；source fact 必须 passed 且绑定同一 candidateId。
    """
    manifest = _load_bundle_manifest(bundle_dir)
    validate_bundle_identity(manifest, commit=commit, tree=tree, parent=parent)
    store = bundle_dir / BUNDLE_STORE_DIR
    files = read_bundle_files(bundle_dir, manifest)
    candidate = _read_store_object(store, manifest["candidate"], "candidate")
    validate_manifest_candidate(manifest, candidate)
    _read_store_object(store, manifest["claim"], "claim")
    source_fact = _read_store_object(store, manifest["sourceFact"], "sourceFact")
    validate_manifest_source(manifest, source_fact)
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
        required.extend(_report_fact_refs(store=store, fact=validated))
        required.extend(_offline_fact_refs(store=store, fact=validated, candidate=candidate))
        validate_manifest_fact(manifest, validated, environment)
    if candidate.get("impactPlanDigest") != manifest["impactPlan"].get("digest"):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "candidate ImpactPlan drifted")
    if {item["ref"]: item["digest"] for item in required} != {ref: _sha256_hex(raw) for ref, raw in files.items()}:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INCOMPLETE", "storeFiles is not the exact evidence closure")
    if validate_only:
        # 完整可验证 admission 条件与最终签发同轨；receipt 只从 bundle 闭包读取。
        from quwoquan_ops.ci.scoped_candidate.core import validate_publish_inputs
        validate_publish_inputs(repository=ROOT, store_root=store, candidate_ref=manifest["candidate"],
            source_fact_refs=[manifest["sourceFact"]], alpha_fact_ref=manifest["alphaFact"], beta_fact_ref=manifest["betaFact"],
            expected_remote_oid=parent, receipt_root=bundle_dir / "repository")
        return {"manifest": manifest, "candidate": candidate, "importedFiles": 0, "storeFiles": len(files)}
    destination = _store()
    imported = sum(_bundle_put(destination, ref, raw) for ref, raw in files.items())
    _bundle_put(OUTPUT_ROOT, output_ref, receipt_raw)
    return {"manifest": manifest, "candidate": candidate, "importedFiles": imported, "storeFiles": len(files)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", default="HEAD", help="exact commit（HEAD 或 lane head sha）")
    parser.add_argument("--candidate-ref", default="", help="acceptance：复用已冻结 candidate 的 store ref=sha256:digest，不重新 acquire claim")
    parser.add_argument("--mode", choices=("integrate", "acceptance"), default="integrate",
                        help="integrate=integration 工作区消费 acceptance bundle 并 admit/publish；"
                             "acceptance=本地 lane/integration 跑 readiness + typed Alpha/Beta 并签发事实与 bundle")
    parser.add_argument("--baseline", default="",
                        help="acceptance 专用：显式确认 exact parent；必须等于当前远端 dev1.0 head，不接受历史基线发布")
    parser.add_argument("--alpha", action="store_true",
                        help="acceptance 专用：显式 opt-in 真跑 Alpha live；缺省以 typed "
                             "not_required(reason=ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV) 闭合")
    parser.add_argument("--beta", action="store_true",
                        help="acceptance 专用：显式 opt-in 真跑 Beta；缺省不按集成深度分流，"
                             "以 typed not_required(reason=ACCEPTANCE.BETA_OPTIONAL_BY_POLICY) 闭合")
    parser.add_argument("--merged-lanes", action="append", default=[],
                        help="acceptance 专用：candidate 显式合并的其他 lane（lane/<name>，可重复）；每个都必须是 candidate 的祖先")
    parser.add_argument("--acceptance-bundle", type=Path, default=None,
                        help="integrate 专用：lane `make accept` 产出的 acceptance-bundle 目录；缺失即 INTEGRATION_RUN.ACCEPTANCE_REQUIRED")
    parser.add_argument("--validate-bundle-only", action="store_true",
                        help="integrate：本地 FF 前校验 exact bundle/candidate/远端 parent，仅输出 bundle_validated；不导入、不 admit/publish")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--owner-identity", default="", help="PRE owner identity manifest ref（make feature-context 输出）")
    parser.add_argument("--candidate-evidence", default="")
    parser.add_argument("--review-consolidation", default="")
    parser.add_argument("--required-evidence", action="append", default=[])
    parser.add_argument("--readiness-level", choices=("fast", "scope"), default="scope",
                        help="可发布源码验收只接受默认 scope；Review consolidation 与 required evidence 可选，fast 明确拒绝")
    parser.add_argument("--release-attestation", type=Path, default=None,
                        help="acceptance：live Alpha/Beta 必填的 candidate production Data release attestation")
    parser.add_argument("--rollback-release-attestation", type=Path, default=None,
                        help="acceptance：live Alpha/Beta 必填的 rollback production Data release attestation")
    parser.add_argument("--release-handoff-ref", default="",
                        help="acceptance：live Alpha/Beta 必填的 candidate release producer 输出相对 ref=sha256:digest；"
                             "rollback release 只参与 stackctl package 候选绑定，因此不需要其 handoff-ref")
    parser.add_argument("--workload", default="full", choices=("content-release", "content-commercial", "full"))
    parser.add_argument("--profile", default="integration", choices=("smoke", "integration"))
    parser.add_argument("--signer-identity", default=DEFAULT_SIGNER)
    parser.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH,
                        help="仓内 Ed25519 公钥 keyring；私钥来自仓外 QWQ_EVIDENCE_SIGNING_KEY_ROOT")
    parser.add_argument("--fact-ttl-hours", type=int, default=72)
    parser.add_argument("--writer", default="integration")
    parser.add_argument("--publish", action="store_true", help="admit 后以 local-git CAS 发布到远端 dev1.0")
    parser.add_argument("--reuse", action="store_true",
                        help="acceptance 专用：复用同 commit/tree/parent/ImpactPlan/profile/平台计划 的有效 Alpha/Beta 事实；"
                             "Beta 状态必须匹配本次 --beta 政策，summary 标记 reused")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--app-platform", choices=("android", "ios", "all"), default="all",
                        help="Alpha App acceptance 平台；默认双端，显式单平台不要求另一端证据")
    parser.add_argument("--android-device-id", default="", help="Alpha 离线 UAT 的 exact Android emulator serial；不自动发现")
    parser.add_argument("--ios-device-id", default="", help="Alpha 离线 UAT 的 exact iOS simulator UDID；不自动发现")
    return parser


def _prepare_signing(args: argparse.Namespace, summary: dict[str, Any]) -> tuple[Any, Any]:
    validate_mode_inputs(args)
    if args.validate_bundle_only:
        from quwoquan_ops.ci.scoped_candidate.core import validate_integration_publish_origin
        validate_integration_publish_origin(ROOT, args.remote)
    try:
        keyring = load_keyring(args.signing_keyring)
    except EvidenceSigningError as exc:
        raise IntegrationRunError("INTEGRATION_RUN.SIGNER_UNAVAILABLE", exc.detail) from exc
    if args.mode == "integrate":
        return keyring, None
    try:
        signer = ed25519_signer(args.signer_identity, root=key_root(), keyring=keyring)
    except EvidenceSigningError as exc:
        code = "INTEGRATION_RUN.SIGNER_UNREGISTERED" if exc.code == "EVIDENCE_SIGNING.SIGNER_UNREGISTERED" else "INTEGRATION_RUN.SIGNER_UNAVAILABLE"
        raise IntegrationRunError(code, exc.detail) from exc
    live_environment = bool(getattr(args, "alpha", False) or args.beta)
    has_data = args.release_attestation is not None or args.rollback_release_attestation is not None or bool(args.release_handoff_ref)
    if live_environment or has_data:
        for label, path in (("release", args.release_attestation), ("rollback", args.rollback_release_attestation)):
            if path is None or not path.is_file():
                raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"{label} attestation is required for live Alpha/Beta or when any Data input is set: {path}")
        candidate_id = _release_id(args.release_attestation)
        rollback_id = _release_id(args.rollback_release_attestation)
        release_ids = {candidate_id, rollback_id}
        if candidate_id == rollback_id:
            summary["dataChange"] = UNCHANGED_DATA_CHANGE
        summary["dataReleases"] = sorted(release_ids)
        summary["dataReleaseHandoffRef"] = _handoff_ref(args.release_handoff_ref, label="--release-handoff-ref")
    return keyring, signer


def _integrate_bundle(args: argparse.Namespace, *, identity: Mapping[str, str], phases: Phases,
                      summary: dict[str, Any], keyring: Any) -> None:
    imported = phases.run("validate-bundle" if args.validate_bundle_only else "import-bundle", lambda: _import_acceptance_bundle(
        bundle_dir=args.acceptance_bundle, commit=identity["commit"], tree=identity["tree"], parent=identity["parent"],
        args=args, keyring=keyring, validate_only=args.validate_bundle_only,
    ))
    manifest = imported["manifest"]
    if args.validate_bundle_only:
        if _git("ls-remote", args.remote, DEV_REF).split()[0] != identity["parent"]:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_STALE", "remote dev1.0 changed during prevalidation")
        summary["acceptanceBundle"] = {"path": str(args.acceptance_bundle), "bundleId": manifest["bundleId"],
                                        "storeFiles": imported["storeFiles"], "importedFiles": 0}
        summary["terminal"] = "bundle_validated"
        return
    record_imported_bundle(summary, imported, bundle_dir=args.acceptance_bundle)
    admission_path = phases.run("admit", lambda: create_publish_admission(
        repository=ROOT, policy_path=POLICY, candidate_ref=manifest["candidate"], source_fact_refs=[manifest["sourceFact"]],
        alpha_fact_ref=manifest["alphaFact"], beta_fact_ref=manifest["betaFact"], expected_remote_oid=identity["parent"],
    ))
    summary["admission"] = store_ref(repository=ROOT, policy_path=POLICY, path=admission_path)
    summary["terminal"] = "admitted"
    if args.publish:
        result_path = phases.run("publish", lambda: local_git_cas_publish(
            repository=ROOT, policy_path=POLICY, admission_ref=admission_path, remote=args.remote,
        ))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        summary["publish"] = {**store_ref(repository=ROOT, policy_path=POLICY, path=result_path),
                              "beforeOid": result["beforeOid"], "afterOid": result["afterOid"], "readbackOid": result["readbackOid"]}
        summary["terminal"] = "published"


def _accept_alpha(*, args: argparse.Namespace, candidate_ref: Mapping[str, str], candidate: Mapping[str, Any],
                  plan: Mapping[str, Any], plan_path: Path, reusable: Mapping[str, Any] | None, phases: Phases,
                  run_dir: Path, summary: dict[str, Any], signer: Any) -> tuple[dict[str, str], dict[str, Any] | None]:
    if reusable is not None:
        alpha_ref = reusable["alpha"]
        summary["reused"]["alpha"] = True
        summary["environments"]["alpha"] = {"environment": "alpha", "executed": False, "reused": True, "acceptance": alpha_ref}
        phases.run("alpha.reuse", lambda: alpha_ref)
        return alpha_ref, None
    if not (getattr(args, "alpha", False) or args.beta):
        evidence = _not_required_alpha(
            candidate=candidate, impact_plan_digest=plan["plan_digest"], impact_plan_path=plan_path,
            profile=args.profile, reason_code=ALPHA_LIVE_DEFERRED,
        )
        summary["environments"]["alpha"] = {
            "environment": "alpha", "executed": False, "reasonCode": ALPHA_LIVE_DEFERRED,
        }
        alpha_ref = phases.run("alpha.issue", lambda: _issue(
            environment="alpha", candidate_ref=candidate_ref, impact_plan_digest=plan["plan_digest"], evidence=evidence,
            status="not_required", predecessor=None, profile=args.profile, args=args, signer=signer,
        ))
        summary["environments"]["alpha"]["acceptance"] = alpha_ref
        return alpha_ref, None
    offline_pages = None
    if "app" in plan["scopes"]:
        offline_pages = phases.run("alpha.offline-pages", lambda: _alpha_offline_pages(
            candidate=candidate, candidate_ref=candidate_ref, args=args, run_dir=run_dir, phases=phases,
        ))
    evidence = _run_environment(environment="alpha", profile=args.profile, candidate=candidate,
                                impact_plan_digest=plan["plan_digest"], args=args, run_dir=run_dir, phases=phases, summary=summary,
                                scopes=tuple(str(scope) for scope in plan["scopes"]), offline_pages=offline_pages)
    alpha_ref = phases.run("alpha.issue", lambda: _issue(
        environment="alpha", candidate_ref=candidate_ref, impact_plan_digest=plan["plan_digest"], evidence=evidence,
        status="passed", predecessor=None, profile=args.profile, args=args, signer=signer,
    ))
    summary["environments"]["alpha"]["acceptance"] = alpha_ref
    return alpha_ref, evidence


def _accept_beta(*, args: argparse.Namespace, candidate_ref: Mapping[str, str], candidate: Mapping[str, Any],
                 plan_path: Path, alpha_ref: Mapping[str, str], alpha_evidence: Mapping[str, Any] | None,
                 reusable: Mapping[str, Any] | None, phases: Phases, run_dir: Path,
                 summary: dict[str, Any], signer: Any) -> dict[str, str]:
    impact_digest = summary["impactPlan"]["digest"]
    depth = summary["impactPlan"]["integrationDepth"]
    reason = None if args.beta else BETA_OPTIONAL_BY_POLICY
    if reusable is not None and reusable["beta"] is not None:
        beta_ref = reusable["beta"]
        summary["reused"]["beta"] = True
        summary["environments"]["beta"] = {"environment": "beta", "executed": False, "reused": True,
                                             "acceptance": beta_ref, "reasonCode": reason, "integrationDepth": depth}
        phases.run("beta.reuse", lambda: beta_ref)
        return beta_ref
    if args.beta:
        if alpha_evidence is None:
            raise IntegrationRunError("INTEGRATION_RUN.BETA_REUSE_UNAVAILABLE", "Alpha reused without recoverable exact Beta predecessor; rerun acceptance without --reuse")
        evidence = _run_environment(environment="beta", profile=args.profile, candidate=candidate,
                                    impact_plan_digest=impact_digest, args=args, run_dir=run_dir, phases=phases, summary=summary,
                                    previous_readiness=alpha_evidence["readiness"])
    else:
        evidence = _not_required_beta(candidate=candidate, impact_plan_digest=impact_digest, impact_plan_path=plan_path,
                                     profile=args.profile, reason_code=reason)
        summary["environments"]["beta"] = {"environment": "beta", "executed": False, "reasonCode": reason, "integrationDepth": depth}
    beta_ref = phases.run("beta.issue", lambda: _issue(
        environment="beta", candidate_ref=candidate_ref, impact_plan_digest=impact_digest, evidence=evidence,
        status="passed" if args.beta else "not_required", predecessor=alpha_ref, profile=args.profile, args=args, signer=signer,
    ))
    summary["environments"]["beta"]["acceptance"] = beta_ref
    return beta_ref


def _select_candidate(*, args: argparse.Namespace, identity: Mapping[str, str], impact_digest: str,
                      keyring: Any, phases: Phases, summary: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any], dict[str, Any] | None, Path | None]:
    reusable = None
    if args.reuse:
        live_alpha = bool(getattr(args, "alpha", False) or args.beta)
        release_inputs = _acceptance_release_inputs(args) if live_alpha or args.release_attestation else None
        reusable = phases.run("reuse-lookup", lambda: _find_reusable_candidate(
            store=_store(), commit=identity["commit"], tree=identity["tree"], parent=identity["parent"],
            impact_plan_digest=impact_digest, profile=args.profile, beta=args.beta, live_alpha=live_alpha,
            signature_verifier=ed25519_environment_verifier(keyring, [args.signer_identity]),
            expected_signer_identity=args.signer_identity, owner_identity=args.owner_identity,
            release_inputs=release_inputs,
        ))
    if args.candidate_ref:
        ref, candidate = _existing_candidate(exact=args.candidate_ref, identity=identity,
            impact_plan_digest=impact_digest, owner_identity=args.owner_identity)
        if reusable is not None and reusable["candidateRef"] != ref:
            reusable = None
        summary["reused"]["candidate"] = True
        return ref, candidate, reusable, None
    if reusable is not None:
        summary["reused"]["candidate"] = True
        return reusable["candidateRef"], reusable["candidate"], reusable, None
    expires = (datetime.now(timezone.utc) + timedelta(hours=args.fact_ttl_hours)).isoformat().replace("+00:00", "Z")
    path = phases.run("build-head", lambda: build_head_candidate(
        repository=ROOT, policy_path=POLICY, commit=identity["commit"], expected_parent=identity["parent"],
        owner_identity_ref=args.owner_identity or f"integration-run:{summary['runId']}", impact_plan_digest=impact_digest,
        writer_id=args.writer, expires_at=expires,
    ))
    ref = store_ref(repository=ROOT, policy_path=POLICY, path=path)
    candidate = json.loads(path.read_text(encoding="utf-8"))
    return ref, candidate, None, _store() / candidate["claimRef"]


def main(argv: list[str] | None = None) -> int:
    started_monotonic = time.monotonic()
    args = _parser().parse_args(argv)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    phases = Phases()
    summary: dict[str, Any] = {
        "schema": "quwoquan_ops.integration_run_summary.v1", "runId": run_id, "startedAt": _now(),
        "terminal": "running", "environments": {}, "phases": phases.items,
    }
    claim_path: Path | None = None
    try:
        summary["mode"] = args.mode
        keyring, signer = _prepare_signing(args, summary)

        identity = phases.run("preflight", lambda: preflight_identity(args, git=_git, is_ancestor=_is_ancestor))
        summary["candidate"] = identity

        if args.mode == "integrate":
            _integrate_bundle(args, identity=identity, phases=phases, summary=summary, keyring=keyring)
            return 0

        lane_branch = _readiness_local_ref(args=args, commit=identity["commit"])
        merged_lanes = _merged_lanes(values=args.merged_lanes, lane_branch=lane_branch, commit=identity["commit"], remote=args.remote)
        _apply_acceptance_execution_scope(args, lane_branch)
        summary["laneBranch"] = lane_branch
        summary["mergedLanes"] = merged_lanes
        plan, plan_path = phases.run("impact-plan", lambda: _impact_plan(parent=identity["parent"], commit=identity["commit"], run_dir=run_dir))
        depth = str(plan["integration_depth"])
        impact_digest = str(plan["plan_digest"])
        summary["impactPlan"] = {"digest": impact_digest, "integrationDepth": depth, "ref": _output_ref(plan_path), "scopes": plan["scopes"]}
        if depth == "no_live":
            # ImpactPlan 保留真实分类；可发布验收仍走既有最小 smoke profile，绝不伪造 EAF。
            args.profile = "smoke"
            summary["note"] = "无 runtime 增量默认签发 typed Alpha/Beta；live 仅 --alpha/--beta opt-in。"

        receipt_path, receipt = phases.run(f"readiness-{args.readiness_level}", lambda: _local_readiness(
            level=args.readiness_level, parent=identity["parent"], commit=identity["commit"], run_dir=run_dir, args=args,
        ))
        reused: dict[str, bool] = {"readiness": receipt.get("cache_hit") is True, "candidate": False, "alpha": False, "beta": False}
        summary["reused"] = reused
        summary["readiness"] = {"level": args.readiness_level, "receiptRef": _output_ref(receipt_path), "deferred": len(receipt.get("plan", {}).get("deferred", [])), "reused": reused["readiness"]}

        candidate_ref, candidate, reusable, claim_path = _select_candidate(args=args, identity=identity,
            impact_digest=impact_digest, keyring=keyring, phases=phases, summary=summary)
        candidate_identity = {"candidateId": candidate["candidateId"], "commit": candidate["commit"], "tree": candidate["tree"]}
        summary["candidate"].update({"candidateId": candidate["candidateId"], "candidateRef": candidate_ref, "claimRef": candidate["claimRef"], "reused": reused["candidate"]})

        source_path = create_source_fact(
            repository=ROOT, policy_path=POLICY, candidate_ref=candidate_ref,
            kind=f"local_readiness_{args.readiness_level}", receipt_path=receipt_path, status="passed",
        )
        source_ref = store_ref(repository=ROOT, policy_path=POLICY, path=source_path)
        summary["sourceFact"] = source_ref

        if _git("rev-parse", "HEAD") != identity["commit"]:
            raise IntegrationRunError("INTEGRATION_RUN.LANE_IDENTITY_INVALID", "lane HEAD moved after readiness; reaccept the new exact candidate")

        alpha_ref, alpha_evidence = _accept_alpha(args=args, candidate_ref=candidate_ref, candidate=candidate_identity,
            plan=plan, plan_path=plan_path, reusable=reusable, phases=phases, run_dir=run_dir, summary=summary, signer=signer)
        beta_ref = _accept_beta(args=args, candidate_ref=candidate_ref, candidate=candidate_identity,
            plan_path=plan_path, alpha_ref=alpha_ref, alpha_evidence=alpha_evidence, reusable=reusable,
            phases=phases, run_dir=run_dir, summary=summary, signer=signer)
        live_alpha = bool(getattr(args, "alpha", False) or args.beta)
        alpha_status = "passed" if live_alpha else "not_required"
        alpha_reason = None if live_alpha else ALPHA_LIVE_DEFERRED
        beta_status = "passed" if args.beta else "not_required"
        beta_reason = None if args.beta else BETA_OPTIONAL_BY_POLICY

        # 环境事实已 create-once 落盘；admission/publish 只属于 integration 工作区（gamma/prod 亦然）。
        # bundle 把全部 exact 事实按 store 相对路径复制出去，供 integration 逐字节导入。
        bundle_dir = phases.run("bundle", lambda: _write_acceptance_bundle(
            run_dir=run_dir, candidate_ref=candidate_ref, source_ref=source_ref, alpha_ref=alpha_ref, beta_ref=beta_ref,
            identity=identity, plan_path=plan_path, summary=summary,
            alpha_status=alpha_status, alpha_reason=alpha_reason, beta_status=beta_status, beta_reason=beta_reason,
            lane_branch=lane_branch, merged_lanes=merged_lanes, args=args,
        ))
        manifest = json.loads((bundle_dir / BUNDLE_MANIFEST).read_bytes())
        summary["terminal"] = "accepted"
        summary["acceptance"] = {"alphaFactRef": alpha_ref, "betaFactRef": beta_ref,
                                 "alphaStatus": alpha_status, "alphaReasonCode": alpha_reason,
                                 "betaStatus": beta_status, "betaReasonCode": beta_reason,
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
        if claim_path is not None:
            # claim 只保护候选构造期；run 终态后显式释放，避免下一轮同 scope 候选被过期 claim 卡住。
            try:
                release_claim(repository=ROOT, policy_path=POLICY, claim_ref=claim_path, reason=f"integration-run {run_id} terminal {summary['terminal']}")
            except ScopedCandidateError as exc:
                summary.setdefault("warnings", []).append(f"claim release failed: {exc}")
        summary["endedAt"] = _now()
        summary["wallClockSeconds"] = round(time.monotonic() - started_monotonic, 3)
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
    if "reused" in summary:
        reused = summary["reused"]
        lines.append("- reused: " + ", ".join(f"{name}={'yes' if flag else 'no'}" for name, flag in sorted(reused.items())))
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
