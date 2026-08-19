from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/content_service/content/post/verify_post_view_projection_wire_keys.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_post_view_projection_wire_keys_companion",
        GATE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_post_projection_rejects_every_bare_card_block_or_next_key(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    gate.ROOT = tmp_path
    gate.TARGET = tmp_path / "post_view_projection.dart"
    gate.TARGET.write_text(
        "card[ArticleCardWireKeys.title]; block[ArticleBlockWireKeys.body];\n",
        encoding="utf-8",
    )
    assert gate.main() == 0

    for bare_key in ("card['title']", 'block["body"]', "next['id']"):
        gate.TARGET.write_text(f"{bare_key};\n", encoding="utf-8")
        assert gate.main() == 1

    gate.TARGET.unlink()
    assert gate.main() == 1
