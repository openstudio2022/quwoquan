"""prod plane 渲染 main 装配流程（从 render_prod_plane_stack.py 逐字搬移）。

``_rewrite_service`` / ``_write_config_tree`` / ``_write_caddyfile`` 被 gate
源码文本扫描钉在薄入口文件中，本模块在 ``main`` 内延迟导入入口模块并按
模块属性访问它们，既避免初始化环，也保持 monkeypatch 语义。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files
from quwoquan_ops.cli.lib.output_paths import deployment_target_path
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import portal_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import remove_deployment_tree
from quwoquan_ops.cli.lib.output_paths import target_local_dir as resolve_target_local_dir
from quwoquan_ops.cli.lib.output_paths import web_deployment_package_dir
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    materialize_web_runtime_config,
)

from .constants import ROOT, RUNTIME_LOG_EXPORT_SERVICES
from .package_inputs import (
    _git_revision,
    _load_yaml,
    _plane_spec,
    _prevalidation_spec,
    _resolve_render_output_dir,
    parse_args,
)
from .runtime_outputs import (
    _write_env_file,
    _write_observability_tree,
    _write_runtime_systemd_unit,
)
from .volume_layout import _filter_top_level_volumes

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

def main() -> int:
    # 延迟导入入口模块：_rewrite_service / _write_config_tree / _write_caddyfile
    # 被 gate 文本扫描钉在薄入口文件，按模块属性访问以避免初始化环。
    from quwoquan_ops.cli.prod import render_prod_plane_stack as _stack

    args = parse_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.replica_id) is None:
        raise SystemExit("FAIL: --replica-id must be a safe lowercase identifier")
    if args.host_id and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.host_id) is None:
        raise SystemExit("FAIL: --host-id must be a safe lowercase identifier")
    plane = _plane_spec(args.plane)
    compose_template = ROOT / str(plane.get("rootlessComposeTemplate") or "")
    if not compose_template.is_file():
        raise SystemExit(f"FAIL: missing compose template: {compose_template}")

    governed = [str(item) for item in plane.get("rootlessGovernedComposeServices") or []]
    support = [str(item) for item in plane.get("rootlessSupportComposeServices") or []]
    config_services = [str(item) for item in plane.get("rootlessConfigServices") or []]
    startup_services = list(governed + support)
    image_only_services: list[str] = []
    prevalidation_images: dict[str, str] = {}
    if args.instance == "prevalidate":
        if args.prevalidate_scope != "first-party":
            raise SystemExit("FAIL: prevalidate instance requires --prevalidate-scope first-party")
        prevalidation = _prevalidation_spec()
        if args.data_mode not in (prevalidation.get("allowedDataModes") or []):
            raise SystemExit(f"FAIL: unsupported prevalidation data mode: {args.data_mode}")
        plane_projection = (prevalidation.get("planes") or {}).get(args.plane)
        if not isinstance(plane_projection, dict):
            raise SystemExit(f"FAIL: prevalidation plane projection missing: {args.plane}")
        startup_governed = [
            str(item) for item in (plane_projection.get("startupServices") or [])
        ]
        image_only_services = [
            str(item)
            for item in (plane_projection.get("imageAndConfigOnlyServices") or [])
        ]
        governed = startup_governed + image_only_services
        support = ["gamma-proxy"] if args.plane == "service" else []
        if args.data_mode == "isolated" and args.plane == "service":
            isolated = prevalidation.get("isolatedData") or {}
            support = [str(item) for item in (isolated.get("services") or [])] + support
            prevalidation_images = {
                str(name): str(ref)
                for name, ref in (isolated.get("images") or {}).items()
            }
        startup_services = support + startup_governed
        allowed = set(plane.get("rootlessGovernedComposeServices") or [])
        if not set(governed).issubset(allowed):
            raise SystemExit(
                f"FAIL: prevalidation services escape {args.plane} plane ownership"
            )
        if args.plane == "service" and "integration-service" not in image_only_services:
            raise SystemExit("FAIL: integration-service must remain image/config-only")
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    runtime_credentials = dict(plane.get("rootlessRuntimeCredentials") or {})
    selected = governed + support
    if not selected:
        raise SystemExit(f"FAIL: plane {args.plane} missing rootless compose service list")

    layout = plane.get("rootlessRuntimeLayout") or {}
    config_root = str(layout.get("configRoot") or "runtime/config-root")
    caddyfile_path = str(layout.get("caddyfile") or "runtime/Caddyfile")
    media_state_ref = str(layout.get("mediaStateRef") or "").strip()
    if not media_state_ref:
        raise SystemExit("FAIL: rootlessRuntimeLayout.mediaStateRef is required")
    media_ref_path = Path(media_state_ref)
    if media_ref_path.is_absolute() or ".." in media_ref_path.parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.mediaStateRef must be a safe state-relative path")
    media_root = str((resolve_target_local_dir("prod-hosted") / media_ref_path).resolve())
    legal_root = str(layout.get("legalStaticRoot") or "runtime/legal-static")
    portal_root = str(layout.get("portalStaticRoot") or "runtime/portal")
    web_root = str(layout.get("webStaticRoot") or "runtime/public-web")
    model_cache_root = str(layout.get("modelCacheRoot") or "runtime/model-cache")
    if Path(config_root).is_absolute() or ".." in Path(config_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.configRoot must remain relative")
    if Path(caddyfile_path).is_absolute() or ".." in Path(caddyfile_path).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.caddyfile must remain relative")
    if Path(legal_root).is_absolute() or ".." in Path(legal_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.legalStaticRoot must remain relative")
    if Path(portal_root).is_absolute() or ".." in Path(portal_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.portalStaticRoot must remain relative")
    if Path(web_root).is_absolute() or ".." in Path(web_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.webStaticRoot must remain relative")
    if Path(model_cache_root).is_absolute() or ".." in Path(model_cache_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.modelCacheRoot must remain relative")

    render_name = f"{args.plane}-{args.instance}-{args.replica_id}"
    output_root = _resolve_render_output_dir(
        args.output_dir,
        plane=args.plane,
        instance=args.instance,
        replica_id=args.replica_id,
    )
    if output_root.exists():
        remove_deployment_tree("prod-hosted", "rendered", render_name)
    output_root.mkdir(parents=True, exist_ok=True)
    Path(media_root).mkdir(parents=True, exist_ok=True)
    legal_package_public = (
        legal_static_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "public"
    )
    legal_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(legal_root).parts,
    )
    if legal_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(legal_root).parts,
        )
    if legal_package_public.is_dir():
        shutil.copytree(legal_package_public, legal_output_root)
    else:
        legal_output_root.mkdir(parents=True, exist_ok=True)
    # 运维运营 Portal 静态站点：只消费 build_portal_release.py 发布的不可变
    # release 产物；缺失时保留空目录（Caddy 返回 404，不回退 dev server）。
    portal_release_dist = (
        portal_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "dist"
    )
    portal_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(portal_root).parts,
    )
    if portal_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(portal_root).parts,
        )
    if portal_release_dist.is_dir():
        shutil.copytree(portal_release_dist, portal_output_root)
    else:
        portal_output_root.mkdir(parents=True, exist_ok=True)
    web_release_public = (
        web_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "public"
    )
    web_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(web_root).parts,
    )
    if web_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(web_root).parts,
        )
    if web_release_public.is_dir():
        shutil.copytree(web_release_public, web_output_root)
    else:
        web_output_root.mkdir(parents=True, exist_ok=True)
    web_runtime_config_digests: dict[str, str] = {}
    trust_path = Path(str(args.web_runtime_config_trust or "")).expanduser()
    package_path = Path(str(args.web_runtime_config_package or "")).expanduser()
    if "gamma-proxy" in support and args.instance != "prevalidate":
        missing_runtime_inputs = [
            label
            for label, path in (
                ("trust", trust_path),
                ("package", package_path),
            )
            if not path.is_absolute() or not path.is_file() or path.is_symlink()
        ]
        if missing_runtime_inputs:
            raise SystemExit(
                "FAIL: prod Web hosting runtime configuration is required: "
                + ", ".join(missing_runtime_inputs)
            )
        try:
            trust_envelope = json.loads(trust_path.read_text(encoding="utf-8"))
            runtime_package = json.loads(package_path.read_text(encoding="utf-8"))
            if not isinstance(trust_envelope, dict) or not isinstance(
                runtime_package, dict
            ):
                raise ValueError("runtime configuration inputs must be JSON objects")
            web_runtime_config_digests = materialize_web_runtime_config(
                hosting_root=web_output_root,
                trust_envelope=trust_envelope,
                runtime_package=runtime_package,
                expected_environment="prod",
                expected_target="prod-hosted",
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
            WebOfficialReleaseError,
        ) as exc:
            raise SystemExit(
                f"FAIL: prod Web hosting runtime configuration is invalid: {exc}"
            ) from exc
    deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(model_cache_root).parts,
    ).mkdir(parents=True, exist_ok=True)

    template = _load_yaml(compose_template)
    services = dict(template.get("services") or {})
    service_fragments = domain_service_compose_files(ROOT)
    service_fragments.append(
        ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "deploy"
        / "compose.yaml"
    )
    for fragment in service_fragments:
        fragment_services = _load_yaml(fragment).get("services") or {}
        duplicates = set(services) & set(fragment_services)
        if duplicates:
            raise SystemExit(
                f"FAIL: Compose service has multiple owners {sorted(duplicates)}: {fragment}"
            )
        services.update(fragment_services)
    rendered_services: dict[str, Any] = {}
    selected_names = set(selected)
    governed_names = set(governed)
    observability_config = plane.get("rootlessObservabilityRuntime") or {}
    service_network_name = str(
        observability_config.get("serviceNetworkName") or ""
    ).strip()
    config_sources = _stack._write_config_tree(
        config_services=config_services,
        candidate_digest=args.candidate_digest,
        output_root=output_root,
        isolated_prevalidation=(
            args.instance == "prevalidate" and args.data_mode == "isolated"
        ),
    )
    for service_name in selected:
        raw = services.get(service_name)
        if raw is None:
            raise SystemExit(
                f"FAIL: compose template missing selected service {service_name}: {compose_template}"
            )
        rendered = _stack._rewrite_service(
            service_name,
            raw,
            selected_names,
            image_version=args.image_transport_tag,
            config_version=str(
                (config_sources.get(service_name) or {}).get("configurationDigest") or ""
            ),
            release_evidence_digest=args.release_evidence_digest,
            versioned_image=service_name in governed_names,
            instance=args.instance,
            replica_id=args.replica_id,
            config_root=config_root,
            media_root=media_root,
            legal_root=legal_root,
            portal_root=portal_root,
            web_root=web_root,
            caddyfile_path=caddyfile_path,
            model_cache_root=model_cache_root,
            credentials_root=credentials_root,
            runtime_credentials=(
                {} if args.instance == "prevalidate" else runtime_credentials
            ),
            data_mode=args.data_mode,
            prevalidation_images=prevalidation_images,
            startup_services=set(startup_services),
        )
        if service_network_name:
            rendered["networks"] = ["service-plane"]
        rendered_services[service_name] = rendered

    compose_payload: dict[str, Any] = {"services": rendered_services}
    if service_network_name:
        compose_payload["networks"] = {
            "service-plane": {"name": service_network_name}
        }
    top_level_volumes = dict(template.get("volumes") or {})
    if any(name in RUNTIME_LOG_EXPORT_SERVICES for name in rendered_services):
        top_level_volumes.setdefault("runtime-log-spool", {})
    if args.instance == "prevalidate" and "platform-ops-service" in rendered_services:
        top_level_volumes.setdefault("platform-ops-prevalidation-state", {})
    filtered = _filter_top_level_volumes(rendered_services, top_level_volumes)
    if filtered:
        compose_payload["volumes"] = filtered

    compose_file_name = (
        ((plane.get("rootlessRuntimeLayout") or {}).get("composeFile"))
        or "docker-compose.prod-hosted.yaml"
    )
    if (
        Path(str(compose_file_name)).is_absolute()
        or ".." in Path(str(compose_file_name)).parts
    ):
        raise SystemExit("FAIL: rootlessRuntimeLayout.composeFile must remain relative")
    compose_out = output_root / str(compose_file_name)
    compose_out.write_text(
        yaml.safe_dump(compose_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    observability_runtime = (
        None
        if args.instance == "prevalidate"
        else _write_observability_tree(
            output_root,
            args.plane,
            render_name=render_name,
            remote_root=(
                f"{str(plane.get('composeProjectRoot') or '').rstrip('/')}"
                f"/instances/{args.instance}/{args.replica_id}"
            ),
        )
    )
    _stack._write_caddyfile(output_root, args.instance, args.rollout_stage)
    _write_env_file(
        output_root,
        args.candidate_digest,
        args.image_transport_tag,
        args.instance,
    )
    systemd_unit_file = _write_runtime_systemd_unit(
        output_root,
        plane=plane,
        plane_name=args.plane,
        instance=args.instance,
        replica_id=args.replica_id,
        remote_root=(
            f"{str(plane.get('composeProjectRoot') or '').rstrip('/')}"
            f"/instances/{args.instance}/{args.replica_id}"
        ),
        startup_services=startup_services,
    )

    report = {
        "plane": args.plane,
        "host": args.host or "",
        "composeTemplate": str(compose_template.relative_to(ROOT)),
        "composeFile": str(compose_out.relative_to(ROOT) if compose_out.is_relative_to(ROOT) else compose_out),
        "instance": args.instance,
        "replicaId": args.replica_id,
        "hostId": args.host_id,
        "remoteRoot": (
            f"{str(plane.get('composeProjectRoot') or '').rstrip('/')}"
            f"/instances/{args.instance}/{args.replica_id}"
        ),
        "project": f"quwoquan-{args.plane}-{args.instance}-{args.replica_id}",
        "governedComposeServices": governed,
        "supportComposeServices": support,
        "startupServices": startup_services,
        "imageAndConfigOnlyServices": image_only_services,
        "dataMode": args.data_mode,
        "configServices": config_services,
        "candidateDigest": args.candidate_digest,
        "imageTransportTag": args.image_transport_tag,
        "outputDir": str(output_root),
        "sourceRevision": _git_revision(),
        "configSources": config_sources,
        "mediaStateRef": media_state_ref,
        "mediaRoot": media_root,
        "legalStaticRoot": legal_root,
        "legalStaticSource": str(legal_package_public),
        "portalStaticRoot": portal_root,
        "portalStaticSource": str(portal_release_dist),
        "publicWebRuntimeConfig": web_runtime_config_digests,
        "observabilityRuntime": observability_runtime,
        "systemdUnitFile": systemd_unit_file,
    }
    (output_root / "provenance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0
