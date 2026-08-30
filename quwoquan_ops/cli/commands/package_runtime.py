"""stackctl `package` 域 runtime 打包执行层。

从 stackctl.py 逐字迁出仅被 package 域消费的 runtime 打包实现:

- `_command_package_unlocked`:锁内的全量 runtime 打包执行体,同时向
  非 runtime 子 kind(legal-static / ops-portal / web / app-release /
  release-manifest)分发;
- `_validate_runtime_package_identity_readback` /
  `_runtime_package_report_path`:package report / fingerprint /
  candidate manifest 三件套的身份回读校验;
- `_run_runtime_compile_preflight`:物料化前的运行时入口编译预检。

锁与候选 CAS 编排(`command_package` / `_target_package_lock`)在
`commands/package_domain.py`;非 runtime 子 kind 实现与打包物料 helper
在 `commands/package_shared.py`。测试经 ``mock.patch.object(stackctl,
...)`` patch `_command_package_unlocked` / `_build_runtime_shared_package`
等符号,因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问,
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.package_runtime_support import (
    _build_official_skill_package_publication as _build_skill_publication,
)
from quwoquan_ops.cli.commands.package_runtime_support import (
    _receipt_safe_step,
    _receipt_safe_text,
    _runtime_package_report_path,
    _validate_runtime_package_identity_readback,
)
from quwoquan_ops.cli.commands.package_runtime_support import (
    _run_runtime_compile_preflight as _run_compile_preflight,
)

__all__ = (
    "_command_package_unlocked",
    "_run_runtime_compile_preflight",
    "_runtime_package_report_path",
    "_validate_runtime_package_identity_readback",
)

# 与 stackctl.ROOT 同源同值(仓库根);仅用于函数默认参数,
# 函数体内仍统一经 `_stackctl.ROOT` 访问。
_REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_CAPSULE_CAS_BLOCKER = "OPS.PACKAGE.input_capsule_cas_drift"


def _persist_package_capsule_cas_failure(
    *, report_dir: Path, env_name: str, target_name: str,
    package_snapshot: dict[str, object], reports: list[dict[str, Any]],
    detail: str, timing: dict[str, Any],
) -> dict[str, Any]:
    from quwoquan_ops.cli.commands.package_runtime_capsule_receipt import (
        _persist_package_capsule_cas_failure as persist_failure,
    )
    return persist_failure(
        report_dir=report_dir, env_name=env_name, target_name=target_name,
        package_snapshot=package_snapshot, reports=reports, detail=detail, timing=timing,
    )


def _build_official_skill_package_publication(
    env_name: str,
    target_name: str,
    *,
    package_source_root: Path,
    package_environment: dict[str, str],
    output_root: Path | None = None,
) -> dict[str, Any]:
    return _build_skill_publication(
        env_name,
        target_name,
        package_source_root=package_source_root,
        package_environment=package_environment,
        output_root=output_root,
    )


def _run_runtime_compile_preflight(
    *,
    package_environment: dict[str, str],
    source_root: Path = _REPO_ROOT,
) -> tuple[list[dict[str, Any]], str]:
    return _run_compile_preflight(
        package_environment=package_environment,
        source_root=source_root,
    )


def _command_package_unlocked(
    args: argparse.Namespace,
    *,
    package_snapshot: dict[str, object] | None = None,
    package_input_roots: Sequence[str] | None = None,
    package_source_root: Path = _REPO_ROOT,
    package_capsule_root: Path | None = None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import manifest

    if getattr(args, "kind", "runtime") == "release-manifest":
        return _stackctl._command_package_release_manifest(args)
    if getattr(args, "kind", "runtime") == "app-artifact":
        from quwoquan_ops.cli.commands.package_app_artifact import (
            command_package_app_artifact,
        )

        return command_package_app_artifact(args)
    if getattr(args, "kind", "runtime") == "legal-static":
        return _stackctl._command_package_legal_static(args)
    if getattr(args, "kind", "runtime") == "ops-portal":
        return _stackctl._command_package_ops_portal(args)
    if getattr(args, "kind", "runtime") == "web":
        topology = _stackctl.load_environment_topology()
        env_name = args.env
        target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
        target = _stackctl.get_target(topology, target_name)
        public_bases = target.get("publicBases") or {}
        try:
            release = _stackctl.package_web_official_release(
                repo_root=_stackctl.ROOT,
                environment=env_name,
                target=target_name,
                package_root=_stackctl.web_deployment_package_dir(
                    env_name,
                    target=target_name,
                ),
                public_origin=str(public_bases.get("publicWeb") or ""),
            )
        except _stackctl.WebOfficialReleaseError as error:
            return {
                "exitCode": 2,
                "summary": f"stackctl Web package failed for {env_name}",
                "details": [str(error)],
            }
        return {
            "exitCode": 0,
            "summary": f"stackctl Web package completed for {env_name}",
            "details": [
                f"origin: {release['publicOrigin']}",
                f"release: {release['releaseId']}",
                f"manifest: {_stackctl.relpath(Path(str(release['manifestPath'])))}",
                f"active: {_stackctl.relpath(Path(str(release['activePath'])))}",
                f"noindex: {release['noindex']}",
            ],
        }
    if getattr(args, "kind", "runtime") == "app-release":
        topology = _stackctl.load_environment_topology()
        env_name = args.env
        target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
        target = _stackctl.get_target(topology, target_name)
        public_bases = target.get("publicBases") or {}
        package_root = _stackctl.app_deployment_package_dir(env_name, target=target_name)
        if not args.apk_path:
            return {
                "exitCode": 2,
                "summary": f"stackctl app release package blocked for {env_name}",
                "details": ["--apk-path must reference a signed release APK"],
            }
        try:
            release = _stackctl.package_android_official_release(
                apk_path=Path(args.apk_path),
                package_root=package_root,
                public_origin=str(public_bases.get("publicWeb") or ""),
                download_origin=str(public_bases.get("appDownload") or ""),
                # 官网 APK 是 Release 制品；包名按 canonical 身份映射推导，
                # 非 prod 环境带环境后缀，禁止硬编码单一 applicationId。
                expected_package=_stackctl.application_id_for(
                    "android", env_name, "release"
                ),
                expected_signing_certificate_sha256=os.environ.get(
                    "QWQ_ANDROID_EXPECTED_SIGNING_CERTIFICATE_SHA256", ""
                ),
                minimum_supported_version=os.environ.get(
                    "QWQ_ANDROID_MINIMUM_SUPPORTED_VERSION", ""
                ),
                minimum_supported_build=os.environ.get(
                    "QWQ_ANDROID_MINIMUM_SUPPORTED_BUILD", ""
                ),
                minimum_supported_build_evidence_path=(
                    Path(evidence_path)
                    if (
                        evidence_path := os.environ.get(
                            "QWQ_ANDROID_MINIMUM_SUPPORTED_BUILD_EVIDENCE_PATH", ""
                        ).strip()
                    )
                    else None
                ),
                verify_remote=bool(args.verify_remote_apk),
            )
        except _stackctl.AndroidOfficialReleaseError as error:
            return {
                "exitCode": 2,
                "summary": f"stackctl app release package failed for {env_name}",
                "details": [str(error)],
            }
        return {
            "exitCode": 0,
            "summary": f"stackctl app release package completed for {env_name}",
            "details": [
                f"android {release['versionName']} build {release['buildNumber']}",
                f"manifest: {_stackctl.relpath(Path(str(release['manifestPath'])))}",
                f"remoteVerified: {release['remoteVerified']}",
            ],
        }

    topology = _stackctl.load_environment_topology()
    env_name = args.env
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    if package_input_roots is None:
        package_input_roots = _stackctl.deployment_input_roots(
            env_name,
            target_name,
            [args.service] if args.service else _stackctl._all_services(),
            release_attestation=str(
                getattr(args, "release_attestation", "") or ""
            ),
            rollback_release_attestation=str(
                getattr(args, "rollback_release_attestation", "") or ""
            ),
        )
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    details: list[str] = []
    reports: list[dict[str, Any]] = []
    packaged_services: list[str] = []
    provider_runtime_package: dict[str, Any] | None = None
    provider_binding_overlay_package: dict[str, Any] | None = None
    observability_log_sink_package: dict[str, Any] | None = None
    graphql_read_registry_package: dict[str, Any] | None = None
    package_cache = _stackctl.target_cache_dir(target_name) / "package"
    go_build_cache = package_cache / "go-build"
    go_tmp = package_cache / "go-tmp"
    go_build_cache.mkdir(parents=True, exist_ok=True)
    go_tmp.mkdir(parents=True, exist_ok=True)
    package_environment = {
        "QWQ_DEPLOY_TARGET": target_name,
        # Capsule-owned modules derive defaults from their own immutable
        # location.  Runtime outputs and deploy payloads remain host-owned
        # external state, so pass both roots explicitly into every producer.
        "QWQ_OUTPUT_ROOT": str(_stackctl.output_root().expanduser().resolve()),
        "QWQ_DEPLOY_WORK_ROOT": str(
            _stackctl.deployment_work_root(target_name).parent.expanduser().resolve()
        ),
        "QWQ_PACKAGE_SOURCE_REVISION": str(
            (package_snapshot or {}).get("sourceRevision") or ""
        ),
        "GOCACHE": str(go_build_cache),
        "GOTMPDIR": str(go_tmp),
    }
    preflight_reports, preflight_error = _stackctl._run_runtime_compile_preflight(
        package_environment=package_environment,
        source_root=package_source_root,
    )
    reports.extend(preflight_reports)
    if preflight_error:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "status": "GATE_BLOCK",
                "command": "package",
                "env": env_name,
                "target": target_name,
                "details": [preflight_error],
                "steps": reports,
                **timing,
            },
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="GATE_BLOCK",
            summary=f"stackctl runtime compile preflight blocked for {env_name}",
            details=[preflight_error],
            extra={"env": env_name},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime compile preflight blocked for {env_name}",
            "details": [preflight_error],
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    if not args.service:
        legal_result, legal_payload = _stackctl._legal_static_command(
            "package",
            env_name,
            target=target_name,
            source_root=package_source_root,
            environment=package_environment,
        )
        reports.append(
            _receipt_safe_step({
                "name": "legal-static-package",
                "argv": legal_payload.get("argv", []),
                "exitCode": legal_result.returncode,
                "stdout": legal_result.stdout,
                "stderr": legal_result.stderr,
            })
        )
        if legal_result.returncode != 0:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            detail = (
                _receipt_safe_text(legal_result.stderr.strip())
                or _receipt_safe_text(legal_result.stdout.strip())
                or "legal-static package failed"
            )
            _stackctl.write_json(
                report_dir / "report.json",
                {"status": "failed", "steps": reports, **timing},
            )
            return {
                "exitCode": legal_result.returncode,
                "summary": f"stackctl package failed for legal-static/{env_name}",
                "details": [detail],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            f"legal-static package ready: {legal_payload.get('packageDir', '')}"
        )

    if not args.service:
        app_cmd = ["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", env_name]
        app_result = _stackctl.run(app_cmd, cwd=package_source_root, env=package_environment)
        reports.append(
            _receipt_safe_step({
                "name": "app-package",
                "argv": app_cmd,
                "exitCode": app_result.returncode,
                "stdout": app_result.stdout,
                "stderr": app_result.stderr,
            })
        )
        if app_result.returncode != 0:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            _stackctl.write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _stackctl._write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=f"stackctl package failed for {env_name}",
                details=[
                    _receipt_safe_text(app_result.stderr.strip())
                    or _receipt_safe_text(app_result.stdout.strip())
                ],
                extra={"env": env_name},
                timing=timing,
            )
            _stackctl._write_stdout_markdown(report_dir, [("app-package", "\n".join(filter(None, [app_result.stdout, app_result.stderr])))])
            return {
                "exitCode": app_result.returncode,
                "summary": f"stackctl package failed for {env_name}",
                "details": [
                    _receipt_safe_text(app_result.stderr.strip())
                    or _receipt_safe_text(app_result.stdout.strip())
                ],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            f"app package ready: {_stackctl.relpath(_stackctl.app_deployment_package_dir(env_name, target=target_name))}"
        )

    if args.include_services or args.service:
        services = [args.service] if args.service else _stackctl._all_services()
        packaged_services = list(services)
        for service in services:
            svc_cmd = [
                "bash",
                "quwoquan_service/scripts/runtime/packaging/build_service_env_package.sh",
                "--service",
                service,
                "--env",
                env_name,
            ]
            svc_result = _stackctl.run(svc_cmd, cwd=package_source_root, env=package_environment)
            reports.append(
                _receipt_safe_step({
                    "name": f"service-package:{service}",
                    "argv": svc_cmd,
                    "exitCode": svc_result.returncode,
                    "stdout": svc_result.stdout,
                    "stderr": svc_result.stderr,
                })
            )
            if svc_result.returncode != 0:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                _stackctl.write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="package",
                    target=target_name,
                    status="failed",
                    summary=f"stackctl package failed for {service}/{env_name}",
                    details=[
                        _receipt_safe_text(svc_result.stderr.strip())
                        or _receipt_safe_text(svc_result.stdout.strip())
                    ],
                    extra={"env": env_name},
                    timing=timing,
                )
                _stackctl._write_stdout_markdown(
                    report_dir,
                    [(f"service-package:{service}", "\n".join(filter(None, [svc_result.stdout, svc_result.stderr])))],
                )
                return {
                    "exitCode": svc_result.returncode,
                    "summary": f"stackctl package failed for {service}/{env_name}",
                    "details": [
                        _receipt_safe_text(svc_result.stderr.strip())
                        or _receipt_safe_text(svc_result.stdout.strip())
                    ],
                    "reportDir": _stackctl.relpath(report_dir),
                    **timing,
                }
            details.append(
                "service package ready: "
                f"{_stackctl.relpath(_stackctl.service_deployment_package_dir(env_name, service, target=target_name))}"
            )

    if not args.service:
        skill_step = _build_official_skill_package_publication(
            env_name,
            target_name,
            package_source_root=package_source_root,
            package_environment=package_environment,
        )
        skill_step = _receipt_safe_step(skill_step)
        reports.append(skill_step)
        if skill_step["exitCode"] != 0:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            _stackctl.write_json(
                report_dir / "report.json",
                {"status": "failed", "steps": reports, **timing},
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=(
                    "stackctl package failed while building the official "
                    f"Skill package publication for {env_name}"
                ),
                details=[
                    str(skill_step["stderr"]).strip()
                    or str(skill_step["stdout"]).strip()
                ],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": int(skill_step["exitCode"]),
                "summary": (
                    "stackctl package failed while building the official "
                    f"Skill package publication for {env_name}"
                ),
                "details": [
                    str(skill_step["stderr"]).strip()
                    or str(skill_step["stdout"]).strip()
                ],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append("official Skill package publication ready")

    materialized_release_evidence: dict[str, str] = {}
    if not args.service:
        try:
            materialized_release_evidence = _stackctl._materialize_release_evidence_configuration(
                env_name,
                target=target_name,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            _stackctl.write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _stackctl._write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=(
                    "stackctl package failed while materializing release evidence "
                    f"for {env_name}"
                ),
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": (
                    "stackctl package failed while materializing release evidence "
                    f"for {env_name}"
                ),
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        if materialized_release_evidence:
            details.append(
                f"{env_name} release evidence materialized: "
                f"candidateId={materialized_release_evidence['candidateId']}"
            )

    if not args.service:
        if package_snapshot is None:
            raise RuntimeError("runtime package requires an immutable input capsule")
        try:
            api_edge_package = _stackctl.service_deployment_package_dir(
                env_name,
                "api-edge",
                target=target_name,
            )
            graphql_read_registry_package = (
                _stackctl.materialize_graphql_read_registry_package(
                    repo_root=package_source_root,
                    candidate_root=api_edge_package.parents[2],
                    environment=env_name,
                    target=target_name,
                    candidate_digest=str(package_snapshot["baselineId"]),
                    scratch_root=package_cache / "graphql-read-registry",
                    signing=getattr(
                        args,
                        "_graphql_read_signing_material",
                        None,
                    ),
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": (
                    "stackctl package signed GraphQL registry is GATE_BLOCK for "
                    f"{env_name}"
                ),
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                "baselineId": package_snapshot["baselineId"],
                **timing,
            }
        details.append(
            "signed GraphQL registry ready: "
            + str(graphql_read_registry_package["envelopeDigest"])
        )

    if not args.service:
        try:
            shared_package_dir = _stackctl._build_runtime_shared_package(
                env_name,
                target=target_name,
                source_root=package_source_root,
            )
        except (OSError, FileNotFoundError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            _stackctl.write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _stackctl._write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=f"stackctl package failed while building shared runtime package for {env_name}",
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": f"stackctl package failed while building shared runtime package for {env_name}",
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(f"runtime shared package ready: {_stackctl.relpath(shared_package_dir)}")
        try:
            provider_runtime_package = _stackctl.materialize_provider_runtime_package(
                env_name,
                target_name,
                source_root=package_source_root,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": (
                    "stackctl package Provider runtime is GATE_BLOCK for "
                    f"{env_name}"
                ),
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            "Provider runtime package ready: "
            + str(
                provider_runtime_package["composition"][
                    "runtimeCompositionDigest"
                ]
            )
        )
        try:
            provider_binding_overlay_package = (
                _stackctl.materialize_provider_binding_overlay(
                    env_name,
                    target_name,
                    source_root=package_source_root,
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": (
                    "stackctl package Provider binding overlay is GATE_BLOCK for "
                    f"{env_name}"
                ),
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            "Provider binding overlay ready: "
            + str(provider_binding_overlay_package["bindingManifestDigest"])
        )
        try:
            observability_log_sink_package = (
                _stackctl.materialize_observability_log_sink_package(
                    env_name,
                    target_name,
                    provider_runtime_package["composition"],
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": (
                    "stackctl package observability log sink is GATE_BLOCK for "
                    f"{env_name}"
                ),
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            "observability log-sink package ready: "
            + str(observability_log_sink_package["bindingDigest"])
        )

    if (
        bool(args.include_services)
        and not args.service
        and target_name in {"alpha-local", "beta-local", "gamma-local"}
    ):
        if (
            provider_runtime_package is None
            or provider_binding_overlay_package is None
            or observability_log_sink_package is None
        ):
            raise RuntimeError(
                "Provider and observability runtime packages were not materialized"
            )
        try:
            image_manifest_path, image_manifest = _stackctl._build_package_bound_local_images(
                env_name,
                target_name,
                report_dir=report_dir,
                provider_binding_overlay=provider_binding_overlay_package,
                provider_runtime=provider_runtime_package,
                observability_log_sink=observability_log_sink_package,
                candidate_root=shared_package_dir.parent.parent,
                candidate_digest=str(package_snapshot["baselineId"]),
                source_root=package_source_root,
            )
        except RuntimeError as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            detail = _receipt_safe_text(str(exc))
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "status": "GATE_BLOCK",
                    "command": "package",
                    "env": env_name,
                    "target": target_name,
                    "details": [detail],
                    "steps": reports,
                    **timing,
                },
            )
            return {
                "exitCode": 2,
                "summary": f"stackctl package OCI build blocked for {env_name}",
                "details": [detail],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.extend(
            [
                f"OCI image manifest ready: {_stackctl.relpath(image_manifest_path)}",
                f"buildInputDigest: {image_manifest['buildInputDigest']}",
                f"imageDigest: {image_manifest['imageDigest']}",
            ]
        )
    elif (
        bool(args.include_services)
        and not args.service
        and target_name == "prod-hosted"
    ):
        if provider_runtime_package is None or package_snapshot is None:
            raise RuntimeError("prod-hosted package inputs were not materialized")
        try:
            image_manifest_path, image_manifest = (
                manifest._materialize_prod_hosted_oci_manifest(
                    env_name,
                    target_name,
                    provider_runtime=provider_runtime_package,
                    candidate_root=shared_package_dir.parent.parent,
                    package_snapshot=package_snapshot,
                    materialized_release_evidence=materialized_release_evidence,
                    source_root=package_source_root,
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            detail = str(exc)
            return {
                "exitCode": 2,
                "summary": f"stackctl package hosted OCI evidence blocked for {env_name}",
                "details": [detail],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            }
        details.append(
            f"hosted OCI image manifest ready: {_stackctl.relpath(image_manifest_path)} "
            f"buildInputDigest={image_manifest['buildInputDigest']} "
            f"imageDigest={image_manifest['imageDigest']}"
        )

    app_launch_bundle: dict[str, Any] | None = None
    if target_name == "prod-sim":
        if package_snapshot is None or package_capsule_root is None:
            raise RuntimeError("prod-sim App launch bundle requires immutable inputs")
        try:
            app_launch_bundle = manifest.materialize_prod_sim_app_launch_bundle(
                candidate_root=package_capsule_root.parent,
                package_snapshot=package_snapshot,
                materialized_release_evidence=materialized_release_evidence,
                source_root=package_source_root,
            )
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl package prod-sim App launch bundle is GATE_BLOCK",
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                "baselineId": package_snapshot["baselineId"],
                **timing,
            }
        details.append(
            "prod-sim App launch bundle ready: "
            + str(app_launch_bundle["artifactManifestDigest"])
        )

    if package_snapshot is None or package_capsule_root is None:
        raise RuntimeError("runtime package requires an immutable input capsule")
    try:
        _stackctl.verify_package_input_capsule(
            package_capsule_root,
            expected_snapshot=package_snapshot,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return _persist_package_capsule_cas_failure(
            report_dir=report_dir,
            env_name=env_name,
            target_name=target_name,
            package_snapshot=package_snapshot,
            reports=reports,
            detail=str(exc),
            timing=timing,
        )

    try:
        release_bindings = _stackctl.validate_release_attestations(
            str(getattr(args, "release_attestation", "") or ""),
            str(getattr(args, "rollback_release_attestation", "") or ""),
        )
        release_classification = _stackctl.classify_release_inputs(release_bindings)
        contract_graph_digest = _stackctl.canonical_contract_graph_digest()
        fingerprint = _stackctl.write_package_fingerprint(
            env_name,
            target_name,
            report_dir=_stackctl.relpath(report_dir),
            include_services=True,
            details=details,
            release_input_classification=release_classification,
            contract_graph_digest=contract_graph_digest,
            graphql_read_registry=graphql_read_registry_package or {},
            app_launch_bundle=(
                {
                    **app_launch_bundle,
                    "candidateDigest": _stackctl.package_content_digest(
                        env_name,
                        target_name,
                        service_packages=packaged_services,
                        candidate_root=package_capsule_root.parent,
                    )[0],
                }
                if app_launch_bundle is not None
                else None
            ),
            service_packages=packaged_services,
            release_attestation=str(
                getattr(args, "release_attestation", "") or ""
            ),
            rollback_release_attestation=str(
                getattr(args, "rollback_release_attestation", "") or ""
            ),
            expected_snapshot=package_snapshot,
            candidate_root=package_capsule_root.parent,
        )
        candidate_manifest = _stackctl.write_candidate_manifest(
            env_name,
            target_name,
            package_snapshot=package_snapshot,
            release_attestation=str(
                getattr(args, "release_attestation", "") or ""
            ),
            rollback_release_attestation=str(
                getattr(args, "rollback_release_attestation", "") or ""
            ),
            app_launch_bundle=app_launch_bundle,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "status": "GATE_BLOCK",
                "command": "package",
                "env": env_name,
                "target": target_name,
                "baselineId": package_snapshot["baselineId"],
                "details": [str(exc)],
                "steps": reports,
                **timing,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl package candidate manifest blocked for {env_name}",
            "details": [str(exc)],
            "reportDir": _stackctl.relpath(report_dir),
            "baselineId": package_snapshot["baselineId"],
            **timing,
        }
    candidate_manifest_payload = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    package_identity_digest = str(candidate_manifest_payload.get("packageDigest") or "")
    details.append(f"package fingerprint: {_stackctl.relpath(fingerprint)}")
    details.append(f"candidate manifest: {candidate_manifest}")
    details.append(f"baselineId: {package_snapshot['baselineId']}")
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "baselineId": package_snapshot["baselineId"],
        "sourceRevision": package_snapshot["sourceRevision"],
        "workspaceStatusDigest": package_snapshot["workspaceStatusDigest"],
        "releaseInputClassification": release_classification,
        "contractGraphDigest": contract_graph_digest,
        "graphqlReadRegistry": graphql_read_registry_package,
        "appLaunchBundle": (
            {**app_launch_bundle, "candidateDigest": package_identity_digest}
            if app_launch_bundle is not None
            else None
        ),
        "timestamp": _stackctl.utc_now(),
        "reportDir": _stackctl.relpath(report_dir),
        "steps": reports,
        **timing,
    }
    payload.update(materialized_release_evidence)
    if topology is not None:
        payload["topologyTarget"] = _stackctl.get_target(topology, target_name)
    _stackctl.write_json(report_dir / "report.json", payload)
    try:
        package_identity = _stackctl._validate_runtime_package_identity_readback(
            report_path=report_dir / "report.json",
            fingerprint_path=fingerprint,
            manifest_path=candidate_manifest,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "summary": f"stackctl package identity readback blocked for {env_name}",
            "details": [str(exc)],
            "reportDir": _stackctl.relpath(report_dir),
            "baselineId": package_snapshot["baselineId"],
            **timing,
        }
    _stackctl._write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status="ok",
        summary=f"stackctl package completed for {env_name}",
        details=details,
        extra={"env": env_name},
        timing=timing,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl package completed for {env_name}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "packageFingerprint": _stackctl.relpath(fingerprint),
        "baselineId": package_snapshot["baselineId"],
        **package_identity,
        **timing,
    }
