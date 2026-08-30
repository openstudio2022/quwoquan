"""app content preflight 合约测试共享 imports 与 helpers
（自 test_app_content_preflight__local_contract_test 拆分）。
"""
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import hashlib  # noqa: F401 - re-exported to split test modules
import json  # noqa: F401 - re-exported to split test modules
import os  # noqa: F401 - re-exported to split test modules
import subprocess  # noqa: F401 - re-exported to split test modules
import tempfile  # noqa: F401 - re-exported to split test modules
import unittest  # noqa: F401 - re-exported to split test modules
from pathlib import Path  # noqa: F401 - re-exported to split test modules
from unittest.mock import patch  # noqa: F401 - re-exported to split test modules

from quwoquan_ops.cli import stackctl  # noqa: F401 - re-exported to split test modules
from quwoquan_ops.cli.smoke import (
    run_environment_patrol_smoke as patrol_smoke,  # noqa: F401 - re-export
)

