"""Freeze live App inputs and create a private writable test-live projection."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
from quwoquan_ops.cli.lib.package_reuse import (
    materialize_package_input_capsule,
    verify_package_input_capsule,
    workspace_snapshot,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    AppDependencyBundleStaleError,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_fs import remove_private_tree


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--attempt-root", required=True)
    return parser


def _require_real_directory(
    path: Path,
    *,
    error_code: str,
    allow_canonical_alias: bool = False,
) -> Path:
    """Reject explicit symlink nodes except the caller-authorized OS root alias."""

    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(error_code) from error
    if path.is_symlink() or not path.is_dir():
        raise ValueError(error_code)
    if not allow_canonical_alias and resolved != path:
        raise ValueError(error_code)
    return resolved


def _safe_attempt_root(output_root: Path, attempt_root: Path) -> Path:
    output = output_root.expanduser().absolute()
    output.mkdir(parents=True, exist_ok=True)
    resolved_output = _require_real_directory(
        output,
        error_code="APP.LAUNCH.workspace_projection_output_unsafe",
        allow_canonical_alias=True,
    )
    attempt = attempt_root.expanduser().absolute()
    if any(part == ".." for part in attempt_root.expanduser().parts):
        raise ValueError("APP.LAUNCH.workspace_projection_path_unsafe")
    if not attempt.is_relative_to(output) or attempt == output:
        raise ValueError("APP.LAUNCH.workspace_projection_path_unsafe")
    if attempt.exists() or attempt.is_symlink():
        raise ValueError("APP.LAUNCH.workspace_projection_not_fresh")
    attempt.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = _require_real_directory(
        attempt.parent,
        error_code="APP.LAUNCH.workspace_projection_path_unsafe",
        allow_canonical_alias=True,
    )
    if not resolved_parent.is_relative_to(resolved_output):
        raise ValueError("APP.LAUNCH.workspace_projection_path_unsafe")
    attempt.mkdir(mode=0o700)
    resolved_attempt = _require_real_directory(
        attempt,
        error_code="APP.LAUNCH.workspace_projection_path_unsafe",
        allow_canonical_alias=True,
    )
    if not resolved_attempt.is_relative_to(resolved_output):
        raise ValueError("APP.LAUNCH.workspace_projection_path_unsafe")
    return attempt


def _make_writable_projection(root: Path) -> None:
    for path in (root, *sorted(root.rglob("*"))):
        if path.is_symlink():
            continue
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(stat.S_IMODE(metadata.st_mode) | 0o700)
        elif stat.S_ISREG(metadata.st_mode):
            path.chmod(stat.S_IMODE(metadata.st_mode) | 0o600)
        else:
            raise ValueError("APP.LAUNCH.workspace_projection_special_node")


def verify_workspace_launch_projection(
    *,
    output_root: Path,
    projection_root: Path,
    source_capsule_manifest: Path,
) -> dict[str, object]:
    """Prove the fresh projection is an exact writable copy of capsule source."""

    output = output_root.expanduser().absolute()
    projection = projection_root.expanduser().absolute()
    manifest_ref = source_capsule_manifest.expanduser().absolute()
    _require_real_directory(
        output,
        error_code="APP.LAUNCH.workspace_projection_handoff_unsafe",
    )
    if (
        not projection.is_relative_to(output)
        or projection == output
        or projection.is_symlink()
        or not projection.is_dir()
        or manifest_ref.name != "manifest.json"
        or manifest_ref.is_symlink()
        or not manifest_ref.is_file()
        or not manifest_ref.is_relative_to(output)
    ):
        raise ValueError("APP.LAUNCH.workspace_projection_handoff_unsafe")
    _require_real_directory(
        projection,
        error_code="APP.LAUNCH.workspace_projection_handoff_unsafe",
    )
    if manifest_ref.resolve(strict=True) != manifest_ref:
        raise ValueError("APP.LAUNCH.workspace_projection_handoff_unsafe")
    manifest = verify_package_input_capsule(manifest_ref.parent)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise TypeError("APP.LAUNCH.workspace_projection_entries_invalid")
    expected_paths: set[Path] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise TypeError("APP.LAUNCH.workspace_projection_entry_invalid")
        capsule_relative = Path(str(raw.get("capsulePath") or ""))
        if not capsule_relative.parts or capsule_relative.parts[0] != "repo":
            continue
        relative = Path(*capsule_relative.parts[1:])
        if not relative.parts or relative.parts[0] == ".git":
            continue
        source = manifest_ref.parent / capsule_relative
        destination = projection / relative
        expected_paths.add(relative)
        if raw.get("kind") == "file":
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("APP.LAUNCH.workspace_projection_file_kind_drift")
            if destination.read_bytes() != source.read_bytes():
                raise ValueError("APP.LAUNCH.workspace_projection_file_cas_drift")
            expected_executable = int(raw.get("mode") or 0) == 0o555
            if bool(destination.stat().st_mode & 0o111) != expected_executable:
                raise ValueError("APP.LAUNCH.workspace_projection_file_mode_drift")
        elif raw.get("kind") == "symlink":
            if not destination.is_symlink() or os.readlink(destination) != os.readlink(
                source
            ):
                raise ValueError("APP.LAUNCH.workspace_projection_symlink_drift")
        else:
            raise ValueError("APP.LAUNCH.workspace_projection_kind_invalid")
    actual_paths = {
        path.relative_to(projection)
        for path in projection.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_paths != expected_paths:
        raise ValueError("APP.LAUNCH.workspace_projection_undeclared_source")
    return manifest


def prepare_workspace_launch_projection(
    *, output_root: Path, attempt_root: Path
) -> dict[str, str]:
    roots = app_source_capsule_roots()
    attempt = _safe_attempt_root(output_root, attempt_root)
    capsule_root = attempt / "input-capsule"
    projection_root = attempt / "repo"
    complete = False
    try:
        before = workspace_snapshot(deployment_roots=roots)
        capsule = materialize_package_input_capsule(
            roots,
            capsule_root=capsule_root,
        )
        after = workspace_snapshot(deployment_roots=roots)
        if before != after:
            raise ValueError("WORKSPACE.CONCURRENT_WRITER: App source changed during freeze")
        for field in (
            "baselineId",
            "sourceRevision",
            "workspaceStatusDigest",
            "deploymentInputDigest",
            "deploymentInputFileCount",
        ):
            if capsule.get(field) != before.get(field):
                raise ValueError(f"APP.LAUNCH.workspace_projection_{field}_drift")
        verify_package_input_capsule(capsule_root, expected_snapshot=before)
        shutil.copytree(
            capsule_root / "repo",
            projection_root,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        _make_writable_projection(projection_root)
        for required in (
            "quwoquan_app/run.sh",
            "quwoquan_ops/cli/stackctl.py",
        ):
            path = projection_root / required
            if path.is_symlink() or not path.is_file():
                raise ValueError(
                    f"APP.LAUNCH.workspace_projection_required_source_missing: {required}"
                )
        if (projection_root / ".git").exists() or (
            projection_root / ".git"
        ).is_symlink():
            raise ValueError("APP.LAUNCH.workspace_projection_git_leak")
        verify_workspace_launch_projection(
            output_root=output_root,
            projection_root=projection_root,
            source_capsule_manifest=capsule_root / "manifest.json",
        )
        complete = True
        return {
            "projectionRoot": str(projection_root),
            "sourceCapsuleManifest": str(capsule_root / "manifest.json"),
            "sourceRevision": str(capsule["sourceRevision"]),
            "sourceCapsuleDigest": str(capsule["deploymentInputDigest"]),
        }
    finally:
        if not complete and attempt.exists():
            remove_private_tree(attempt)


def _failure_envelope(error: BaseException) -> tuple[dict[str, str], str]:
    """一份失败拆两路：stdout 机器可读 envelope，stderr 人类可读 typed 行。

    成功路径的 stdout 仍是 projection 导出 JSON（无 ``status`` 字段）；失败
    envelope 以 ``"status": "failed"`` 区分，消费方（run.sh）按此判别。
    """

    if isinstance(error, AppDependencyBundleStaleError):
        return (
            {
                "status": "failed",
                "errorCode": error.code,
                "errorField": error.field,
            },
            f"{error.code}: {error}",
        )
    detail = str(error) or type(error).__name__
    if not detail.startswith(("APP.LAUNCH", "WORKSPACE.")):
        detail = f"APP.LAUNCH.workspace_projection_failed: {detail}"
    return (
        {
            "status": "failed",
            "errorCode": detail.split(":", 1)[0].strip(),
        },
        detail,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = prepare_workspace_launch_projection(
            output_root=Path(args.output_root),
            attempt_root=Path(args.attempt_root),
        )
    except (OSError, TypeError, ValueError) as error:
        envelope, detail = _failure_envelope(error)
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
        print(detail, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
