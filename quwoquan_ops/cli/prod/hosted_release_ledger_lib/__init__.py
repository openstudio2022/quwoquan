"""hosted release ledger 的实现包（stdlib-only）。

唯一稳定入口是 ``quwoquan_ops/cli/prod/hosted_release_ledger.py``（双栖薄壳）。
本包与入口一起经 ``sync_prod_plane_stack.sh`` tar 传输到远端主机临时目录执行，
因此**不得 import 仓库内任何其他模块**，只允许 Python 标准库与包内相对导入。

- ``contract``：schema 常量、字段闭集、正则与基础校验原语。
- ``request_validation``：transition/soak 请求与晋级/回滚证据校验。
- ``ledger_store``：state/receipt 的安全读写、锁与 readback 一致性校验。
- ``actions``：commit/fetch 五个动作与 CLI main。
"""
from __future__ import annotations

from .contract import *  # noqa: F401,F403
from .contract import (  # noqa: F401
    _canonical_bytes,
    _receipt_id,
    _require_non_negative_integer,
    _require_safe_string,
    _require_timestamp,
)
from .request_validation import (  # noqa: F401
    _validate_check_summaries,
    _validate_request,
    _validate_soak_request,
    validate_promotion_evidence,
    validate_rollback_evidence,
)
from .ledger_store import (  # noqa: F401
    _atomic_write,
    _history_receipt_matches_transaction,
    _ledger_lock,
    _load_hosted_receipt,
    _load_hosted_soak_receipt,
    _load_state,
    _next_stage_receipt_history,
    _validate_stage_receipt_history,
    _validated_readback,
)
from .actions import (  # noqa: F401
    _parser,
    commit,
    commit_soak,
    fetch,
    fetch_receipt,
    fetch_soak_receipt,
    main,
)
