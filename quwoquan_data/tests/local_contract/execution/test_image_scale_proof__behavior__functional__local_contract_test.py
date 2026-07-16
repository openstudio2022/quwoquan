"""Open-license image scale proof tests."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from itertools import count
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_image_scale_proof_"))
for _readonly_dir in ("schema",):
    src = DATA_ROOT / _readonly_dir
    dst = _TMP / _readonly_dir
    if dst.exists():
        continue
    try:
        dst.symlink_to(src, target_is_directory=True)
    except OSError:
        shutil.copytree(src, dst)

from core.io import write_json  # noqa: E402
from core.paths import STAGE_DOWNLOAD  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir  # noqa: E402
from content.execution import store  # noqa: E402
from content.execution.selection import build_multimodal_spec  # noqa: E402
from content.source.image_scale_proof import (  # noqa: E402
    apply_open_license_scale_proof_to_execution,
    build_open_license_scale_proof,
)

_SEQUENCE = count(1)


def _make_task(
    name: str,
    targets: list[str],
    *,
    image_count_policy: str = "score_bonus",
    minimum_images_per_target: int = 0,
) -> str:
    execution_id = f"20260711--travel-image-scale-proof--cn-zhejiang--canary-{next(_SEQUENCE):03d}"
    spec = build_multimodal_spec(
        execution_id=execution_id,
        name=name,
        title=name,
        region="中国/浙江省",
        category="景区",
        targets=[{"entityType": "地点/景区", "name": target} for target in targets],
        created_by="test",
        entity_articles_per_target=4,
        entity_homepages_per_target=1,
        image_works_per_target=2,
        target_entity_count=len(targets),
    )
    spec["content"]["research"]["imageCountPolicy"] = image_count_policy
    spec["content"]["research"]["minimumPublishableImagesPerTarget"] = minimum_images_per_target
    spec["status"] = "active"
    store.save_spec(spec)
    store.save_progress(store.init_progress(spec["executionId"]))
    return spec["executionId"]


def _write_image_plan(execution_id: str, entity: str, count: int) -> None:
    dl = resolve_entity_object_dir(execution_id, entity, etype_hint="地点/景区") / STAGE_DOWNLOAD
    collections = []
    for index in range(1, count + 1):
        collection_id = f"commons:{entity}:{index}"
        collections.append(
            {
                "sourceCollectionId": collection_id,
                "creator": f"Creator {index}",
                "credit": f"Creator {index}",
                "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:{entity}_{index}.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "licenseSnapshot": "CC BY-SA 4.0 recorded on Wikimedia Commons file page",
                "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{entity}_{index}.jpg",
                "usageScope": "app_publish",
                "images": [
                    {
                        "url": f"https://upload.wikimedia.org/{entity}_{index}.jpg",
                        "license": "CC BY-SA 4.0",
                        "credit": f"Creator {index}",
                        "sourceUrl": f"https://commons.wikimedia.org/wiki/File:{entity}_{index}.jpg",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "licenseSnapshot": "CC BY-SA 4.0 recorded on Wikimedia Commons file page",
                        "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{entity}_{index}.jpg",
                        "usageScope": "app_publish",
                        "width": 1200,
                        "height": 800,
                        "sourceCollectionId": collection_id,
                        "creator": f"Creator {index}",
                        "researchLane": "image",
                    }
                ],
            }
        )
    write_json(dl / "image_source_plan.json", {"payload": {"collections": collections}})


def test_open_license_scale_proof_passes_and_can_apply_task():
    execution_id = _make_task("开放许可证明通过", ["景区甲", "景区乙"])
    execution_id = execution_id
    _write_image_plan(execution_id, "景区甲", 2)
    _write_image_plan(execution_id, "景区乙", 2)

    report = build_open_license_scale_proof(execution_id)

    assert report["passed"] is True
    assert report["proof"]["preScreenedEntityCount"] == 2
    assert report["proof"]["scoredEntityCount"] == 2
    assert report["proof"]["publishableImageAssets"] == 4
    assert report["desiredPassed"] is True
    assert report["averageImageCountScore"] == 1.0
    apply_open_license_scale_proof_to_execution(execution_id, report["proof"])
    raw = store.load_raw_spec(execution_id)
    assert raw["content"]["research"]["openLicenseScaleProof"]["publishableImageAssets"] == 4


def test_open_license_scale_proof_scores_below_desired_without_failing_soft_policy():
    execution_id = _make_task("开放许可证明软评分", ["景区甲", "景区乙"])
    execution_id = execution_id
    _write_image_plan(execution_id, "景区甲", 2)
    _write_image_plan(execution_id, "景区乙", 1)

    report = build_open_license_scale_proof(execution_id)

    assert report["passed"] is True
    assert report["desiredPassed"] is False
    assert report["proof"]["preScreenedEntityCount"] == 2
    assert report["belowDesiredEntitySample"] == ["景区乙"]
    assert report["entities"][1]["imageCountScore"] == 0.5
    assert report["averageImageCountScore"] == 0.75


def test_open_license_scale_proof_fails_when_hard_quota_entity_lacks_required_images():
    execution_id = _make_task(
        "开放许可证明失败",
        ["景区甲", "景区乙"],
        image_count_policy="hard_quota",
    )
    execution_id = execution_id
    _write_image_plan(execution_id, "景区甲", 2)
    _write_image_plan(execution_id, "景区乙", 1)

    report = build_open_license_scale_proof(execution_id)

    assert report["passed"] is False
    assert report["proof"]["preScreenedEntityCount"] == 1
    assert report["failedEntitySample"] == ["景区乙"]
