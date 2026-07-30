from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import write_run_manifest
from quwoquan_ops.cli.lib.output_paths import (
    output_root,
    run_evidence_dir,
    safe_segment,
)


@dataclass(frozen=True)
class LocalRunPaths:
    env: str
    target: str
    run_id: str
    run_root: Path
    observability_root: Path


def resolve_local_run(
    *,
    env: str,
    target: str,
    action: str,
    root: Path | None = None,
    explicit_run_root: str = "",
    explicit_observability_root: str = "",
) -> LocalRunPaths:
    base = root or output_root()
    state_dir = base / "env" / env / "local" / target / "process"
    state_path = state_dir / "local_run.json"
    saved = _read_state(state_path)
    explicit_observability = _resolve_explicit(explicit_observability_root)
    explicit_run = _resolve_explicit(explicit_run_root)
    if explicit_observability is not None:
        run_id = safe_segment(explicit_observability.name, fallback="local-run")
    elif action == "up":
        run_id = run_evidence_dir(base, "up", target).name
    else:
        run_id = safe_segment(str(saved.get("runId") or ""), fallback=f"local-{target}")
    run_root = explicit_run or base / "env" / env / "runs" / run_id
    observability_root = (
        explicit_observability
        or base / "env" / env / "observability" / run_id
    )
    paths = LocalRunPaths(
        env=env,
        target=target,
        run_id=run_id,
        run_root=run_root,
        observability_root=observability_root,
    )
    _materialize(paths, state_path=state_path, action=action)
    return paths


def _resolve_explicit(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _read_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _materialize(paths: LocalRunPaths, *, state_path: Path, action: str) -> None:
    paths.run_root.mkdir(parents=True, exist_ok=True)
    paths.observability_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        paths.observability_root,
        env_name=paths.env,
        run_id=paths.run_id,
        command=f"local {action}",
        target=paths.target,
        report_dir=paths.run_root,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "env": paths.env,
                "target": paths.target,
                "runId": paths.run_id,
                "runRoot": str(paths.run_root),
                "observabilityRoot": str(paths.observability_root),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def shell_exports(paths: LocalRunPaths) -> str:
    values = {
        "QWQ_LOCAL_RUN_ID": paths.run_id,
        "QWQ_RUN_ROOT": str(paths.run_root),
        "QWQ_OBSERVABILITY_RUN_ROOT": str(paths.observability_root),
    }
    return "\n".join(
        f"export {name}={shlex.quote(value)}" for name, value in values.items()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--action", choices=("up", "down", "status"), required=True)
    parser.add_argument("--output-root", default=os.environ.get("QWQ_OUTPUT_ROOT", ""))
    parser.add_argument("--run-root", default=os.environ.get("QWQ_RUN_ROOT", ""))
    parser.add_argument(
        "--observability-root",
        default=os.environ.get("QWQ_OBSERVABILITY_RUN_ROOT", ""),
    )
    args = parser.parse_args(argv)
    root = Path(args.output_root).expanduser() if args.output_root else None
    paths = resolve_local_run(
        env=args.env,
        target=args.target,
        action=args.action,
        root=root,
        explicit_run_root=args.run_root,
        explicit_observability_root=args.observability_root,
    )
    print(shell_exports(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
