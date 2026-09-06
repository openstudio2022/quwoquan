"""stackctl `package` 域共享子命令与打包 helper。

从 stackctl.py 逐字迁出仅被 package 域消费的实现:

- 非 runtime 子 kind 命令:`_command_package_legal_static` /
  `_command_package_ops_portal`
  (由 `commands/package_runtime.py` 的 `_command_package_unlocked` 分发);
- runtime 打包物料 helper:`_build_runtime_shared_package` /
  `_build_package_bound_local_images`(仅被 `_command_package_unlocked`
  与测试消费)。

`_command_package_ops_portal` 受
`quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py` 的 SCOPED_FUNCTIONS
按 AST 定义位置锁定,该映射已随本次迁移指向本文件。

跨域共用的 `_legal_static_command` / `_materialize_release_evidence_configuration`
等仍由 stackctl 命名空间拥有(verify / deploy 等留守域共用,且测试经
``mock.patch.object(stackctl, ...)`` patch 它们),因此函数体内一律经
函数内延迟导入 `_stackctl` 属性访问,保持 monkeypatch 语义并避免
顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.local_environment_object_storage import (
    package_build_object_storage_environment,
)

# 与 stackctl.ROOT 同源同值(仓库根);仅用于函数默认参数,
# 函数体内仍统一经 `_stackctl.ROOT` 访问。
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _runtime_shared_source_ref(source: Path, source_root: Path) -> str:
    """Record repo-relative provenance even when packaging from a capsule tree."""
    resolved = source.resolve()
    for root in (source_root, _REPO_ROOT):
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    text = resolved.as_posix()
    marker = "/repo/"
    idx = text.find(marker)
    if idx != -1:
        return text[idx + len(marker) :]
    return text


def _build_runtime_shared_package(
    env_name: str,
    *,
    target: str = "",
    source_root: Path = _REPO_ROOT,
) -> Path:
    """将运行栈共享静态配置封装为环境 package,禁止启动期直读仓内源文件。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    target_name = _stackctl.deployment_target_for_env(env_name, target=target)
    package_dir = _stackctl.runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if package_dir.exists():
        _stackctl.remove_deployment_tree(
            target_name,
            "packages",
            "runtime-shared",
        )
    package_dir.mkdir(parents=True, exist_ok=True)
    sources = (
        source_root / "quwoquan_service" / "runtime" / "reliabletask" / "resources" / "module_catalog.yaml",
        source_root / "quwoquan_service" / "runtime" / "reliabletask" / "resources" / "retention_policy.yaml",
        source_root / "quwoquan_ops" / "environments" / "compose" / "object-storage-lifecycle.json",
        source_root / "quwoquan_ops" / "external" / "livekit" / "base" / "livekit.yaml",
        source_root / "quwoquan_ops" / "environments" / "gamma" / "local" / "Caddyfile",
    )
    files: dict[str, dict[str, str]] = {}
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(f"missing runtime shared package source: {source}")
        destination = package_dir / source.name
        shutil.copy2(source, destination)
        files[source.name] = {
            "source": _runtime_shared_source_ref(source, source_root),
            "sha256": _stackctl._sha256_file(destination),
        }
    _stackctl.materialize_runtime_topology_package(
        env_name,
        target_name,
        package_dir,
        repo_root=source_root,
    )
    _stackctl.write_json(
        package_dir / "manifest.json",
        {
            "schema": "qwq.runtime_shared_package",
            "environment": env_name,
            "createdAt": _stackctl.utc_now(),
            "provenance": {"files": files},
        },
    )
    return package_dir


def _build_package_bound_local_images(
    env_name: str,
    target_name: str,
    *,
    report_dir: Path,
    provider_binding_overlay: Mapping[str, Any],
    provider_runtime: Mapping[str, Any],
    observability_log_sink: Mapping[str, Any],
    candidate_root: Path,
    candidate_digest: str,
    source_root: Path = _REPO_ROOT,
) -> tuple[Path, dict[str, Any]]:
    """Build and attest the exact local OCI inputs during package, never during up."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest) is None:
        raise ValueError("package-bound OCI candidate digest is invalid")
    topology = _stackctl.load_environment_topology()
    environment = _stackctl._gamma_env_from_port_manifest(topology, target_name)
    environment.update(
        _stackctl._provider_runtime_launch_environment(
            provider_runtime,
            candidate_root=candidate_root,
            workload="full",
            require_images=False,
        )
    )
    environment.update(
        _stackctl._observability_log_sink_launch_environment(
            observability_log_sink,
            environment_name=env_name,
            target_name=target_name,
            candidate_root=candidate_root,
            workload="full",
        )
    )
    _stackctl._bind_gamma_down_parse_environment(environment)
    environment.update(
        {
            "QWQ_RUN_ROOT": str(report_dir.resolve()),
            "QWQ_OBSERVABILITY_RUN_ROOT": str(
                _stackctl.env_observability_run_dir(env_name, report_dir.name).resolve()
            ),
            "QWQ_WORKLOAD": "full",
            "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
            "QWQ_RELEASE_CANDIDATE_DIGEST": candidate_digest,
            # DEC-005：镜像字节环境无关，环境名只作为 Compose 插值输入；
            # 环境身份由部署面在 up 时生成 artifact-identity.json 并挂载。
            "QWQ_COMPOSE_ENV": env_name,
        }
    )
    environment.update(
        package_build_object_storage_environment(target_name=target_name)
    )
    _stackctl._sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    _stackctl._bind_package_provider_reference_environment(
        environment,
        environment_name=env_name,
        runtime_composition=provider_runtime["composition"],
    )
    overlay_dir, _, binding_manifest_digest = (
        _stackctl.provider_binding_overlay_build_inputs(
            provider_binding_overlay,
            candidate_root=candidate_root,
            build_context=source_root,
        )
    )
    environment["QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT"] = str(overlay_dir)
    environment["QWQ_PROVIDER_BINDING_MANIFEST_DIGEST"] = binding_manifest_digest
    composition = _stackctl._bind_gamma_build_service_image_refs(
        env_name,
        environment,
        candidate_digest=candidate_digest,
    )
    provider_images = _stackctl._build_provider_runtime_images(
        provider_runtime,
        environment,
    )
    for role, descriptor in provider_images.items():
        environment[_stackctl.provider_runtime_image_environment_key(role)] = str(
            descriptor["imageDigest"]
        )
    def inspect_images() -> tuple[dict[str, dict[str, str]], list[str]]:
        inspected: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        for service, descriptor in sorted(composition["images"].items()):
            image_ref = str(descriptor["ref"])
            inspect = _stackctl.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]
            )
            image_digest = inspect.stdout.strip()
            if (
                inspect.returncode != 0
                or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None
            ):
                missing.append(service)
                continue
            inspected[service] = {
                "ref": image_ref,
                "imageDigest": image_digest,
            }
        return inspected, missing

    # Source-digest tags are common build artifacts.  Rebuilding the same tag
    # for every target produces non-deterministic OCI config timestamps and
    # lets the later target overwrite the earlier target's attested image ID.
    # Build exactly once when any source image is absent; otherwise attest the
    # already materialized immutable source set for every target package.
    images, missing_images = inspect_images()
    build_results: list[subprocess.CompletedProcess[str]] = []
    if missing_images:
        build_results = _stackctl._build_missing_runtime_images(
            missing_images,
            source_root=source_root,
            environment=environment,
            refs=composition["images"],
        )
        images, missing_images = inspect_images()
    if missing_images:
        details = [
            "package-bound OCI digest is unavailable: " + ", ".join(missing_images)
        ]
        for build_result in build_results:
            for stream_name, stream_value in (
                ("stdout", build_result.stdout),
                ("stderr", build_result.stderr),
            ):
                normalized = stream_value.strip()
                if normalized:
                    details.append(
                        f"OCI build {stream_name} tail: {normalized[-4000:]}"
                    )
        raise RuntimeError("\n".join(details))
    sealed_provider_runtime = _stackctl.seal_provider_runtime_package_images(
        env_name,
        target_name,
        candidate_root,
        provider_images,
    )
    images.update(provider_images)
    image_set_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            images,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema": _stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "configurationDigest": composition["configurationDigest"],
        "buildInputDigest": "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "firstPartyImageVersion": composition["imageVersion"],
                    "providerRuntimeDigest": sealed_provider_runtime["composition"][
                        "runtimeCompositionDigest"
                    ],
                    "providerBindingManifestDigest": binding_manifest_digest,
                    "providerImageRefs": {
                        role: {
                            "buildInputDigest": descriptor["buildInputDigest"],
                            "ref": descriptor["ref"],
                        }
                        for role, descriptor in sorted(provider_images.items())
                    },
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "imageDigest": image_set_digest,
        "images": images,
    }
    manifest_path = (
        _stackctl.runtime_shared_deployment_package_dir(env_name, target=target_name)
        / "oci-images.json"
    )
    _stackctl.write_json(manifest_path, manifest)
    return manifest_path, manifest


def _command_package_legal_static(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = args.env
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    if args.service or args.include_services:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        details = ["legal-static packages cannot include service packages"]
        _stackctl._write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl legal-static package failed for {env_name}",
            details=details,
            extra={"env": env_name, "kind": "legal-static"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl legal-static package failed for {env_name}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    result, legal_payload = _stackctl._legal_static_command(
        "package",
        env_name,
        target=target_name,
    )
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = "ok" if result.returncode == 0 else "failed"
    details = []
    if result.returncode == 0:
        details.append(f"legal-static package ready: {legal_payload.get('packageDir', '')}")
        if legal_payload.get("currentPointer"):
            details.append(f"legal-static current pointer: {legal_payload['currentPointer']}")
    else:
        issues = legal_payload.get("issues") if isinstance(legal_payload.get("issues"), list) else []
        details.extend(str(issue) for issue in issues)
        if not details:
            details.append(result.stderr.strip() or result.stdout.strip() or "legal-static package failed")
    report = {
        "status": status,
        "command": "package",
        "kind": "legal-static",
        "env": env_name,
        "target": target_name,
        "timestamp": _stackctl.utc_now(),
        "step": {
            "name": "legal-static-package",
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "payload": legal_payload,
        },
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    _stackctl._write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "kind": "legal-static"},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(
        report_dir,
        [("legal-static-package", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _command_package_ops_portal(args: argparse.Namespace) -> dict[str, Any]:
    """通过 stackctl 构建 Portal 包，并补齐可复算的 package provenance。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = args.env
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    details: list[str] = []
    if env_name != "prod" or target_name != "prod-hosted":
        details.append("ops-portal package is supported only for prod/prod-hosted")
    if args.service or args.include_services:
        details.append("ops-portal packages cannot include service packages")
    oidc_values = {
        "issuer": str(
            getattr(args, "oidc_issuer", "") or os.environ.get("PROD_OPS_OIDC_ISSUER", "")
        ).strip(),
        "clientId": str(
            getattr(args, "oidc_client_id", "")
            or os.environ.get("PROD_OPS_OIDC_CLIENT_ID", "")
        ).strip(),
        "audience": str(
            getattr(args, "oidc_audience", "")
            or os.environ.get("PROD_OPS_OIDC_AUDIENCE", "")
        ).strip(),
        "scope": str(
            getattr(args, "oidc_scope", "") or os.environ.get("PROD_OPS_OIDC_SCOPE", "")
        ).strip(),
    }
    missing_oidc = [name for name, value in oidc_values.items() if not value]
    if missing_oidc:
        details.append(
            "ops-portal package requires OIDC values: " + ", ".join(missing_oidc)
        )
    if details:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl._write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl ops-portal package failed for {env_name}",
            details=details,
            extra={"env": env_name, "kind": "ops-portal"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl ops-portal package failed for {env_name}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    command = [
        "python3",
        "quwoquan_ops/cli/prod/build_portal_release.py",
        "--oidc-issuer",
        oidc_values["issuer"],
        "--oidc-client-id",
        oidc_values["clientId"],
        "--oidc-audience",
        oidc_values["audience"],
        "--oidc-scope",
        oidc_values["scope"],
        "--target",
        target_name,
    ]
    for flag, attribute in (
        ("--ops-base-url", "ops_base_url"),
        ("--content-base-url", "content_base_url"),
        ("--entity-base-url", "entity_base_url"),
    ):
        value = str(getattr(args, attribute, "") or "").strip()
        if value:
            command.extend((flag, value))
    if getattr(args, "skip_install", False):
        command.append("--skip-install")

    result = _stackctl.run(command, env={"QWQ_DEPLOY_TARGET": target_name})
    package_root = _stackctl.portal_deployment_package_dir(env_name, target=target_name)
    current_package = package_root / "current"
    package_dir = current_package.resolve()
    if result.returncode == 0:
        manifest_path = package_dir / "manifest.json"
        dist_dir = package_dir / "dist"
        if not manifest_path.is_file() or not dist_dir.is_dir():
            result = subprocess.CompletedProcess(
                command,
                1,
                stdout=result.stdout,
                stderr=(
                    "ops-portal builder did not produce manifest.json and dist/: "
                    f"{package_dir}"
                ),
            )
        else:
            revision_result = _stackctl.run(["git", "rev-parse", "HEAD"])
            revision = revision_result.stdout.strip()
            if (
                revision_result.returncode != 0
                or not re.fullmatch(r"[0-9a-f]{40}", revision)
            ):
                result = subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=result.stdout,
                    stderr=(
                        "ops-portal package provenance requires git revision: "
                        + (revision_result.stderr.strip() or revision_result.stdout.strip())
                    ),
                )
            else:
                portal_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                package_digest = str(portal_manifest.get("packageDigest") or "")
                if (
                    not re.fullmatch(r"sha256:[0-9a-f]{64}", package_digest)
                    or package_dir.name != package_digest.removeprefix("sha256:")
                ):
                    result = subprocess.CompletedProcess(
                        command,
                        1,
                        stdout=result.stdout,
                        stderr="ops-portal builder produced invalid packageDigest identity",
                    )
                    package_digest = ""
                provenance = {
                    "schema": "qwq.ops_portal_package",
                    "packageKind": "ops-portal",
                    "environment": env_name,
                    "target": target_name,
                    "packageDigest": package_digest,
                    "gitRevision": revision,
                    "digests": {
                        "manifest": _stackctl._sha256_file(manifest_path),
                        "distTree": _stackctl._sha256_tree(dist_dir),
                    },
                }
                if result.returncode == 0:
                    _stackctl.write_json(package_dir / "provenance.json", provenance)
                    details.append(f"ops-portal package ready: {_stackctl.relpath(package_dir)}")
    if result.returncode != 0:
        details.extend(_stackctl._command_details(result))
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = "ok" if result.returncode == 0 else "failed"
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "package",
            "kind": "ops-portal",
            "env": env_name,
            "target": target_name,
            "step": {
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            **timing,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            f"stackctl ops-portal package completed for {env_name}"
            if status == "ok"
            else f"stackctl ops-portal package failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "kind": "ops-portal"},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(
        report_dir,
        [("ops-portal-package", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl ops-portal package completed for {env_name}"
            if status == "ok"
            else f"stackctl ops-portal package failed for {env_name}"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
