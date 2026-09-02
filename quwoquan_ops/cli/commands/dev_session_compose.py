"""stackctl dev-session Compose 物化域: 当前工作树 Compose 闭包解析与
execution-only 副本生成。

从 dev_session_runtime.py 逐字迁出（改写规则与该模块相同）:
- `_dev_session_source_compose_files` / `_dev_session_materialize_compose_files`。

测试经 ``mock.patch.object(stackctl, ...)`` patch stackctl 命名空间符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本域符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import os

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _dev_session_source_compose_files(
    *,
    environment: str,
    target: str,
    provider_composition: Mapping[str, Any],
) -> tuple[list[Path], list[str]]:
    """Resolve the complete current-worktree Compose closure without packaging."""
    import quwoquan_ops.cli.stackctl as _stackctl


    _stackctl._dev_session_compose_project(environment, target)
    services_root = _stackctl.ROOT / "quwoquan_service" / "services"
    active_services = set(_stackctl.first_party_service_names(_stackctl.ROOT))
    files = [
        _stackctl.ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
    ]
    files.extend(
        sorted(
            path
            for path in services_root.glob("*/deploy/compose.yaml")
            if path.parents[1].name in active_services
        )
    )
    files.extend(
        sorted(
            path
            for path in services_root.glob(
                f"*/environments/{environment}/deploy/compose.yaml"
            )
            if path.parents[3].name in active_services
        )
    )
    files.extend(
        (
            _stackctl.ROOT
            / "quwoquan_service/services/product-ops-service/deploy/local-elasticsearch.compose.yaml",
            _stackctl.ROOT
            / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
        )
    )
    # 上面无条件把 control-plane/platform-ops 的 compose 选入闭包，而该文件用
    # profile 门控 platform-ops-service。test_live 只有 full workload 一种形态，
    # 因此这里读 immutable full workload 的同一处 profile 声明，而不是并列抄一份。
    profiles = set(_stackctl.FULL_WORKLOAD_COMPOSE_PROFILES)
    validated_provider = _stackctl.validate_provider_runtime_composition(
        dict(provider_composition),
        expected_environment=environment,
        expected_target=target,
    )
    for workload in validated_provider["workloads"]:
        compose_ref = Path(str(workload["composeRef"]))
        if compose_ref.is_absolute() or ".." in compose_ref.parts:
            raise ValueError("mutable Provider Compose reference is unsafe")
        compose_path = (_stackctl.ROOT / compose_ref).resolve()
        if (
            not compose_path.is_relative_to(_stackctl.ROOT)
            or not compose_path.is_file()
            or compose_path.is_symlink()
            or _stackctl._sha256_file(compose_path) != str(workload["composeDigest"])
        ):
            raise ValueError(
                f"mutable Provider Compose identity drifted: {workload['role']}"
            )
        files.append(compose_path)
        profiles.update(str(item) for item in workload["composeProfiles"])

    canonical_files: list[Path] = []
    seen: set[Path] = set()
    for raw_path in files:
        path = raw_path.resolve()
        if (
            path in seen
            or not path.is_relative_to(_stackctl.ROOT)
            or not path.is_file()
            or path.is_symlink()
        ):
            if path in seen:
                continue
            raise ValueError(f"mutable test_live Compose source is unsafe: {path}")
        seen.add(path)
        canonical_files.append(path)
    if not canonical_files:
        raise ValueError("mutable test_live Compose closure is empty")
    return canonical_files, sorted(profiles)


def _dev_session_materialize_compose_files(
    source_files: Sequence[Path],
    *,
    destination_root: Path,
    provider_binding_overlay_context: Path | None = None,
    provider_binding_manifest_digest: str = "",
) -> list[Path]:
    """Create execution-only Compose copies with source-relative build contexts."""
    import quwoquan_ops.cli.stackctl as _stackctl


    def contains_symlink(path: Path) -> bool:
        current = _stackctl.ROOT
        for part in path.relative_to(_stackctl.ROOT).parts:
            current /= part
            if current.is_symlink():
                return True
        return False

    destination_root.mkdir(parents=True, exist_ok=True)
    execution_files: list[Path] = []
    compose_base = (
        Path(os.path.abspath(source_files[0].parent)) if source_files else _stackctl.ROOT
    )
    for index, source in enumerate(source_files):
        payload = _stackctl.load_json_yaml(source)
        try:
            source_ref = source.relative_to(_stackctl.ROOT).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"mutable test_live Compose source escapes repository: {source}"
            ) from exc
        if source_ref == (
            "quwoquan_service/services/product-ops-service/deploy/"
            "local-elasticsearch.compose.yaml"
        ):
            canonical = _stackctl.canonical_local_observability_log_sink_composition(
                source
            )
            payload = canonical["compose"]
        services = payload.get("services")
        if services is not None and not isinstance(services, dict):
            raise ValueError(f"mutable Compose services must be an object: {source}")
        if source_ref == "quwoquan_service/services/content-service/deploy/compose.yaml":
            content_service = (services or {}).get("content-service")
            if not isinstance(content_service, dict):
                raise ValueError(
                    "mutable content-service Compose source has no service definition"
                )
            dependencies = content_service.get("depends_on")
            if not isinstance(dependencies, dict):
                raise ValueError(
                    "mutable content-service Compose dependencies must be an object"
                )
            # Full test-live always enables the canonical Elasticsearch-backed
            # feed/search projection.  Formal environment overlays retain their
            # existing ownership; this execution-only copy closes the cold
            # Alpha/Beta race without changing package/deploy semantics.
            dependencies["elasticsearch"] = {"condition": "service_healthy"}
            dependencies["postgres"] = {"condition": "service_healthy"}
        if source_ref == "quwoquan_service/services/recommendation-service/deploy/compose.yaml":
            recommendation_service = (services or {}).get("recommendation-service")
            if not isinstance(recommendation_service, dict):
                raise ValueError(
                    "mutable recommendation-service Compose source has no service definition"
                )
            dependencies = recommendation_service.get("depends_on")
            if dependencies is None:
                dependencies = {}
                recommendation_service["depends_on"] = dependencies
            if not isinstance(dependencies, dict):
                raise ValueError(
                    "mutable recommendation-service Compose dependencies must be an object"
                )
            dependencies["redis"] = {"condition": "service_healthy"}
        for service_name, service in (services or {}).items():
            if not isinstance(service, dict):
                raise ValueError(
                    f"mutable Compose service must be an object: {source}:{service_name}"
                )
            volumes = service.get("volumes")
            if volumes is not None:
                if not isinstance(volumes, list):
                    raise ValueError(
                        f"mutable Compose volumes must be a list: {source}:{service_name}"
                    )
                rewritten_volumes: list[object] = []
                for volume in volumes:
                    if isinstance(volume, str) and volume.startswith("."):
                        host_ref, separator, container_ref = volume.partition(":")
                        host_path = Path(
                            os.path.abspath(source.parent / Path(host_ref))
                        )
                        if (
                            not separator
                            or not host_path.is_relative_to(_stackctl.ROOT)
                            or not host_path.exists()
                            or contains_symlink(host_path)
                        ):
                            raise ValueError(
                                "mutable Compose bind source is unsafe: "
                                f"{source}:{service_name}:{host_ref}"
                            )
                        rewritten_volumes.append(
                            str(host_path) + separator + container_ref
                        )
                        continue
                    if (
                        isinstance(volume, dict)
                        and volume.get("type") == "bind"
                        and str(volume.get("source") or "").startswith(".")
                    ):
                        host_ref = str(volume["source"])
                        host_path = Path(
                            os.path.abspath(source.parent / Path(host_ref))
                        )
                        if (
                            not host_path.is_relative_to(_stackctl.ROOT)
                            or not host_path.exists()
                            or contains_symlink(host_path)
                        ):
                            raise ValueError(
                                "mutable Compose bind source is unsafe: "
                                f"{source}:{service_name}:{host_ref}"
                            )
                        rewritten_volumes.append(
                            {**volume, "source": str(host_path)}
                        )
                        continue
                    rewritten_volumes.append(volume)
                service["volumes"] = rewritten_volumes
            build = service.get("build")
            if isinstance(build, str):
                build = {"context": build}
                service["build"] = build
            elif build is None:
                continue
            elif not isinstance(build, dict):
                raise ValueError(
                    f"mutable Compose build must be a string or object: "
                    f"{source}:{service_name}"
                )
            context_value = str(build.get("context") or "").strip()
            if not context_value:
                raise ValueError(
                    f"mutable Compose build context is empty: {source}:{service_name}"
                )
            context_path = Path(context_value)
            dockerfile_value = str(build.get("dockerfile") or "Dockerfile").strip()
            dockerfile_path = Path(dockerfile_value)
            if not dockerfile_value or dockerfile_path.is_absolute():
                raise ValueError(
                    f"mutable Compose Dockerfile is unsafe: {source}:{service_name}"
                )
            raw_candidates = (
                [Path(os.path.abspath(context_path))]
                if context_path.is_absolute()
                else [
                    Path(os.path.abspath(source.parent / context_path)),
                    Path(os.path.abspath(compose_base / context_path)),
                ]
            )
            candidates: list[Path] = []
            for candidate in raw_candidates:
                if candidate in candidates:
                    continue
                dockerfile = Path(os.path.abspath(candidate / dockerfile_path))
                if (
                    candidate.is_relative_to(_stackctl.ROOT)
                    and candidate.is_dir()
                    and not contains_symlink(candidate)
                    and dockerfile.is_relative_to(candidate)
                    and dockerfile.is_file()
                    and not contains_symlink(dockerfile)
                ):
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise ValueError(
                    f"mutable Compose build context must resolve exactly once: "
                    f"{source}:{service_name}:{context_value}"
                )
            resolved_context = candidates[0]
            build["context"] = str(resolved_context)
        payload = _stackctl.project_compose_document(payload)
        # Provider binding overlay 是 named build context：service-core 合成会
        # 把 dockerfile 替换成 cmd/service-core/Dockerfile，所以对 projection
        # 之后的 build 段统一判定；Dockerfile 声明依赖而 overlay 缺席时
        # fail closed，避免 BuildKit 把该名字当 registry 镜像解析。
        for service_name, service in (payload.get("services") or {}).items():
            build = service.get("build") if isinstance(service, dict) else None
            if not isinstance(build, dict):
                continue
            dockerfile = (
                Path(str(build.get("context") or ""))
                / str(build.get("dockerfile") or "Dockerfile")
            )
            if not dockerfile.is_file():
                raise ValueError(
                    f"mutable Compose Dockerfile is unavailable: "
                    f"{source}:{service_name}:{dockerfile}"
                )
            if b"qwq-provider-bindings" not in dockerfile.read_bytes():
                continue
            if (
                provider_binding_overlay_context is None
                or not provider_binding_manifest_digest
            ):
                raise ValueError(
                    "mutable Compose build requires the Provider binding "
                    f"overlay context: {source}:{service_name}"
                )
            contexts = build.setdefault("additional_contexts", {})
            if not isinstance(contexts, dict):
                raise ValueError(
                    "mutable Compose additional_contexts must be an object: "
                    f"{source}:{service_name}"
                )
            contexts["qwq_provider_bindings"] = str(
                provider_binding_overlay_context
            )
            arguments = build.setdefault("args", {})
            if not isinstance(arguments, dict):
                raise ValueError(
                    f"mutable Compose build args must be an object: "
                    f"{source}:{service_name}"
                )
            arguments["QWQ_PROVIDER_BINDING_MANIFEST_DIGEST"] = (
                provider_binding_manifest_digest
            )
        destination = destination_root / f"{index:02d}-{source.stem}.json"
        if source_ref == (
            "quwoquan_service/services/product-ops-service/deploy/"
            "local-elasticsearch.compose.yaml"
        ):
            destination.write_bytes(canonical["composeBytes"])
        else:
            _stackctl.write_json(destination, payload)
        execution_files.append(destination)
    return execution_files
