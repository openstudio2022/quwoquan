"""`task freeze-homepage-media`：`1.download` 的对象级处置收口命令。

冻结是该阶段的显式交付动作，不是 verify 的副作用——verify 只读。宿主在全部来源
单元就位后对整个 execution 跑一次，随后 `verify homepage-media-decision` 才有可判
定的输入（[`DEC-029`](../../../../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-029)）。

写入 create-once：重跑得到同一结论是幂等，得到不同结论说明有第二个决策点，命令
以退出码 2 拒绝而不是覆盖已冻结的结论。
"""

from __future__ import annotations

import argparse
import sys


def _handle_freeze_homepage_media(args: argparse.Namespace) -> None:
    from content.execution.runtime_state import write_execution_runtime_state
    from content.execution.store import load_spec
    from content.homepage.homepage_media_freeze import (
        freeze_homepage_media_dispositions,
    )
    from governance.coverage.entity_extract import require_domain_etype

    execution_id = str(args.execution_id).strip()
    # `assetId` 由 execution sequence 与 asset registry 共同定址，所以本命令与其他
    # 阶段命令一样先绑定运行态，而不是假设某个上游进程已经绑好。
    write_execution_runtime_state(execution_id, command="homepage")
    spec = load_spec(execution_id)
    targets = ((spec.get("scope") or {}).get("coverageTargets")) or []
    frozen = 0
    for target in targets:
        name = str(target.get("name") or "").strip()
        entity_type = str(target.get("entityType") or "").strip()
        if not name or not entity_type:
            continue
        domain, etype = require_domain_etype(
            entity_type,
            context=f"homepage media freeze for execution={execution_id}",
        )
        try:
            payload = freeze_homepage_media_dispositions(
                execution_id, domain, etype, name
            )
        except (OSError, ValueError) as exc:
            print(f"freeze-homepage-media rejected: {name}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        if payload:
            frozen += 1
            print(f"{name}: {len(payload.get('assets') or [])} dispositions frozen")
        else:
            print(f"{name}: no base draft yet; nothing to freeze")
    print(f"frozen {frozen}/{len(targets)} homepage object(s)")


def register_freeze_homepage_media_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "freeze-homepage-media",
        help="1.download 收口：一次冻结 homepage 逐图处置与 assetId（create-once）",
    )
    parser.add_argument("--execution-id", required=True)
    parser.set_defaults(handler=_handle_freeze_homepage_media)


__all__ = ["register_freeze_homepage_media_parser"]
