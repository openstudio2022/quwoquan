"""门禁失败分类（只读消费门禁输出，不改门禁）。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .models import APP_DIR_NAME

#: 门禁失败按「谁能修」分类，避免每轮人工重读一遍 flat 列表。
GATE_FAILURE_CLASSES: tuple[tuple[str, str, str], ...] = (
    (
        "page_scan_set_gap",
        r"不在页面扫描集|磁盘页面未登记",
        "页面已在对象树目标位置，但 page_disk_scan_paths 的扫描规则尚未跟随；"
        "属页面质量门禁 owner，不能靠改契约绕过",
    ),
    (
        "contract_path_drift",
        r"source_path 不存在|evidence 不存在|Dart part 不存在",
        "契约路径尚未同步；重跑本工具即可收敛",
    ),
    (
        "contract_reference_drift",
        r"typed_presentation .*不存在|object_id 无 object.yaml 定义"
        r"|Query Slice 引用不存在|route_id 引用不存在|surface 引用不存在"
        r"|capability 未在 PlatformCapabilities 定义",
        "契约引用的类型/对象/路由已被端云改名或删除；需按实际实现裁决后改契约",
    ),
    (
        "owner_or_object_missing",
        r"experience_owner .*佐证|data_owner .*佐证|未列入 data_owners"
        r"|experience_owner 必填|data_owners 必须",
        "页面缺 owner 或对象归属佐证；需业务裁决后补契约",
    ),
    (
        "assembly_evidence_broken",
        r"未装配 entry_widget|未消费 entry_widget|未注册 route"
        r"|没有对应 Surface 覆盖|未定义 entry_widget",
        "页面装配点已改动但契约声明的 entry_widget/route 装配不再成立；"
        "需对应 domain 流确认落位后再同步契约",
    ),
)


def classify_gate_failures(output: str) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = {}
    for line in output.splitlines():
        message = line.strip()
        if not message.startswith("- "):
            continue
        message = message[2:].strip()
        bucket = "unclassified"
        for name, pattern, _ in GATE_FAILURE_CLASSES:
            if re.search(pattern, message):
                bucket = name
                break
        classified.setdefault(bucket, []).append(message)
    return classified


def run_page_quality_gates(repository_root: Path) -> dict:
    """只读跑页面横向质量门禁并分类失败，不修改门禁脚本。"""

    runtime = repository_root / APP_DIR_NAME / "scripts" / "runtime" / "page"
    results: list[dict] = []
    for script, extra in (
        ("verify_page_object_contract.py", ()),
        ("verify_page_abc_governance.py", ("--quiet",)),
    ):
        completed = subprocess.run(
            [sys.executable, str(runtime / script), *extra],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = completed.stdout + completed.stderr
        results.append(
            {
                "script": script,
                "exitCode": completed.returncode,
                "output": output.strip(),
                "failuresByClass": classify_gate_failures(output),
            }
        )
    return {
        "classes": {
            name: description for name, _, description in GATE_FAILURE_CLASSES
        },
        "gates": results,
    }
