"""app content preflight 合约测试共享 imports 与 helpers
（自 test_app_content_preflight__local_contract_test 拆分）。
"""
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
)
from quwoquan_ops.cli.lib.test_data.model import canonical_digest
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as patrol_smoke


