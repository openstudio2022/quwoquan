"""批内资产 ID registry 契约测试。"""
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

_TMP = Path(tempfile.mkdtemp(prefix="batch_asset_registry_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common import asset_identity  # noqa: E402
from _common.batch_asset_registry import BatchAssetRegistry, allocate_post_asset_id, load_batch_asset_registry  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import batch_entity_object_dir, batch_root  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"
BATCH = "registry_case"


def test_allocate_post_asset_id_reuses_same_owner_key():
    registry = BatchAssetRegistry(task_id=TASK, batch_id=BATCH, global_batch_seq=7)
    aid1 = allocate_post_asset_id(
        entity_name="峨眉山",
        role="cover",
        ref="峨眉山_攻略",
        global_batch_seq=7,
        registry=registry,
    )
    aid2 = allocate_post_asset_id(
        entity_name="峨眉山",
        role="cover",
        ref="峨眉山_攻略",
        global_batch_seq=7,
        registry=registry,
    )
    assert aid1 == aid2
    saved = load_batch_asset_registry(TASK, BATCH, 7)
    assert aid1 in saved.asset_ids
    assert saved.resolve("7|峨眉山_攻略|峨眉山|cover") == aid1


def test_allocate_post_asset_id_retries_on_collision():
    registry = BatchAssetRegistry(task_id=TASK, batch_id=f"{BATCH}_collision", global_batch_seq=8)
    original = asset_identity.compute_post_asset_id

    def fake_compute_post_asset_id(*, entity_name: str, role: str, global_batch_seq: int | str, ref: str = "", nonce: int = 0) -> str:
        if nonce == 0:
            return "峨眉山_cover_8_deadbeef"
        return f"{asset_identity.asset_token(entity_name)}_{role}_{int(global_batch_seq)}_{nonce:08x}"

    asset_identity.compute_post_asset_id = fake_compute_post_asset_id
    try:
        first = allocate_post_asset_id(
            entity_name="峨眉山",
            role="cover",
            ref="峨眉山_攻略",
            global_batch_seq=8,
            registry=registry,
        )
        second = allocate_post_asset_id(
            entity_name="乐山大佛",
            role="cover",
            ref="乐山大佛_攻略",
            global_batch_seq=8,
            registry=registry,
        )
    finally:
        asset_identity.compute_post_asset_id = original

    assert first == "峨眉山_cover_8_deadbeef"
    assert second != first
    assert second.startswith("乐山大佛_cover_8_")
    assert second in registry.asset_ids


def test_verify_asset_id_zero_collision_cli_passes():
    batch = "registry_cli"
    write_batch_manifest(TASK, batch, command="task_run")
    from _common.batch_manifest import load_batch_manifest

    global_seq = int(load_batch_manifest(TASK, batch)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=global_seq)
    cover = allocate_post_asset_id(
        entity_name="峨眉山",
        role="cover",
        ref="峨眉山_攻略",
        global_batch_seq=global_seq,
        registry=registry,
    )
    detail = allocate_post_asset_id(
        entity_name="峨眉山",
        role="detail",
        ref="峨眉山_攻略",
        global_batch_seq=global_seq,
        registry=registry,
    )
    obj = batch_entity_object_dir(TASK, batch, "地点", "景区", "峨眉山")
    obj.mkdir(parents=True, exist_ok=True)
    write_json(obj / "_entity.json", {"label": "峨眉山", "domain": "地点", "type": "景区"})
    write_json(
        obj / "manifest.json",
        {
            "assets": [
                {"assetId": cover, "fileName": f"{cover}.jpg"},
                {"assetId": detail, "fileName": f"{detail}.jpg"},
            ]
        },
    )
    cli = SCRIPTS_ROOT / "verify" / "verify_asset_id_zero_collision.py"
    result = subprocess.run(
        [sys.executable, str(cli), "--task", TASK, "--batch", batch],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert batch_root(TASK, batch).is_dir()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch asset registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
