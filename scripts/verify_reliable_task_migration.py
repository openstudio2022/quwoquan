#!/usr/bin/env python3
"""Check migration guardrails for current private async schedulers.

The guard is advisory by default because the reliable task runtime lands in
slices. Set QWQ_RELIABLE_TASK_MIGRATION_STRICT=1 to block current private
scheduler usage once the replacement is implemented.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CHAT_SCHEDULER = ROOT / "quwoquan_service/services/chat-service/internal/application/group_avatar_recompute_scheduler.go"
CATALOG = ROOT / "deploy/shared/reliable_task_module_catalog.yaml"
CHAT_SERVICE = ROOT / "quwoquan_service/services/chat-service"


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    strict = os.environ.get("QWQ_RELIABLE_TASK_MIGRATION_STRICT") == "1"
    catalog_text = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else ""
    has_reliable_task = "chat.group_avatar.recompute" in catalog_text
    has_current_scheduler = CURRENT_CHAT_SCHEDULER.exists()

    production_current_refs = []
    if has_reliable_task:
        for path in CHAT_SERVICE.rglob("*.go"):
            if path == CURRENT_CHAT_SCHEDULER or path.name.endswith("_test.go"):
                continue
            text = path.read_text(encoding="utf-8")
            if "NewRedisGroupAvatarTaskScheduler(" in text:
                production_current_refs.append(path.relative_to(ROOT).as_posix())

    if has_reliable_task and production_current_refs:
        fail(
            "chat-service still wires current Redis group avatar scheduler in production code: "
            + ", ".join(production_current_refs)
        )

    if has_reliable_task and has_current_scheduler:
        message = (
            "chat-service current group_avatar_recompute_scheduler.go still exists while "
            "chat.group_avatar.recompute is registered in reliable task catalog; "
            "the file is allowed only as a deprecated compatibility adapter and must not be wired by production code"
        )
        if not strict:
            print(f"[verify] WARN: {message}; strict mode disabled")

    print("[verify] OK: reliable task migration guard checked")


if __name__ == "__main__":
    main()
