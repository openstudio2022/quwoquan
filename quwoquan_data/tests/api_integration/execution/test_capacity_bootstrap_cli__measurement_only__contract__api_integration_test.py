# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t4
"""GWT-019：真实 bootstrap 进程只推进 measurement 状态机。

`t1` 的「不创建 WorkRequest、content execution、author/reviewer、pool-delivery、
canonical object、release 或环境成功事实」与 `t4` 的「零 capacity receipt 可见、
既有内容状态不变」由本文件以真实 CLI 子进程证明：四次命令跑完后 publish 树、
release 树与环境树都不存在，capacity receipt 也不出现。

真实 M100 measurement soak 与 100 次 Provider probe 属于
[`OPEN-006`](../../../../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-006)
的外部资源缺口，本文件不以受控输入替代它。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
CLI = DATA_ROOT / "scripts/cli.py"
DIGEST = "sha256:" + "b" * 64


def _invoke(
    output_root: Path, publish_root: Path, *args: str
) -> dict[str, object]:
    env = dict(os.environ)
    env["QWQ_OUTPUT_ROOT"] = str(output_root)
    env["QWQ_PUBLISH_ROOT"] = str(publish_root)
    result = subprocess.run(
        [sys.executable, "-B", str(CLI), "task", "capacity-bootstrap", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_cli_process_only_advances_bootstrap_state_and_never_writes_success_planes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    publish_root = tmp_path / "publish"

    prepared = _invoke(
        output_root,
        publish_root,
        "prepare",
        "--bootstrap-run-id", "bootstrap-api-001",
        "--host-class", "local-apple-silicon",
        "--provider-tier", "cursor_grok",
        "--semantic-selection-id", "cursor_grok",
        "--workload-digest", DIGEST,
    )
    assert prepared["status"] == "prepared"
    assert _invoke(
        output_root, publish_root, "run", "--bootstrap-run-id", "bootstrap-api-001"
    )["status"] == "running"
    assert _invoke(
        output_root, publish_root, "status", "--bootstrap-run-id", "bootstrap-api-001"
    )["status"] == "running"
    assert _invoke(
        output_root,
        publish_root,
        "cancel",
        "--bootstrap-run-id", "bootstrap-api-001",
        "--reason", "controlled_provider_unavailable",
    )["status"] == "canceled"

    assert not publish_root.exists()
    assert not (output_root / "data/releases").exists()
    assert not (output_root / "env").exists()
    assert not tuple((output_root / "data").rglob("governed_capacity_calibration_receipt.json"))
