# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005.t4
"""退役经真实命令面走完后 `pool-inspect` 的池健康信号恢复可判定。

证据取在 `cli.py` 进程边界上：parser、发布锁、写侧模块、报告 schema 与退出码全部
是生产件，因此它证明的是「运维实际能敲的那条命令」闭环，而不是模块直调闭环。

池本身在测试隔离根内自建：仓内 canonical 池是共享受版本控制真相源，`tests/conftest.py`
的落盘隔离契约禁止任何测试进程读写它。针对真实历史对象的同一断言只能在隔离根之外
人工执行，其真实输出作为交付证据单独给出，不伪装成本文件的自动化结论。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = Path(__file__).resolve().parents[3]
for _path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical.pool_object_retirement import (  # noqa: E402
    RETIREMENT_RECEIPT_RELATIVE_PATH,
)
from core.control_types import PoolObjectRetirementReason  # noqa: E402
from support.pool_object_retirement_fixture import (  # noqa: E402
    HISTORICAL_GENERATOR,
    HISTORICAL_OBJECT_REF,
    pool_with_one_historical_object,
)

pytestmark = pytest.mark.api_integration

_CLI = DATA_ROOT / "scripts" / "cli.py"
_RETIRED_AT = "2026-08-28T00:00:00Z"
_REASON = PoolObjectRetirementReason.HISTORICAL_GENERATOR_NOT_AGENT.value
_HISTORICAL_CODE = "DATA.POOL.GENERATOR_PROVENANCE_INVALID"


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(_CLI), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=DATA_ROOT.parent,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def _ok(*arguments: str) -> dict[str, object]:
    completed = _cli(*arguments)
    assert completed.returncode == 0, (
        f"{' '.join(arguments)}\n{completed.stdout}\n{completed.stderr}"
    )
    return json.loads(completed.stdout)


def _inspect(publish_root: Path) -> dict[str, object]:
    return _ok(
        "release", "pool-inspect", "--publish-root", str(publish_root), "--details"
    )


def _retire(publish_root: Path, *, apply: bool = True) -> subprocess.CompletedProcess[str]:
    arguments = [
        "release", "pool-object", "retire",
        "--object-type", "content",
        "--object-ref", HISTORICAL_OBJECT_REF,
        "--reason", _REASON,
        "--retired-at", _RETIRED_AT,
        "--publish-root", str(publish_root),
    ]
    if apply:
        arguments.append("--apply")
    return _cli(*arguments)


def test_retired_historical_object_restores_quality_and_eligibility_via_cli(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    historical_root = pool_with_one_historical_object(publish_root)

    before = _inspect(publish_root)
    assert before["checks"]["quality"] == "failed"
    assert before["retired"] == {"objectCount": 0, "objects": []}
    assert [
        row["code"]
        for row in before["issues"]
        if row["ref"] == f"posts/{HISTORICAL_OBJECT_REF}"
    ] == [_HISTORICAL_CODE]

    planned = _cli(
        "release", "pool-object", "retire",
        "--object-type", "content",
        "--object-ref", HISTORICAL_OBJECT_REF,
        "--reason", _REASON,
        "--retired-at", _RETIRED_AT,
        "--publish-root", str(publish_root),
    )
    assert planned.returncode == 0
    assert json.loads(planned.stdout)["result"] == "planned"
    # 省略 --apply 时零写入：计划态不得改变池的任何结论。
    assert not (historical_root / RETIREMENT_RECEIPT_RELATIVE_PATH).exists()
    assert _inspect(publish_root)["checks"] == before["checks"]

    applied = _retire(publish_root)
    assert applied.returncode == 0
    receipt = json.loads(applied.stdout)["receipt"]
    assert receipt["reason"] == _REASON
    assert receipt["inadmissibility"] == {"gate": "quality", "code": _HISTORICAL_CODE}

    after = _inspect(publish_root)

    assert after["checks"]["quality"] == "passed"
    assert after["checks"]["eligibility"] == "passed"
    assert after["retired"] == {
        "objectCount": 1,
        "objects": [
            {
                "objectType": "content",
                "objectRef": f"posts/{HISTORICAL_OBJECT_REF}",
                "reason": _REASON,
            }
        ],
    }
    # 累计计数不变：退役只移除该对象的判否结论，不移动 observed/admitted/publishable、
    # usageScope、环境容量与下一波请求量。
    assert after["supply"] == before["supply"]
    assert after["usageScope"] == before["usageScope"]
    assert after["environmentCapacity"] == before["environmentCapacity"]
    assert after["nextWave"] == before["nextWave"]
    assert after["issues"] == [
        row
        for row in before["issues"]
        if row["ref"] != f"posts/{HISTORICAL_OBJECT_REF}"
    ]
    # 溯源未被伪造：命令只加一份回执，manifest 的历史 generator 原样留在池里。
    manifest = json.loads(
        (historical_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["generator"] == HISTORICAL_GENERATOR


def test_cli_refuses_to_retire_an_admissible_object(tmp_path: Path) -> None:
    """合格对象的退役请求在命令面上也判否：非零退出码 + 零写入。"""

    publish_root = tmp_path / "publish"
    pool_with_one_historical_object(publish_root)
    ready_root = publish_root / "posts/image/ready/1"

    refused = _cli(
        "release", "pool-object", "retire",
        "--object-type", "content",
        "--object-ref", "image/ready/1",
        "--reason", _REASON,
        "--retired-at", _RETIRED_AT,
        "--publish-root", str(publish_root),
        "--apply",
    )

    assert refused.returncode != 0
    assert "DATA.POOL.RETIREMENT_OBJECT_ADMISSIBLE" in refused.stderr
    assert not (ready_root / RETIREMENT_RECEIPT_RELATIVE_PATH).exists()


def test_cli_rejects_reasons_outside_the_closed_set(tmp_path: Path) -> None:
    """闭集在 parser 上就收口：越界 reason 到不了写侧。"""

    publish_root = tmp_path / "publish"
    pool_with_one_historical_object(publish_root)

    rejected = _cli(
        "release", "pool-object", "retire",
        "--object-type", "content",
        "--object-ref", HISTORICAL_OBJECT_REF,
        "--reason", "operator_decision",
        "--retired-at", _RETIRED_AT,
        "--publish-root", str(publish_root),
        "--apply",
    )

    assert rejected.returncode != 0
    assert "invalid choice" in rejected.stderr
