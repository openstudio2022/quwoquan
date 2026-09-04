"""user-zsh 激活投影、回退与状态判定。"""

from __future__ import annotations

import hashlib
import os
import shlex
import stat
from collections import namedtuple
from pathlib import Path
from typing import Any, Callable


UserZshActivationContext = namedtuple(
    "UserZshActivationContext",
    (
        "config_relative_path",
        "config_marker",
        "source_begin",
        "source_end",
        "prefix_newline_marker",
        "carrier_path",
        "entrypoint_digest_keys",
        "identity_environment_entries",
        "required_workspace_entrypoint_binding",
        "workspace_entrypoint_binding",
        "resolved_bindings",
        "resolved_sdk_binding",
        "resolved_cocoapods_binding",
        "resolved_python_binding",
        "private_atomic_write",
        "resolution_error_types",
    ),
)


def literal_existing_home(home_path: Path) -> Path:
    if not home_path.is_absolute():
        raise SystemExit("GATE_BLOCK: user-zsh home path must be absolute")
    home_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if home_path.is_symlink():
        raise SystemExit("GATE_BLOCK: user-zsh home path must not be a symlink")
    try:
        return home_path.resolve(strict=True)
    except OSError as error:
        raise SystemExit("GATE_BLOCK: user-zsh home path is unavailable") from error


def user_zsh_paths(
    *,
    home_path: Path,
    config_relative_path: Path,
    config_path: Path | None = None,
    zshrc_path: Path | None = None,
    zprofile_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    home = literal_existing_home(home_path)
    generated = config_path or home / config_relative_path
    zshrc = zshrc_path or home / ".zshrc"
    zprofile = zprofile_path or home / ".zprofile"
    for candidate, field in (
        (generated, "config"),
        (zshrc, "zshrc"),
        (zprofile, "zprofile"),
    ):
        if not candidate.is_absolute():
            raise SystemExit(f"GATE_BLOCK: user-zsh {field} path must be absolute")
    return generated, zshrc, zprofile


def generated_user_zsh_projection(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
    entrypoint_binding: dict[str, str],
    *,
    context: UserZshActivationContext,
) -> bytes:
    carrier = context.carrier_path.resolve(strict=True)
    body_lines = [
        f"export {key}={shlex.quote(value)}"
        for key, value in context.identity_environment_entries(
            sdk_binding,
            cocoapods_binding,
            python_binding,
            entrypoint_binding,
        )
    ]
    body_lines.append(f"builtin source {shlex.quote(str(carrier))}")
    body = ("\n".join(body_lines) + "\n").encode("utf-8")
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    return f"{context.config_marker} {digest}\n".encode("utf-8") + body


def user_zsh_projection_is_recognized(content: bytes, *, config_marker: str) -> bool:
    first_line = content.partition(b"\n")[0]
    return first_line.startswith((config_marker + " ").encode("utf-8"))


def user_zsh_block(
    config_path: Path,
    *,
    inserted_prefix_newline: bool,
    source_begin: str,
    source_end: str,
    prefix_newline_marker: str,
) -> bytes:
    quoted = shlex.quote(str(config_path))
    newline_mode = "inserted" if inserted_prefix_newline else "preserved"
    return (
        f"{source_begin}\n"
        f"{prefix_newline_marker} {newline_mode}\n"
        f"[[ -r {quoted} ]] && builtin source {quoted}\n"
        f"{source_end}\n"
    ).encode("utf-8")


def strip_user_zsh_block(
    original: bytes,
    *,
    path: Path,
    source_begin: str,
    source_end: str,
    prefix_newline_marker: str,
) -> bytes:
    """移除 managed block（含 legacy 形态），按记录的前缀换行逐字回退。"""
    begin = source_begin.encode("utf-8")
    end = source_end.encode("utf-8")
    if begin not in original and end not in original:
        return original
    if original.count(begin) != 1 or original.count(end) != 1:
        raise SystemExit(
            f"GATE_BLOCK: user-zsh managed block markers are malformed in {path}"
        )
    block_start = original.index(begin)
    try:
        block_end = original.index(end, block_start) + len(end)
    except ValueError as error:
        raise SystemExit(
            f"GATE_BLOCK: user-zsh managed block markers are malformed in {path}"
        ) from error
    if original[block_end : block_end + 1] == b"\n":
        block_end += 1
    segment = original[block_start:block_end]
    inserted_marker = f"{prefix_newline_marker} inserted".encode("utf-8")
    if inserted_marker in segment and original[block_start - 1 : block_start] == b"\n":
        block_start -= 1
    return original[:block_start] + original[block_end:]


def with_user_zsh_block(
    original: bytes,
    *,
    config_path: Path,
    path: Path,
    source_begin: str,
    source_end: str,
    prefix_newline_marker: str,
) -> bytes:
    base = strip_user_zsh_block(
        original,
        path=path,
        source_begin=source_begin,
        source_end=source_end,
        prefix_newline_marker=prefix_newline_marker,
    )
    inserted = bool(base and not base.endswith(b"\n"))
    prefix = b"\n" if inserted else b""
    return base + prefix + user_zsh_block(
        config_path,
        inserted_prefix_newline=inserted,
        source_begin=source_begin,
        source_end=source_end,
        prefix_newline_marker=prefix_newline_marker,
    )


def _paths(
    context: UserZshActivationContext,
    *,
    home_path: Path,
    config_path: Path | None,
    zshrc_path: Path | None,
    zprofile_path: Path | None,
) -> tuple[Path, Path, Path]:
    return user_zsh_paths(
        home_path=home_path,
        config_relative_path=context.config_relative_path,
        config_path=config_path,
        zshrc_path=zshrc_path,
        zprofile_path=zprofile_path,
    )


def _strip(original: bytes, *, path: Path, context: UserZshActivationContext) -> bytes:
    return strip_user_zsh_block(
        original,
        path=path,
        source_begin=context.source_begin,
        source_end=context.source_end,
        prefix_newline_marker=context.prefix_newline_marker,
    )


def _with(
    original: bytes,
    *,
    config_path: Path,
    path: Path,
    context: UserZshActivationContext,
) -> bytes:
    return with_user_zsh_block(
        original,
        config_path=config_path,
        path=path,
        source_begin=context.source_begin,
        source_end=context.source_end,
        prefix_newline_marker=context.prefix_newline_marker,
    )


def activate_user_zsh(
    *,
    context: UserZshActivationContext,
    home_path: Path,
    environ: dict[str, str] | None = None,
    config_path: Path | None = None,
    zshrc_path: Path | None = None,
    zprofile_path: Path | None = None,
) -> str:
    entrypoint_binding = context.required_workspace_entrypoint_binding()
    generated, zshrc, zprofile = _paths(
        context,
        home_path=home_path,
        config_path=config_path,
        zshrc_path=zshrc_path,
        zprofile_path=zprofile_path,
    )
    env = dict(os.environ if environ is None else environ)
    sdk_binding, cocoapods_binding, python_binding = context.resolved_bindings(env)
    expected_generated = generated_user_zsh_projection(
        sdk_binding,
        cocoapods_binding,
        python_binding,
        entrypoint_binding,
        context=context,
    )
    if generated.exists():
        metadata = generated.lstat()
        if not stat.S_ISREG(metadata.st_mode) or generated.is_symlink():
            raise SystemExit("GATE_BLOCK: user-zsh generated projection is not regular")
        if not user_zsh_projection_is_recognized(
            generated.read_bytes(), config_marker=context.config_marker
        ):
            raise SystemExit(
                "GATE_BLOCK: refusing to replace foreign user-zsh projection"
            )
    originals = {
        zshrc: zshrc.read_bytes() if zshrc.exists() else b"",
        zprofile: zprofile.read_bytes() if zprofile.exists() else b"",
    }
    updates = {
        zshrc: _with(
            originals[zshrc], config_path=generated, path=zshrc, context=context
        ),
        # 新契约只在 zshrc 维护单个 managed block；zprofile 里的 legacy 块被回收。
        zprofile: _strip(originals[zprofile], path=zprofile, context=context),
    }
    generated_missing = not generated.exists()
    changed = generated_missing or generated.read_bytes() != expected_generated
    changed = changed or any(updates[path] != originals[path] for path in originals)
    if not changed:
        return "unchanged"
    context.private_atomic_write(
        generated, expected_generated, mode=0o600, private_parent=True
    )
    for startup in (zshrc, zprofile):
        if updates[startup] != originals[startup]:
            context.private_atomic_write(startup, updates[startup])
    return "activated" if generated_missing else "refreshed"


def deactivate_user_zsh(
    *,
    context: UserZshActivationContext,
    home_path: Path,
    config_path: Path | None = None,
    zshrc_path: Path | None = None,
    zprofile_path: Path | None = None,
) -> str:
    generated, zshrc, zprofile = _paths(
        context,
        home_path=home_path,
        config_path=config_path,
        zshrc_path=zshrc_path,
        zprofile_path=zprofile_path,
    )
    originals = {
        zshrc: zshrc.read_bytes() if zshrc.exists() else b"",
        zprofile: zprofile.read_bytes() if zprofile.exists() else b"",
    }
    updates = {
        zshrc: _strip(originals[zshrc], path=zshrc, context=context),
        zprofile: _strip(originals[zprofile], path=zprofile, context=context),
    }
    generated_present = generated.exists()
    if generated_present:
        metadata = generated.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or generated.is_symlink()
            or not user_zsh_projection_is_recognized(
                generated.read_bytes(), config_marker=context.config_marker
            )
        ):
            raise SystemExit("GATE_BLOCK: refusing to delete foreign user-zsh projection")
    changed = generated_present or any(
        updates[path] != originals[path] for path in originals
    )
    if not changed:
        return "unchanged"
    for startup in (zshrc, zprofile):
        if updates[startup] != originals[startup]:
            context.private_atomic_write(startup, updates[startup])
    if generated_present:
        generated.unlink()
    return "deactivated"


def user_zsh_status(
    *,
    context: UserZshActivationContext,
    home_path: Path,
    environ: dict[str, str] | None = None,
    config_path: Path | None = None,
    zshrc_path: Path | None = None,
    zprofile_path: Path | None = None,
) -> dict[str, Any]:
    generated, zshrc, zprofile = _paths(
        context,
        home_path=home_path,
        config_path=config_path,
        zshrc_path=zshrc_path,
        zprofile_path=zprofile_path,
    )
    env = dict(os.environ if environ is None else environ)
    expected_generated: bytes | None = None
    resolution_error = ""
    try:
        expected_generated = generated_user_zsh_projection(
            context.resolved_sdk_binding(env),
            context.resolved_cocoapods_binding(env),
            context.resolved_python_binding(env),
            context.workspace_entrypoint_binding(),
            context=context,
        )
    except context.resolution_error_types as error:
        resolution_error = str(error)

    if not generated.exists():
        generated_state = "missing"
    elif expected_generated is None:
        generated_state = "unverifiable"
    else:
        generated_state = (
            "active" if generated.read_bytes() == expected_generated else "drifted"
        )

    zshrc_bytes = zshrc.read_bytes() if zshrc.exists() else b""
    if (
        context.source_begin.encode("utf-8") not in zshrc_bytes
        and context.source_end.encode("utf-8") not in zshrc_bytes
    ):
        zshrc_state = "missing"
    else:
        try:
            zshrc_state = (
                "active"
                if _with(
                    zshrc_bytes,
                    config_path=generated,
                    path=zshrc,
                    context=context,
                )
                == zshrc_bytes
                else "drifted"
            )
        except SystemExit:
            zshrc_state = "drifted"

    zprofile_bytes = zprofile.read_bytes() if zprofile.exists() else b""
    legacy_zprofile_block = (
        context.source_begin.encode("utf-8") in zprofile_bytes
        or context.source_end.encode("utf-8") in zprofile_bytes
    )

    if (
        generated_state == "active"
        and zshrc_state == "active"
        and not legacy_zprofile_block
    ):
        projection_state = "active"
    elif (
        generated_state == "missing"
        and zshrc_state == "missing"
        and not legacy_zprofile_block
    ):
        projection_state = "inactive"
    else:
        projection_state = "drifted"
    stored_entrypoint_digests: dict[str, str] = {}
    if generated.exists():
        try:
            generated_text = generated.read_text(encoding="utf-8")
        except OSError:
            generated_text = ""
        for line in generated_text.splitlines():
            for key in context.entrypoint_digest_keys:
                prefix = f"export {key}="
                if not line.startswith(prefix):
                    continue
                try:
                    assignment = shlex.split(line[len("export ") :], posix=True)
                except ValueError:
                    continue
                if len(assignment) == 1 and "=" in assignment[0]:
                    stored_entrypoint_digests[key] = assignment[0].split("=", 1)[1]
    payload = {
        "projectionState": projection_state,
        "generatedProjectionState": generated_state,
        "zshrcBlockState": zshrc_state,
        "workspaceEntrypointState": (
            "active"
            if generated_state == "active"
            else "missing"
            if generated_state == "missing"
            else "drifted"
        ),
        "workspaceEntrypointDigests": stored_entrypoint_digests,
        "legacyZprofileBlockPresent": "present" if legacy_zprofile_block else "absent",
    }
    if resolution_error:
        payload["resolutionError"] = resolution_error
    return payload
