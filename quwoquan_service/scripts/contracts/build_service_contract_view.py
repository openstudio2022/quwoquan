#!/usr/bin/env python3
"""Build the disposable compiler view for service-owned contracts.

The repository truth lives under services/*/contracts (and control-plane
contracts). Existing compilers consume a domain/context/object tree, so this
script projects the service-owned truth into .qwq_output without creating a
second tracked metadata tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import yaml

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names


ENV_OUTPUT_PARTS = (".qwq_output", "env", "repo", "local")
PROVENANCE_FILENAME = ".contract-view-provenance"
PROVENANCE_FORMAT = "contract-view-provenance"

#: 同一缓存父目录下保留的历史视图数量，以及不受回收影响的时间窗（分钟）。
#:
#: 每个调用方都往同一个 cache 目录写自己命名的视图，却没有任何一方负责回收。
#: 一次 `make gate` 就能新增十几个约 600MB 的视图，实测一台开发机上积压到 291 个、
#: 174GB。两个维度必须同时设限：个数保证长期不膨胀，时间窗保证并发运行的其他进程
#: 不会被删掉脚下正在读的目录。
RETAINED_VIEWS = 8
RETENTION_MINUTES = 60

#: `_shared/test_fixtures` 是 canonical 树里唯一同时存放契约文档和「文档所描述的媒体
#: 字节」的地方，视图只投影前者。文档确实被视图消费方读——`internal/metadata/load` 的
#: collectSourceDigests 摘要视图内全部 `.yaml/.yml/.json`，fixture 的 descriptor/manifest
#: 因此进入 ContractGraph 的 sources；载荷则没有任何视图消费方，object/governance/schema
#: 三处 WalkDir 都对 `test_fixtures` SkipDir，真正读字节的 gate 与环境脚本一律直读
#: canonical 路径。
#:
#: 这不削弱完整性证明：载荷的 sha256 本就记在随行文档里（coverSha256、probeHash、
#: sourceHash……），保留文档即传递性钉住载荷，只是不再逐份拷贝已被钉住的字节——那笔拷贝
#: 让单视图 680MB 里有 670MB 是死重量。
#:
#: 只放行文档后缀，而不是屏蔽已知媒体后缀：新增一种媒体格式时视图默认不收，而不是
#: 默默重新长回去。
FIXTURE_TREE_NAME = "test_fixtures"
FIXTURE_DOCUMENT_SUFFIXES = frozenset({".json", ".yaml", ".yml"})


def repository_root() -> Path:
    return REPO_ROOT


def is_fixture_media_payload(view_path: Path) -> bool:
    """判断视图内相对路径是否为 fixture 树的媒体载荷。

    按视图内相对路径而不是绝对路径判断：仓库若被检出到名为 `test_fixtures` 的目录
    之下，绝对路径判断会把整棵契约树误判成载荷。
    """
    if FIXTURE_TREE_NAME not in view_path.parts:
        return False
    return view_path.suffix.lower() not in FIXTURE_DOCUMENT_SUFFIXES


def load_domain(path: Path, snapshot: ContractViewSnapshot | None = None) -> str:
    content = snapshot.read_source(path) if snapshot is not None else path.read_bytes()
    payload = yaml.safe_load(content) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected mapping")
    domain = str(payload.get("domain") or "").strip()
    if not domain or "/" in domain or domain.startswith("_"):
        raise ValueError(f"{path}: invalid domain {domain!r}")
    if set(payload) != {"domain"}:
        raise ValueError(f"{path}: only the path-derived domain selector is allowed")
    return domain


def safe_output(
    root: Path,
    requested: Path,
    *,
    external_output_root: Path | None = None,
) -> Path:
    output = requested.resolve()
    if external_output_root is not None:
        allowed = external_output_root.resolve(strict=True)
        if external_output_root.is_symlink() or not allowed.is_dir():
            raise ValueError("external output root must be a real directory")
        repository = root.resolve()
        if (
            allowed == repository
            or repository in allowed.parents
            or allowed in repository.parents
        ):
            raise ValueError("external output root must be outside repository source")
        if output == allowed or allowed not in output.parents:
            raise ValueError(f"output must be below external root {allowed}")
        current = output.parent
        while current != allowed:
            if current.exists() and current.is_symlink():
                raise ValueError(f"output parent cannot be a symlink: {current}")
            current = current.parent
        return output
    allowed = root.joinpath(*ENV_OUTPUT_PARTS).resolve()
    if output == allowed or allowed not in output.parents:
        raise ValueError(f"output must be below {allowed}")
    relative = output.relative_to(allowed)
    if len(relative.parts) < 3 or relative.parts[1] != "cache":
        raise ValueError(
            "output must use local/<target>/cache/<run>: "
            f"{output}"
        )
    return output


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ContractViewSnapshot:
    """Copies immutable bytes and records their canonical repository provenance."""

    def __init__(self, root: Path, output: Path) -> None:
        self.root = root.resolve()
        self.output = output.resolve()
        self._sources: dict[str, str] = {}
        self._files: dict[str, tuple[str, tuple[str, ...]]] = {}

    def _canonical_source_path(self, source: Path) -> tuple[Path, str]:
        if source.is_symlink():
            raise ValueError(f"canonical source must not be a symlink: {source}")
        resolved = source.resolve(strict=True)
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError(f"canonical source is outside repository root: {source}") from exc
        return resolved, relative

    def read_source(self, source: Path) -> bytes:
        resolved, relative = self._canonical_source_path(source)
        payload = resolved.read_bytes()
        digest = sha256_bytes(payload)
        previous = self._sources.get(relative)
        if previous is not None and previous != digest:
            raise ValueError(f"canonical source changed while building view: {relative}")
        self._sources[relative] = digest
        return payload

    def _write_file(
        self,
        target: Path,
        payload: bytes,
        source_paths: list[Path],
    ) -> None:
        resolved_target = target.resolve()
        try:
            relative = resolved_target.relative_to(self.output).as_posix()
        except ValueError as exc:
            raise ValueError(f"view output escapes root: {target}") from exc
        if relative == PROVENANCE_FILENAME:
            raise ValueError(f"view file uses reserved name: {relative}")
        if relative in self._files:
            raise ValueError(f"duplicate contract view output: {relative}")
        canonical_sources: list[str] = []
        for source in source_paths:
            _, source_relative = self._canonical_source_path(source)
            if source_relative not in self._sources:
                raise ValueError(f"unread canonical source for {relative}: {source_relative}")
            canonical_sources.append(source_relative)
        canonical_sources = sorted(set(canonical_sources))
        if not canonical_sources:
            raise ValueError(f"contract view output has no canonical provenance: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        self._files[relative] = (sha256_bytes(payload), tuple(canonical_sources))

    def copy_file(self, source: Path, target: Path) -> None:
        self._write_file(target, self.read_source(source), [source])

    def copy_tree(self, source: Path, target: Path) -> None:
        # 目录由 `_write_file` 按需创建：只含媒体载荷的 fixture 目录不投影任何文件，
        # 预先 mkdir 会在视图里留下上千个空目录，看起来像内容丢失。
        for child in sorted(source.iterdir()):
            destination = target / child.name
            if child.is_dir():
                self.copy_tree(child, destination)
            elif not is_fixture_media_payload(destination.relative_to(self.output)):
                self.copy_file(child, destination)

    def write_derived(
        self,
        target: Path,
        payload: bytes,
        source_paths: list[Path],
    ) -> None:
        self._write_file(target, payload, source_paths)

    def _verify_sources_unchanged(self) -> None:
        for relative, expected in sorted(self._sources.items()):
            source = self.root / relative
            current = sha256_bytes(source.read_bytes())
            if current != expected:
                raise ValueError(f"canonical source changed while building view: {relative}")

    def write_provenance(self) -> None:
        self._verify_sources_unchanged()
        actual_files: list[str] = []
        for path in sorted(self.output.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"contract view contains a live symlink: {path}")
            if path.is_file() and path.name != PROVENANCE_FILENAME:
                actual_files.append(path.relative_to(self.output).as_posix())
        expected_files = sorted(self._files)
        if actual_files != expected_files:
            raise ValueError(
                "contract view inventory differs from provenance: "
                f"actual={actual_files}, expected={expected_files}"
            )

        digest = hashlib.sha256()
        files: list[dict[str, object]] = []
        for path in expected_files:
            file_digest, source_paths = self._files[path]
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_digest.encode("ascii"))
            digest.update(b"\n")
            files.append(
                {
                    "path": path,
                    "sha256": file_digest,
                    "sourcePaths": list(source_paths),
                }
            )
        manifest = {
            "format": PROVENANCE_FORMAT,
            "viewDigest": digest.hexdigest(),
            "sources": [
                {"path": path, "sha256": source_digest}
                for path, source_digest in sorted(self._sources.items())
            ],
            "files": files,
        }
        target = self.output / PROVENANCE_FILENAME
        temporary = self.output / (PROVENANCE_FILENAME + ".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._verify_sources_unchanged()
        temporary.replace(target)


def contract_roots(root: Path) -> list[Path]:
    # Only physical service/control-plane contracts participate. Retired
    # domains must leave the tree; no materialized dual-track is accepted.
    candidates = sorted((root / "quwoquan_service/services").glob("*/contracts"))
    candidates.extend(
        sorted((root / "quwoquan_service/control-plane").glob("*/contracts"))
    )
    return [path for path in candidates if (path / "domain.yaml").is_file()]


def build_config_views(
    root: Path,
    output: Path,
    contracts_roots: list[Path],
    snapshot: ContractViewSnapshot,
) -> None:
    """聚合服务自治 schema，供尚未改造完成的编译器读取派生视图。"""
    active_services = set(first_party_service_names(root))
    schema_paths: list[Path] = []
    for contracts in contracts_roots:
        schema_path = contracts.parent / "config/schema.yaml"
        if "services" not in contracts.parts:
            schema_paths.append(schema_path)
            continue
        service_name = contracts.parent.name
        if service_name in active_services:
            schema_paths.append(schema_path)
    schema_paths.extend(
        [
            root / "quwoquan_service/runtime/config/schema.yaml",
            root / "quwoquan_app/config/schema.yaml",
        ]
    )
    definitions: dict[str, tuple[dict, Path]] = {}
    for schema_path in schema_paths:
        if not schema_path.is_file():
            raise ValueError(f"missing autonomous config schema: {schema_path}")
        payload = yaml.safe_load(snapshot.read_source(schema_path)) or {}
        entries = payload.get("configs", []) or []
        if not isinstance(entries, list):
            raise ValueError(f"{schema_path}: configs must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
                raise ValueError(f"{schema_path}: invalid config definition")
            key = entry["key"]
            if key in definitions:
                raise ValueError(
                    f"config key {key} has multiple owners: "
                    f"{definitions[key][1]} and {schema_path}"
                )
            definitions[key] = (entry, schema_path)

    platform = [entry for key, (entry, _) in sorted(definitions.items()) if key.startswith("sys.")]
    product = [entry for key, (entry, _) in sorted(definitions.items()) if key.startswith("ops.")]
    unknown = sorted(key for key in definitions if not key.startswith(("sys.", "ops.")))
    if unknown:
        raise ValueError(f"config keys must start with sys. or ops.: {unknown}")
    for target, description, entries in (
        (
            output / "platform/config.yaml",
            "由服务自治 config/schema.yaml 生成的 sys.* 编译视图；不可编辑。",
            platform,
        ),
        (
            output / "_control_plane/product/config.yaml",
            "由服务自治 config/schema.yaml 生成的 ops.* 编译视图；不可编辑。",
            product,
        ),
    ):
        rendered = yaml.safe_dump(
            {"description": description, "configs": entries},
            allow_unicode=True,
            sort_keys=False,
            width=120,
        ).encode("utf-8")
        snapshot.write_derived(target, rendered, schema_paths)


def prune_sibling_views(output: Path, *, now: float | None = None) -> list[Path]:
    """回收同级目录下的陈旧契约视图。

    只认带 ``PROVENANCE_FILENAME`` 的目录，调用方放在同一父目录下的其他产物不会被
    误删；并且只在缓存位于 ``.qwq_output`` 内时动手，``--output`` 指到别处的构建
    完全不受影响。
    """
    parent = output.parent
    if ENV_OUTPUT_PARTS[0] not in parent.parts:
        return []
    cutoff = (time.time() if now is None else now) - RETENTION_MINUTES * 60
    views: list[tuple[float, Path]] = []
    for entry in parent.iterdir():
        if entry == output or entry.is_symlink() or not entry.is_dir():
            continue
        if not (entry / PROVENANCE_FILENAME).is_file():
            continue
        views.append((entry.stat().st_mtime, entry))
    views.sort(reverse=True)
    removed: list[Path] = []
    for index, (mtime, entry) in enumerate(views):
        if index < RETAINED_VIEWS or mtime > cutoff:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry)
    return removed


def build(
    root: Path,
    output: Path,
    *,
    external_output_root: Path | None = None,
) -> Path:
    output = safe_output(
        root,
        output,
        external_output_root=external_output_root,
    )
    if output.exists() or output.is_symlink():
        if output.is_symlink():
            output.unlink()
        else:
            shutil.rmtree(output)
    output.mkdir(parents=True)
    snapshot = ContractViewSnapshot(root, output)

    try:
        foundation = root / "quwoquan_service/contracts/metadata"
        for name in ("_schemas", "_shared", "_control_plane", "_vectors", "platform"):
            source = foundation / name
            if source.is_dir():
                snapshot.copy_tree(source, output / name)
        for source in sorted(foundation.glob("*.yaml")):
            snapshot.copy_file(source, output / source.name)

        roots = contract_roots(root)
        owners: dict[tuple[str, str], Path] = {}
        for contracts in roots:
            domain = load_domain(contracts / "domain.yaml", snapshot)
            domain_output = output / domain
            domain_output.mkdir(exist_ok=True)
            for child in sorted(contracts.iterdir()):
                if child.name == "domain.yaml":
                    continue
                if child.name == "_shared":
                    for shared_child in sorted(child.iterdir()):
                        if shared_child.is_dir():
                            # Historical domain-owned support contracts are not
                            # bounded contexts and remain direct compiler inputs.
                            snapshot.copy_tree(shared_child, domain_output / shared_child.name)
                        else:
                            snapshot.copy_file(
                                shared_child,
                                domain_output / "_shared" / shared_child.name,
                            )
                    continue
                owner_key = (domain, child.name)
                if owner_key in owners:
                    raise ValueError(
                        f"context {domain}.{child.name} has multiple contract owners: "
                        f"{owners[owner_key]} and {contracts}"
                    )
                owners[owner_key] = contracts
                snapshot.copy_tree(child, domain_output / child.name)

            generated_openapi = contracts.parent / "generated" / "openapi.yaml"
            if generated_openapi.is_file():
                snapshot.copy_file(generated_openapi, domain_output / "openapi.yaml")

        if not owners:
            raise ValueError("no service-owned contracts found")
        build_config_views(root, output, roots, snapshot)
        snapshot.write_provenance()
        prune_sibling_views(output)
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    root = repository_root()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=root.joinpath(
            *ENV_OUTPUT_PARTS,
            "service-contract-view",
            "cache",
            "view",
        ),
    )
    parser.add_argument("--external-output-root", type=Path)
    args = parser.parse_args()
    try:
        print(
            build(
                root,
                args.output,
                external_output_root=args.external_output_root,
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[service-contract-view] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
