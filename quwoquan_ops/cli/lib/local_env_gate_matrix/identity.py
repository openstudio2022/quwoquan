"""矩阵常量、运行标识、执行租约与证据路径原语（自原单文件逐字搬移）。"""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

# 测试通过 mock.patch.object(matrix_mod, "output_root") 重定向输出根；
# 这里保持对包属性的延迟访问以兼容 monkeypatch（参考 feature_tree/gitio 模式）。
import quwoquan_ops.cli.lib.local_env_gate_matrix as _matrix_pkg
from quwoquan_ops.cli.lib.local_env_gate_timing import utc_now

# 原文件位于 lib/ 下用 parents[3]；本模块深一层，用 parents[4] 指向仓库根。
ROOT = Path(__file__).resolve().parents[4]
PROFILE_LOCAL_ENV_GATE = "local-env-gate"
DEVICE_PROFILE_FULL = "full"
DEVICE_PROFILE_EMULATOR_ONLY = "emulator_only"
DEVICE_PROFILES = (DEVICE_PROFILE_FULL, DEVICE_PROFILE_EMULATOR_ONLY)
EMULATOR_ONLY_CLAIM = "ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN"
CANONICAL_TARGETS = ("alpha-local", "beta-local", "gamma-local")
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "AppRoot/JNY-001/SCN-004/UAT-009",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
    "runtime/runtime-external-integration/provider-adapter-conformance-suite/GWT-002",
)

EnvRunner = Callable[..., dict[str, Any]]
DataRunner = Callable[..., dict[str, Any]]
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_ATTEMPT_ID = re.compile(r"(?!unknown\b)[A-Za-z0-9][A-Za-z0-9._:-]{5,}")
_PROVIDER_CAPABILITY_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")
_PROVIDER_LAYERS = ("local_contract", "api_integration", "user_acceptance")


def _startup_attempt_matches_package_identity(
    startup_attempt: object,
    *,
    target: str,
    environment: str,
    package_baseline: str,
) -> bool:
    """校验 running receipt 与当前 target package 的完整启动身份绑定。"""

    if not isinstance(startup_attempt, dict):
        return False
    return (
        startup_attempt.get("status") == "running"
        and startup_attempt.get("target") == target
        and startup_attempt.get("env") == environment
        and startup_attempt.get("workload") == "full"
        and startup_attempt.get("candidateDigest") == package_baseline
        and bool(str(startup_attempt.get("composeProject") or "").strip())
        and _SHA256.fullmatch(str(startup_attempt.get("configurationDigest") or ""))
        is not None
        and _SHA256.fullmatch(str(startup_attempt.get("imageTransportTag") or ""))
        is not None
    )


def _new_matrix_run_id() -> str:
    return (
        "matrix-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:12]
    )


def _matrix_lease_path() -> Path:
    path = (
        _matrix_pkg.output_root()
        / "env"
        / "repo"
        / "local"
        / "repo-gate"
        / "process"
        / "local-env-gate.lock"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class MatrixExecutionLeaseBusy(RuntimeError):
    """Another live local environment matrix still owns the repository lease."""


@contextmanager
def _matrix_execution_lease(matrix_run_id: str) -> Iterator[Path]:
    """Bind live matrix exclusion to one process lifetime via an OS lock."""
    path = _matrix_lease_path()
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip()
            detail = owner if owner else "owner metadata unavailable"
            raise MatrixExecutionLeaseBusy(
                f"live local environment matrix lease is already held: {detail}"
            ) from exc

        owner = {
            "schema": "quwoquan_ops.local_env_gate_matrix_lease",
            "status": "active",
            "matrixRunId": matrix_run_id,
            "pid": os.getpid(),
            "startedAt": utc_now(),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        try:
            yield path
        finally:
            released = {
                **owner,
                "status": "released",
                "releasedAt": utc_now(),
            }
            try:
                handle.seek(0)
                handle.truncate()
                json.dump(released, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _repo_matrix_dir(matrix_run_id: str) -> Path:
    path = (
        _matrix_pkg.output_root()
        / "env"
        / "repo"
        / "runs"
        / "local-env-gate"
        / matrix_run_id
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence_path(path: Path) -> str:
    """Keep repo evidence relative while allowing isolated test/output roots."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _namespace(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)
