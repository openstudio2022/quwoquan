"""Target-scoped transactional receipt for local runtime startup.

原 ``startup_attempt_receipt.py`` 的同名包形态；对外 import 路径与符号完全
不变（含被测私有 ``_`` 符号）。按职责切分：

- ``constants``：schema、字段集合、状态机与 fan-out 事务常量。
- ``receipt_fs``：symlink-safe 读取与 staged 原子写入/提交/回收原语。
- ``receipt_contract``：receipt 路径、校验（``validate_startup_attempt``）与加载。
- ``fanout_transaction``：多目的地 fan-out 事务日志、回滚与恢复。
- ``oci_composition``：candidate OCI manifest 到 startup 身份的投影与加载。
- ``transition``：``transition_startup_attempt`` 状态机。
- ``startup_attempt_receipt``：argparse 脚本入口（gamma 启动脚本按路径执行）。

测试通过 ``mock.patch.object(本包, "<符号>")`` 拦截内部依赖，因此子模块对这些
符号一律经包属性（``_pkg.``）消费；本模块 re-export 的名字就是 patch 的锚点。
``output_root`` / ``active_candidate_manifest_path`` / ``deployment_candidate_dir`` /
``load_candidate_manifest`` 等外部名字同样保持为包属性以维持 patch 语义。
"""

from __future__ import annotations

from ..deployment_candidate_manifest import load_candidate_manifest  # noqa: F401
from ..immutable_image_composition import immutable_image_digest  # noqa: F401
from ..output_paths import (  # noqa: F401
    ACTIVE_CANDIDATE_SCHEMA,
    active_candidate_manifest_path,
    deployment_candidate_dir,
    output_root,
    target_process_dir,
)

from .constants import (  # noqa: F401
    RECEIPT_FIELDS,
    SCHEMA,
    STATUSES,
    WORKLOADS,
    _ACTIVE_CANDIDATE_FIELDS,
    _DIGEST,
    _FANOUT_DESTINATION_FIELDS,
    _FANOUT_TRANSACTION_FIELDS,
    _FANOUT_TRANSACTION_SCHEMA,
    _IMAGE_COMPOSITION_FIELDS,
    _IMAGE_ROLE,
    _IMMUTABLE_RECEIPT_IDENTITY_FIELDS,
    _OCI_FIELDS,
    _OCI_IMAGE_FIELD_SETS,
    _OCI_SCHEMA,
    _TRANSITIONS,
)
from .receipt_fs import (  # noqa: F401
    _StagedReceiptWrite,
    _UnsafeStartupReceiptPath,
    _absolute_path,
    _atomic_write,
    _atomic_write_bytes,
    _commit_staged_receipt,
    _directory_flags,
    _discard_staged_receipt,
    _encode_json,
    _entry_info,
    _file_flags,
    _open_parent,
    _prevalidate_write_path,
    _revalidate_parent,
    _secure_read,
    _secure_unlink_if_matches,
    _stage_receipt_bytes,
    _write_transaction_journal_exclusive,
)
from .receipt_contract import (  # noqa: F401
    _canonical_run_root,
    _environment_for_target,
    _read,
    _sha256_json,
    _utc_now,
    load_startup_attempt,
    load_workload_startup_attempt,
    read_startup_attempt,
    startup_attempt_path,
    startup_attempt_path_for_workload,
    validate_startup_attempt,
)
from .fanout_transaction import (  # noqa: F401
    _fanout_destinations,
    _fanout_transaction_path,
    _recover_fanout_transaction,
    _rollback_fanout_transaction,
    _transactional_fanout_write,
    _validate_fanout_transaction,
    _validate_old_receipt_text,
)
from .oci_composition import (  # noqa: F401
    image_composition_from_candidate_oci,
    load_candidate_oci_image_composition,
)
from .transition import transition_startup_attempt  # noqa: F401
from .startup_attempt_receipt import main  # noqa: F401
