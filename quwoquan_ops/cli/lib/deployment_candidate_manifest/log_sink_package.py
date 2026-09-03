"""observability log-sink（Elasticsearch）package 的物化与校验（逐字迁自原单文件）。

``runtime_shared_deployment_package_dir`` 经包属性（``_pkg.``）消费，
保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from pathlib import Path
from typing import Any

import yaml

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from quwoquan_ops.cli.lib.provider_runtime_composition import (
    validate_provider_runtime_composition,
)

from .candidate_fs import (
    _UnsafeCandidatePath,
    _read_candidate_bytes,
    _read_candidate_object,
    _sha256_file,
    _sha256_json,
    _validate_candidate_artifact_ref,
)
from .candidate_staging import (
    _atomic_write_candidate_file,
    _begin_candidate_directory_materialization,
    _discard_candidate_staging_directory,
    _publish_candidate_staging_directory,
)
from .constants import (
    _DIGEST,
    LOG_SINK_ADAPTER_ID,
    OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
    ROOT,
)

# 官方基镜像与 quwoquan/elasticsearch-cjk（官方 8.13.4 + analysis-ik/analysis-pinyin，
# 见 services/product-ops-service/build/elasticsearch/）两种 repo 均合法；发布形态是
# @sha256 digest pin，本地构建镜像在推送私有 registry 前允许精确版本 tag（非浮动）。
_ELASTICSEARCH_IMAGE_LITERAL_RE = re.compile(
    r"^(?:docker\.elastic\.co/elasticsearch/elasticsearch|quwoquan/elasticsearch-cjk)"
    r"@(sha256:[0-9a-f]{64})$"
)
_ELASTICSEARCH_IMAGE_DEFAULT_RE = re.compile(
    r"^\$\{QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-"
    r"(?:docker\.elastic\.co/elasticsearch/elasticsearch|quwoquan/elasticsearch-cjk)"
    r"@(sha256:[0-9a-f]{64})\}$"
)
_ELASTICSEARCH_IMAGE_LOCAL_TAG_RE = re.compile(
    r"^quwoquan/elasticsearch-cjk:(\d+\.\d+\.\d+)$"
)
_ELASTICSEARCH_IMAGE_LOCAL_TAG_DEFAULT_RE = re.compile(
    r"^\$\{QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-"
    r"quwoquan/elasticsearch-cjk:(\d+\.\d+\.\d+)\}$"
)


def local_elasticsearch_image_digest(image_reference: str) -> str:
    """Resolve the one immutable local ES image form accepted by packaging."""

    normalized = str(image_reference or "").strip()
    for pattern in (
        _ELASTICSEARCH_IMAGE_LITERAL_RE,
        _ELASTICSEARCH_IMAGE_DEFAULT_RE,
    ):
        match = pattern.fullmatch(normalized)
        if match is not None:
            return match.group(1)
    for pattern in (
        _ELASTICSEARCH_IMAGE_LOCAL_TAG_RE,
        _ELASTICSEARCH_IMAGE_LOCAL_TAG_DEFAULT_RE,
    ):
        match = pattern.fullmatch(normalized)
        if match is not None:
            # 本地构建镜像在推 registry 前没有 manifest digest；provenance 记录
            # 精确版本 tag，仍满足两处 packaging 一致性比对的单一身份语义。
            return "tag:" + match.group(1)
    raise ValueError(
        "canonical local Elasticsearch image must be an immutable digest "
        "(docker.elastic.co/elasticsearch/elasticsearch or "
        "quwoquan/elasticsearch-cjk), an exact quwoquan/elasticsearch-cjk "
        "version tag, or the package-owned QWQ_COMPOSE_ELASTICSEARCH_IMAGE "
        "expression with one of those immutable defaults"
    )


def _canonical_observability_log_sink_binding(
    provider_composition: object,
    *,
    env_name: str,
    target_name: str,
) -> dict[str, Any]:
    composition = validate_provider_runtime_composition(
        provider_composition,
        expected_environment=env_name,
        expected_target=target_name,
    )
    binding = next(
        (
            item
            for item in composition["bindings"]
            if item["capabilityId"] == "runtime.log.sink"
        ),
        None,
    )
    if not isinstance(binding, dict):
        raise TypeError("canonical Product Ops log-sink Binding is missing")
    if (
        binding.get("state") != "enabled"
        or binding.get("adapterId") != LOG_SINK_ADAPTER_ID
        or binding.get("endpointEnvironmentKeys")
        != {"endpoint": "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"}
    ):
        raise ValueError("canonical Product Ops log-sink Binding is invalid")
    if env_name == "prod":
        if (
            binding.get("endpointRef")
            != "environment_binding:product_ops.elasticsearch"
            or binding.get("secretEnvironmentKeys")
            != ["PRODUCT_OPS_ELASTICSEARCH_API_KEY"]
        ):
            raise ValueError(
                "Prod Product Ops Binding must select protected managed Elasticsearch"
            )
    elif env_name in {"alpha", "beta", "gamma"}:
        if (
            binding.get("endpointRef") != "local_topology:elasticsearch"
            or binding.get("secretEnvironmentKeys") != []
        ):
            raise ValueError(
                f"{env_name} Product Ops Binding does not use the shared "
                "nonprod Elasticsearch authority"
            )
    else:
        raise ValueError(f"unsupported Product Ops log-sink environment: {env_name}")
    return binding


def _local_elasticsearch_runtime_selection(
    compose: object,
    *,
    machine: str | None = None,
) -> dict[str, str]:
    if not isinstance(compose, dict):
        raise TypeError("canonical local Elasticsearch workload must be an object")
    policy = compose.get("x-qwq-package-elasticsearch")
    if not isinstance(policy, dict) or set(policy) != {
        "runtimeEndpoint",
        "platforms",
    }:
        raise ValueError("canonical local Elasticsearch package policy is invalid")
    runtime_endpoint = str(policy.get("runtimeEndpoint") or "").strip()
    if runtime_endpoint != "http://elasticsearch:9200":
        raise ValueError("canonical local Elasticsearch runtime endpoint is invalid")
    platforms = policy.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != {"arm64", "amd64"}:
        raise ValueError("canonical local Elasticsearch platform policy is invalid")
    normalized_machine = (machine or platform.machine()).strip().lower()
    platform_key = (
        "arm64"
        if normalized_machine in {"arm64", "aarch64"}
        else "amd64"
        if normalized_machine in {"amd64", "x86_64"}
        else ""
    )
    if not platform_key:
        raise ValueError(
            f"unsupported local Elasticsearch package architecture: {normalized_machine}"
        )
    selected = platforms.get(platform_key)
    if not isinstance(selected, dict) or set(selected) != {
        "image",
        "cliJavaOpts",
        "esJavaOpts",
    }:
        raise ValueError("canonical local Elasticsearch platform entry is invalid")
    image = str(selected.get("image") or "").strip()
    image_digest = local_elasticsearch_image_digest(image)
    return {
        "platform": platform_key,
        "image": image,
        "imageDigest": image_digest,
        "runtimeEndpoint": runtime_endpoint,
        "cliJavaOpts": str(selected.get("cliJavaOpts") or ""),
        "esJavaOpts": str(selected.get("esJavaOpts") or ""),
    }


def canonical_observability_log_sink_compose_bytes(compose: object) -> bytes:
    """Serialize one normalized local log-sink Compose document canonically."""

    if not isinstance(compose, dict) or "x-qwq-package-elasticsearch" in compose:
        raise ValueError("normalized local Elasticsearch composition is invalid")
    services = compose.get("services")
    elasticsearch = (
        services.get("elasticsearch") if isinstance(services, dict) else None
    )
    if not isinstance(elasticsearch, dict):
        raise ValueError("normalized local Elasticsearch workload is missing")
    return (
        json.dumps(
            compose,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def observability_log_sink_composition_digest(compose: object) -> str:
    """Digest the same canonical bytes used by mutable and immutable execution."""

    return "sha256:" + hashlib.sha256(
        canonical_observability_log_sink_compose_bytes(compose)
    ).hexdigest()


def canonical_local_observability_log_sink_composition(
    source_path: Path,
    *,
    machine: str | None = None,
) -> dict[str, Any]:
    """Resolve one source Compose into the exact local runtime composition.

    Both immutable packaging and mutable test-live execution consume this
    helper.  Its digest covers the normalized Compose bytes after the canonical
    platform selector has been removed and its image/JVM values have been
    fixed, so the identity describes the bytes that Compose actually executes.
    """

    source = Path(source_path).resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("canonical local Elasticsearch workload is unsafe")
    try:
        compose = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(
            f"canonical local Elasticsearch workload is unreadable: {exc}"
        ) from exc
    selection = _local_elasticsearch_runtime_selection(compose, machine=machine)
    services = compose.get("services") if isinstance(compose, dict) else None
    elasticsearch = (
        services.get("elasticsearch") if isinstance(services, dict) else None
    )
    if not isinstance(elasticsearch, dict):
        raise TypeError("canonical Product Ops Elasticsearch workload is missing")
    compose.pop("x-qwq-package-elasticsearch", None)
    elasticsearch["image"] = selection["image"]
    environment = elasticsearch.get("environment")
    if not isinstance(environment, dict):
        raise TypeError("canonical Product Ops Elasticsearch environment is missing")
    environment["CLI_JAVA_OPTS"] = selection["cliJavaOpts"]
    environment["ES_JAVA_OPTS"] = selection["esJavaOpts"]
    compose_bytes = canonical_observability_log_sink_compose_bytes(compose)
    return {
        "compose": compose,
        "composeBytes": compose_bytes,
        "composeDigest": observability_log_sink_composition_digest(compose),
        "sourceComposeDigest": _sha256_file(source),
        "selection": selection,
    }


def materialize_observability_log_sink_package(
    env_name: str,
    target_name: str,
    provider_composition: object,
) -> dict[str, Any]:
    """Seal the selected ES Binding and exact local workload into a candidate."""

    binding = _canonical_observability_log_sink_binding(
        provider_composition,
        env_name=env_name,
        target_name=target_name,
    )
    shared_root = _pkg.runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    candidate_root = shared_root.parent.parent
    artifact_relative = Path(
        "packages/runtime-shared/observability-log-sink"
    )
    common = {
        "schema": OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
        "adapterId": LOG_SINK_ADAPTER_ID,
        "bindingDigest": _sha256_json(binding),
        "endpointRef": str(binding["endpointRef"]),
        "endpointEnvironmentKey": str(
            binding["endpointEnvironmentKeys"]["endpoint"]
        ),
        "secretEnvironmentKeys": list(binding["secretEnvironmentKeys"]),
    }
    staged_files: dict[str, bytes] = {}
    if env_name == "prod":
        payload = {
            **common,
            "deploymentMode": "managed-external",
            "platform": "",
            "runtimeEndpoint": "",
            "imageDigest": "",
            "sourceComposeDigest": "",
            "composeRef": "",
            "composeDigest": "",
            "clusterRef": "environment-binding:product_ops.elasticsearch",
        }
    else:
        source_path = (
            ROOT
            / "quwoquan_service"
            / "services"
            / "product-ops-service"
            / "deploy"
            / "local-elasticsearch.compose.yaml"
        )
        canonical = canonical_local_observability_log_sink_composition(source_path)
        selection = canonical["selection"]
        compose_bytes = canonical["composeBytes"]
        staged_files["elasticsearch.compose.yaml"] = compose_bytes
        deployment_ref = (
            artifact_relative / "elasticsearch.compose.yaml"
        ).as_posix()
        payload = {
            **common,
            "deploymentMode": "package-bound-local",
            "platform": selection["platform"],
            "runtimeEndpoint": selection["runtimeEndpoint"],
            "imageDigest": selection["imageDigest"],
            "sourceComposeDigest": canonical["sourceComposeDigest"],
            "composeRef": deployment_ref,
            "composeDigest": canonical["composeDigest"],
            "clusterRef": f"target:{target_name}/product-ops/elasticsearch",
        }
    validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
    )
    staged_files["manifest.json"] = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (
        artifact_relative,
        parent_descriptor,
        parent_identities,
        temporary,
        staging_identity,
    ) = _begin_candidate_directory_materialization(
        candidate_root,
        artifact_relative,
        label="observability log-sink package",
    )
    staging_exists = True
    try:
        for name, encoded in staged_files.items():
            _atomic_write_candidate_file(
                candidate_root,
                artifact_relative.parent / temporary / name,
                encoded,
                label=f"observability log-sink package {name}",
            )
        _publish_candidate_staging_directory(
            candidate_root,
            artifact_relative,
            parent_descriptor,
            parent_identities,
            temporary,
            staging_identity,
            label="observability log-sink package",
        )
        staging_exists = False
    finally:
        if staging_exists:
            _discard_candidate_staging_directory(
                parent_descriptor,
                temporary,
                expected_identity=staging_identity,
            )
        os.close(parent_descriptor)
    return validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def load_observability_log_sink_package(
    env_name: str,
    target_name: str,
    candidate_root: Path,
) -> dict[str, Any]:
    payload = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/observability-log-sink/manifest.json",
        label="observability log-sink package manifest",
    )
    return validate_observability_log_sink_package(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def validate_observability_log_sink_package(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    required = {
        "schema",
        "adapterId",
        "bindingDigest",
        "endpointRef",
        "endpointEnvironmentKey",
        "secretEnvironmentKeys",
        "deploymentMode",
        "platform",
        "runtimeEndpoint",
        "imageDigest",
        "sourceComposeDigest",
        "composeRef",
        "composeDigest",
        "clusterRef",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("observability log-sink package fields mismatch")
    if (
        payload.get("schema") != OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA
        or payload.get("adapterId") != LOG_SINK_ADAPTER_ID
        or _DIGEST.fullmatch(str(payload.get("bindingDigest") or "")) is None
        or payload.get("endpointEnvironmentKey")
        != "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"
    ):
        raise ValueError("observability log-sink package identity is invalid")
    if expected_environment == "prod":
        if (
            expected_target != "prod-hosted"
            or payload.get("deploymentMode") != "managed-external"
            or payload.get("endpointRef")
            != "environment_binding:product_ops.elasticsearch"
            or payload.get("secretEnvironmentKeys")
            != ["PRODUCT_OPS_ELASTICSEARCH_API_KEY"]
            or payload.get("clusterRef")
            != "environment-binding:product_ops.elasticsearch"
            or any(
                payload.get(field) != ""
                for field in (
                    "platform",
                    "runtimeEndpoint",
                    "imageDigest",
                    "sourceComposeDigest",
                    "composeRef",
                    "composeDigest",
                )
            )
        ):
            raise ValueError(
                "Prod observability log sink must bind managed Elasticsearch"
            )
        return payload
    # 每个身份字段单独报错：失败终态必须能指名是哪一个字段、期望什么、实到什么，
    # 否则调用方只能看到一条无法定位的聚合拒绝。
    identity_issues: list[str] = []
    if expected_environment not in {"alpha", "beta", "gamma"}:
        identity_issues.append(
            f"expectedEnvironment={expected_environment!r}, "
            "expected one of ['alpha', 'beta', 'gamma']"
        )
    elif expected_target != f"{expected_environment}-local":
        identity_issues.append(
            f"expectedTarget={expected_target!r}, "
            f"expected {expected_environment + '-local'!r}"
        )
    for field, expected in (
        ("deploymentMode", "package-bound-local"),
        ("endpointRef", "local_topology:elasticsearch"),
        ("secretEnvironmentKeys", []),
        ("runtimeEndpoint", "http://elasticsearch:9200"),
        ("clusterRef", f"target:{expected_target}/product-ops/elasticsearch"),
    ):
        actual = payload.get(field)
        if actual != expected:
            identity_issues.append(
                f"{field}={actual!r}, expected {expected!r}"
            )
    if payload.get("platform") not in {"arm64", "amd64"}:
        identity_issues.append(
            f"platform={payload.get('platform')!r}, "
            "expected one of ['arm64', 'amd64']"
        )
    if identity_issues:
        raise ValueError(
            "local observability log-sink package identity is invalid: "
            + "; ".join(identity_issues)
        )
    for field in (
        "imageDigest",
        "sourceComposeDigest",
        "composeDigest",
    ):
        value = str(payload.get(field) or "")
        # imageDigest 允许本地构建 quwoquan/elasticsearch-cjk 的精确版本 tag 身份
        # （推 registry 前无 manifest digest）；compose 摘要仍必须是 sha256。
        if field == "imageDigest" and re.fullmatch(r"tag:\d+\.\d+\.\d+", value):
            continue
        if _DIGEST.fullmatch(value) is None:
            raise ValueError(f"observability log-sink {field} is invalid")
    deployment_ref = _validate_candidate_artifact_ref(
        payload.get("composeRef"),
        prefix="packages/runtime-shared/observability-log-sink/",
        label="observability log-sink deployment",
    )
    if candidate_root is not None:
        try:
            deployment_bytes = _read_candidate_bytes(
                candidate_root,
                deployment_ref,
                label="packaged observability log-sink artifact",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "packaged observability log-sink artifact is unsafe"
            ) from exc
        if (
            "sha256:" + hashlib.sha256(deployment_bytes).hexdigest()
            != payload["composeDigest"]
        ):
            raise ValueError("packaged observability log-sink artifact drifted")
        try:
            compose = yaml.safe_load(deployment_bytes.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                "packaged observability log-sink artifact is unreadable"
            ) from exc
        if (
            not isinstance(compose, dict)
            or "x-qwq-package-elasticsearch" in compose
        ):
            raise ValueError(
                "packaged observability log-sink retains a runtime selector"
            )
        services = compose.get("services")
        elasticsearch = (
            services.get("elasticsearch")
            if isinstance(services, dict)
            else None
        )
        if (
            not isinstance(elasticsearch, dict)
            or local_elasticsearch_image_digest(
                str(elasticsearch.get("image") or "")
            )
            != payload["imageDigest"]
        ):
            raise ValueError(
                "packaged observability log-sink image identity drifted"
            )
    return payload
