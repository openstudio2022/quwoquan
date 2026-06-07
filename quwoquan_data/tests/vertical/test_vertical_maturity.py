"""规模化数据工程成熟度整改契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from ship.activation import write_activation_smoke_report  # noqa: E402
from ship.consistency import scan_release_contract  # noqa: E402
from task.queue import enqueue, list_jobs, run_workers  # noqa: E402
from vertical.benchmark import evaluate_benchmark  # noqa: E402
from vertical.coverage import evaluate_registry, list_verticals  # noqa: E402
from vertical.governance import verify_vertical_script_governance  # noqa: E402
from vertical.license import validate_image_rights  # noqa: E402
from vertical.quality import verify_vertical_quality  # noqa: E402


def test_coverage_registry_reports_all_target_verticals():
    assert set(list_verticals()) >= {"travel", "photography", "campus"}
    for vertical in ("travel", "photography", "campus"):
        report = evaluate_registry(vertical)
        assert report["totals"]["units"] >= 2
        assert report["status"] in {"passed", "gap"}


def test_vertical_script_governance_passes_with_campus_wrappers():
    assert verify_vertical_script_governance() == []


def test_photography_image_rights_blocks_pinterest_and_missing_license():
    issues = validate_image_rights({"url": "https://example.com/a.jpg", "platform": "Pinterest"}, vertical="photography")
    assert any("Pinterest" in issue for issue in issues)
    assert any("missing required field license" in issue for issue in issues)


def test_photography_image_rights_accepts_authorized_payload():
    issues = validate_image_rights(
        {
            "url": "https://example.com/a.jpg",
            "platform": "Unsplash",
            "license": "Unsplash License",
            "credit": "Alice",
            "sourceUrl": "https://example.com/a",
            "termsUrl": "https://unsplash.com/license",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
        },
        vertical="photography",
    )
    assert issues == []


def test_vertical_quality_gate_has_golden_samples():
    assert verify_vertical_quality() == []


def test_post_activation_requires_smoke_report_and_active_release_match():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        contract = {
            "releaseId": "rel-1",
            "environment": "gamma",
            "desiredRefs": {"entities": [], "posts": []},
            "actions": [],
        }
        report = scan_release_contract(contract, publish_root=root, metadata_root=root, phase="post-activation")
        assert report["status"] == "failed"
        assert report["blockingIssues"][0]["code"] == "missing_activation_smoke_report"
        write_activation_smoke_report(contract, active_release_id="rel-1", publish_root=root)
        report = scan_release_contract(contract, publish_root=root, metadata_root=root, phase="post-activation")
        assert report["status"] == "passed", report
        assert report["observability"]["activeReleaseId"] == "rel-1"


def test_task_queue_enqueue_lists_without_running_job():
    with tempfile.TemporaryDirectory() as td:
        import task.queue as q

        old_root, old_ready, old_running, old_done, old_dead = q.QUEUE_ROOT, q.READY_DIR, q.RUNNING_DIR, q.DONE_DIR, q.DEAD_DIR
        q.QUEUE_ROOT = Path(td) / "queue"
        q.READY_DIR = q.QUEUE_ROOT / "ready"
        q.RUNNING_DIR = q.QUEUE_ROOT / "running"
        q.DONE_DIR = q.QUEUE_ROOT / "done"
        q.DEAD_DIR = q.QUEUE_ROOT / "dead"
        try:
            enqueue("旅行/地域/四川省/景区/样例", batch_id="b1", until="download_plan")
            jobs = list_jobs()
            assert jobs["ready"]
            assert run_workers(limit=0) == []
        finally:
            q.QUEUE_ROOT, q.READY_DIR, q.RUNNING_DIR, q.DONE_DIR, q.DEAD_DIR = old_root, old_ready, old_running, old_done, old_dead


def test_benchmark_reports_blocked_targets_in_current_maturity():
    report = evaluate_benchmark([1000, 10000, 100000])
    assert [row["targetDailyPosts"] for row in report["targets"]] == [1000, 10000, 100000]
    assert any(row["status"] == "blocked" for row in report["targets"])


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"vertical maturity tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
