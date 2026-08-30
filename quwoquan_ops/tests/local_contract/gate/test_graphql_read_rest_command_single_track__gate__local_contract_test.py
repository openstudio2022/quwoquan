from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
CONTRACT = (
    ROOT
    / "quwoquan_service/services/api-edge/tests/local_contract/graphql_read/"
    "persisted_query_execution/graphql_read_rest_command_single_track__local_contract_test.py"
)


def test_graphql_read_rest_command_single_track_contract_suite() -> None:
    environment = os.environ.copy()
    environment.pop("GRAPHQL_MIGRATION_BASE_SHA", None)
    environment.pop("GRAPHQL_MIGRATION_CANDIDATE_SHA", None)
    completed = subprocess.run(
        [sys.executable, "-B", str(CONTRACT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
