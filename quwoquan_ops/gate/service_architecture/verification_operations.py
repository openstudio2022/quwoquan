"""Verification 运维资产检查段：资源/迁移、Compose 归属、端口契约、Kustomize 与子门禁。"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .constants import (
    COMMON_RESOURCE_ROOT_ROLES,
    ENVIRONMENTS,
    MIGRATION_RE,
    OPS_ROOT,
    ROOT,
    SERVICE_ROOT,
    SKILL_PACKAGE_RUNTIME_RELATIVE_ROOT,
    SKILL_PACKAGE_SOURCE_RELATIVE_ROOT,
)
from .repository import (
    compose_ownership_violations,
    domain_service_names,
    load_yaml,
    relative,
    service_roots,
)


class OperationsVerificationMixin:
    """承载原 Verification 类中资源/部署/运维方法，方法体逐字搬移。

    唯一非字面改动：原模块级私有函数 ``_compose_ownership_violations`` 因跨模块
    消费改名为 ``repository.compose_ownership_violations``。
    """

    def verify_resources_and_migrations(self) -> None:
        for service in service_roots():
            resources = service / "resources"
            if resources.is_dir():
                unexpected = {
                    path.name
                    for path in resources.iterdir()
                    if path.name not in COMMON_RESOURCE_ROOT_ROLES
                }
                if unexpected:
                    self.error(
                        f"{service.name}: unsupported common resource roots: {sorted(unexpected)}"
                    )
                skill_source_area = resources / "skill_packages"
                skill_runtime_area = resources / "skills"
                skill_runtime_packages = skill_runtime_area / "packages"
                skill_source_root = resources / SKILL_PACKAGE_SOURCE_RELATIVE_ROOT
                skill_runtime_root = resources / SKILL_PACKAGE_RUNTIME_RELATIVE_ROOT
                if skill_source_area.exists() or skill_runtime_area.exists():
                    if not skill_source_root.is_dir():
                        self.error(
                            f"{service.name}: controlled Skill publisher source must be "
                            f"{relative(skill_source_root)}"
                        )
                    if not skill_runtime_root.is_dir():
                        self.error(
                            f"{service.name}: immutable Skill runtime assets must be "
                            f"{relative(skill_runtime_root)}"
                        )
                    source_entries = (
                        {path.name for path in skill_source_area.iterdir()}
                        if skill_source_area.is_dir()
                        else set()
                    )
                    if source_entries != {"official"}:
                        self.error(
                            f"{service.name}: Skill publisher source root must contain only "
                            f"official, got {sorted(source_entries)}"
                        )
                    runtime_entries = (
                        {path.name for path in skill_runtime_area.iterdir()}
                        if skill_runtime_area.is_dir()
                        else set()
                    )
                    if runtime_entries != {"packages"}:
                        self.error(
                            f"{service.name}: Skill runtime root must contain only packages, "
                            f"got {sorted(runtime_entries)}"
                        )
                    package_entries = (
                        {path.name for path in skill_runtime_packages.iterdir()}
                        if skill_runtime_packages.is_dir()
                        else set()
                    )
                    if package_entries != {"official"}:
                        self.error(
                            f"{service.name}: Skill runtime packages root must contain only "
                            f"official, got {sorted(package_entries)}"
                        )
                    if any(
                        path.is_symlink()
                        for path in (
                            skill_source_area,
                            skill_source_root,
                            skill_runtime_area,
                            skill_runtime_packages,
                            skill_runtime_root,
                        )
                    ):
                        self.error(
                            f"{service.name}: Skill source/runtime roots must be physical, not symlinks"
                        )
                    if (
                        skill_source_root.is_dir()
                        and skill_runtime_root.is_dir()
                        and skill_source_root.resolve() == skill_runtime_root.resolve()
                    ):
                        self.error(
                            f"{service.name}: Skill publisher source and immutable runtime assets "
                            "must be physically distinct"
                        )
            for path in resources.rglob("*") if resources.is_dir() else []:
                lowered = {part.lower() for part in path.parts}
                if path.is_file() and lowered & {"fixture", "fixtures", "testdata"}:
                    self.error(f"{relative(path)}: test fixture is forbidden in runtime resources")
            migrations = sorted((resources / "migrations").rglob("*")) if resources.is_dir() else []
            numbers: dict[int, Path] = {}
            for path in migrations:
                if not path.is_file():
                    continue
                match = MIGRATION_RE.match(path.name)
                if not match:
                    self.error(f"{relative(path)}: migration requires numeric prefix")
                    continue
                number = int(match.group(1))
                if number in numbers:
                    self.error(
                        f"{service.name}: duplicate migration number {number}: "
                        f"{relative(numbers[number])}, {relative(path)}"
                    )
                numbers[number] = path
            if numbers and sorted(numbers) != list(range(1, max(numbers) + 1)):
                self.error(f"{service.name}: migration numbering must be contiguous from 001")
            for environment in ("gamma", "prod"):
                seed_root = service / "environments" / environment / "resources" / "seeds"
                if seed_root.exists() and any(path.is_file() for path in seed_root.rglob("*")):
                    self.error(f"{relative(seed_root)}: gamma/prod seed is forbidden")
            for environment in ENVIRONMENTS:
                environment_resources = service / "environments" / environment / "resources"
                if service.name == "content-service":
                    delivery_manifest = (
                        environment_resources / "artifacts" / "media" / "delivery_manifest.yaml"
                    )
                    if delivery_manifest.exists():
                        self.error(
                            f"{relative(delivery_manifest)}: environment media manifests are forbidden; immutable release activation owns public media"
                        )
                if not environment_resources.is_dir():
                    continue
                allowed_environment = {"seeds", "releases", "artifacts"}
                unexpected = {
                    path.name
                    for path in environment_resources.iterdir()
                    if path.name not in allowed_environment
                }
                if unexpected:
                    self.error(
                        f"{relative(environment_resources)}: unsupported resource roots: "
                        f"{sorted(unexpected)}"
                    )
                for category in ("releases", "artifacts"):
                    for manifest in (environment_resources / category).rglob("*.yaml"):
                        try:
                            document = load_yaml(manifest)
                        except (OSError, ValueError, yaml.YAMLError) as exc:
                            self.error(f"{relative(manifest)}: invalid resource manifest: {exc}")
                            continue
                        reference = str(
                            document.get("releaseRef") or document.get("artifactRef") or ""
                        )
                        digest = str(document.get("digest") or "")
                        if not reference or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                            self.error(
                                f"{relative(manifest)}: requires releaseRef/artifactRef and sha256 digest"
                            )
                            continue
                        if reference.startswith("service-resource://"):
                            source = resources / reference.removeprefix("service-resource://")
                            if not source.is_file():
                                self.error(
                                    f"{relative(manifest)}: service resource does not exist: {relative(source)}"
                                )
                                continue
                            actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
                            if actual != digest:
                                self.error(
                                    f"{relative(manifest)}: digest {digest} differs from {actual}"
                                )

    def verify_compose_ownership(self) -> None:
        for service in service_roots():
            path = service / "deploy" / "compose.yaml"
            if not path.is_file():
                self.error(f"{service.name}: active local workload requires deploy/compose.yaml")
                continue
            try:
                services = load_yaml(path).get("services") or {}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self.error(f"{relative(path)}: invalid Compose fragment: {exc}")
                continue
            illegal = compose_ownership_violations(service.name, services)
            if illegal is not None:
                self.error(
                    f"{relative(path)}: must own only {service.name} "
                    f"(optional `{service.name}-migrate*` one-shots), got {illegal}"
                )
            for environment_overlay in sorted(
                (service / "environments").glob("*/deploy/compose.yaml")
            ):
                try:
                    overlay_services = load_yaml(environment_overlay).get("services") or {}
                except (OSError, ValueError, yaml.YAMLError) as exc:
                    self.error(
                        f"{relative(environment_overlay)}: invalid service Compose overlay: {exc}"
                    )
                    continue
                illegal = compose_ownership_violations(service.name, overlay_services)
                if illegal is not None:
                    self.error(
                        f"{relative(environment_overlay)}: must own only {service.name} "
                        f"(optional `{service.name}-migrate*` one-shots), got {illegal}"
                    )

        platform_path = SERVICE_ROOT / "control-plane/platform-ops/deploy/compose.yaml"
        try:
            platform_services = load_yaml(platform_path).get("services") or {}
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self.error(f"{relative(platform_path)}: invalid Compose fragment: {exc}")
        else:
            if set(platform_services) != {"platform-ops-service"}:
                self.error(
                    f"{relative(platform_path)}: must own only platform-ops-service"
                )

        compose_root = OPS_ROOT / "environments" / "compose"
        for path in sorted(compose_root.glob("*.y*ml")):
            try:
                services = load_yaml(path).get("services") or {}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self.error(f"{relative(path)}: invalid Ops Compose assembly: {exc}")
                continue
            first_party = domain_service_names() | {"platform-ops-service"}
            duplicated: list[str] = []
            for name in sorted(set(services) & first_party):
                service = services.get(name) or {}
                # Merge-only overlays (e.g. gamma ES depends_on) are allowed; full
                # workload copies that redefine image/build must stay in service fragments.
                if isinstance(service, dict) and (
                    "image" in service or "build" in service
                ):
                    duplicated.append(name)
            if duplicated:
                self.error(
                    f"{relative(path)}: first-party workload copies belong to service fragments: "
                    f"{duplicated}"
                )

    def verify_special_assets(self) -> None:
        required = {
            "quwoquan_ops/external/coturn/base/kustomization.yaml",
            "quwoquan_ops/external/livekit/base/kustomization.yaml",
            "quwoquan_service/static/legal/manifest.yaml",
            "quwoquan_service/static/legal/tests/local_contract/manifest__contract__local_contract_test.py",
            "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
            "quwoquan_service/control-plane/platform-ops/deploy/base/kustomization.yaml",
        }
        for source in sorted(required):
            if not (ROOT / source).is_file():
                self.error(f"required external/static/control-plane asset is missing: {source}")
        repository_roots = (
            SERVICE_ROOT,
            OPS_ROOT,
            ROOT / "quwoquan_app",
            ROOT / "quwoquan_data",
            ROOT / "specs",
        )
        ignored_directories = {
            ".git",
            ".qwq_output",
            ".dart_tool",
            ".pytest_cache",
            "Pods",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
        }
        retired_seed_box_found = False
        for repository_root in repository_roots:
            if not repository_root.is_dir():
                continue
            for _, directories, _ in os.walk(repository_root):
                if "seed-box" in directories:
                    retired_seed_box_found = True
                    break
                directories[:] = [
                    directory
                    for directory in directories
                    if directory not in ignored_directories
                ]
            if retired_seed_box_found:
                break
        if retired_seed_box_found:
            self.error("retired seed-box physical directory returned")
        for workload in ("coturn", "livekit"):
            environment_root = OPS_ROOT / "external" / workload / "environments"
            actual = sorted(path.name for path in environment_root.iterdir() if path.is_dir())
            if actual != list(ENVIRONMENTS):
                self.error(f"external {workload}: environment set is {actual}")

    def verify_runtime_port_contracts(self) -> None:
        for service in service_roots():
            deployment_path = service / "deploy/base/deployment.yaml"
            dockerfile_path = service / "build/Dockerfile"
            schema_path = service / "config/schema.yaml"
            try:
                deployment = load_yaml(deployment_path)
                container = deployment["spec"]["template"]["spec"]["containers"][0]
            except (OSError, ValueError, yaml.YAMLError, KeyError, IndexError, TypeError) as exc:
                self.error(f"{relative(deployment_path)}: invalid deployment container: {exc}")
                continue
            ports = [
                int(item["containerPort"])
                for item in container.get("ports") or []
                if isinstance(item, dict) and "containerPort" in item
            ]
            if len(ports) != 1:
                self.error(f"{relative(deployment_path)}: expected one service container port")
                continue
            docker_ports = [
                int(value)
                for value in re.findall(
                    r"(?m)^EXPOSE\s+(\d+)", dockerfile_path.read_text(encoding="utf-8")
                )
            ]
            if docker_ports != ports:
                self.error(
                    f"{service.name}: Docker EXPOSE {docker_ports} differs from deployment {ports}"
                )
            definitions = load_yaml(schema_path).get("configs") or []
            address_key = f"sys.{service.name}.service.http.addr"
            addresses = [
                item.get("default")
                for item in definitions
                if isinstance(item, dict) and item.get("key") == address_key
            ]
            if len(addresses) != 1 or str(addresses[0]) != f":{ports[0]}":
                self.error(
                    f"{service.name}: {address_key} default {addresses} differs from :{ports[0]}"
                )
            env_from = container.get("envFrom") or []
            expected_secret = f"{service.name}-runtime-secrets"
            if not any(
                isinstance(item, dict)
                and isinstance(item.get("secretRef"), dict)
                and item["secretRef"].get("name") == expected_secret
                for item in env_from
            ):
                self.error(f"{service.name}: deployment must envFrom {expected_secret}")
            mounts = container.get("volumeMounts") or []
            if not any(
                isinstance(item, dict)
                and item.get("name") == "runtime-config"
                and item.get("readOnly") is True
                for item in mounts
            ):
                self.error(f"{service.name}: runtime config must be mounted read-only")

    def verify_kustomize_entries(self) -> None:
        builder = shutil.which("kustomize")
        command_prefix = [builder, "build"] if builder else []
        if not command_prefix and shutil.which("kubectl"):
            command_prefix = [shutil.which("kubectl") or "kubectl", "kustomize"]
        if not command_prefix:
            self.error("kustomize or kubectl is required for 60 environment builds")
            return
        entries = [
            service / "environments" / environment / "deploy"
            for service in service_roots()
            for environment in ENVIRONMENTS
        ] + [OPS_ROOT / "environments" / environment for environment in ENVIRONMENTS]
        for entry in entries:
            result = subprocess.run(
                command_prefix + [str(entry)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                tail = "\n".join((result.stdout + result.stderr).splitlines()[-8:])
                self.error(f"{relative(entry)}: kustomize build failed:\n{tail}")

    @staticmethod
    def _executable_magic(path: Path) -> str | None:
        try:
            with path.open("rb") as source:
                prefix = source.read(4)
        except OSError as error:
            raise ValueError(f"executable magic unreadable: {path}: {error}") from error
        if prefix == b"\x7fELF":
            return "ELF"
        if prefix in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
            return "Mach-O"
        if prefix[:2] == b"MZ":
            return "PE"
        return None

    def verify_no_source_artifacts(self) -> None:
        # Align with gate_repo.sh: purge ephemeral caches before asserting absence.
        # Concurrent local agents may recreate bytecode mid-gate; a single purge+scan
        # keeps the check deterministic without allowing committed cache debt.
        os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        sys.dont_write_bytecode = True
        source_roots = (
            ROOT / "quwoquan_app",
            SERVICE_ROOT,
            ROOT / "quwoquan_data",
            OPS_ROOT,
        )
        ignored_directories = {
            ".dart_tool",
            ".git",
            ".gradle",
            ".idea",
            ".qwq_output",
            ".venv",
            "Pods",
            "build",
            "dist",
            "node_modules",
            "vendor",
        }

        def walk_source_tree(source_root: Path):
            for current, directories, files in os.walk(source_root):
                directories[:] = [
                    name for name in directories if name not in ignored_directories
                ]
                current_path = Path(current)
                for directory in directories:
                    yield current_path / directory
                for filename in files:
                    yield current_path / filename

        for source_root in source_roots:
            if not source_root.is_dir():
                continue
            for path in walk_source_tree(source_root):
                if path.name in {"__pycache__", ".pytest_cache"}:
                    shutil.rmtree(path, ignore_errors=True)
                elif path.suffix in {".pyc", ".pyo"} and path.is_file():
                    path.unlink(missing_ok=True)
        for source_root in source_roots:
            if not source_root.is_dir():
                continue
            for path in walk_source_tree(source_root):
                if path.name in {"__pycache__", ".pytest_cache"} or path.suffix in {
                    ".pyc",
                    ".pyo",
                }:
                    self.error(f"source-tree cache is forbidden: {relative(path)}")
                if path.is_file() and (path.name in {".coverage", "coverage.out"} or path.suffix == ".test"):
                    self.error(f"source-tree test artifact is forbidden: {relative(path)}")
                if path.is_file() and not path.is_symlink():
                    try:
                        magic = self._executable_magic(path)
                    except ValueError as error:
                        self.error(str(error))
                        continue
                    if magic:
                        self.error(f"source-tree executable build artifact is forbidden: {relative(path)} ({magic})")

    def run_subgates(self) -> None:
        commands = [
            (
                ["bash", "quwoquan_service/scripts/runtime/packaging/verify_service_config_layout.sh"],
                "service config ownership",
            ),
            (
                [sys.executable, "quwoquan_ops/gate/verify_environment_assembly.py"],
                "derived environment topology",
            ),
            (
                [sys.executable, "quwoquan_ops/gate/verify_prod_plane_access_isolation.py"],
                "prod access isolation",
            ),
        ]
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for command, label in commands:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
                self.error(f"{label} failed:\n{tail}")
