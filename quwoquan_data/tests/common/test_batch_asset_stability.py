"""双批稳定性比对契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
import subprocess
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="batch_asset_stability_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from publish_ops.rebuild_directory_layout_sample import rebuild  # noqa: E402
from verify.verify_batch_stability_compare import compare_batches, snapshot_batch, write_snapshot  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"
BASELINE = "e2e_baseline"
STABILITY = "e2e_stability_2"


def test_two_batch_sample_compare_passes():
    rebuild(TASK, BASELINE)
    rebuild(TASK, STABILITY)
    baseline, candidate, issues = compare_batches(TASK, BASELINE, STABILITY)
    assert not issues, issues
    assert candidate["globalBatchSeq"] == baseline["globalBatchSeq"] + 1
    assert set(baseline["assetIds"]) & set(candidate["assetIds"]) == set()


def test_snapshot_can_be_written():
    rebuild(TASK, BASELINE)
    snapshot = snapshot_batch(TASK, BASELINE)
    out = _TMP / "snapshot.json"
    write_snapshot(out, snapshot)
    assert out.is_file()
    assert snapshot["globalBatchSeq"] > 0


def test_verify_cli_batch_stability_entrypoint():
    rebuild(TASK, BASELINE)
    rebuild(TASK, STABILITY)
    cli = SCRIPTS_ROOT / "cli.py"
    report = _TMP / "report.json"
    baseline_snapshot = _TMP / "baseline_snapshot.json"
    result = subprocess.run(
        [
            sys.executable,
            str(cli),
            "verify",
            "batch-stability",
            "--task",
            TASK,
            "--baseline",
            BASELINE,
            "--candidate",
            STABILITY,
            "--baseline-snapshot-out",
            str(baseline_snapshot),
            "--report-out",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert baseline_snapshot.is_file()
    assert report.is_file()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch asset stability tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
