"""Cursor API key 单一真相源 + auth 错误分流（无人托管长跑必需）。

无人托管长跑期间 Cursor API key 会被定期轮换。仓库只接受仓外、权限受限的
`~/.config/quwoquan/cursor_api_key`；不接受把 key 作为持久环境配置、命令参数或运行产物。
`QWQ_CURSOR_API_KEY_FILE` 仅用于受控测试或显式替换该文件位置。

本模块提供两件事，专治该脆弱点：

- `resolve_cursor_api_key()`：每次 agent 调用前从**单一真相源**动态读取最新 key
  （默认 `~/.config/quwoquan/cursor_api_key`），只把值返回给 SDK 的显式
  `AgentOptions.api_key`，绝不回写 `CURSOR_API_KEY`。文件按行解析，`#` 注释行与空行
  被跳过，只有首个有效行是现行 key，因此轮换可以把旧 key 注释留档而不污染凭据。
  运营/daemon
  轮换时只需原子更新该文件，无需重启长进程。
- `is_cursor_auth_error()`：把 401/403/unauthorized/invalid api key/plan_required 等
  **凭据类**失败与 bridge 瞬时噪声分流。凭据失效不应计入 retryable bridge 预算，而应触发
  一次 key reload + bridge 重建；reload 后仍失败才上报"凭据失效"（区别于内容失败与噪声）。
"""
from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

CURSOR_API_KEY_ENV = "CURSOR_API_KEY"
CURSOR_API_KEY_FILE_ENV = "QWQ_CURSOR_API_KEY_FILE"
CURSOR_API_KEY_FD_ENV = "QWQ_CURSOR_API_KEY_FD"
DEFAULT_CURSOR_API_KEY_FILE = Path.home() / ".config" / "quwoquan" / "cursor_api_key"
CURSOR_SENSITIVE_PROCESS_ENV_KEYS = frozenset(
    {
        CURSOR_API_KEY_ENV,
        CURSOR_API_KEY_FD_ENV,
        "CURSOR_SDK_BRIDGE_TOKEN",
        "CURSOR_SDK_BRIDGE_AUTH_TOKEN",
        "CURSOR_SDK_STORE_CALLBACK_AUTH_TOKEN",
        "CURSOR_SDK_STORE_CALLBACK_URL",
        "CURSOR_SDK_TOOL_CALLBACK_AUTH_TOKEN",
        "CURSOR_SDK_TOOL_CALLBACK_URL",
    }
)

# 明确的凭据失效信号。刻意避免裸 "auth" 子串，以免误判 bridge 的
# "tool-callback-auth-token" argv 噪声（那是 retryable bridge 启动问题，不是凭据失效）。
_AUTH_MESSAGE_MARKERS = (
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "api key is invalid",
    "api key expired",
    "expired api key",
    "invalid credentials",
    "authentication failed",
    "plan_required",
    "plan required",
    "forbidden",
    "token expired",
    "credential invalid",
)
_AUTH_CODE_MARKERS = (
    "unauthenticated",
    "unauthorized",
    "permission_denied",
    "plan_required",
    "forbidden",
    "invalid_api_key",
    "invalid_token",
)


def cursor_api_key_file() -> Path:
    """Return the external key-file path without reading or caching its content."""
    raw = str(os.environ.get(CURSOR_API_KEY_FILE_ENV) or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_CURSOR_API_KEY_FILE


def parse_cursor_api_key(content: str) -> str | None:
    """Return the first active key line from a key-file body.

    Rotation keeps superseded keys in the file behind ``#`` so the previous value
    stays auditable; only the first non-blank, non-comment line is the live key.
    """
    for line in str(content or "").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        return candidate
    return None


def redact_cursor_api_key(value: object, *, api_key: str | None = None) -> str:
    """Redact the actually resolved key, regardless of its provider-specific shape."""
    text = str(value or "")
    if api_key:
        text = text.replace(api_key, "<redacted-cursor-key>")
    return text


def cursor_key_file_issues() -> list[str]:
    """Return redacted contract failures for the sole supported credential source."""
    key_file = cursor_api_key_file()
    try:
        stat = key_file.stat()
    except OSError:
        return ["cursor API key file missing or unreadable"]
    if not key_file.is_file():
        return ["cursor API key file is not a regular file"]
    if stat.st_mode & 0o077:
        return ["cursor API key file permissions must be 0600 or stricter"]
    try:
        content = key_file.read_text(encoding="utf-8")
    except OSError:
        return ["cursor API key file missing or unreadable"]
    if not content.strip():
        return ["cursor API key file is empty"]
    if parse_cursor_api_key(content) is None:
        return ["cursor API key file has no active key line (all lines are comments)"]
    return []


def resolve_cursor_api_key(*, refresh: bool = True) -> str | None:
    """Resolve the freshest Cursor API key from the single source of truth.

    Only the key file is accepted.  The legacy environment variable is neither
    read nor populated: nested bridge processes must receive no credential and
    all SDK calls pass this return value explicitly.
    """
    del refresh  # Kept for source compatibility; key-file reads are never cached.
    os.environ.pop(CURSOR_API_KEY_ENV, None)
    key_file = cursor_api_key_file()
    if cursor_key_file_issues():
        return None
    try:
        file_key = parse_cursor_api_key(key_file.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not file_key:
        return None
    return file_key


@contextmanager
def protected_cursor_api_key_fd(api_key: str) -> Iterator[int]:
    """Expose one credential to one child through a short-lived anonymous pipe.

    The value never enters argv, stdin, an environment value, a generated
    script, or a filesystem artifact. ``pass_fds`` grants the selected child
    the read end; the child must read and close it before launching the SDK
    bridge so descendants cannot inherit the capability.
    """
    if not api_key:
        raise ValueError("Cursor API key is required for protected FD transport")
    read_fd, write_fd = os.pipe()
    try:
        payload = f"{api_key}\n".encode()
        with os.fdopen(write_fd, "wb", closefd=True) as handle:
            write_fd = -1
            handle.write(payload)
            handle.flush()
        yield read_fd
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        try:
            os.close(read_fd)
        except OSError:
            pass


def cursor_credential_subprocess_env(
    base: Mapping[str, str], *, credential_fd: int
) -> dict[str, str]:
    """Return a scrubbed child environment containing only the FD capability."""
    if credential_fd < 0:
        raise ValueError("Cursor credential FD must be non-negative")
    env = cursor_safe_subprocess_env(base)
    env[CURSOR_API_KEY_FD_ENV] = str(credential_fd)
    return env


def cursor_safe_subprocess_env(base: Mapping[str, str]) -> dict[str, str]:
    """Copy process configuration while excluding every Cursor secret channel.

    The external key-file *path* remains available so a runtime child can resolve
    the canonical 0600 file itself. Credential values, inherited FD capabilities,
    bridge bearer tokens and callback credentials never cross that boundary.
    """

    return {
        str(name): str(value)
        for name, value in base.items()
        if str(name) not in CURSOR_SENSITIVE_PROCESS_ENV_KEYS
    }


def is_cursor_auth_error(
    message: str | None,
    *,
    code: str | None = None,
    status: object = None,
) -> bool:
    """Classify a Cursor failure as a credential/authorization failure.

    Auth failures (rotated/expired/invalid key, plan_required, 401/403) must be
    handled by reloading the key and rebuilding the bridge, never counted as a
    retryable bridge-noise failure that silently burns the infra retry budget.
    """
    lowered = str(message or "").casefold()
    code_lower = str(code or "").casefold()
    try:
        status_int = int(status) if status is not None else 0
    except (TypeError, ValueError):
        status_int = 0
    if status_int in (401, 403):
        return True
    if code_lower and any(code_lower == marker for marker in _AUTH_CODE_MARKERS):
        return True
    return any(marker in lowered for marker in _AUTH_MESSAGE_MARKERS)
