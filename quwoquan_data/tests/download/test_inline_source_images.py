"""RC3 子步C2：同源内联 <img> 候选构建 + 走五道硬门后回连段落占位的契约测试。

可直接运行：python3 quwoquan_data/tests/download/test_inline_source_images.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import io  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp(prefix="inline_img_rt_"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import download.handler_images as hi  # noqa: E402


def _jpeg(seed: int, size=(800, 600)) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class _OkVerdict:
    blocks_image_publish = False
    status = "ok"
    reasons: list[str] = []


def test_build_inline_image_candidates_maps_src_and_placeholder():
    rows = [
        {"placeholderId": "source-inline-001", "src": "https://img/a.jpg", "caption": "五花海"},
        {"placeholderId": "source-inline-002", "src": "https://img/b.jpg", "caption": ""},
        {"placeholderId": "", "src": "https://img/c.jpg", "caption": "无占位被跳过"},
        {"placeholderId": "source-inline-004", "src": "", "caption": "无src被跳过"},
        "not-a-mapping",
    ]
    out = hi.build_inline_image_candidates(rows, entity_id="九寨沟")
    assert [c["placeholderId"] for c in out] == ["source-inline-001", "source-inline-002"]
    assert [c["url"] for c in out] == ["https://img/a.jpg", "https://img/b.jpg"]
    assert out[0]["caption"] == "五花海"
    # 相关性用真实 caption，不用实体名拼接伪造；caption 为空则留空交相关性门判定。
    assert out[0]["relevance"] == "五花海"
    assert out[1]["relevance"] == ""


def test_build_inline_image_candidates_empty_input():
    assert hi.build_inline_image_candidates(None, entity_id="九寨沟") == []
    assert hi.build_inline_image_candidates([], entity_id="九寨沟") == []


def test_inline_candidate_flows_through_gates_with_placeholder():
    """内联候选与计划 imageUrls 合并走同一五道硬门；通过门后回连 placeholderId。"""
    saved: dict[str, object] = {}

    def patch(name: str, value) -> None:
        saved[name] = getattr(hi, name)
        setattr(hi, name, value)

    try:
        patch("validate_image_rights", lambda spec, vertical: [])
        patch("_cached_source_image_payload", lambda *a, **k: None)
        patch(
            "fetch_image_payload",
            lambda url, max_bytes=0: {
                "bytes": _jpeg(7),
                "ext": ".jpg",
                "url": url,
                "requestedUrl": url,
                "contentType": "image/jpeg",
                "sha256": "z",
            },
        )
        patch("image_dimensions", lambda b: (800, 600))
        patch("pixel_size_issue", lambda w, h, asset_id: None)
        patch(
            "_write_image_check_temp_file",
            lambda task_id, batch_id, subdir=None, payload=None: Path(tempfile.mkstemp()[1]),
        )
        patch("_assess_source_image", lambda temp, spec, task_id=None, batch_id=None: _OkVerdict())
        patch("_cleanup_image_check_temp_file", lambda p: None)
        patch("relevance_issue", lambda relevance, entity_id, asset_id: None)

        images, issues, funnel = hi._download_source_unit_images(
            {
                "source_id": "article_qunar_base",
                "imageUrls": [],
                "license": "internal-curated",
                "credit": "qunar",
                "url": "https://travel.qunar.com/youji/7870084",
            },
            task_id="旅行/地域/四川省/景区/x",
            batch_id="inline_gate",
            entity_id="九寨沟",
            object_dir=Path(tempfile.mkdtemp(prefix="inline_obj_")),
            ordinal=1,
            vertical="travel",
            extra_candidates=hi.build_inline_image_candidates(
                [
                    {
                        "placeholderId": "source-inline-001",
                        "src": "https://travel.qunar.com/photo/a.jpg",
                        "caption": "五花海高山湖泊实景",
                    }
                ],
                entity_id="九寨沟",
            ),
        )
    finally:
        for key, value in saved.items():
            setattr(hi, key, value)

    assert len(images) == 1, (issues, funnel)
    assert images[0]["placeholderId"] == "source-inline-001"
    assert images[0]["url"] == "https://travel.qunar.com/photo/a.jpg"
    assert funnel["candidateCount"] == 1


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"inline source image tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
