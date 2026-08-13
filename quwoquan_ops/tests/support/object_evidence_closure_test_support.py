"""verify_object_evidence_closure strict-zero 合约测试的共享 support。

`test_object_evidence_closure__strict_zero__*__local_contract_test.py` 系列由
Python 1000 行硬顶治理从单文件按场景拆分而来；合成图构造、临时工作区/门禁
子进程 harness 与路径常量逐字下沉到本模块。支撑基类不含任何测试方法。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_object_evidence_closure.py"
PACKAGE_DIR = ROOT / "quwoquan_ops/gate/object_evidence_closure"
BASELINE = ROOT / "quwoquan_ops/policies/gates/object_evidence_closure_baseline.json"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"
COMMITTED_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 主流程与 mock.patch 注入点都在包的 gate 模块（入口只 re-export）；
# 契约必须 patch 函数真实解析名字的那个命名空间。
from quwoquan_ops.gate.object_evidence_closure import gate as closure  # noqa: E402


def canonical_evidence_packet(object_id: str = "content.demo") -> dict:
    return {
        "objectId": object_id,
        "operationIds": [],
        "service": {
            "domain": [],
            "store": [],
            "outbox": [],
            "reader": [],
            "transport": [],
            "localContract": [],
            "apiIntegration": [],
        },
        "app": {
            "domain": [],
            "application": [],
            "adapters": [],
            "presentation": [],
            "localContract": [],
            "apiIntegration": [],
            "userAcceptance": [],
            "pageParticipant": False,
            "pageOwned": False,
        },
        "ops": {
            "environmentAcceptance": [],
            "rollbackRunner": [],
            "replayRunner": [],
        },
        "sourcePath": "content/demo/object.yaml",
    }


def synthetic_graph(
    kind: str = "projection",
    missing: str = "implementation.app.application",
) -> dict:
    """最小合成图：只保留 readiness 展开所需的三段，避免把真实契约拖进判定。"""
    return {
        "objects": [
            {"id": "content.demo", "kind": kind, "sourcePath": "content/demo/object.yaml"}
        ],
        "objectReadiness": [
            {
                "objectId": "content.demo",
                "stage": "implemented",
                "contractReady": True,
                "missing": [missing],
            }
        ],
        "readinessEvidence": [canonical_evidence_packet()],
        "operations": [],
    }


class ObjectEvidenceClosureStrictZeroSupport(unittest.TestCase):
    """共享 harness：临时工作区、图/工件写入与门禁子进程调用。"""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)

    def write_graph(self, document: dict) -> Path:
        path = self.workspace / "graph.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def write_artifact(self, name: str, payload: bytes) -> tuple[Path, str]:
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    def write_blind_spot_registry(self, entries: list[dict]) -> Path:
        path = self.workspace / "blind_spots.yaml"
        path.write_text(
            json.dumps({"unresolved_sites": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def write_page_contract(self, document: dict) -> Path:
        path = self.workspace / "page_object_contract.yaml"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def commercial_inputs(self) -> tuple[SimpleNamespace, list[str]]:
        files = {}
        for name in (
            "readiness_bundle",
            "signed_current_snapshot",
            "snapshot_keyring",
            "runner_keyring",
        ):
            path = self.workspace / f"{name}.json"
            path.write_text(json.dumps({"input": name}), encoding="utf-8")
            files[name] = path
        receipt_root = self.workspace / "receipts"
        evidence_root = self.workspace / "evidence"
        receipt_root.mkdir()
        evidence_root.mkdir()
        (receipt_root / "receipt.json").write_text("{}", encoding="utf-8")
        (evidence_root / "artifact.json").write_text("{}", encoding="utf-8")
        arguments = SimpleNamespace(
            **files,
            receipt_root=receipt_root,
            evidence_root=evidence_root,
        )
        cli = [
            "--readiness-bundle",
            str(files["readiness_bundle"]),
            "--signed-current-snapshot",
            str(files["signed_current_snapshot"]),
            "--snapshot-keyring",
            str(files["snapshot_keyring"]),
            "--runner-keyring",
            str(files["runner_keyring"]),
            "--receipt-root",
            str(receipt_root),
            "--evidence-root",
            str(evidence_root),
        ]
        return arguments, cli

    def run_gate(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_OUTPUT_ROOT": str(ROOT / ".qwq_output"),
        }
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--report-dir",
                str(self.workspace / "report"),
                *arguments,
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
