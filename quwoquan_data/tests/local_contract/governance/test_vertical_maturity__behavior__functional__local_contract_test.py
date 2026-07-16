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

from core.io import read_json  # noqa: E402
from content.release.environment.activation import write_activation_smoke_report  # noqa: E402
from content.release.environment.consistency import scan_release_contract  # noqa: E402
from governance.coverage.benchmark import evaluate_benchmark  # noqa: E402
from governance.coverage.coverage import evaluate_registry, list_verticals  # noqa: E402
from governance.coverage.governance import verify_vertical_script_governance  # noqa: E402
from governance.coverage.license import load_travel_license_policy, validate_image_rights  # noqa: E402
from governance.coverage.quality import verify_vertical_quality  # noqa: E402


def test_coverage_registry_reports_all_target_verticals():
    assert set(list_verticals()) >= {"travel", "photography", "campus"}
    for vertical in ("travel", "photography", "campus"):
        report = evaluate_registry(vertical)
        assert report["totals"]["units"] >= 2
        assert report["status"] in {"passed", "gap"}


def test_vertical_script_governance_passes_with_campus_wrappers():
    assert verify_vertical_script_governance() == []


def test_photography_image_rights_are_asset_level_not_platform_name_level():
    issues = validate_image_rights({"url": "https://example.com/a.jpg", "platform": "Pinterest"}, vertical="photography")
    assert any("missing required field license" in issue for issue in issues)
    assert not any("Pinterest" in issue for issue in issues)

    authorized = validate_image_rights(
        {
            "url": "https://example.com/a.jpg",
            "platform": "Pinterest",
            "license": "Unsplash License",
            "credit": "Original Creator",
            "sourceUrl": "https://example.com/original",
            "termsUrl": "https://unsplash.com/license",
            "usageScope": "app_publish",
            "authorizationProof": "https://example.com/original",
            "modelReleaseStatus": "not_required",
        },
        vertical="photography",
    )
    assert authorized == []


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
            "authorizationProof": "https://example.com/a",
            "modelReleaseStatus": "not_required",
        },
        vertical="photography",
    )
    assert issues == []


def test_travel_image_rights_are_asset_level_and_accept_authorized_payload():
    policy = load_travel_license_policy()
    assert policy["vertical"] == "travel"
    issues = validate_image_rights(
        {
            "url": "https://example.com/t.jpg",
            "platform": "小红书",
        },
        vertical="travel",
    )
    assert any("missing required field license" in issue for issue in issues), issues
    assert not any("灵感或参考" in issue for issue in issues), issues
    allowed = validate_image_rights(
        {
            "url": "https://example.com/t2.jpg",
            "platform": "景区官网",
            "license": "scenic_official_authorized",
            "credit": "九寨沟景区",
            "sourceUrl": "https://official.example/image",
            "termsUrl": "https://official.example/terms",
            "usageScope": "app_publish",
            "authorizationProof": "https://official.example/authorization",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert allowed == [], allowed


def test_travel_image_rights_accepts_versioned_commons_cc_licenses():
    base = {
        "url": "https://upload.wikimedia.org/example.jpg",
        "platform": "Wikimedia Commons",
        "credit": "Example photographer",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/3.0/",
        "usageScope": "app_publish",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "modelReleaseStatus": "not_required",
    }
    for license_value in (
        "CC BY 2.0",
        "CC BY-SA 2.0",
        "CC BY-SA 3.0",
        "CC BY 4.0",
        "Public domain",
    ):
        issues = validate_image_rights(
            {**base, "license": license_value},
            vertical="travel",
        )
        assert issues == [], (license_value, issues)


def test_travel_image_rights_requires_generated_asset_provenance():
    base = {
        "url": "file:///workspace/generated.png",
        "platform": "OpenAI image generation",
        "license": "AI Generated Original",
        "credit": "Quwoquan synthetic media pipeline",
        "sourceUrl": "file:///workspace/generated.png",
        "termsUrl": "file:///workspace/provenance.json",
        "usageScope": "app_publish",
        "authorizationProof": "file:///workspace/provenance.json",
        "modelReleaseStatus": "not_required",
    }
    missing = validate_image_rights(base, vertical="travel")
    assert any("generationModel" in issue for issue in missing), missing
    allowed = validate_image_rights(
        {
            **base,
            "generationModel": "gpt-image",
            "generationPromptHash": "sha256:abc",
            "generatedAt": "2026-06-13T00:00:00Z",
            "syntheticDisclosure": True,
        },
        vertical="travel",
    )
    assert allowed == [], allowed


def test_vertical_quality_gate_has_golden_samples():
    assert verify_vertical_quality() == []


def test_travel_source_registry_is_part_of_vertical_quality():
    issues = verify_vertical_quality()
    assert not any("source registry" in issue for issue in issues), issues


def test_post_activation_requires_smoke_report_and_active_release_match():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        contract = {
            "schemaVersion": "quwoquan_data.release_desired_state/1",
            "releaseId": "rel-1",
            "desiredRefs": {"entities": [], "posts": []},
            "actions": [],
        }
        run = root / "env/gamma/runs/data-release/rel-1/apply-1"
        report = scan_release_contract(
            contract,
            publish_root=root,
            env_run_root=run,
            metadata_root=root,
            phase="post-activation",
        )
        assert report["status"] == "failed"
        assert report["blockingIssues"][0]["code"] == "environment_evidence_missing"
        write_activation_smoke_report(
            contract,
            environment="gamma",
            run_id="apply-1",
            active_release_id="rel-1",
            output_root=root,
        )
        report = scan_release_contract(
            contract,
            publish_root=root,
            env_run_root=run,
            metadata_root=root,
            phase="post-activation",
        )
        assert report["status"] == "passed", report
        assert read_json(run / "activation-smoke.json")["activeReleaseId"] == "rel-1"


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
