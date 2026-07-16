"""游记感密度门 contract tests：出发动机 + 喜欢/不喜欢 + 取舍 + 注意事项就地融入。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_travelogue_density__behavior__functional__local_contract_test.py
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

from content.post.route_review_checks import _check_travelogue_density  # noqa: E402

CONTRACT = {
    "openingTension": {"required": True},
    "explicitFeelings": {"requireLike": True, "requireDislike": True},
    "decisionPoints": {"required": True, "minPoints": 2},
    "tipsEmbeddingPolicy": {"forbidStandaloneBlock": True},
}


def test_dead_itinerary_fails_red():
    """死板行程介绍：无动机、无喜欢/不喜欢、无取舍、带独立实用信息块 -> 红。"""
    article = (
        "# 稻城亚丁经典线\n\n"
        "第一天从成都出发到康定，第二天到稻城，第三天游览亚丁，第四天返回。\n\n"
        "## 实用信息\n\n来源平台：携程攻略。门票约150元。\n"
    )
    result = _check_travelogue_density(article, CONTRACT)
    assert result["passed"] is False
    joined = " ".join(result["issues"])
    assert "motivation" in joined
    assert "like" in joined and "dislike" in joined
    assert "decision" in joined
    assert "standalone" in joined


def test_travelogue_passes_green():
    article = (
        "# 稻城亚丁慢游\n\n"
        "出发前我犹豫最久的，不是要不要去，而是这条线值得慢下来走，还是会被赶路拖垮——"
        "我既盼着那点松弛感，又怕一上来就硬撑着把自己累垮。\n\n"
        "## 第1站：康定\n\n我会先把节奏放稳，如果你也怕高反，宁可在康定多睡一晚。\n\n"
        "愿意停下来的理由，是清晨那条街的安静。\n\n"
        "## 出发前真正要看什么\n\n海拔和体力要算明白，我更愿意把住宿订在低海拔，这样第二天不至于难受。\n"
    )
    result = _check_travelogue_density(article, CONTRACT)
    assert result["passed"] is True, result["issues"]


def test_standalone_tips_block_blocked():
    article = (
        "# 线路\n\n出发前我有点犹豫，但还是想去，既期待又怕累。我会优先看交通，如果你赶时间宁可减点。\n\n"
        "## 小贴士：\n\n带好证件。\n"
    )
    result = _check_travelogue_density(article, CONTRACT)
    assert result["passed"] is False
    assert any("standalone" in i for i in result["issues"])


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"travelogue density tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
