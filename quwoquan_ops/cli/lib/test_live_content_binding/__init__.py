"""Run-bound content evidence for one mutable non-production runtime.

The binding deliberately does not create or consume an immutable deployment
candidate.  It joins an already-running ``test_live`` startup attempt to an
explicit Data release readiness receipt and, for commercial readiness, its
rollback/replay lifecycle exit.  The resulting target-scoped record is always
non-promotable and create-once.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001

原单文件 ``test_live_content_binding.py`` 拆分为同名包；本 ``__init__`` re-export
全部公开与被测私有符号，外部 ``from quwoquan_ops.cli.lib.test_live_content_binding
import X`` 与 ``from quwoquan_ops.cli.lib import test_live_content_binding`` 的既有
用法保持不变。下方来自 ``output_paths`` / ``test_live_startup_attempt_receipt`` /
``app_content_uat_plan`` 的符号在原单文件中即为模块属性且被测试 monkeypatch，
因此必须继续以包属性暴露；子模块对这些符号（含 ``_load_evidence``）一律经包属性
（``_pkg.``）消费，本模块 re-export 的名字就是 patch 的锚点。
"""

from __future__ import annotations

from quwoquan_ops.cli.lib.app_content_uat_plan import (  # noqa: F401
    build_app_content_uat_plan,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: F401
    env_runs_root,
    output_root,
    target_process_dir,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (  # noqa: F401
    test_live_startup_attempt_path,
    validate_test_live_startup_attempt,
)

from .constants import (  # noqa: F401
    _BINDING_FIELDS,
    _DIGEST,
    _LIFECYCLE_FIELDS,
    _SEGMENT,
    _STARTUP_IDENTITY_FIELDS,
    SCHEMA,
    UnsafeTestLiveContentBindingPath,
)
from .safe_io import (  # noqa: F401
    _RegularJson,
    _create_once,
    _directory_flags,
    _file_digest,
    _file_flags,
    _open_directory_chain,
    _read_regular_json,
    _regular_identity,
    _revalidate_directory_chain,
)
from .evidence import (  # noqa: F401
    _Evidence,
    _canonical_digest,
    _canonical_ref,
    _copy_source_identity,
    _document_checksum,
    _lifecycle_path,
    _load_evidence,
    _safe_segment,
    _source_identity,
    _validate_attestation,
    _validate_lifecycle,
    _validate_readiness,
)
from .binding import (  # noqa: F401
    _binding_payload,
    _evidence_token,
    _startup_identity,
    _utc_now,
    _validate_binding,
    _validate_timestamp,
    create_test_live_content_binding,
    load_test_live_content_binding,
    test_live_content_binding_path,
)
