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
from _common import paths as paths_mod  # noqa: E402
from _common.batch_asset_registry import BatchAssetRegistry, allocate_post_asset_id, load_batch_asset_registry  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import batch_entity_object_dir, batch_root  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"
BATCH = "registry_case"


def _cli_env() -> dict[str, str]:
    """CLI 子进程 env 与父进程已冻结的 paths 常量对齐。

    pytest 全量一起跑时，其他测试模块会在导入期改写 os.environ 的 QWQ_* 根，
    而本进程 paths 常量在首次导入时已冻结——子进程若裸继承 os.environ 会读到
    另一个 tempfile 根导致 batch not found。显式回传常量根，保证父子一致。
    """
    return {
        **os.environ,
        "QWQ_DATA_ROOT": str(paths_mod.DATA_ROOT),
        "QWQ_RUNTIME_ROOT": str(paths_mod.RUNTIME_ROOT),
        "QWQ_PUBLISH_ROOT": str(paths_mod.PUBLISH_ROOT),
    }


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


def test_allocate_is_idempotent_across_recompose_reload():
    """recompose 漂移防回归：重跑 compose（重新从磁盘 load registry）必须返回同一 assetId。"""
    batch = f"{BATCH}_recompose"
    reg1 = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=9)
    aid_first = allocate_post_asset_id(
        entity_name="峨眉山", role="cover", ref="峨眉山_攻略", global_batch_seq=9, registry=reg1,
    )
    # 模拟下一轮 compose：全新 registry 从磁盘加载，再次分配同 owner_key
    reg2 = load_batch_asset_registry(TASK, batch, 9)
    aid_again = allocate_post_asset_id(
        entity_name="峨眉山", role="cover", ref="峨眉山_攻略", global_batch_seq=9, registry=reg2,
    )
    assert aid_first == aid_again, "recompose 必须复用同一 assetId，禁止漂移"


def test_rename_asset_id_syncs_registry_after_fold():
    """繁简折叠改名后 registry 必须同步，否则目录证据链门判 registry↔manifest 断链。"""
    batch = f"{BATCH}_fold_rename"
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=2)
    aid = allocate_post_asset_id(
        entity_name="澳门威尼斯人",
        role="detail",
        ref="sources/澳门威尼斯人__encyclopedia__x/assets/002.jpg",
        global_batch_seq=2,
        registry=registry,
        caption="興建中的「威尼斯人」攝於2007",
    )
    assert "興建中的" in aid
    folded = aid.replace("興建中的", "兴建中的")
    assert registry.rename_asset_id(aid, folded) is True
    saved = load_batch_asset_registry(TASK, batch, 2)
    assert folded in saved.asset_ids
    assert aid not in saved.asset_ids
    assert list(saved.entries.values()) == [folded]
    # 幂等：再 rename 同一对返回 False（old 已不存在）
    assert saved.rename_asset_id(aid, folded) is False


def test_rename_asset_id_collision_raises():
    batch = f"{BATCH}_fold_collision"
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=2)
    aid_a = allocate_post_asset_id(
        entity_name="峨眉山", role="cover", ref="a", global_batch_seq=2, registry=registry, caption="金顶"
    )
    aid_b = allocate_post_asset_id(
        entity_name="峨眉山", role="detail", ref="b", global_batch_seq=2, registry=registry, caption="金顶"
    )
    try:
        registry.rename_asset_id(aid_a, aid_b)
        raise AssertionError("rename collision must raise RuntimeError")
    except RuntimeError as exc:
        assert "rename collision" in str(exc)


def test_fold_homepage_manifest_assets_renames_registry():
    """build/homepage 的折叠步骤必须把 registry 一起改名（消费同一真相源）。"""
    from build.homepage import _fold_homepage_manifest_assets

    batch = f"{BATCH}_fold_pipeline"
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=2)
    aid = allocate_post_asset_id(
        entity_name="澳门威尼斯人",
        role="detail",
        ref="sources/澳门威尼斯人__encyclopedia__x/assets/003.jpg",
        global_batch_seq=2,
        registry=registry,
        caption="澳門威尼斯人度假村酒店夜景",
    )
    assets_dir = batch_root(TASK, batch) / "entities" / "地点" / "景区" / "澳门威尼斯人" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / f"{aid}.jpg").write_bytes(b"stub")
    rows = [{"assetId": aid, "fileName": f"{aid}.jpg", "caption": "澳門威尼斯人度假村酒店夜景"}]
    _fold_homepage_manifest_assets(rows, assets_dir, task_id=TASK, batch_id=batch)
    new_id = rows[0]["assetId"]
    assert new_id != aid and "澳门" in new_id
    assert (assets_dir / rows[0]["fileName"]).is_file()
    saved = load_batch_asset_registry(TASK, batch, 2)
    assert new_id in saved.asset_ids
    assert aid not in saved.asset_ids


def test_allocate_post_asset_id_retries_on_collision():
    registry = BatchAssetRegistry(task_id=TASK, batch_id=f"{BATCH}_collision", global_batch_seq=8)
    original = asset_identity.compute_post_asset_id

    def fake_compute_post_asset_id(
        *,
        entity_name: str,
        role: str,
        global_batch_seq: int | str,
        ref: str = "",
        nonce: int = 0,
        caption: str = "",
        section_slug: str = "",
        ordinal: int = 0,
    ) -> str:
        if nonce == 0:
            return "峨眉山_cover_实景_8_deadbeef"
        return f"{asset_identity.asset_token(entity_name)}_{role}_实景_{int(global_batch_seq)}_{nonce:08x}"

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

    assert first == "峨眉山_cover_实景_8_deadbeef"
    assert second != first
    assert second.startswith("乐山大佛_cover_实景_8_")
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
        env=_cli_env(),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert batch_root(TASK, batch).is_dir()


def test_verify_asset_id_zero_collision_counts_image_manifest_without_gallery():
    batch = "registry_image_cli"
    write_batch_manifest(TASK, batch, command="task_run")
    from _common.batch_manifest import load_batch_manifest

    global_seq = int(load_batch_manifest(TASK, batch)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=global_seq)
    cover = allocate_post_asset_id(
        entity_name="峨眉山",
        role="cover",
        ref="峨眉山_image",
        global_batch_seq=global_seq,
        registry=registry,
    )
    obj = batch_root(TASK, batch) / "posts" / "image" / "攻略" / "峨眉山·云海" / "1"
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "assets").mkdir(parents=True, exist_ok=True)
    (obj / "assets" / f"{cover}.jpg").write_bytes(b"image")
    write_json(obj / "_object.json", {"ref": "峨眉山_image", "contentType": "image"})
    write_json(
        obj / "manifest.json",
        {"contentType": "image", "assets": [{"assetId": cover, "fileName": f"{cover}.jpg"}]},
    )

    cli = SCRIPTS_ROOT / "verify" / "verify_asset_id_zero_collision.py"
    result = subprocess.run(
        [sys.executable, str(cli), "--task", TASK, "--batch", batch],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_env(),
    )
    assert result.returncode == 0, result.stderr + result.stdout


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch asset registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
