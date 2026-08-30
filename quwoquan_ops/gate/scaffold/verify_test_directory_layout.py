#!/usr/bin/env python3
"""Verify physical three-layer test directories and canonical file names.

实现单轨落在 ``test_directory_layout/`` 包内；本文件只是稳定 CLI 入口，为既有
消费者 re-export 包 API，并把合约测试对本模块全局量的运行时改写同步回包内
实现模块。
"""
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001

from __future__ import annotations

import gc
import sys
from pathlib import Path
from types import ModuleType

sys.dont_write_bytecode = True

_SCAFFOLD_ROOT = Path(__file__).resolve().parent
if str(_SCAFFOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCAFFOLD_ROOT))

from test_directory_layout_lib import ROOT  # noqa: E402

sys.dont_write_bytecode = True

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.scaffold import test_directory_layout as _impl_package  # noqa: E402
from quwoquan_ops.gate.scaffold.test_directory_layout import *  # noqa: E402,F401,F403
from quwoquan_ops.gate.scaffold.test_directory_layout import main, opm  # noqa: E402,F401
from quwoquan_ops.gate.scaffold.test_directory_layout import (  # noqa: E402
    app_layout as _app_layout_module,
    app_support as _app_support_module,
    common as _common_module,
    constants as _constants_module,
    dart_lexer as _dart_lexer_module,
    data as _data_module,
    ops as _ops_module,
    report as _report_module,
    service as _service_module,
)

#: 合约测试通过 spec_from_file_location 加载本入口，并对入口模块做
#: ``verifier.ROOT = ...`` / ``verifier.APP_UNMIGRATED_LAYER_DIRS = ...`` 这类
#: 全局量改写；改写必须同步到持有同名全局量的全部实现模块，才能保持与
#: 单文件时代一致的语义。
_IMPL_MODULES = (
    _impl_package,
    _app_layout_module,
    _app_support_module,
    _common_module,
    _constants_module,
    _dart_lexer_module,
    _data_module,
    _ops_module,
    _report_module,
    _service_module,
)


class _EntryFacadeModule(ModuleType):
    """把入口模块上的属性赋值广播到包内实现模块的同名全局量。"""

    def __setattr__(self, name: str, value: object) -> None:
        for module in _IMPL_MODULES:
            if name in vars(module):
                module.__dict__[name] = value
        super().__setattr__(name, value)


def _entry_module() -> ModuleType | None:
    """定位当前入口模块对象。

    直接执行或常规 import 时可经 ``sys.modules`` 命中；合约测试用
    ``importlib.util.spec_from_file_location`` 加载且不登记 ``sys.modules``，
    此时经 gc 反查持有本命名空间的模块对象。
    """
    module = sys.modules.get(__name__)
    if isinstance(module, ModuleType) and module.__dict__ is globals():
        return module
    for referrer in gc.get_referrers(globals()):
        if isinstance(referrer, ModuleType) and referrer.__dict__ is globals():
            return referrer
    return None


_ENTRY_MODULE = _entry_module()
if _ENTRY_MODULE is not None:
    _ENTRY_MODULE.__class__ = _EntryFacadeModule


if __name__ == "__main__":
    raise SystemExit(main())
