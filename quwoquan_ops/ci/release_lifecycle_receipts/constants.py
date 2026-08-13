"""release lifecycle receipts 的 hosted schema 常量与放量阶段闭集。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的共享常量子模块。
"""

from __future__ import annotations

import re

from quwoquan_ops.cli.prod import hosted_release_ledger

HOSTED_AUTHORITY = hosted_release_ledger.AUTHORITY
HOSTED_READBACK_SCHEMA = hosted_release_ledger.READBACK_SCHEMA
HOSTED_RECEIPT_READBACK_SCHEMA = hosted_release_ledger.RECEIPT_READBACK_SCHEMA
HOSTED_RECEIPT_SCHEMA = hosted_release_ledger.RECEIPT_SCHEMA
HOSTED_STATE_SCHEMA = hosted_release_ledger.STATE_SCHEMA
HOSTED_SOAK_REQUEST_SCHEMA = hosted_release_ledger.SOAK_REQUEST_SCHEMA
HOSTED_SOAK_RECEIPT_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_SCHEMA
HOSTED_SOAK_READBACK_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_READBACK_SCHEMA
STAGES = ("canary", "5", "20", "50", "100")
RECEIPT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
HOSTED_RECEIPT_FIELDS = hosted_release_ledger.RECEIPT_FIELDS
HOSTED_STATE_FIELDS = hosted_release_ledger.STATE_FIELDS
