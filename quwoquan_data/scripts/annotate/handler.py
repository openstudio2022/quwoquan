"""qwq-data annotate — Human-in-loop 标注：在发布前对账本图片/事实/文章下人判定。

队列与裁决都作用于内容对象的 `5.review/review_ledger.json`（materialize 会随 post 拷贝）。

用法：
  # 列出待人工处理队列（fix 态或需人确认项）
  qwq-data annotate --task T --batch B --list

  # 对某项下人判定 + 打分
  qwq-data annotate --task T --batch B --ref R --kind image --target <assetId> --judgment credible --score 4

  # 直接置发布态（人裁定可发布 / 丢弃）
  qwq-data annotate --task T --batch B --ref R --kind image --target <assetId> --override discard

  # 记录一次再加工（低质量重做）
  qwq-data annotate --task T --batch B --ref R --kind article --target R --reprocess
"""
from __future__ import annotations

import argparse
import sys

from _common.review_ledger import (
    JUDGE_CREDIBLE,
    JUDGE_DOUBTFUL,
    KIND_ARTICLE,
    KIND_FACT,
    KIND_IMAGE,
    OVERRIDE_DISCARD,
    OVERRIDE_PUBLISHABLE,
    iter_ledgers,
    load_ledger,
    needs_human,
    reprocess_exhausted,
    resolve_publish_state,
    save_ledger,
)

KINDS = (KIND_IMAGE, KIND_FACT, KIND_ARTICLE)
JUDGMENTS = (JUDGE_CREDIBLE, JUDGE_DOUBTFUL)
OVERRIDES = (OVERRIDE_PUBLISHABLE, OVERRIDE_DISCARD)


def _print_queue(task_id: str, batch_id: str) -> int:
    ledgers = iter_ledgers(task_id, batch_id)
    pending = 0
    for ledger in ledgers:
        rows = []
        for item in ledger.all_items():
            state = resolve_publish_state(item, ledger.policy)
            if needs_human(item, ledger.policy) or state != "publishable":
                exhausted = reprocess_exhausted(item, ledger.policy)
                rows.append(
                    f"    [{item.kind}] {item.target} :: state={state} "
                    f"agent={item.agentJudgment}/{item.agentScore} human={item.humanJudgment}/{item.humanScore} "
                    f"reprocess={item.reprocessCount}{' EXHAUSTED' if exhausted else ''}"
                    + (f" reasons={item.reasons}" if item.reasons else "")
                )
        if rows:
            pending += len(rows)
            print(f"[annotate] {ledger.ref}:")
            for r in rows:
                print(r)
    if pending == 0:
        print("[annotate] queue empty — 无待人工处理项。")
    else:
        print(f"[annotate] {pending} item(s) awaiting human decision.")
    return pending


def handle_annotate(args: argparse.Namespace) -> None:
    task_id = args.task
    batch_id = args.batch

    if args.list:
        _print_queue(task_id, batch_id)
        return

    if not (args.ref and args.kind and args.target):
        print("[annotate] ERROR: 需要 --ref --kind --target（或 --list）", file=sys.stderr)
        raise SystemExit(2)

    ledger = load_ledger(task_id, batch_id, args.ref)
    if ledger is None:
        print(f"[annotate] ERROR: 账本不存在 ref={args.ref}", file=sys.stderr)
        raise SystemExit(1)

    item = ledger.find_item(args.kind, args.target)
    if item is None:
        print(f"[annotate] ERROR: 账本中无此项 kind={args.kind} target={args.target}", file=sys.stderr)
        raise SystemExit(1)

    changed = False
    if args.judgment:
        item.humanJudgment = args.judgment
        changed = True
    if args.score is not None:
        item.humanScore = int(args.score)
        changed = True
    if args.override:
        item.humanOverride = args.override
        changed = True
    if args.reprocess:
        item.reprocessCount += 1
        changed = True
    if args.note:
        item.notes = args.note
        changed = True

    if not changed:
        print("[annotate] ERROR: 未提供任何裁决（--judgment/--score/--override/--reprocess/--note）", file=sys.stderr)
        raise SystemExit(2)

    save_ledger(ledger)
    state = resolve_publish_state(item, ledger.policy)
    print(
        f"[annotate] {args.ref} [{item.kind}] {item.target} -> publishState={state} "
        f"(human={item.humanJudgment}/{item.humanScore} override={item.humanOverride} reprocess={item.reprocessCount})"
    )


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("annotate", help="Human-in-loop 标注：发布前对账本下人判定/打分/置发布态")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--list", action="store_true", help="列出待人工处理队列")
    p.add_argument("--ref", help="账本 ref（post topicId）")
    p.add_argument("--kind", choices=KINDS, help="标注对象类型")
    p.add_argument("--target", help="对象标识：image=assetId / fact=事实串 / article=ref")
    p.add_argument("--judgment", choices=JUDGMENTS, help="人判定：可信/存疑")
    p.add_argument("--score", type=int, choices=[1, 2, 3, 4, 5], help="人打分 1-5")
    p.add_argument("--override", choices=OVERRIDES, help="人直接置发布态：publishable/discard")
    p.add_argument("--reprocess", action="store_true", help="记录一次再加工（低质量重做）")
    p.add_argument("--note", help="备注")
    p.set_defaults(handler=handle_annotate)
