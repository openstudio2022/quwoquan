"""Run the real Alpha content API consumer against explicit live authorities.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/
multi-carrier-release/spec.md#gwt-034
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
_ENABLED = "QWQ_RUN_CONTENT_API_CONSUMER_INTEGRATION"
_ARGUMENTS = {
    "--release-id": "QWQ_CONTENT_API_CONSUMER_RELEASE_ID",
    "--import-run-id": "QWQ_CONTENT_API_CONSUMER_IMPORT_RUN_ID",
    "--verify-run-id": "QWQ_CONTENT_API_CONSUMER_VERIFY_RUN_ID",
    "--manifest-digest": "QWQ_CONTENT_API_CONSUMER_MANIFEST_DIGEST",
    "--sample-plan-ref": "QWQ_CONTENT_API_CONSUMER_SAMPLE_PLAN_REF",
    "--sample-plan-digest": "QWQ_CONTENT_API_CONSUMER_SAMPLE_PLAN_DIGEST",
    "--data-readiness-ref": "QWQ_CONTENT_API_CONSUMER_DATA_READINESS_REF",
    "--data-readiness-digest": "QWQ_CONTENT_API_CONSUMER_DATA_READINESS_DIGEST",
    "--consumer-health-ref": "QWQ_CONTENT_API_CONSUMER_HEALTH_REF",
    "--consumer-health-digest": "QWQ_CONTENT_API_CONSUMER_HEALTH_DIGEST",
    "--report-dir": "QWQ_CONTENT_API_CONSUMER_REPORT_DIR",
}


def test_real_alpha_content_api_consumer_matrix() -> None:
    assert os.environ.get(_ENABLED) == "1", (
        f"set {_ENABLED}=1 with explicit live authority refs/digests"
    )
    missing = [
        name for name in _ARGUMENTS.values() if not os.environ.get(name, "").strip()
    ]
    if missing:
        pytest.fail(
            "explicit live content API consumer authority is incomplete: "
            + ", ".join(missing)
        )
    argv = [
        sys.executable,
        str(STACKCTL),
        "--output-format",
        "json",
        "content-api-consumer",
        "--target",
        "alpha-local",
    ]
    for flag, variable in _ARGUMENTS.items():
        argv.extend((flag, os.environ[variable]))
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["exitCode"] == 0
    assert len(result["requiredRawResults"]) == 16
    assert {row["status"] for row in result["requiredRawResults"]} == {"passed"}
