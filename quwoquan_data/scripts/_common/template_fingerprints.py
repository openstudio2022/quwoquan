"""模板指纹门：拦截脚本 f-string 拼接的"定式句"冒充会话模型创作。

背景：历史上 produce 的正文由 route_workflow/_fact_sentence、_render_* 等用固定句式
拼接而成（如"真正难的从来不是把节点凑齐"），这些定式句高度可识别。会话模型真实创作
的自然行文几乎不可能逐字命中多条这种长定式。本模块把这些定式收成指纹库，review/verify
检测命中即判定为模板生成并阻断进入交付面。

新增模板句式时禁止往这里"放水删除"以掩盖机械生成；只允许在真正废弃某句式后清理对应行。
"""
from __future__ import annotations

import re

# STRONG：单条命中即判模板（足够长且高度独有，自然创作不会逐字出现）。
STRONG_FINGERPRINTS: tuple[str, ...] = (
    "出发前我犹豫最久的，不是要不要去",
    "真正难的从来不是把节点凑齐",
    "这类线路要先判断路线逻辑",
    "适合放在线路开头",
    "路线就进入需要认真算海拔和体力的阶段",
    "这一站真正值钱的是人文停留",
    "放在收束位置，是为了让返程前还有一个能把呼吸和节奏重新放慢",
    "跟团线最好选前一晚已在成都集合",
    "下单前我先看费用包含里",
    "凡是把观光车、特色体验或二次进沟留作现场自费项目",
    "退改规则一定要截图留底",
    "海拔与高反风险不是到高点才出现",
    "高原晴天最容易低估的是强紫外线",
    "昼夜温差大的线路不适合",
    "午后雷阵雨最怕的不是淋湿",
    "先把大交通方式算清楚",
    "真正影响体验的不是票面价格",
    "外地进川西最不该省掉的是休整安排",
    "总里程不是拿来吓人的数字",
    "补给点之间的间距",
    "应急避险最大的价值",
    "最佳季节不等于全年只有那一段能去",
    "出发地决定了你周末这条线能不能真正两天闭环",
    "门票和预约这些硬门槛",
    "真正值得提前确认的，是交通、住宿、体力和退路能不能彼此对上",
    "真正适合你的，不是节点最多的版本",
    "这样的长线来说，取舍比补景点更重要",
    "真正把线路写得可信，不在于景点名多",
    "我会把最累的一段和最想停留的一段错开",
    # entity_workflow 定式
    "能让人真正松弛下来，又怕它只是个被过度宣传的打卡点",
    "决定体验的从来不是名气",
    "的玩法，不是把每个角落都走遍",
    "先给我的不是名气，而是它现场的节奏感",
    "如果你也想看懂它，我会建议把时间留够",
    "把最想慢慢看的部分和最容易扎堆的时段错开",
    "真正让我愿意慢下来的，是那点绕着",
    "值得多留一晚的理由，常常就藏在",
    "真正劝退人的不是距离，而是",
)

# WEAK：较短句式，单条可能巧合，命中阈值 >= WEAK_BLOCK_THRESHOLD 才判模板。
WEAK_FINGERPRINTS: tuple[str, ...] = (
    "我最看重的是",
    "到了第二段，关注点会变成",
    "第三段如果只盯着打卡",
    "最后一段我更愿意把注意力留给",
    "如果同行的人节奏不一样",
    "我没急着把",
    "当成一个打卡点",
    "说实话，去之前我担心它被过度宣传",
    "我不会假装它完美",
)

WEAK_BLOCK_THRESHOLD = 2


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def detect_template_fingerprint(article: str) -> dict:
    """返回 {hits: [...], strongHits: [...], isTemplate: bool}。"""
    compact = _norm(article)
    strong_hits = [fp for fp in STRONG_FINGERPRINTS if _norm(fp) in compact]
    weak_hits = [fp for fp in WEAK_FINGERPRINTS if _norm(fp) in compact]
    is_template = bool(strong_hits) or len(weak_hits) >= WEAK_BLOCK_THRESHOLD
    return {
        "hits": strong_hits + weak_hits,
        "strongHits": strong_hits,
        "weakHits": weak_hits,
        "isTemplate": is_template,
    }


def template_fingerprint_issues(article: str) -> list[str]:
    """门禁问题列表（空=通过）。"""
    result = detect_template_fingerprint(article)
    if not result["isTemplate"]:
        return []
    issues: list[str] = []
    for fp in result["strongHits"]:
        issues.append(f"template fingerprint (strong): '{fp[:24]}'")
    if len(result["weakHits"]) >= WEAK_BLOCK_THRESHOLD:
        issues.append(
            f"template fingerprints (weak x{len(result['weakHits'])}): "
            + ", ".join(f"'{fp[:16]}'" for fp in result["weakHits"][:4])
        )
    return issues
