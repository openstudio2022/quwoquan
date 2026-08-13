#!/usr/bin/env python3
"""Render canonical Prod readiness and outcome receipts from hosted evidence."""

# 原单文件拆分为「薄入口 + 同目录子包 release_lifecycle_receipts/」：
# workflow 仍以 `python3 quwoquan_ops/ci/render_release_lifecycle_receipts.py`
# 调用本文件；consumer 仍 `from quwoquan_ops.ci import
# render_release_lifecycle_receipts as lifecycle`。本模块 re-export 全部公开与
# 被测私有符号（含 ``dt`` / ``yaml`` / ``hosted_release_ledger`` 模块属性与被
# 测试 monkeypatch 的 ``validate_manifest``）；子包对被 patch 符号一律经本模块
# 属性（``_pkg.``）消费，本模块 re-export 的名字就是 patch 的锚点。

from __future__ import annotations

import datetime as dt  # noqa: F401  # 测试经 lifecycle.dt 访问
import sys
from pathlib import Path

import yaml  # noqa: F401  # 原单文件的模块属性，保持可经 lifecycle.yaml 访问

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 以脚本路径直接执行（workflow 形态）时本模块名是 __main__；先把自身注册为
# canonical 模块名，子包 `import ... as _pkg` 才能命中同一实例，避免二次加载
# 引发的循环 import。
_CANONICAL_MODULE = "quwoquan_ops.ci.render_release_lifecycle_receipts"
if _CANONICAL_MODULE not in sys.modules:
    sys.modules[_CANONICAL_MODULE] = sys.modules[__name__]

from quwoquan_ops.cli.prod import hosted_release_ledger  # noqa: E402,F401
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (  # noqa: E402,F401
    DIGEST_PATTERN,
    validate_manifest,
)

from quwoquan_ops.ci.release_lifecycle_receipts.constants import (  # noqa: E402,F401
    HOSTED_AUTHORITY,
    HOSTED_READBACK_SCHEMA,
    HOSTED_RECEIPT_FIELDS,
    HOSTED_RECEIPT_READBACK_SCHEMA,
    HOSTED_RECEIPT_SCHEMA,
    HOSTED_SOAK_READBACK_SCHEMA,
    HOSTED_SOAK_RECEIPT_SCHEMA,
    HOSTED_SOAK_REQUEST_SCHEMA,
    HOSTED_STATE_FIELDS,
    HOSTED_STATE_SCHEMA,
    RECEIPT_ID_PATTERN,
    STAGES,
)
from quwoquan_ops.ci.release_lifecycle_receipts.receipt_codec import (  # noqa: E402,F401
    _canonical_bytes,
    _canonical_receipt,
    _digest_bytes,
    _digest_file,
    _load_json,
    _manifest_source,
    _parse_binding,
    _receipt_id,
    _utc_now,
    _validate_archive_prefix,
    _validate_timestamp,
    _window_seconds,
)
from quwoquan_ops.ci.release_lifecycle_receipts.hosted_readback import (  # noqa: E402,F401
    _validate_hosted_receipt,
    _validate_ledger_readback,
    _validate_receipt_readback,
    _validate_soak_readback,
)
from quwoquan_ops.ci.release_lifecycle_receipts.rollback_readiness import (  # noqa: E402,F401
    render_rollback_readiness,
)
from quwoquan_ops.ci.release_lifecycle_receipts.prod_outcome import (  # noqa: E402,F401
    render_prod_outcome,
)
from quwoquan_ops.ci.release_lifecycle_receipts.prod_soak import (  # noqa: E402,F401
    render_prod_soak_request,
)
from quwoquan_ops.ci.release_lifecycle_receipts.cli import (  # noqa: E402,F401
    _parser,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
