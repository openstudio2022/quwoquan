#!/usr/bin/env python3
"""Validate the canonical startup environment CaseResult evidence flow.

Package/define checks are component-readiness evidence only.  A release-bound
matrix can pass only when every required launcher, readback and observability
case exists and validates against one baseline/release identity.

实现单轨落在 ``startup_environment_matrix/`` 包内（context / package_probe /
evidence_validation / reporting / cli）；本文件是稳定 CLI 入口，并为既有
消费者（startup probe parser、iOS runtime dart defines 等测试）re-export
包 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from startup_environment_matrix import *  # noqa: E402,F401,F403
from startup_environment_matrix import (  # noqa: E402,F401
    APP_DIR,
    DEVICE_PROFILES,
    ENVIRONMENTS,
    OBSERVABILITY_EVIDENCE_SCHEMA,
    READBACK_EVIDENCE_SCHEMA,
    REQUIRED_DEFINES,
    RUNTIME_CASES,
    RUNTIME_EVIDENCE_SCHEMA,
    RUNTIME_TARGETS,
    SHA256_PATTERN,
    SPEC_REFS,
    _case,
    _case_counts,
    _ios_defines,
    _launcher_handoff,
    _missing_spec_refs,
    _report_status,
    _run,
    _runtime_defines,
    _validate_defines,
    _validate_observability_evidence,
    _validate_readback_evidence,
    _validate_runtime_evidence,
    _validate_runtime_sample,
    _write_report,
    cli,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
