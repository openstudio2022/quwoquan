"""受管模拟器本地 CA 信任包（由原单文件 local_device_trust.py 拆分）。

对外契约保持不变：``from quwoquan_ops.cli.lib import local_device_trust`` 与
``from quwoquan_ops.cli.lib.local_device_trust import Y`` 均可用。

monkeypatch 兼容模式：测试通过 ``mock.patch.object(local_device_trust, "X")``
替换本包属性；子模块顶部 ``import quwoquan_ops.cli.lib.local_device_trust as
_pkg``，被 patch 的符号在包内消费点一律经 ``_pkg.X(...)`` 属性访问，保证
patch 生效。``ssl`` / ``json`` 等 stdlib 模块保持为包属性，维持
``patch.object(local_device_trust.ssl, ...)`` 与 ``local_device_trust.json``
的既有语义。
"""

from __future__ import annotations

# stdlib 模块保持为包属性（原单文件顶层 import，测试有 subject.ssl / subject.json 用法）。
import hashlib  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import platform  # noqa: F401
import re  # noqa: F401
import ssl  # noqa: F401
import subprocess  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401
from uuid import uuid4  # noqa: F401

# 外部协作模块符号保持为包属性（测试 patch 锚点）。
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: F401
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_device_android_trust import (  # noqa: F401
    AndroidTrustOverlayError,
    remote_tree_sha256,
    verify_runtime_trust_stores,
)
from quwoquan_ops.cli.lib.local_device_resolver import (  # noqa: F401
    LocalDeviceResolverError,
    install_android_host_overlay,
    verify_android_host_overlay,
)
from quwoquan_ops.cli.lib.local_target_handoff import (  # noqa: F401
    load_handoff,
    materialize_handoff,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: F401
    target_cache_dir,
    target_process_dir,
)
from quwoquan_ops.cli.lib.public_domain_tls import (  # noqa: F401
    root_certificate_path,
    verify_certificate,
)

from .constants import (  # noqa: F401
    PLATFORMS,
    SCHEMA,
    _ANDROID_CONSCRYPT_CACERTS,
    _ANDROID_SYSTEM_CACERTS,
    _ANDROID_TRUST_STAGE_ROOT,
    _ROOT,
    _SAFE,
)
from .errors import (  # noqa: F401
    AndroidSystemTrustUnavailable,
    AndroidSystemTrustVerificationError,
    LocalDeviceTrustError,
)
from .device_commands import (  # noqa: F401
    _booted_ios_simulators,
    _read_receipt,
    _receipt_path,
    _require_success,
    _root_fingerprint,
    _run,
    _target_probe_url,
    _utc_now,
    _write_receipt,
    resolve_managed_device,
)
from .ios_trust import (  # noqa: F401
    _install_ios,
    _ios_probe_binary,
    _probe_ios_system_trust,
)
from .android_trust import (  # noqa: F401
    _android_conscrypt_source_cacerts,
    _android_identity,
    _android_mount_namespace_evidence,
    _android_property,
    _android_remote_sha256,
    _android_root,
    _android_subject_hash,
    _android_trust_stage_root,
    _android_zygote_pids,
    _install_android,
    _install_android_conscrypt,
    _install_android_system_store,
    _verify_android_system_trust,
)
from .lifecycle import (  # noqa: F401
    install_device_trust,
    release_device_trust,
    verify_device_trust,
)
