# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-005
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-006
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-002

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]


def test_service_architecture_governance_facade() -> None:
    result = subprocess.run(
        [sys.executable, "quwoquan_ops/gate/verify_service_architecture.py"],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
