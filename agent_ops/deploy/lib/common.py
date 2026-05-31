from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in shell usage
        raise RuntimeError(
            f"Cannot parse manifest without PyYAML installed: {path}"
        ) from exc
    return yaml.safe_load(text)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        argv,
        cwd=str(cwd or ROOT),
        env=merged_env,
        text=True,
        capture_output=True,
        check=check,
    )


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def artifact_run_dir(
    env_name: str,
    command_name: str,
    *,
    target: str = "local",
    output_root: Path | None = None,
) -> Path:
    root = output_root or (ROOT / "artifacts" / "stackctl")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return root / env_name / f"{stamp}-{command_name}-{target}"
