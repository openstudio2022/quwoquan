from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from content.source.professional_image_discovery import (
    CATALOG_PATH,
    ProfessionalImageDiscoveryError,
    create_professional_image_discovery_plan,
)
from content.source.research.image_provider_compliance import classify_image_provider


def test_professional_image_discovery_is_pinterest_first_and_tuchong_supplemental(
    tmp_path: Path,
) -> None:
    plan, path = create_professional_image_discovery_plan(
        entities=["西湖", "乌镇"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path,
    )

    assert path.is_file()
    assert plan["candidateCount"] == 12
    assert plan["providerCandidateCounts"] == [
        {"provider": "pinterest", "displayName": "Pinterest", "plannedAssetCount": 4},
        {"provider": "tuchong", "displayName": "图虫", "plannedAssetCount": 4},
        {
            "provider": "wikimedia_commons",
            "displayName": "Wikimedia Commons",
            "plannedAssetCount": 4,
        },
    ]
    pinterest = [row for row in plan["candidates"] if row["provider"] == "pinterest"]
    tuchong = [row for row in plan["candidates"] if row["provider"] == "tuchong"]
    commons = [
        row for row in plan["candidates"]
        if row["provider"] == "wikimedia_commons"
    ]
    assert all(row["priority"] == 0 for row in pinterest)
    assert all(row["manualSearchRequired"] is True for row in pinterest)
    assert all(row["discoveryUrl"] == "https://www.pinterest.com/" for row in pinterest)
    assert all(row["priority"] == 1 for row in tuchong)
    assert all(row["manualSearchRequired"] is True for row in tuchong)
    assert all(row["discoveryUrl"] == "https://tuchong.com/explore/" for row in tuchong)
    assert all(row["priority"] == 2 for row in commons)
    assert all(row["manualSearchRequired"] is False for row in commons)
    assert all(
        row["discoveryUrl"].startswith(
            "https://commons.wikimedia.org/w/index.php?search="
        )
        for row in commons
    )
    assert all(
        row["acquisitionPaths"] == ["supported_api", "manual_file"]
        for row in pinterest
    )
    assert all(
        row["acquisitionPaths"] == ["public_direct", "supported_api", "manual_file"]
        for row in tuchong
    )
    assert classify_image_provider(source_id="pinterest")["acquisitionPaths"] == [
        "manual_file",
        "supported_api",
    ]
    assert all(
        row["acquisitionPaths"] == ["supported_api", "manual_file"]
        for row in commons
    )
    assert classify_image_provider(source_id="wikimedia_commons")[
        "acquisitionPaths"
    ] == ["manual_file", "supported_api"]

    replay, replay_path = create_professional_image_discovery_plan(
        entities=["乌镇", "西湖"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path,
    )
    assert replay_path == path
    assert replay == plan


def test_professional_image_discovery_rejects_provider_priority_drift(tmp_path: Path) -> None:
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog["providerOrder"] = [
        "tuchong",
        "pinterest",
        "wikimedia_commons",
    ]
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(catalog, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ProfessionalImageDiscoveryError, match="Pinterest first"):
        create_professional_image_discovery_plan(
            entities=["西湖"],
            category="风光",
            season="秋季",
            style="纪实",
            viewpoint="航拍",
            popularity="热门",
            catalog_path=path,
            output_root=tmp_path / "out",
        )
