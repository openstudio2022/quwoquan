#!/usr/bin/env python3
"""Hosted service-plane authority for immutable production release receipts.

实现单轨落在同目录 ``hosted_release_ledger_lib/`` 包内（stdlib-only）；本文件
是双栖薄入口。``sync_prod_plane_stack.sh`` 把「本入口 + 实现包」经 tar 传输到
远端主机临时目录后执行 ``python3 <tmp>/hosted_release_ledger.py``（远端没有
仓库树，因此入口与包都不得 import 仓库内任何其他模块）。The hosted filesystem
owns the CAS generation and immutable receipt; local ``.qwq_output`` files are
readback copies only.

双栖导入：
- 仓库内 ``from quwoquan_ops.cli.prod import hosted_release_ledger`` 时，
  ``__package__`` 非空，包经常规相对路径解析；
- 远端裸执行（或 ``python3 quwoquan_ops/cli/prod/hosted_release_ledger.py``）
  时按脚本运行，把自身目录加入 ``sys.path`` 后裸导入实现包。
两种形态导出的符号完全一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from quwoquan_ops.cli.prod.hosted_release_ledger_lib import *  # noqa: F401,F403
    from quwoquan_ops.cli.prod.hosted_release_ledger_lib import (  # noqa: F401
        _atomic_write,
        _canonical_bytes,
        _history_receipt_matches_transaction,
        _ledger_lock,
        _load_hosted_receipt,
        _load_hosted_soak_receipt,
        _load_state,
        _next_stage_receipt_history,
        _parser,
        _receipt_id,
        _require_non_negative_integer,
        _require_safe_string,
        _require_timestamp,
        _validate_check_summaries,
        _validate_request,
        _validate_soak_request,
        _validate_stage_receipt_history,
        _validated_readback,
        main,
    )
else:
    _ENTRY_DIR = str(Path(__file__).resolve().parent)
    if _ENTRY_DIR not in sys.path:
        sys.path.insert(0, _ENTRY_DIR)
    from hosted_release_ledger_lib import *  # noqa: F401,F403
    from hosted_release_ledger_lib import (  # noqa: F401
        _atomic_write,
        _canonical_bytes,
        _history_receipt_matches_transaction,
        _ledger_lock,
        _load_hosted_receipt,
        _load_hosted_soak_receipt,
        _load_state,
        _next_stage_receipt_history,
        _parser,
        _receipt_id,
        _require_non_negative_integer,
        _require_safe_string,
        _require_timestamp,
        _validate_check_summaries,
        _validate_request,
        _validate_soak_request,
        _validate_stage_receipt_history,
        _validated_readback,
        main,
    )

if __name__ == "__main__":
    raise SystemExit(main())
