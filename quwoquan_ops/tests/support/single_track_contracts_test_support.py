"""verify_single_track_contracts 合约测试的共享 support。

`test_single_track_contracts__*__local_contract_test.py` 系列由 Python 1000 行
硬顶治理从单文件按场景拆分而来；verifier 加载与扫描 fixture harness 逐字
下沉到本模块。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_single_track_contracts.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_single_track_contracts",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scanner_module():
    """扫描逻辑所在的包模块；其模块级 ``ROOT`` 是测试注入扫描根的挂点。"""
    return sys.modules["quwoquan_ops.gate.single_track_contracts.scanner"]


def _scan_fixture(module, relative_path: str, text: str):
    scanner = _scanner_module()
    original_root = scanner.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        scanner.ROOT = Path(tmp)
        try:
            path = scanner.ROOT / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            inventory = module.Inventory()
            module.scan_file(path, inventory)
            return inventory
        finally:
            scanner.ROOT = original_root
