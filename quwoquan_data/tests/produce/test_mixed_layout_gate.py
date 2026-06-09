"""图文混合编排 layout 门 contract tests。

可直接运行：python3 quwoquan_data/tests/produce/test_mixed_layout_gate.py
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

import sys
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from produce.route_workflow import _check_mixed_layout  # noqa: E402


def _fig(aid: str, cap: str) -> str:
    return f":::figure\n![{cap}](asset://{aid})\n{cap}\n:::"


def test_no_or_single_figure_is_exempt():
    assert _check_mixed_layout("# t\n\n正文。\n")["passed"] is True
    one = f"# t\n\n## a\n\n{_fig('a1','x')}\n\n正文。\n"
    assert _check_mixed_layout(one)["passed"] is True


def test_well_interspersed_passes():
    body = "# t\n\n" + "## 一\n\n" + "正" * 120 + f"\n\n{_fig('a1','晨雾')}\n\n"
    body += "## 二\n\n" + "文" * 120 + f"\n\n{_fig('a2','草甸')}\n\n"
    body += "## 三\n\n" + "末" * 120 + f"\n\n{_fig('a3','傍晚')}\n\n"
    res = _check_mixed_layout(body)
    assert res["passed"] is True, res["issues"]


def test_clustered_figures_fail():
    body = "# t\n\n" + f"{_fig('a1','x')}\n\n{_fig('a2','y')}\n\n" + "正" * 800 + "\n"
    res = _check_mixed_layout(body)
    assert res["passed"] is False
    assert any("clustered" in i for i in res["issues"])


def test_empty_figure_block_fails():
    body = "# t\n\n## a\n\n:::figure\n\n:::\n\n" + "正" * 50 + f"\n\n## b\n\n{_fig('a2','y')}\n"
    res = _check_mixed_layout(body)
    assert res["passed"] is False
    assert any("empty" in i for i in res["issues"])


def test_large_text_gap_fails():
    body = "# t\n\n## a\n\n" + f"{_fig('a1','x')}\n\n" + "正" * 1500 + f"\n\n{_fig('a2','y')}\n"
    res = _check_mixed_layout(body)
    assert res["passed"] is False
    assert any("gap" in i for i in res["issues"])


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"mixed layout gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
