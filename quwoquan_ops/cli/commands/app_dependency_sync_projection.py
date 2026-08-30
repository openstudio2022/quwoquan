"""Build the immutable source projection used by App dependency sync."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from quwoquan_ops.cli.lib.package_reuse.dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)

_MANIFEST_RELATIVE = (
    "quwoquan_app/tool/app_launch_contract_codegen/generated_manifest.json"
)
_MANIFEST_SCHEMA = "qwq.app-launch-contract-codegen-manifest"
_MANIFEST_GENERATOR = "tools/codegen_app_metadata --app-launch-contract-only"
_INPUT_ROOT = PurePosixPath("quwoquan_service/contracts/metadata")
_OUTPUT_ROOTS = (
    PurePosixPath("quwoquan_app"),
    PurePosixPath("quwoquan_ops/cli/lib/generated"),
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IGNORED_DIRECTORIES = {
    ".dart_tool",
    ".gradle",
    ".idea",
    ".kotlin",
    ".qwq_output",
    ".symlinks",
    "Pods",
    "build",
    "ephemeral",
    "example",
    "example_ohos",
}
_IGNORED_FILES = {
    ".flutter-plugins",
    ".flutter-plugins-dependencies",
    "Flutter.podspec",
    "Generated.xcconfig",
    "flutter_export_environment.sh",
    "local.properties",
}


@dataclass(frozen=True, slots=True)
class _ClosureSeal:
    manifest: tuple[bytes, int]
    files: tuple[tuple[str, tuple[bytes, int]], ...]


def _failure(reason: str, detail: str = "") -> ValueError:
    suffix = f": {detail}" if detail else ""
    return ValueError(f"APP.DEPENDENCY.source_projection_{reason}{suffix}")


def _canonical_real_directory(raw: Path, *, reason: str) -> Path:
    lexical = raw.expanduser().absolute()
    try:
        canonical = lexical.resolve(strict=True)
        assert_real_directory(canonical, label="source projection directory")
    except (OSError, RuntimeError, ValueError) as exc:
        raise _failure(reason) from exc
    if canonical != lexical:
        raise _failure(reason)
    return canonical


def _read_projection_file(
    path: Path,
    *,
    label: str,
    scope: str,
    detail: str,
) -> tuple[bytes, int]:
    try:
        return read_regular_nofollow(path, label=label)
    except (RuntimeError, ValueError) as exc:
        raise _failure(f"{scope}_read_invalid", detail) from exc


def _canonical_path(raw: object, *, field: str) -> tuple[str, PurePosixPath]:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise _failure("manifest_path_invalid", field)
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or path.as_posix() != raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _failure("manifest_path_invalid", field)
    return raw, path


def _valid_digest(raw: object, *, field: str) -> str:
    if not isinstance(raw, str) or _DIGEST.fullmatch(raw) is None:
        raise _failure("manifest_digest_invalid", field)
    return raw


def _is_relative_to(path: PurePosixPath, root: PurePosixPath) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def _manifest_entries(encoded: bytes) -> list[tuple[str, str, int | None]]:
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _failure("manifest_invalid_json") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "generator",
        "sourceDigest",
        "inputs",
        "outputs",
    }:
        raise _failure("manifest_shape_invalid")
    if value["schema"] != _MANIFEST_SCHEMA:
        raise _failure("manifest_schema_invalid")
    if value["generator"] != _MANIFEST_GENERATOR:
        raise _failure("manifest_generator_invalid")
    _valid_digest(value["sourceDigest"], field="sourceDigest")
    if not isinstance(value["inputs"], list) or not isinstance(value["outputs"], list):
        raise _failure("manifest_shape_invalid", "inputs/outputs")
    if not value["inputs"] or not value["outputs"]:
        raise _failure("manifest_shape_invalid", "empty inputs/outputs")

    entries: list[tuple[str, str, int | None]] = []
    seen: set[str] = set()
    for kind, items in (("input", value["inputs"]), ("output", value["outputs"])):
        expected_keys = {"path", "sha256"} | ({"bytes"} if kind == "output" else set())
        for index, item in enumerate(items):
            field = f"{kind}[{index}]"
            if not isinstance(item, dict) or set(item) != expected_keys:
                raise _failure("manifest_entry_invalid", field)
            relative, pure = _canonical_path(item["path"], field=f"{field}.path")
            if relative in seen:
                raise _failure("manifest_path_duplicate", relative)
            seen.add(relative)
            if kind == "input":
                if not _is_relative_to(pure, _INPUT_ROOT):
                    raise _failure("manifest_input_outside_allowlist", relative)
                byte_count = None
            else:
                if not any(_is_relative_to(pure, root) for root in _OUTPUT_ROOTS):
                    raise _failure("manifest_output_outside_allowlist", relative)
                byte_count = item["bytes"]
                if (
                    not isinstance(byte_count, int)
                    or isinstance(byte_count, bool)
                    or byte_count < 0
                ):
                    raise _failure("manifest_bytes_invalid", relative)
            digest = _valid_digest(item["sha256"], field=f"{field}.sha256")
            entries.append((relative, digest, byte_count))
    return entries


def _seal_source_closure(source_root: Path) -> _ClosureSeal:
    manifest = _read_projection_file(
        source_root / _MANIFEST_RELATIVE,
        label="App launch generated closure manifest",
        scope="source",
        detail=_MANIFEST_RELATIVE,
    )
    files: list[tuple[str, tuple[bytes, int]]] = []
    for relative, expected_digest, expected_bytes in _manifest_entries(manifest[0]):
        sealed = _read_projection_file(
            source_root / relative,
            label=f"App launch generated closure source {relative}",
            scope="source",
            detail=relative,
        )
        actual_digest = "sha256:" + hashlib.sha256(sealed[0]).hexdigest()
        if actual_digest != expected_digest:
            raise _failure("closure_digest_mismatch", relative)
        if expected_bytes is not None and len(sealed[0]) != expected_bytes:
            raise _failure("closure_bytes_mismatch", relative)
        files.append((relative, sealed))
    return _ClosureSeal(manifest=manifest, files=tuple(files))


def _assert_projection_closure(target_root: Path, seal: _ClosureSeal) -> None:
    projected_manifest = _read_projection_file(
        target_root / _MANIFEST_RELATIVE,
        label="projected App launch generated closure manifest",
        scope="target",
        detail=_MANIFEST_RELATIVE,
    )
    if projected_manifest != seal.manifest:
        raise _failure("closure_drift", _MANIFEST_RELATIVE)
    for relative, expected in seal.files:
        actual = _read_projection_file(
            target_root / relative,
            label=f"projected App launch generated closure {relative}",
            scope="target",
            detail=relative,
        )
        if actual != expected:
            raise _failure("closure_drift", relative)


def _assert_source_closure(source_root: Path, seal: _ClosureSeal) -> None:
    current_manifest = _read_projection_file(
        source_root / _MANIFEST_RELATIVE,
        label="App launch generated closure manifest readback",
        scope="source",
        detail=_MANIFEST_RELATIVE,
    )
    if current_manifest != seal.manifest:
        raise _failure("source_drift", _MANIFEST_RELATIVE)
    for relative, expected in seal.files:
        current = _read_projection_file(
            source_root / relative,
            label=f"App launch generated closure source readback {relative}",
            scope="source",
            detail=relative,
        )
        if current != expected:
            raise _failure("source_drift", relative)


def _assert_no_link_escape(target_root: Path) -> None:
    for node in target_root.rglob("*"):
        if node.is_symlink() and not node.resolve(strict=True).is_relative_to(
            target_root
        ):
            raise _failure("link_escape", node.relative_to(target_root).as_posix())


def project(repo_root: Path, destination: Path) -> Path:
    """Copy App sources plus the manifest-declared generated-code closure."""

    source_root = _canonical_real_directory(repo_root, reason="source_root_invalid")
    raw_target = destination.expanduser().absolute()
    target_parent = _canonical_real_directory(
        raw_target.parent,
        reason="target_parent_invalid",
    )
    target_root = target_parent / raw_target.name
    if target_root.exists() or target_root.is_symlink():
        raise _failure("must_be_fresh")
    seal = _seal_source_closure(source_root)
    app_source = source_root / "quwoquan_app"
    service_relative = Path(
        "quwoquan_service/contracts/runtime_errors/packages/dart/"
        "quwoquan_runtime_errors"
    )
    service_source = source_root / service_relative
    for source in (app_source, service_source):
        try:
            assert_real_directory(source, label="source projection copy root")
        except (RuntimeError, ValueError) as exc:
            raise _failure(
                "source_root_invalid",
                source.relative_to(source_root).as_posix(),
            ) from exc
    target_root.mkdir(mode=0o700)

    def ignored(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in _IGNORED_DIRECTORIES or name in _IGNORED_FILES
        }

    app = target_root / "quwoquan_app"
    shutil.copytree(app_source, app, symlinks=True, ignore=ignored)
    service_target = target_root / service_relative
    service_target.parent.mkdir(parents=True)
    shutil.copytree(
        service_source,
        service_target,
        symlinks=True,
        ignore=ignored,
    )

    for relative, sealed in seal.files:
        if relative.startswith("quwoquan_app/"):
            actual = _read_projection_file(
                target_root / relative,
                label=f"copied App launch generated closure {relative}",
                scope="target",
                detail=relative,
            )
            if actual != sealed:
                raise _failure("closure_drift", relative)
            continue
        write_fresh_relative_file(
            root=target_root,
            relative=relative,
            content=sealed[0],
            mode=sealed[1],
        )

    _assert_no_link_escape(target_root)
    _assert_projection_closure(target_root, seal)
    _assert_source_closure(source_root, seal)
    return app
