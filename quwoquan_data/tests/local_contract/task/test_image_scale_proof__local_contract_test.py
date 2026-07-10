"""Open-license image scale proof tests."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_image_scale_proof_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
for _readonly_dir in ("schema", "sop"):
    src = DATA_ROOT / _readonly_dir
    dst = _TMP / _readonly_dir
    if dst.exists():
        continue
    try:
        dst.symlink_to(src, target_is_directory=True)
    except OSError:
        shutil.copytree(src, dst)

from _common.io import write_json  # noqa: E402
from _common.paths import STAGE_DOWNLOAD  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from task import store  # noqa: E402
from task.image_scale_proof import (  # noqa: E402
    apply_open_license_scale_proof_to_task,
    build_open_license_scale_proof,
)


def _make_task(
    name: str,
    targets: list[str],
    *,
    image_count_policy: str = "score_bonus",
    minimum_images_per_target: int = 0,
) -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name=name,
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": target}
                for target in targets
            ],
        },
        content={
            "modalityContract": "separated_research",
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
            },
            "research": {
                "imageAssetStrategy": "open_license_publish",
                "imageCountPolicy": image_count_policy,
                "minimumPublishableImagesPerTarget": minimum_images_per_target,
                "allowAiImages": False,
            },
        },
        created_by="test",
    )
    spec["status"] = "active"
    store.save_spec(spec)
    store.save_progress(store.init_progress(spec["taskId"]))
    return spec["taskId"]


def _write_image_plan(task_id: str, batch_id: str, entity: str, count: int) -> None:
    dl = resolve_entity_object_dir(task_id, batch_id, entity, etype_hint="地点/景区") / STAGE_DOWNLOAD
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
    task_id = _make_task("开放许可证明通过", ["景区甲", "景区乙"])
    batch_id = "proof_ok"
    _write_image_plan(task_id, batch_id, "景区甲", 2)
    _write_image_plan(task_id, batch_id, "景区乙", 2)

    report = build_open_license_scale_proof(task_id, batch_id)

    assert report["passed"] is True
    assert report["proof"]["preScreenedEntityCount"] == 2
    assert report["proof"]["scoredEntityCount"] == 2
    assert report["proof"]["publishableImageAssets"] == 4
    assert report["desiredPassed"] is True
    assert report["averageImageCountScore"] == 1.0
    apply_open_license_scale_proof_to_task(task_id, report["proof"])
    raw = store.load_raw_spec(task_id)
    assert raw["content"]["research"]["openLicenseScaleProof"]["publishableImageAssets"] == 4


def test_open_license_scale_proof_scores_below_desired_without_failing_soft_policy():
    task_id = _make_task("开放许可证明软评分", ["景区甲", "景区乙"])
    batch_id = "proof_fail"
    _write_image_plan(task_id, batch_id, "景区甲", 2)
    _write_image_plan(task_id, batch_id, "景区乙", 1)

    report = build_open_license_scale_proof(task_id, batch_id)

    assert report["passed"] is True
    assert report["desiredPassed"] is False
    assert report["proof"]["preScreenedEntityCount"] == 2
    assert report["belowDesiredEntitySample"] == ["景区乙"]
    assert report["entities"][1]["imageCountScore"] == 0.5
    assert report["averageImageCountScore"] == 0.75


def test_open_license_scale_proof_fails_when_hard_quota_entity_lacks_required_images():
    task_id = _make_task(
        "开放许可证明失败",
        ["景区甲", "景区乙"],
        image_count_policy="hard_quota",
    )
    batch_id = "proof_hard_fail"
    _write_image_plan(task_id, batch_id, "景区甲", 2)
    _write_image_plan(task_id, batch_id, "景区乙", 1)

    report = build_open_license_scale_proof(task_id, batch_id)

    assert report["passed"] is False
    assert report["proof"]["preScreenedEntityCount"] == 1
    assert report["failedEntitySample"] == ["景区乙"]
