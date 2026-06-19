"""Content plan article candidate ordering is quality-driven."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from task.run import _article_source_quality_sort_key  # noqa: E402


def test_article_source_quality_sort_has_no_qunar_prefix_bias():
    candidates = [
        {
            "sourceId": "article_qunar_base_1",
            "sourceQualityScore": 0,
            "textLen": 3000,
            "rows": [{"fileName": "a.jpg"}],
        },
        {
            "sourceId": "article_xiaohongshu_base_1",
            "sourceQualityScore": 0,
            "textLen": 4800,
            "rows": [{"fileName": "b.jpg"}, {"fileName": "c.jpg"}],
        },
    ]
    ordered = sorted(candidates, key=_article_source_quality_sort_key)
    assert ordered[0]["sourceId"] == "article_xiaohongshu_base_1"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content plan quality sort tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
