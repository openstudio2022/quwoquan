"""面向读者的正文不得携带生产过程行话，且该禁令必须在创作前下发。

历史失败形态：`20260824--travel-homepage-m1-first--sichuan--pilot-002` 的乐山大佛
成稿写出「底稿所载管理部门回应」，被独立审阅丢弃。读者不知道「底稿」是什么——那是
我们与创作方之间的内部称谓，prompt 通篇用它指代来源，却没有一条禁止它进正文。
article lane 的 prompt renderer 早有同类禁令，homepage lane 缺失。

本测试把两侧钉在同一组常量上：门禁拦什么，prompt 就必须提前告知什么。只拦不告知
与只告知不拦是同一个缺陷的两面，都会让无人值守放量的通过率不可预期。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.entity_page_quality import (
    PRODUCTION_VOCABULARY_PHRASES,
    entity_page_quality_issues,
)

_READER_FACING_BODY = """# 乐山大佛

## 概况

乐山大佛开凿于唐代开元元年，历时约九十年建成，是世界上最大的石刻弥勒佛坐像。

## 历史沿革

唐开元元年动工，贞元十九年完工。宋代与明代均有修缮记录。
"""


def _write(tmp_path: Path, body: str) -> Path:
    page = tmp_path / "page.md"
    page.write_text(body, encoding="utf-8")
    return page


def test_reader_facing_body_is_not_flagged(tmp_path: Path) -> None:
    """真实成稿不得被误伤，否则这条门会被当成噪声绕过。"""

    assert entity_page_quality_issues(_write(tmp_path, _READER_FACING_BODY)) == []


def test_base_draft_reference_in_body_is_rejected(tmp_path: Path) -> None:
    """pilot-002 乐山大佛的真实丢弃原因，必须由确定性门拦下而非依赖审阅方主观发现。"""

    body = _READER_FACING_BODY + "\n据底稿所载管理部门回应，相关传闻并不属实。\n"
    issues = entity_page_quality_issues(_write(tmp_path, body), label="地点/景区/乐山大佛")

    assert any("底稿" in issue for issue in issues), issues
    assert all(issue.startswith("地点/景区/乐山大佛: ") for issue in issues), issues


@pytest.mark.parametrize("phrase", PRODUCTION_VOCABULARY_PHRASES)
def test_every_production_phrase_is_rejected(tmp_path: Path, phrase: str) -> None:
    """闭集里的每一条都必须真的拦得住，不允许挂而不用的装饰性常量。"""

    body = _READER_FACING_BODY + f"\n本段提到 {phrase} 这一生产过程称谓。\n"

    assert entity_page_quality_issues(_write(tmp_path, body)) != []


@pytest.mark.parametrize(
    "prompt_name",
    ("entity_homepage.system.md", "checkpoint_build_homepage.system.md"),
)
def test_authoring_prompt_forbids_what_the_gate_rejects(prompt_name: str) -> None:
    """门禁拦什么，创作方就必须在动笔前被告知什么——只拦不告知同样让通过率归零。

    首轮创作与修复轮各有入口，任一入口漏掉禁令都会让该轮成稿必然撞门。
    """

    from core.prompt_render import PROMPTS_ROOT

    prompt = (PROMPTS_ROOT / "homepage" / prompt_name).read_text(encoding="utf-8")
    never_block = prompt.split("<never>", 1)[1].split("</never>", 1)[0]

    assert "底稿" in never_block, f"{prompt_name} 用「底稿」指代来源，却未禁止它进正文"
