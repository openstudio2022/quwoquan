"""以当前部署输入和完整 runtime package 摘要判定 package 是否可复用。

原单文件 ``package_reuse.py`` 拆分为同名包；本 ``__init__`` re-export 全部
公开与被测私有符号，外部 ``from quwoquan_ops.cli.lib.package_reuse import X``
与 ``from quwoquan_ops.cli.lib import package_reuse`` 的既有用法保持不变。
下方来自 ``deployment_candidate_manifest`` 与 ``output_paths`` 的符号在原
单文件中即为模块属性且被测试 monkeypatch，因此必须继续以包属性暴露。
"""

from __future__ import annotations

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: F401
    RELEASE_INPUT_CLASSIFICATIONS,
    RUNTIME_CANDIDATE_TYPE,
    validate_candidate_manifest,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: F401
    PACKAGE_ROOT_OVERRIDE_ENV,
    active_deployment_candidate,
    app_deployment_package_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)

from .constants import (  # noqa: F401
    _CAPSULE_ENTRY_FIELDS,
    _CAPSULE_FIELDS,
    _DEPLOYMENT_INPUT_FIELDS,
    _DIGEST_FIELDS,
    _FINGERPRINT_FIELDS,
    CURRENTNESS_TIMEOUT_SECONDS,
    FINGERPRINT_NAME,
    FINGERPRINT_SCHEMA,
    PACKAGE_INPUT_CAPSULE_DIRECTORY,
    PACKAGE_INPUT_CAPSULE_SCHEMA,
    PACKAGE_VALIDATION_PURPOSES,
    ROOT,
)
from .fingerprint_store import (  # noqa: F401
    _absolute_fingerprint_path,
    _atomic_write_fingerprint,
    _fingerprint_directory_flags,
    _fingerprint_entry_info,
    _fingerprint_file_flags,
    _open_fingerprint_parent,
    _revalidate_fingerprint_parent,
    _UnsafeFingerprintPath,
    fingerprint_path,
)
from .input_capsule import (  # noqa: F401
    _baseline_id,
    _capsule_identity_payload,
    _copy_regular_capsule_input,
    _digest_record,
    _enumerated_deployment_inputs,
    _normalized_input_roots,
    _path_entry,
    _read_capsule_manifest,
    _safe_capsule_source,
    materialize_package_input_capsule,
    verify_package_input_capsule,
)
from .workspace_inputs import (  # noqa: F401
    _expected_service_packages,
    _normalized_service_packages,
    deployment_input_digest,
    deployment_input_roots,
    workspace_drift_details,
    workspace_snapshot,
)
from .reuse_decision import (  # noqa: F401
    _candidate_service_packages,
    _digest_payload,
    _package_roots,
    can_reuse_package,
    package_content_digest,
    write_package_fingerprint,
)
