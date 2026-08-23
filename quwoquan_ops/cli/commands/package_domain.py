"""stackctl `package` 子命令域(argparse 表面与锁/候选 CAS 编排)。

从 stackctl.py 逐字迁出:

- `register_parser`:`package` 子命令的 argparse 表面(帮助文案与
  参数集合逐字节保持不变);
- `_target_package_lock`:按 target 串行化 package 物料化的文件锁
  (仅 `command_package` 与测试消费);
- `command_package`:runtime 候选的锁获取、input capsule CAS、
  候选复用/碰撞判定与激活编排。

runtime 打包执行体在 `commands/package_runtime.py`,非 runtime 子 kind
与打包物料 helper 在 `commands/package_shared.py`。测试经
``mock.patch.object(stackctl, ...)`` patch `_command_package_unlocked` /
`_target_package_lock` / `can_reuse_package` 等符号,因此函数体内一律
经函数内延迟导入 `_stackctl` 属性访问,保持 monkeypatch 语义并避免
顶层循环 import。
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    package_parser.add_argument("--env", choices=_stackctl.ENVIRONMENTS, default="")
    package_parser.add_argument(
        "--kind",
        choices=[
            "runtime",
            "legal-static",
            "ops-portal",
            "app-release",
            "app-artifact",
            "web",
            "release-manifest",
        ],
        default="runtime",
    )
    # app-artifact 原子消费 canonical build product；平台、profile、模式、格式与
    # 分发类全部从 metadata 解析，旧环境/分项构建参数不得作为兼容入口。
    package_parser.add_argument("--build-product-id", default="")
    package_parser.add_argument(
        "--app-platform", choices=["android", "ios", "web"], default=""
    )
    package_parser.add_argument(
        "--app-build-mode", choices=["debug", "profile", "release"], default=""
    )
    package_parser.add_argument(
        "--distribution-class",
        choices=[
            "dev_direct",
            "simulator",
            "registered_device",
            "store",
            "official_web",
            "hosted_web",
        ],
        default="",
    )
    package_parser.add_argument("--device", default="")
    # artifactFormat 由请求显式声明或按平台默认推导（DEC-005）；
    # 禁止由 distribution-class 推导，aab 仅限 android × release 硬需求。
    package_parser.add_argument(
        "--artifact-format", choices=["apk", "aab"], default=""
    )
    package_parser.add_argument("--service", default="")
    package_parser.add_argument("--include-services", action="store_true")
    package_parser.add_argument(
        "--release-attestation",
        default="",
        help="Canonical candidate Data release attestation bound into a full package.",
    )
    package_parser.add_argument(
        "--rollback-release-attestation",
        default="",
        help="Canonical rollback Data release attestation bound into a full package.",
    )
    package_parser.add_argument("--target", choices=_stackctl.TARGETS, default="")
    package_parser.add_argument("--ops-base-url", default="")
    package_parser.add_argument("--content-base-url", default="")
    package_parser.add_argument("--entity-base-url", default="")
    package_parser.add_argument("--oidc-issuer", default="")
    package_parser.add_argument("--oidc-client-id", default="")
    package_parser.add_argument("--oidc-audience", default="")
    package_parser.add_argument("--oidc-scope", default="")
    package_parser.add_argument("--skip-install", action="store_true")
    package_parser.add_argument("--apk-path", default="")
    package_parser.add_argument("--verify-remote-apk", action="store_true")
    package_parser.add_argument("--release-artifact-dir", default="")
    package_parser.add_argument("--application-packages-dir", default="")
    package_parser.add_argument("--application-package-payloads-dir", default="")
    package_parser.add_argument("--application-evidence-ref", default="")
    package_parser.add_argument("--public-web-manifest", default="")
    package_parser.add_argument("--android-release-manifest", default="")
    package_parser.add_argument("--ops-portal-provenance", default="")
    package_parser.add_argument("--contract-graph", default="")
    package_parser.add_argument("--provider-evidence", default="")
    package_parser.add_argument("--provider-raw-dir", default="")
    package_parser.add_argument("--test-evidence", default="")


@contextlib.contextmanager
def _target_package_lock(target_name: str) -> Any:
    """Serialize package materialization per target without blocking other envs."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(target_name).strip()
    if target not in _stackctl.TARGETS:
        raise ValueError(f"package lock does not support {target!r}")
    lock_path = _stackctl.deployment_target_path(target, "locks", "package.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} target={target} startedAt={_stackctl.utc_now()}\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def command_package(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    package_kind = str(getattr(args, "kind", "runtime") or "runtime")
    if package_kind != "runtime":
        if package_kind == "release-manifest":
            return _stackctl._command_package_unlocked(args, package_snapshot=None)
        env_name = str(getattr(args, "env", "") or "").strip()
        target_name = str(getattr(args, "target", "") or "").strip()
        if package_kind == "app-artifact":
            # build product producer 属于仓库级构建面，不挂靠任一部署环境/target；
            # 完整旧接口拒绝与结构化 decision 由 canonical writer 统一返回。
            return _stackctl._command_package_unlocked(args, package_snapshot=None)
        if not env_name:
            return {
                "exitCode": 2,
                "summary": f"stackctl {package_kind} package requires --env",
                "details": ["--env is required for deployment-scoped package kinds"],
            }
        if not target_name and env_name in _stackctl.DEFAULT_TARGET_BY_ENV:
            target_name = _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
        previous_override = os.environ.get(_stackctl.PACKAGE_ROOT_OVERRIDE_ENV)
        isolated_root = _stackctl.deployment_target_path(
            target_name,
            "standalone-packages",
            package_kind,
            "packages",
        )
        os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = str(isolated_root)
        try:
            return _stackctl._command_package_unlocked(args, package_snapshot=None)
        finally:
            if previous_override is None:
                os.environ.pop(_stackctl.PACKAGE_ROOT_OVERRIDE_ENV, None)
            else:
                os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    if not target_name and env_name in _stackctl.DEFAULT_TARGET_BY_ENV:
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    if not target_name:
        return _stackctl._command_package_unlocked(args)
    if str(getattr(args, "service", "") or "").strip():
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package blocked for {env_name}",
            "details": [
                "runtime candidates are full-only; --service cannot create or activate a runtime candidate"
            ],
        }
    args.include_services = True
    # 打包会把服务镜像层写进 Docker 数据盘；容量不足时构建会以镜像层写失败、
    # 拉取中断等形态失败，前置判定让报告直接指向容量。
    capacity = _stackctl.local_runtime_capacity_evidence(
        _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
    )
    if capacity["issues"]:
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package is GATE_BLOCK for {env_name}",
            "details": capacity["issues"],
            "firstBlocker": capacity["blocker"],
            "capacity": capacity["evidence"],
        }
    try:
        requested_release_bindings = _stackctl.validate_release_attestations(
            str(getattr(args, "release_attestation", "") or ""),
            str(getattr(args, "rollback_release_attestation", "") or ""),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package inputs blocked for {env_name}",
            "details": [str(exc)],
        }
    try:
        build_cache_use_lock = _stackctl.acquire_local_runtime_use_lock(
            target=target_name,
            purpose="runtime-package-build",
        )
    except RuntimeError as exc:
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package blocked for {env_name}",
            "details": [str(exc)],
        }
    with contextlib.closing(build_cache_use_lock), _stackctl._target_package_lock(target_name):
        package_input_roots = _stackctl.deployment_input_roots(
            env_name,
            target_name,
            [args.service] if args.service else _stackctl._all_services(),
            release_attestation=str(getattr(args, "release_attestation", "") or ""),
            rollback_release_attestation=str(
                getattr(args, "rollback_release_attestation", "") or ""
            ),
        )
        capsule_parent = _stackctl.deployment_candidate_dir(
            target_name,
            "sha256:" + "0" * 64,
        ).parent
        capsule_parent.mkdir(parents=True, exist_ok=True)
        # Capture directly inside the future candidate staging tree.  The
        # capsule seals its root read-only, and macOS correctly refuses moving
        # that sealed directory on its own.  Moving the still-writable parent
        # at final candidate CAS preserves the seal without a writable gap.
        staging_dir = Path(
            tempfile.mkdtemp(prefix=".package-staging-", dir=str(capsule_parent))
        )
        capsule_staging_root = staging_dir / _stackctl.PACKAGE_INPUT_CAPSULE_DIRECTORY
        try:
            package_snapshot = _stackctl.materialize_package_input_capsule(
                package_input_roots,
                capsule_root=capsule_staging_root,
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return {
                "exitCode": 2,
                "summary": f"stackctl package input capsule blocked for {env_name}",
                "details": [str(exc)],
            }
        if package_snapshot is None:
            return _stackctl._command_package_unlocked(
                args,
                package_snapshot=None,
                package_input_roots=package_input_roots,
            )

        baseline_id = str(package_snapshot["baselineId"])
        candidate_dir = _stackctl.deployment_candidate_dir(target_name, baseline_id)
        previous_override = os.environ.get(_stackctl.PACKAGE_ROOT_OVERRIDE_ENV)
        if candidate_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
            os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = str(candidate_dir / "packages")
            try:
                reusable, detail = _stackctl.can_reuse_package(
                    env_name,
                    target_name,
                    include_services=bool(args.include_services or args.service),
                    required_services=[args.service] if args.service else None,
                    candidate_root=candidate_dir,
                )
            finally:
                if previous_override is None:
                    os.environ.pop(_stackctl.PACKAGE_ROOT_OVERRIDE_ENV, None)
                else:
                    os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
            if not reusable:
                return {
                    "exitCode": 2,
                    "summary": f"stackctl package candidate collision for {target_name}",
                    "details": [detail, f"candidateDir={candidate_dir}"],
                    "baselineId": baseline_id,
                }
            reused_manifest = _stackctl.load_candidate_manifest(
                env_name,
                target_name,
                baseline_id,
                require_full=True,
            )
            if reused_manifest.get("release") != requested_release_bindings:
                return {
                    "exitCode": 2,
                    "summary": f"stackctl package release binding collision for {target_name}",
                    "details": [
                        "immutable candidate exists with different candidate/rollback release attestations"
                    ],
                    "baselineId": baseline_id,
                }
            reused_fingerprint_path = (
                candidate_dir / "packages" / "app" / "package-fingerprint.json"
            )
            reused_fingerprint = json.loads(
                reused_fingerprint_path.read_text(encoding="utf-8")
            )
            report_ref = str(reused_fingerprint.get("reportRef") or "").strip()
            reused_report_path = _stackctl._runtime_package_report_path(report_ref)
            try:
                package_identity = _stackctl._validate_runtime_package_identity_readback(
                    report_path=reused_report_path,
                    fingerprint_path=reused_fingerprint_path,
                    manifest_path=candidate_dir / "manifest.json",
                )
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                return {
                    "exitCode": 2,
                    "summary": (
                        f"stackctl package reuse identity blocked for {target_name}"
                    ),
                    "details": [str(exc)],
                    "baselineId": baseline_id,
                }
            pointer = _stackctl.activate_deployment_candidate(target_name, baseline_id)
            return {
                "exitCode": 0,
                "summary": f"stackctl package reused immutable candidate for {env_name}",
                "details": [detail, f"candidateDir={candidate_dir}"],
                "baselineId": baseline_id,
                "candidateDir": str(candidate_dir),
                "activeCandidateRef": str(pointer),
                "reportDir": str(reused_fingerprint.get("reportRef") or ""),
                "packageFingerprint": str(reused_fingerprint_path),
                **package_identity,
                "packageDigest": reused_manifest["packageDigest"],
                "buildInputDigest": reused_manifest["buildInputDigest"],
                "imageDigest": reused_manifest["imageDigest"],
                "runtimeConfigDigest": reused_manifest["runtimeConfigDigest"],
                "environmentRuntimeDigest": reused_manifest[
                    "environmentRuntimeDigest"
                ],
                "runtimeSchemaVersion": reused_manifest["runtimeSchemaVersion"],
                "observabilityLogSink": reused_manifest[
                    "observabilityLogSink"
                ],
                "providerRuntime": reused_manifest["providerRuntime"],
            }

        try:
            args._graphql_read_signing_material = (
                _stackctl._resolve_graphql_read_signing_for_local_target(
                    env_name, target_name
                )
            )
        except (OSError, ValueError) as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return {
                "exitCode": 2,
                "summary": f"stackctl package GraphQL signing inputs blocked for {env_name}",
                "details": [str(exc)],
                "baselineId": baseline_id,
            }

        capsule_root = capsule_staging_root
        os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = str(staging_dir / "packages")
        try:
            payload = _stackctl._command_package_unlocked(
                args,
                package_snapshot=package_snapshot,
                package_input_roots=package_input_roots,
                package_source_root=capsule_root / "repo",
                package_capsule_root=capsule_root,
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        finally:
            if previous_override is None:
                os.environ.pop(_stackctl.PACKAGE_ROOT_OVERRIDE_ENV, None)
            else:
                os.environ[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
        if int(payload.get("exitCode") or 0) != 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return payload
        if candidate_dir.exists():
            shutil.rmtree(staging_dir)
            return {
                "exitCode": 2,
                "summary": f"stackctl package candidate collision for {target_name}",
                "details": [f"candidate already exists: {candidate_dir}"],
                "baselineId": baseline_id,
            }
        staging_dir.replace(candidate_dir)
        staging_text = str(staging_dir)
        candidate_text = str(candidate_dir)
        payload = json.loads(
            json.dumps(payload, ensure_ascii=False).replace(
                staging_text,
                candidate_text,
            )
        )
        report_ref = str(payload.get("reportDir") or "").strip()
        if report_ref:
            evidence_root = (_stackctl.ROOT / report_ref).resolve()
            if evidence_root.is_dir() and evidence_root.is_relative_to(_stackctl.ROOT):
                for evidence_path in evidence_root.rglob("*"):
                    if not evidence_path.is_file() or evidence_path.suffix not in {
                        ".json",
                        ".md",
                    }:
                        continue
                    evidence_text = evidence_path.read_text(encoding="utf-8")
                    if staging_text in evidence_text:
                        evidence_path.write_text(
                            evidence_text.replace(staging_text, candidate_text),
                            encoding="utf-8",
                        )
        payload["candidateDir"] = str(candidate_dir)
        candidate_manifest = _stackctl.load_candidate_manifest(
            env_name,
            target_name,
            baseline_id,
            require_full=True,
        )
        for field in (
            "releaseInputClassification",
            "contractGraphDigest",
            "graphqlReadRegistry",
            "packageDigest",
            "buildInputDigest",
            "imageDigest",
            "runtimeConfigDigest",
            "environmentRuntimeDigest",
            "runtimeSchemaVersion",
            "observabilityLogSink",
            "providerRuntime",
        ):
            payload[field] = candidate_manifest[field]
        fingerprint_path = (
            candidate_dir / "packages" / "app" / "package-fingerprint.json"
        )
        report_ref = str(payload.get("reportDir") or "").strip()
        report_path = _stackctl._runtime_package_report_path(report_ref)
        try:
            package_identity = _stackctl._validate_runtime_package_identity_readback(
                report_path=report_path,
                fingerprint_path=fingerprint_path,
                manifest_path=candidate_dir / "manifest.json",
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "exitCode": 2,
                "summary": (
                    f"stackctl package identity readback blocked for {target_name}"
                ),
                "details": [str(exc)],
                "baselineId": baseline_id,
                "candidateDir": str(candidate_dir),
            }
        payload.update(package_identity)
        # Activate only after report rewrite and full candidate validation so a
        # failed package command cannot leave the environment pointing at a new
        # candidate.
        pointer = _stackctl.activate_deployment_candidate(target_name, baseline_id)
        payload["activeCandidateRef"] = str(pointer)
        return payload
