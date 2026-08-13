"""同步结果的终端输出与 `.qwq_output` 一次性运行报告。"""

from __future__ import annotations

import json
from pathlib import Path

from .models import SyncReport


def render_report(report: SyncReport, *, write: bool) -> str:
    lines = [
        "[page-object-source-path] "
        f"pages={report.total_pages} drift={report.drift_total} "
        f"fixed={len(report.fixes)} manual={len(report.manual)} "
        f"review={len(report.review)} written={'yes' if report.changed else 'no'}"
    ]
    for fix in report.fixes:
        verb = "FIXED" if write else "WOULD-FIX"
        lines.append(f"  {verb} {fix.page_id}.{fix.field_name} [{fix.method}]")
        lines.append(f"        {fix.old_path}")
        lines.append(f"     -> {fix.new_path}")
    for item in report.manual:
        lines.append(f"  MANUAL {item.page_id}.{item.field_name}")
        lines.append(f"        {item.field_name}={item.old_path}")
        lines.append(f"        {item.reason}")
        for candidate in item.candidates:
            lines.append(f"        candidate: {candidate}")
    for item in report.review:
        lines.append(f"  REVIEW [{item.kind}] {item.page_id}")
        lines.append(f"        source_path={item.source_path}")
        lines.append(f"        {item.detail}")
    return "\n".join(lines)


def render_markdown_report(payload: dict) -> str:
    lines = [
        "# page_object_contract 路径同步运行报告",
        "",
        "一次性运行输出，可删除可重建；页面集合真相仍是磁盘扫描与 "
        "`page_object_contract.yaml`，本文件不是台账。",
        "",
        f"- 扫描时点：`{payload['scanAt']}`",
        f"- HEAD：`{payload['headCommit']}`",
        f"- 契约登记页面：{payload['sync']['totalPages']}",
        f"- 本轮 drift：{payload['sync']['driftTotal']}"
        f"（已修 {len(payload['sync']['fixes'])}，"
        f"待人工裁决 {len(payload['sync']['manual'])}）",
        f"- 契约是否被写入：{'是' if payload['sync']['changed'] else '否'}",
        "",
    ]
    if payload["sync"]["fixes"]:
        lines += ["## 已同步", ""]
        for item in payload["sync"]["fixes"]:
            lines.append(
                f"- `{item['pageId']}`.{item['field']} [{item['method']}]："
                f"`{item['oldPath']}` -> `{item['newPath']}`"
            )
        lines.append("")
    if payload["sync"]["manual"]:
        lines += ["## 需人工裁决（无法唯一定位）", ""]
        for item in payload["sync"]["manual"]:
            lines.append(f"- `{item['pageId']}`.{item['field']}：{item['reason']}")
            for candidate in item["candidates"]:
                lines.append(f"  - 候选：`{candidate}`")
        lines.append("")
    if payload["sync"]["review"]:
        lines += ["## 需人工裁决（伴生风险）", ""]
        for item in payload["sync"]["review"]:
            lines.append(
                f"- [{item['kind']}] `{item['pageId']}`（`{item['sourcePath']}`）："
                f"{item['detail']}"
            )
        lines.append("")
    gate = payload.get("gate")
    if gate:
        lines += ["## 页面横向质量门禁", ""]
        for entry in gate["gates"]:
            lines.append(f"### `{entry['script']}` exit={entry['exitCode']}")
            lines.append("")
            for bucket, messages in sorted(entry["failuresByClass"].items()):
                lines.append(
                    f"- **{bucket}**（{gate['classes'].get(bucket, '未归类')}）："
                    f"{len(messages)} 条"
                )
                for message in messages:
                    lines.append(f"  - {message}")
            if not entry["failuresByClass"]:
                lines.append("- 无失败项")
            lines.append("")
    return "\n".join(lines) + "\n"


def write_run_report(report_dir: Path, payload: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (report_dir / "report.md").write_text(
        render_markdown_report(payload), encoding="utf-8"
    )
    return report_dir
