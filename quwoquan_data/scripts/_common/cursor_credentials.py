"""Cursor API key 单一真相源 + auth 错误分流（无人托管长跑必需）。

无人托管长跑期间 Cursor API key 会被定期轮换。runner 在进程启动时 `export CURSOR_API_KEY`
后，正在运行的长进程 `os.environ` 在其生命周期内是冻结的：轮换后旧 key 失效，但进程不会
读到新值，导致后续 `Agent.prompt` 全部以旧 key 失败，且失败表象像 bridge 噪声，被当作
retryable 反复重试耗尽 infra 预算后硬停。

本模块提供两件事，专治该脆弱点：

- `resolve_cursor_api_key()`：每次 agent 调用前从**单一真相源**动态读取最新 key
  （`QWQ_CURSOR_API_KEY_FILE` 指向的 key 文件优先，env 仅 fallback），并把读到的最新值
  回写 `os.environ["CURSOR_API_KEY"]`，使随后新启动的 bridge 子进程继承新 key。运营/daemon
  轮换时只需原子更新该文件，无需重启长进程。
- `is_cursor_auth_error()`：把 401/403/unauthorized/invalid api key/plan_required 等
  **凭据类**失败与 bridge 瞬时噪声分流。凭据失效不应计入 retryable bridge 预算，而应触发
  一次 key reload + bridge 重建；reload 后仍失败才上报"凭据失效"（区别于内容失败与噪声）。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

CURSOR_API_KEY_ENV = "CURSOR_API_KEY"
CURSOR_API_KEY_FILE_ENV = "QWQ_CURSOR_API_KEY_FILE"
CURSOR_CLOUD_API_ME_URL = "https://api.cursor.com/v1/me"

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


def cursor_api_key_file() -> Path | None:
    """Single-source key file path (`QWQ_CURSOR_API_KEY_FILE`), if configured."""
    raw = str(os.environ.get(CURSOR_API_KEY_FILE_ENV) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_cursor_api_key(*, refresh: bool = True) -> str | None:
    """Resolve the freshest Cursor API key from the single source of truth.

    Precedence: key file (`QWQ_CURSOR_API_KEY_FILE`) > `CURSOR_API_KEY` env.
    When a key file value is found it is written back into `os.environ` so any
    bridge subprocess launched afterwards inherits the rotated key. Pass
    ``refresh=False`` to skip the file read and only consult the cached env.
    """
    env_key = str(os.environ.get(CURSOR_API_KEY_ENV) or "").strip()
    if not refresh:
        return env_key or None
    key_file = cursor_api_key_file()
    if key_file is not None:
        try:
            file_key = key_file.read_text(encoding="utf-8").strip()
        except OSError:
            file_key = ""
        if file_key:
            if file_key != env_key:
                os.environ[CURSOR_API_KEY_ENV] = file_key
            return file_key
    return env_key or None


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


def probe_cursor_key_ready(*, timeout_seconds: float = 20.0) -> bool:
    """探测当前单一真相源 key 是否已恢复可用（HTTP 200 on /v1/me）。

    key 生命周期内置能力（替代家目录守护脚本）：403/limit 暂停后由调用方
    轮询本函数；keyfile 被运营原子轮换出新 key 时立即返回 True，长跑进程
    据此自动续跑。探测失败（网络/非 200）一律返回 False，由调用方退避。
    """
    key = resolve_cursor_api_key()
    if not key:
        return False
    proc = subprocess.run(
        [
            "curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
            "--max-time", str(max(1, int(timeout_seconds))),
            "-H", f"Authorization: Bearer {key}",
            "-H", "Accept: application/json",
            CURSOR_CLOUD_API_ME_URL,
        ],
        capture_output=True,
        check=False,
    )
    code = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode == 0 and code == "200"
