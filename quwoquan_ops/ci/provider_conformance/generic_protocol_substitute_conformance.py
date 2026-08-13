"""Execute package-bound conformance probes against the generic substitute.

This module does not select an Adapter or maintain a Provider registry.  The
selected Adapter, operations and endpoint material keys come from the source
metadata, the object-owned ``operations.yaml`` and the active candidate's
packaged Provider composition.  Target-specific endpoint and operator values
remain in the protected deployment workspace and are never returned by this
module.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import ssl
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

import yaml

from quwoquan_ops.ci.provider_conformance.native_case_result import (
    _ASSERTION_MARKER,
    _CLEANUP_MARKER,
)
from quwoquan_ops.ci.provider_conformance.run_provider_patrol_uat import (
    _load_nonprod_runtime_identity,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile
from quwoquan_ops.cli.lib.local_environment_auth import load_local_environment_auth
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    deployment_work_root,
)
from quwoquan_ops.cli.lib.port_manifest import canonical_port, load_port_manifest
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

# 实现单轨落在 generic_protocol_substitute_lib/ 包内；本文件仅 re-export
# 公开与被测私有符号，保持既有 import 面与模块命名空间不变。
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.models import (  # noqa: E402,F401
    ADAPTER_ID,
    ROLE,
    ROOT,
    SUPPORTED_PUBLIC_ASSERTIONS,
    _DIGEST_PREFIX,
    AssertionEvidence,
    ConformanceBlocked,
    HTTPResult,
    InvocationEvidence,
    RuntimeContext,
    SupportedRun,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.evidence_helpers import (  # noqa: E402,F401
    _aggregate_assertion,
    _endpoint_for_operation,
    _load_provider_material,
    _owner_dependency,
    _packaged_binding,
    _probe_request,
    _provider_request_digest,
    _provider_workload,
    _read_protected_json,
    _receipt_ref,
    _required_assertion_ids,
    _required_environment,
    _sha256_json,
    _sha256_text,
    _validate_success,
    diagnostic_payload,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.protocol_client import (  # noqa: E402,F401
    ProtocolClient,
    _NoRedirect,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.runtime_scenes import (  # noqa: E402,F401
    _validated_native_marker_lines,
    emit_markers,
    execute_offline_local_contract,
    execute_supported_scenes,
    load_runtime_context,
)
