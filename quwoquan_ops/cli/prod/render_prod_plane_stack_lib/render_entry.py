"""prod plane 渲染 main 装配流程（从 render_prod_plane_stack.py 逐字搬移）。

``_rewrite_service`` / ``_write_config_tree`` / ``_write_caddyfile`` 被 gate
源码文本扫描钉在薄入口文件中，本模块在 ``main`` 内延迟导入入口模块并按
模块属性访问它们，既避免初始化环，也保持 monkeypatch 语义。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files
from quwoquan_ops.cli.lib.data_plane_binding import (
    DATA_PLANE_BINDING_PACKAGE_REF,
    DataPlaneBindingError,
    resolve_data_plane_environment,
    validate_canonical_data_plane_binding,
)
from quwoquan_ops.cli.lib.output_paths import deployment_candidate_dir
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

def _load_candidate_data_plane_projection(
    *,
    data_mode: str,
    candidate_digest: str,
    data_plane_binding: str | Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if data_mode != "external":
        return None, None
    candidate_root = deployment_candidate_dir("prod-hosted", candidate_digest)
    binding_path = Path(str(data_plane_binding or "")).expanduser()
    expected_binding = candidate_root / DATA_PLANE_BINDING_PACKAGE_REF.as_posix()
    if (
        not binding_path.is_absolute()
        or binding_path != expected_binding
        or binding_path.is_symlink()
        or not binding_path.is_file()
    ):
        raise SystemExit(
            "FAIL: external data mode requires the candidate-owned "
            "--data-plane-binding artifact"
        )
    manifest_path = candidate_root / "manifest.json"
    try:
        candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(candidate, dict):
            raise ValueError("candidate manifest must be an object")
        if (
            candidate.get("schema") != "stackctl-deployment-candidate"
            or candidate.get("candidateType") != "runtime-full"
            or candidate.get("environment") != "prod"
            or candidate.get("target") != "prod-hosted"
            or candidate.get("baselineId") != candidate_digest
        ):
            raise ValueError("candidate manifest identity mismatch")
        data_plane_identity = candidate.get("dataPlaneBinding")
        if not isinstance(data_plane_identity, dict) or set(data_plane_identity) != {
            "ref", "digest", "bindingDigest"
        }:
            raise ValueError("candidate dataPlaneBinding fields mismatch")
        encoded_binding = binding_path.read_bytes()
        canonical = validate_canonical_data_plane_binding(
            json.loads(encoded_binding.decode("utf-8"))
        )
        artifact_digest = "sha256:" + hashlib.sha256(encoded_binding).hexdigest()
        if data_plane_identity != {
            "ref": DATA_PLANE_BINDING_PACKAGE_REF.as_posix(),
            "digest": artifact_digest,
            "bindingDigest": canonical["bindingDigest"],
        }:
            raise ValueError("candidate dataPlaneBinding identity drifted")
        projection = resolve_data_plane_environment(
            {
                "dataPlane": {
                    "resources": canonical["resources"],
                    "bindings": canonical["bindings"],
                }
            },
            mode="external",
            target_name="prod-hosted",
        )
        if projection["bindingDigest"] != data_plane_identity["bindingDigest"]:
            raise ValueError("candidate data-plane binding digest mismatch")
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        DataPlaneBindingError,
    ) as exc:
        raise SystemExit(f"FAIL: candidate data-plane binding is invalid: {exc}") from exc
    return projection, data_plane_identity


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
    # 媒体状态是远端平面账号的持久目录，不是本机 QWQ_DEPLOY_WORK_ROOT 下的路径：
    # 渲染到 compose 的 bind source 必须是远端 composeProjectRoot 下的 state 目录，
    # 且按 instance/replica 隔离，重新 sync compose 目录时不被覆盖。
    remote_compose_root = str(plane.get("composeProjectRoot") or "").rstrip("/")
    if not remote_compose_root.startswith("/"):
        raise SystemExit(f"FAIL: plane {args.plane} composeProjectRoot must be absolute")
    media_root = (
        f"{remote_compose_root}/state/{args.instance}/{args.replica_id}/"
        f"{media_ref_path.as_posix()}"
    )
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

    data_plane_projection, data_plane_identity = (
        _load_candidate_data_plane_projection(
            data_mode=args.data_mode,
            candidate_digest=args.candidate_digest,
            data_plane_binding=args.data_plane_binding,
        )
    )

    template = _load_yaml(compose_template)
    services = dict(template.get("services") or {})
    isolated_data_volumes: dict[str, Any] = {}
    if (
        args.plane == "service"
        and args.instance == "prevalidate"
        and args.data_mode == "isolated"
        and "elasticsearch" in selected
    ):
        elasticsearch_fragment = _load_yaml(
            ROOT
            / "quwoquan_service"
            / "services"
            / "product-ops-service"
            / "deploy"
            / "local-elasticsearch.compose.yaml"
        )
        elasticsearch_service = (
            elasticsearch_fragment.get("services") or {}
        ).get("elasticsearch")
        if not isinstance(elasticsearch_service, dict):
            raise SystemExit(
                "FAIL: local Elasticsearch Compose fragment missing elasticsearch service"
            )
        services["elasticsearch"] = elasticsearch_service
        isolated_data_volumes = dict(elasticsearch_fragment.get("volumes") or {})
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
        for duplicate in sorted(duplicates):
            base = services.get(duplicate)
            owned = fragment_services.get(duplicate)
            if not isinstance(base, dict) or not isinstance(owned, dict):
                raise SystemExit(
                    f"FAIL: Compose service has invalid owner projection {duplicate}: {fragment}"
                )
            overlap = set(base) & set(owned)
            if any(base[key] != owned[key] for key in overlap):
                raise SystemExit(
                    "FAIL: Compose service has conflicting owners "
                    f"{duplicate}.{sorted(overlap)}: {fragment}"
                )
            services[duplicate] = {**base, **owned}
        services.update(
            {
                name: definition
                for name, definition in fragment_services.items()
                if name not in duplicates
            }
        )
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
    if (
        args.plane == "service"
        and args.data_mode == "external"
        and data_plane_projection is not None
        and "product-ops-service" in selected
    ):
        bootstrap_name = "product-ops-service-migrate-elasticsearch"
        bootstrap_source = services.get(bootstrap_name)
        if not isinstance(bootstrap_source, dict):
            raise SystemExit(
                "FAIL: Product Ops deployment-only Elasticsearch bootstrap is missing"
            )
        deployment_environment = dict(
            (data_plane_projection.get("deploymentEnvironment") or {}).get(
                "deployment-control.telemetry.admin"
            )
            or {}
        )
        owner_environment = dict(
            (data_plane_projection.get("environment") or {}).get(
                "product-ops-service"
            )
            or {}
        )
        admin_credential = deployment_environment.get("credential")
        admin_endpoint = deployment_environment.get("endpoint")
        if not admin_credential or not admin_endpoint:
            raise SystemExit(
                "FAIL: Product Ops Elasticsearch admin binding is incomplete"
            )
        bootstrap = dict(bootstrap_source)
        bootstrap["environment"] = {
            "PRODUCT_OPS_ELASTICSEARCH_ADMIN_ENDPOINT": admin_endpoint,
            "PRODUCT_OPS_ELASTICSEARCH_ADMIN_API_KEY": admin_credential,
            **{
                key: value
                for key, value in owner_environment.items()
                if key.endswith("_INDEX")
            },
        }
        bootstrap["command"] = ["product-ops-elasticsearch-bootstrap"]
        bootstrap["labels"] = {
            **dict(bootstrap.get("labels") or {}),
            "com.quwoquan.runtime.one-shot": "true",
        }
        bootstrap.pop("ports", None)
        bootstrap.pop("healthcheck", None)
        rendered_services[bootstrap_name] = bootstrap

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
            data_plane_environment=(
                dict(
                    (
                        data_plane_projection.get("environment") or {}
                    ).get(service_name) or {}
                )
                if data_plane_projection is not None
                else None
            ),
        )
        if (
            service_name == "product-ops-service"
            and args.data_mode == "external"
            and "product-ops-service-migrate-elasticsearch" in rendered_services
        ):
            dependencies = dict(rendered.get("depends_on") or {})
            dependencies["product-ops-service-migrate-elasticsearch"] = {
                "condition": "service_completed_successfully"
            }
            rendered["depends_on"] = dependencies
        if service_network_name:
            rendered["networks"] = ["service-plane"]
        rendered_services[service_name] = rendered

    compose_payload: dict[str, Any] = {"services": rendered_services}
    if service_network_name:
        compose_payload["networks"] = {
            "service-plane": {"name": service_network_name}
        }
    else:
        # 未声明平面专用网络时，服务仍引用模板网络（如 edge 平面的 default/edge）；
        # 顶层 networks 只保留被引用的模板定义，否则 compose 报 undefined network。
        referenced_networks: set[str] = set()
        for spec in rendered_services.values():
            declared = spec.get("networks")
            names = list(declared) if isinstance(declared, (list, dict)) else []
            referenced_networks.update(str(name) for name in names if name != "default")
        template_networks = dict(template.get("networks") or {})
        kept_networks = {
            name: (template_networks.get(name) or {})
            for name in sorted(referenced_networks)
            if name in template_networks
        }
        if "default" in template_networks and any(
            "default" in (spec.get("networks") or []) for spec in rendered_services.values()
        ):
            kept_networks["default"] = template_networks["default"] or {}
        missing_networks = referenced_networks - set(template_networks)
        if missing_networks:
            raise SystemExit(
                "FAIL: rendered services reference networks missing from the template: "
                + ", ".join(sorted(missing_networks))
            )
        if kept_networks:
            compose_payload["networks"] = kept_networks
    top_level_volumes = dict(template.get("volumes") or {})
    top_level_volumes.update(isolated_data_volumes)
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
        "dataPlaneBinding": data_plane_identity,
        "dataPlaneBindingDigest": (
            str(data_plane_projection.get("bindingDigest") or "")
            if data_plane_projection is not None
            else ""
        ),
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
