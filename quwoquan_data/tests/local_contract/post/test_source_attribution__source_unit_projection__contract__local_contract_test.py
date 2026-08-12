"""SourceAttribution remains source-owned through Article/Image materialization."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.post import source_attribution as subject  # noqa: E402
from core.io import write_json  # noqa: E402
from core.source_attribution import canonical_source_attribution  # noqa: E402

ATTRIBUTION = {
    "isOriginal": False,
    "originalCreatorId": None,
    "originalCreatorName": "摄影师甲",
    "originalCreatorProfileUrl": "https://media.example/creators/a",
    "platform": "Wikimedia Commons",
    "sourcePostUrl": "https://media.example/posts/dujiangyan",
    "originalAssetUrl": "https://media.example/assets/dujiangyan.jpg",
    "attributionText": "摄影师甲 / CC BY-SA 4.0",
    "rightsBasis": "CC BY-SA 4.0",
    "commercialAuthorizationStatus": "verified",
    "publicationAdmission": "commercial_release",
    "authorizationProofUrl": "https://media.example/proofs/dujiangyan",
    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    "riskAcceptanceId": None,
    "watermarkStatus": "absent",
    "audioRightsStatus": "no_audio",
    "modelReleaseStatus": "not_required",
    "propertyReleaseStatus": "not_required",
    "collectedAt": "2026-08-11T00:00:00Z",
    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
}


def _source_unit(root: Path) -> str:
    unit = root / "sources" / "source-a"
    unit.mkdir(parents=True)
    (unit / "source.md").write_text("# 都江堰", encoding="utf-8")
    write_json(unit / "meta.json", {"sourceAttribution": ATTRIBUTION})
    return "sources/source-a/source.md"


def test_source_unit_projection_is_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _source_unit(tmp_path)
    monkeypatch.setattr(subject, "execution_root", lambda _execution_id: tmp_path)
    observed = subject.source_unit_attribution(
        "execution-a",
        "article",
        compose_payload={
            "baseSourceRef": source_ref,
            "sourceUrls": [ATTRIBUTION["sourcePostUrl"]],
        },
        assets=[],
    )
    assert observed == ATTRIBUTION


def test_source_url_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_ref = _source_unit(tmp_path)
    monkeypatch.setattr(subject, "execution_root", lambda _execution_id: tmp_path)
    with pytest.raises(ValueError, match="sourcePostUrl drifts"):
        subject.source_unit_attribution(
            "execution-a",
            "article",
            compose_payload={
                "baseSourceRef": source_ref,
                "sourceUrls": ["https://media.example/posts/other"],
            },
            assets=[],
        )


def test_incomplete_attribution_is_rejected() -> None:
    incomplete = {key: value for key, value in ATTRIBUTION.items() if key != "rightsBasis"}
    with pytest.raises(ValueError, match="rightsBasis"):
        canonical_source_attribution(incomplete)


def test_source_unit_symlink_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.md").write_text("# outside", encoding="utf-8")
    write_json(outside / "meta.json", {"sourceAttribution": ATTRIBUTION})
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "source-a").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(subject, "execution_root", lambda _execution_id: tmp_path)
    with pytest.raises(ValueError, match="meta is unavailable"):
        subject.source_unit_attribution(
            "execution-a",
            "image",
            compose_payload={"sourceUrls": [ATTRIBUTION["sourcePostUrl"]]},
            assets=[{"sourceRef": "sources/source-a/source.md"}],
        )
