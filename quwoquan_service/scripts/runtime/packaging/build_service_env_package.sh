#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
cd "$ROOT"

service="${SERVICE:-}"
env_name="${ENV:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) service="${2:-}"; shift 2 ;;
    --env) env_name="${2:-}"; shift 2 ;;
    *) echo "FAIL: unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$env_name" in alpha|beta|gamma|prod) ;; *) echo "FAIL: --env must be alpha|beta|gamma|prod" >&2; exit 2 ;; esac
[[ -n "$service" ]] || { echo "FAIL: --service is required" >&2; exit 2; }

if [[ "$service" == "platform-ops-service" ]]; then
  owner="quwoquan_service/control-plane/platform-ops"
  overlay="$owner/environments/$env_name/deploy"
else
  owner="quwoquan_service/services/$service"
  overlay="$owner/environments/$env_name/deploy"
fi
[[ -d "$owner" ]] || { echo "FAIL: unknown service: $service" >&2; exit 1; }
schema="$owner/config/schema.yaml"
environment="$owner/environments/$env_name"
[[ -f "$schema" ]] || { echo "FAIL: missing config schema: $schema" >&2; exit 1; }
[[ -f "$environment/config.yaml" ]] || { echo "FAIL: missing environment config: $environment/config.yaml" >&2; exit 1; }
[[ -f "$overlay/kustomization.yaml" ]] || { echo "FAIL: missing environment deploy entry: $overlay/kustomization.yaml" >&2; exit 1; }

out_dir="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$env_name" "$service" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir
print(service_deployment_package_dir(sys.argv[1], sys.argv[2]))
PY
)"
parent_dir="$(dirname "$out_dir")"
mkdir -p "$parent_dir"
stage_dir="$(mktemp -d "$parent_dir/.${service}.${env_name}.XXXXXX")"
cleanup() { rm -rf "$stage_dir"; }
trap cleanup EXIT
mkdir -p "$stage_dir/config" "$stage_dir/resources" "$stage_dir/manifests"

PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/render_runtime_config.py \
  --env "$env_name" \
  --workload "$service" \
  --output "$stage_dir/config/config.yaml" >/dev/null

if [[ -d "$owner/resources" ]]; then
  mkdir -p "$stage_dir/resources/common"
  cp -R "$owner/resources/." "$stage_dir/resources/common/"
fi
if [[ -d "$environment/resources" ]]; then
  mkdir -p "$stage_dir/resources/environment"
  cp -R "$environment/resources/." "$stage_dir/resources/environment/"
fi

if [[ "$service" == "assistant-service" && "$env_name" != "alpha" ]]; then
  (
    cd quwoquan_service
    go test ./services/assistant-service/cmd/policy-publish
    go test ./services/assistant-service/cmd/skill-package-publish
  ) >/dev/null
fi

if command -v kustomize >/dev/null 2>&1; then
  kustomize build "$overlay" > "$stage_dir/manifests/all.yaml"
elif command -v kubectl >/dev/null 2>&1; then
  kubectl kustomize "$overlay" > "$stage_dir/manifests/all.yaml"
else
  echo "FAIL: kustomize or kubectl is required to package deployment manifests" >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$service" "$env_name" "$owner" "$stage_dir" <<'PY'
import hashlib
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

from quwoquan_service.scripts.runtime.packaging.lib.service_image_build_input import (
    service_image_build_input_digest,
)

service, environment, owner_value, package_value = sys.argv[1:5]
root = Path.cwd()
owner = root / owner_value
package = Path(package_value)

def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

def tree_digest(path: Path) -> tuple[str, int]:
    accumulator = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file()) if path.exists() else []
    for item in files:
        relative = item.relative_to(path).as_posix().encode()
        content = item.read_bytes()
        accumulator.update(len(relative).to_bytes(8, "big"))
        accumulator.update(relative)
        accumulator.update(len(content).to_bytes(8, "big"))
        accumulator.update(content)
    return "sha256:" + accumulator.hexdigest(), len(files)

def safe_relative_path(raw: object, *, field: str, manifest: Path) -> Path:
    value = str(raw or "").strip()
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"FAIL: {manifest}: {field} must be a safe relative path")
    return candidate

materialized_resources: list[dict[str, object]] = []
environment_resources = owner / "environments" / environment / "resources"
for category in ("releases", "artifacts"):
    for declaration in sorted((environment_resources / category).rglob("*.yaml")):
        payload = yaml.safe_load(declaration.read_text()) or {}
        if not isinstance(payload, dict):
            raise SystemExit(f"FAIL: {declaration}: resource declaration must be a mapping")
        reference = str(payload.get("releaseRef") or payload.get("artifactRef") or "").strip()
        if not reference.startswith("service-resource://"):
            raise SystemExit(
                f"FAIL: {declaration}: deployable resource must use service-resource://"
            )
        source_relative = safe_relative_path(
            reference.removeprefix("service-resource://"),
            field="releaseRef/artifactRef",
            manifest=declaration,
        )
        source_root = (owner / "resources").resolve()
        source = (source_root / source_relative).resolve()
        try:
            source.relative_to(source_root)
        except ValueError as exc:
            raise SystemExit(f"FAIL: {declaration}: resource reference escapes service resources") from exc
        if not source.is_file():
            raise SystemExit(f"FAIL: {declaration}: resource source does not exist: {source}")
        expected_digest = str(payload.get("digest") or "").strip()
        actual_digest = digest(source)
        if expected_digest != actual_digest:
            raise SystemExit(
                f"FAIL: {declaration}: digest {expected_digest!r} differs from {actual_digest}"
            )
        target = safe_relative_path(payload.get("target"), field="target", manifest=declaration)
        destination = package / "resources" / "materialized" / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        environment_variable = str(payload.get("environmentVariable") or "").strip()
        if environment_variable and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", environment_variable):
            raise SystemExit(
                f"FAIL: {declaration}: environmentVariable must be a portable environment variable name"
            )
        materialized_resources.append(
            {
                "source": source,
                "target": target.as_posix(),
                "content": source.read_bytes(),
                "environmentVariable": environment_variable,
            }
        )

if service == "chat-service":
    shared_root = root / "quwoquan_service" / "runtime" / "reliabletask" / "resources"
    for filename, environment_variable in (
        ("module_catalog.yaml", "RELIABLE_TASK_CATALOG_PATH"),
        ("retention_policy.yaml", "RELIABLE_TASK_RETENTION_POLICY_PATH"),
    ):
        source = shared_root / filename
        if not source.is_file():
            raise SystemExit(f"FAIL: missing reliable task runtime resource: {source}")
        target = Path("reliabletask") / filename
        destination = package / "resources" / "materialized" / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        destination.write_bytes(content)
        materialized_resources.append(
            {
                "source": source,
                "target": target.as_posix(),
                "content": content,
                "environmentVariable": environment_variable,
            }
        )

source_digest, source_count, image_build_inputs = service_image_build_input_digest(
    root,
    owner_value,
)
resource_digest, resource_count = tree_digest(package / "resources")
config_path = package / "config/config.yaml"
manifest_path = package / "manifests/all.yaml"
config_payload = yaml.safe_load(config_path.read_text()) or {}
config_version = str(((config_payload.get("config") or {}).get("version") or "")).strip()
if not config_version.startswith("sha256:"):
    raise SystemExit("FAIL: rendered CONFIG_VERSION must be a sha256 digest")
requires_policy_publication = (
    service == "assistant-service" and environment in {"beta", "gamma", "prod"}
)
if requires_policy_publication:
    publication = config_payload.get("policy_publication") or {}
    if not isinstance(publication, dict):
        raise SystemExit("FAIL: assistant policy_publication config must be a mapping")
    policy_resource_root = owner / "resources" / "policies"
    for field in ("release_artifact_ref", "rollout_artifact_ref"):
        reference = safe_relative_path(
            publication.get(field),
            field=f"policy_publication.{field}",
            manifest=config_path,
        )
        artifact = (policy_resource_root / reference).resolve()
        try:
            artifact.relative_to(policy_resource_root.resolve())
        except ValueError as exc:
            raise SystemExit(
                f"FAIL: policy publication {field} escapes immutable policy resources"
            ) from exc
        if not artifact.is_file():
            raise SystemExit(
                f"FAIL: missing assistant policy publication {field}: {artifact}"
            )
revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
image_digest = ("sha256:" + source_digest.removeprefix("sha256:"))
(package / "image.lock").write_text(
    yaml.safe_dump(
        {
            "service": service,
            "repository": f"quwoquan/{service}",
            "digest": image_digest,
            "digestSource": "build-input",
        },
        sort_keys=False,
    )
)
documents = [item for item in yaml.safe_load_all(manifest_path.read_text()) if isinstance(item, dict)]
deployment_found = False
deployment_document = None
service_container = None
for document in documents:
    if document.get("kind") != "Deployment" or (document.get("metadata") or {}).get("name") != service:
        continue
    deployment_found = True
    deployment_document = document
    pod_metadata = document.setdefault("spec", {}).setdefault("template", {}).setdefault("metadata", {})
    annotations = pod_metadata.setdefault("annotations", {})
    annotations["quwoquan.io/config-version"] = config_version
    annotations["quwoquan.io/image-version"] = image_digest
    containers = document["spec"]["template"].setdefault("spec", {}).get("containers") or []
    for container in containers:
        if isinstance(container, dict) and container.get("name") == service:
            service_container = container
            container["image"] = f"quwoquan/{service}@{image_digest}"
if not deployment_found:
    raise SystemExit(f"FAIL: deployment manifest for {service} was not rendered")
if service_container is None or deployment_document is None:
    raise SystemExit(f"FAIL: deployment manifest for {service} has no matching container")
expected_namespace = f"quwoquan-{environment}"
deployment_namespace = str((deployment_document.get("metadata") or {}).get("namespace") or "")
if deployment_namespace != expected_namespace:
    raise SystemExit(
        f"FAIL: deployment namespace {deployment_namespace!r} must equal {expected_namespace!r}"
    )
documents.append(
    {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": f"{service}-runtime-config", "namespace": expected_namespace},
        "data": {f"{service}.yaml": config_path.read_text()},
    }
)
pod_spec = deployment_document["spec"]["template"].setdefault("spec", {})
volumes = pod_spec.setdefault("volumes", [])
runtime_config_name = f"{service}-runtime-config"
runtime_config_volume = next(
    (item for item in volumes if isinstance(item, dict) and item.get("name") == "runtime-config"),
    None,
)
if not isinstance(runtime_config_volume, dict) or str(
    (runtime_config_volume.get("configMap") or {}).get("name") or ""
) != runtime_config_name:
    raise SystemExit(
        f"FAIL: deployment {service} must mount ConfigMap {runtime_config_name} as runtime-config"
    )
runtime_mount = next(
    (
        item
        for item in service_container.get("volumeMounts") or []
        if isinstance(item, dict) and item.get("name") == "runtime-config"
    ),
    None,
)
if not isinstance(runtime_mount, dict) or not str(runtime_mount.get("mountPath") or "").strip():
    raise SystemExit(f"FAIL: deployment {service} must mount runtime-config in its service container")

if requires_policy_publication:
    init_containers = deployment_document["spec"]["template"].setdefault("spec", {}).get(
        "initContainers"
    ) or []
    policy_init = next(
        (
            item
            for item in init_containers
            if isinstance(item, dict) and item.get("name") == "policy-publish"
        ),
        None,
    )
    if not isinstance(policy_init, dict):
        raise SystemExit(
            "FAIL: assistant-service beta/gamma/prod deployment requires policy publication init container"
        )
    if policy_init.get("command") != ["/usr/local/bin/assistant-policy-publish"]:
        raise SystemExit(
            "FAIL: policy publication init container must invoke assistant-policy-publish"
        )
    policy_init["image"] = f"quwoquan/{service}@{image_digest}"
    init_env = {
        str(item.get("name") or ""): item
        for item in policy_init.get("env") or []
        if isinstance(item, dict)
    }
    if init_env.get("ASSISTANT_POLICY_RESOURCE_ROOT", {}).get("value") != "/app/resources/policies":
        raise SystemExit(
            "FAIL: policy publication init container must use immutable image policy resources"
        )
    init_mounts = policy_init.get("volumeMounts") or []
    if not any(
        isinstance(item, dict) and item.get("name") == "runtime-config"
        for item in init_mounts
    ):
        raise SystemExit("FAIL: policy publication init container must mount runtime config")

    policy_job = next(
        (
            document
            for document in documents
            if document.get("kind") == "Job"
            and str((document.get("metadata") or {}).get("name") or "").startswith(
                "assistant-policy-publish-"
            )
        ),
        None,
    )
    if not isinstance(policy_job, dict):
        raise SystemExit(
            "FAIL: assistant-service beta/gamma/prod package requires policy publication Job"
        )
    policy_job_namespace = str((policy_job.get("metadata") or {}).get("namespace") or "")
    if policy_job_namespace != expected_namespace:
        raise SystemExit(
            f"FAIL: policy publication Job namespace {policy_job_namespace!r} "
            f"must equal {expected_namespace!r}"
        )
    job_template = (
        policy_job.setdefault("spec", {})
        .setdefault("template", {})
    )
    job_annotations = job_template.setdefault("metadata", {}).setdefault(
        "annotations", {}
    )
    job_annotations["quwoquan.io/config-version"] = config_version
    job_containers = job_template.setdefault("spec", {}).get("containers") or []
    policy_container = next(
        (
            item
            for item in job_containers
            if isinstance(item, dict) and item.get("name") == "policy-publish"
        ),
        None,
    )
    if not isinstance(policy_container, dict):
        raise SystemExit("FAIL: policy publication Job has no policy-publish container")
    if policy_container.get("command") != ["/usr/local/bin/assistant-policy-publish"]:
        raise SystemExit("FAIL: policy publication Job must invoke assistant-policy-publish")
    policy_container["image"] = f"quwoquan/{service}@{image_digest}"
    policy_env = {
        str(item.get("name") or ""): item
        for item in policy_container.get("env") or []
        if isinstance(item, dict)
    }
    if policy_env.get("ASSISTANT_POLICY_RESOURCE_ROOT", {}).get("value") != "/app/resources/policies":
        raise SystemExit(
            "FAIL: policy publication Job must use the immutable image policy resource root"
        )
    policy_volumes = job_template["spec"].get("volumes") or []
    if not any(
        isinstance(item, dict)
        and item.get("name") == "runtime-config"
        and str((item.get("configMap") or {}).get("name") or "") == runtime_config_name
        for item in policy_volumes
    ):
        raise SystemExit("FAIL: policy publication Job must mount the runtime config")

if materialized_resources:
    resource_config_name = f"{service}-runtime-resources"
    binary_data: dict[str, str] = {}
    resource_items: list[dict[str, str]] = []
    for index, resource in enumerate(materialized_resources):
        key = f"resource-{index:03d}"
        binary_data[key] = base64.b64encode(resource["content"]).decode("ascii")
        resource_items.append({"key": key, "path": str(resource["target"])})
        environment_variable = str(resource["environmentVariable"] or "")
        if environment_variable:
            env_values = service_container.setdefault("env", [])
            existing = next(
                (
                    item
                    for item in env_values
                    if isinstance(item, dict) and item.get("name") == environment_variable
                ),
                None,
            )
            value = f"/etc/qwq/resources/{resource['target']}"
            if existing is None:
                env_values.append({"name": environment_variable, "value": value})
            elif existing.get("value") != value:
                raise SystemExit(
                    f"FAIL: deployment {service} has conflicting {environment_variable} value"
                )
    volumes.append(
        {
            "name": "runtime-resources",
            "configMap": {"name": resource_config_name, "items": resource_items},
        }
    )
    service_container.setdefault("volumeMounts", []).append(
        {
            "name": "runtime-resources",
            "mountPath": "/etc/qwq/resources",
            "readOnly": True,
        }
    )
    documents.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": resource_config_name, "namespace": expected_namespace},
            "binaryData": binary_data,
        }
    )
manifest_path.write_text(yaml.safe_dump_all(documents, allow_unicode=True, sort_keys=False))
provenance = {
    "schema": "qwq.service_package",
    "service": service,
    "environment": environment,
    "gitRevision": revision,
    "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "configVersion": config_version,
    "digests": {
        "imageLock": digest(package / "image.lock"),
        "config": digest(config_path),
        "resources": resource_digest,
        "manifests": digest(manifest_path),
        "sourceTree": source_digest,
    },
    "counts": {"sourceFiles": source_count, "resourceFiles": resource_count},
    "sources": {
        "serviceRoot": owner_value,
        "imageBuildInputs": list(image_build_inputs),
        "configSchema": f"{owner_value}/config/schema.yaml",
        "environment": f"{owner_value}/environments/{environment}",
    },
}
(package / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
PY

if [[ -e "$out_dir" ]]; then
  rm -rf "$out_dir"
fi
mv "$stage_dir" "$out_dir"
trap - EXIT
echo "[package] OK: $out_dir"
