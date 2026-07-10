"""简体中文本地化门（确定性、离线）——发布字段必须是简体中文。

quwoquan 是面向中文读者的内容产品，**所有可发布字段**（标题 / 正文 / caption）
必须以简体中文呈现：

- 非中文来源（英文 / 拉丁主导，如 English Wikipedia、Unsplash 英文 caption）的正文 /
  标题 / caption，必须先「译为简体中文」后才能发布；
- 繁体来源（含繁体字，如 Wikivoyage 繁体、港台景区名）必须折叠为简体；
- 原文与出处由 source unit（``source.md`` + ``sourceUrl`` + ``provenance``）保留存档，
  本模块只对**发布字段**做「简体中文就绪」的确定性 validate，翻译语义由 Agent 阶段完成
  （CLI-first：``CLI prepare -> Agent translate -> CLI validate + gate``）。

唯一真相源约束（R06/R24）：CJK / 拉丁占比规则与繁→简折叠表集中在本模块；
caption 退化门（``asset_placement``）、繁简归一（``content_evidence``）与标题/正文发布门
全部复用本模块，禁止各处再各写一套占比阈值或折叠表。
"""
from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 拉丁主导阈值（与历史 caption 退化门同源）：拉丁字母 ≥ 6 且 ≥ 中文字符数 × 2。
_LATIN_DOMINANT_MIN = 6
_LATIN_DOMINANT_RATIO = 2

# 繁体 → 简体折叠表（旅游/地名/景区常见繁体字）。集中于此，供全仓共用。
_TRAD_TO_SIMP: dict[str, str] = {
    "亞": "亚",
    "畢": "毕",
    "雲": "云",
    "霧": "雾",
    "臺": "台",
    "颱": "台",
    "風": "风",
    "區": "区",
    "國": "国",
    "峽": "峡",
    "體": "体",
    "觀": "观",
    "遊": "游",
    "龍": "龙",
    "車": "车",
    "鐵": "铁",
    "門": "门",
    "頂": "顶",
    "園": "园",
    "級": "级",
    "廣": "广",
    "東": "东",
    "華": "华",
    "陰": "阴",
    "陽": "阳",
    "隨": "随",
    "縣": "县",
    "處": "处",
    "內": "内",
    "條": "条",
    "節": "节",
    "線": "线",
    "經": "经",
    "運": "运",
    "灣": "湾",
    "鹽": "盐",
    "鄉": "乡",
    "鎮": "镇",
    "賞": "赏",
    "獨": "独",
    "靈": "灵",
    "蠻": "蛮",
    "閣": "阁",
    "後": "后",
    "棧": "栈",
    "會": "会",
    "蓮": "莲",
    "鉆": "钻",
    "達": "达",
    "趙": "赵",
    "壩": "坝",
    "蔴": "麻",
    "溝": "沟",
    "雞": "鸡",
    "蕩": "荡",
    "臥": "卧",
    "廟": "庙",
    "寶": "宝",
    "樓": "楼",
    "宮": "宫",
    "寧": "宁",
    "藝": "艺",
    "義": "义",
    "爲": "为",
    "為": "为",
    "與": "与",
    "護": "护",
    "單": "单",
    "萬": "万",
    "聖": "圣",
    "積": "积",
    "興": "兴",
    "勝": "胜",
    "覺": "觉",
    "脫": "脱",
    "純": "纯",
    "嚴": "严",
    "燈": "灯",
    "昇": "升",
    "雜": "杂",
    "塵": "尘",
    "濕": "湿",
    "遺": "遗",
    "產": "产",
    "時": "时",
    "開": "开",
    "變": "变",
    "應": "应",
    "氣": "气",
    "覽": "览",
    "關": "关",
    "嶺": "岭",
    "崗": "岗",
    "橋": "桥",
    "雖": "虽",
    "則": "则",
    "說": "说",
    "數": "数",
    "幾": "几",
    "貫": "贯",
    "獻": "献",
    "裡": "里",
    "裏": "里",
    "麗": "丽",
    "嵋": "眉",
    "環": "环",
}
_FOLD_TABLE = str.maketrans(_TRAD_TO_SIMP)


def fold_to_simplified(value: str) -> str:
    """把常见繁体字折叠为简体（地名 / 景区常见字）。"""
    return str(value or "").translate(_FOLD_TABLE)


def has_traditional_chars(value: str) -> bool:
    """是否含需折叠为简体的繁体字（按折叠表命中）。"""
    return any(ch in _TRAD_TO_SIMP for ch in str(value or ""))


def latin_dominant(value: str) -> bool:
    """拉丁字母是否明显多于中文（英文 / 外文主导，发布前须译为简体中文）。

    阈值与 caption 退化门同源：拉丁字母 ≥ 6 且 ≥ 中文字符数 × 2。
    纯数字 / 标点（无拉丁字母）不算外文主导。
    """
    text = str(value or "")
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    return latin >= _LATIN_DOMINANT_MIN and latin >= cjk * _LATIN_DOMINANT_RATIO


def needs_translation_to_simplified(value: str) -> bool:
    """发布字段是否仍需译 / 折叠为简体中文（外文主导，或含繁体字）。"""
    text = str(value or "").strip()
    if not text:
        return False
    return latin_dominant(text) or has_traditional_chars(text)


def simplified_chinese_publish_issues(
    *, title: str = "", body: str = "", label: str = ""
) -> list[str]:
    """发布标题 / 正文「简体中文就绪」门：外文未译 / 繁体未折叠 → 阻断。

    翻译语义由 Agent 阶段完成；本门是确定性 validate，保证发布前标题 / 正文已是简体中文，
    原文与出处由 source unit 存档（不在本门内丢弃原文）。
    """
    issues: list[str] = []
    prefix = f"{label}: " if label else ""
    title_text = str(title or "").strip()
    if title_text:
        if latin_dominant(title_text):
            issues.append(f"{prefix}标题为外文/拉丁主导，须先译为简体中文后发布: {title_text!r}")
        elif has_traditional_chars(title_text):
            issues.append(f"{prefix}标题含繁体字，须折叠为简体中文后发布: {title_text!r}")
    body_text = str(body or "").strip()
    if body_text:
        if latin_dominant(body_text):
            issues.append(f"{prefix}正文为外文/拉丁主导，须先译为简体中文后发布")
        elif has_traditional_chars(body_text):
            issues.append(f"{prefix}正文含繁体字，须折叠为简体中文后发布")
    return issues


__all__ = [
    "fold_to_simplified",
    "has_traditional_chars",
    "latin_dominant",
    "needs_translation_to_simplified",
    "simplified_chinese_publish_issues",
]
