"""单一质量门库（single gate library）。

本模块是"正文软质量 + 图文闭环 + 写作主线 + 模板骨架 + 语域"这几类
跨 review/verify 共享门的唯一真相源。produce review（route_workflow/
entity_workflow）与 verify（verify_content_quality/verify_content_semantics）
都必须 import 这里的函数，不得各自再写一套，避免双轨漂移（见整改计划第六阶段
"开发专家视角：单一 gate library"）。

设计约定：
- 每个门返回 `list[str]`（问题描述），空列表表示通过；不抛异常、不打印。
- 硬门（图文闭环、source reject、写作主线缺失）由调用方决定是否 blocking。
- 阈值集中在本模块顶部常量，便于 golden set 标定（见 gate-calibration-goldenset）。
- 仅依赖标准库，不 import produce/verify，避免循环依赖。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 写作主线（writingIntent）契约：顶层主线只描述读者任务，不描述具体实体。
# 垂类题材在 SOP 层细分，但规模化供给需要能表达“交通路线”和“季节时机”
# 这类常见决策主线，避免把 4 篇文章硬塞进 2 个 intent 造成模板化。
# ---------------------------------------------------------------------------
WRITING_INTENTS: dict[str, dict[str, Any]] = {
    "planning_consultation": {
        "label": "计划前咨询/攻略",
        "desc": "用户出行前快速了解：顺序、交通、票务、风险与取舍。",
        # 结构信号桶：每桶为同义线索，要求命中桶数 >= requireBuckets。
        "buckets": {
            "order": ["先", "再", "然后", "第一天", "第二天", "顺序", "动线", "路线", "行程"],
            "transport": ["怎么去", "交通", "自驾", "班车", "高铁", "机场", "包车", "大巴", "停车"],
            "ticket": ["门票", "票价", "预约", "开放时间", "时段", "旺季", "淡季", "排队"],
            "tradeoff": ["如果你", "建议", "宁可", "别赶", "取舍", "注意", "提醒", "避开"],
        },
        "requireBuckets": 3,
    },
    "decision_experience": {
        "label": "决策体验/值不值得去",
        "desc": "用户犹豫要不要去：体验价值、适合/不适合人群、真实得失。",
        "buckets": {
            "audience": ["适合", "不适合", "推荐给", "劝退", "更适合", "不建议"],
            "value": ["值不值", "值得", "性价比", "失望", "惊艳", "意外", "超出预期"],
            "feeling": ["喜欢", "不足", "遗憾", "打动", "失望", "心动", "踩雷"],
            "tradeoff": ["如果你", "我会建议", "取舍", "宁可", "与其"],
        },
        "requireBuckets": 3,
    },
    "post_trip_journal": {
        "label": "游后过程记录",
        "desc": "游玩后过程记录：时间线、现场感、情绪转折、复盘。",
        "buckets": {
            "timeline": ["那天", "清晨", "上午", "中午", "下午", "傍晚", "夜里", "第二天", "抵达", "出发", "当天"],
            "scene": ["走到", "站在", "眼前", "脚下", "排队", "等了", "遇到", "回头", "迎面"],
            "emotion": ["原本", "没想到", "突然", "庆幸", "后悔", "终于", "当时", "心里"],
            "review": ["回看", "如果重来", "下次", "复盘", "值得", "再去"],
        },
        "requireBuckets": 3,
    },
    "route_transport": {
        "label": "路线交通/到达方式",
        "desc": "用户决定怎么去、怎么串联节点：交通方式、换乘、自驾、步行动线与时间成本。",
        "buckets": {
            "origin": ["从", "出发", "抵达", "到达", "进出", "往返", "接驳"],
            "transport": ["交通", "自驾", "高铁", "机场", "班车", "公交", "包车", "停车", "换乘", "索道"],
            "sequence": ["先", "再", "然后", "顺路", "绕行", "动线", "路线", "节点", "入口", "出口"],
            "duration": ["小时", "分钟", "车程", "用时", "耗时", "排队", "停留"],
            "tradeoff": ["建议", "不建议", "如果你", "取舍", "避开", "更适合"],
        },
        "requireBuckets": 3,
    },
    "seasonal_timing": {
        "label": "季节时机/什么时候去",
        "desc": "用户决定何时去：季节、天气、花期/雪期/彩林、淡旺季、开放窗口与风险。",
        "buckets": {
            "season": ["春", "夏", "秋", "冬", "季节", "月份", "淡季", "旺季", "黄金周"],
            "phenology": ["花", "雪", "彩林", "云海", "日出", "日落", "冰川", "瀑布", "草甸", "湖水"],
            "weather": ["天气", "气温", "降雨", "降雪", "高反", "紫外线", "能见度", "封闭"],
            "timing": ["早上", "上午", "中午", "下午", "傍晚", "时间", "开放", "闭园", "窗口"],
            "tradeoff": ["建议", "不建议", "如果你", "取舍", "避开", "更适合"],
        },
        "requireBuckets": 3,
    },
}

# 模板骨架相似度阈值（跨篇）：标题序列 + 结尾段 + 段落 n-gram。
SKELETON_HEADING_SIMILARITY = 0.80
SKELETON_ENDING_SIMILARITY = 0.78
SKELETON_NGRAM_SIMILARITY = 0.62
SKELETON_NGRAM_SIZE = 8
INTRA_DOC_REPEAT_MIN_PARAGRAPH_CHARS = 24
INTRA_DOC_REPEAT_MAX_UNIQUE_RATIO = 0.55
INTRA_DOC_REPEAT_MAX_DUPLICATE_CHAR_RATIO = 0.28
INTRA_DOC_REPEAT_MIN_PARAGRAPH_COUNT = 5
INTRA_DOC_REPEAT_MIN_SENTENCE_CHARS = 16
INTRA_DOC_REPEAT_MIN_SENTENCE_COUNT = 3

# 写作主线一致性：命中桶数下限由各 intent 的 requireBuckets 决定。


def normalize_writing_intent(value: Any) -> str | None:
    """规范化 writingIntent 值；未知/缺失返回 None。"""
    if not value:
        return None
    text = str(value).strip()
    return text if text in WRITING_INTENTS else None


def writing_intent_issues(value: Any) -> list[str]:
    """校验 writingIntent 字段本身是否合法（契约门，content_plan/brief 用）。

    底稿中心模型：writingIntent 是底稿派生的可选标签——缺失不再报错（空=未派生/未知），
    仅当给出了**非法**取值时报错。
    """
    if not value:
        return []
    if normalize_writing_intent(value) is None:
        return [f"writingIntent invalid: {value!r}; allowed={sorted(WRITING_INTENTS)}"]
    return []


# 顶层三大主线：用于从底稿正文派生 publish 类目（angle）与软标签。
_TOP_LEVEL_INTENTS = ("planning_consultation", "decision_experience", "post_trip_journal")


def derive_writing_intent(text: str, *, default: str = "planning_consultation") -> str:
    """从单一底稿正文派生最贴合的 writingIntent 标签（命中结构桶最多者）。

    底稿中心模型下 writingIntent 不再硬阻断，只作 publish 类目与软评分提示；
    在三大顶层主线（攻略/体验/游记）间择优，无明显信号时回退 default。
    """
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return default
    best_intent, best_hits = default, -1
    for intent in _TOP_LEVEL_INTENTS:
        spec = WRITING_INTENTS[intent]
        hits = sum(1 for cues in spec["buckets"].values() if any(cue in compact for cue in cues))
        if hits > best_hits:
            best_hits, best_intent = hits, intent
    return best_intent


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
_WS_RE = re.compile(r"\s+")
_FIGURE_RE = re.compile(r":::figure[^\n]*\n(?:.*\n)*?:::", re.MULTILINE)
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9._:/\u4e00-\u9fff-]+)")


def _compact(text: str) -> str:
    return _WS_RE.sub("", text or "")


def _strip_figures(text: str) -> str:
    return _FIGURE_RE.sub("", text or "")


def _headings(text: str) -> list[str]:
    return [line.strip().lstrip("#").strip() for line in (text or "").splitlines() if line.strip().startswith("##")]


def _paragraphs(text: str) -> list[str]:
    body = _strip_figures(text or "")
    paras: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b or b.startswith("#") or b.startswith(">"):
            continue
        paras.append(b)
    return paras


def _normalized_blocks(blocks: Iterable[str], *, min_chars: int) -> list[str]:
    out: list[str] = []
    for block in blocks:
        compact = _compact(block)
        if len(compact) < min_chars:
            continue
        out.append(compact)
    return out


def _char_jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _ngrams(text: str, n: int) -> set[str]:
    compact = _compact(text)
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def _ngram_jaccard(a: str, b: str, n: int) -> float:
    ga, gb = _ngrams(a, n), _ngrams(b, n)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def intra_doc_repetition_issues(
    text: str,
    *,
    min_paragraph_chars: int = INTRA_DOC_REPEAT_MIN_PARAGRAPH_CHARS,
    max_unique_ratio: float = INTRA_DOC_REPEAT_MAX_UNIQUE_RATIO,
    max_duplicate_char_ratio: float = INTRA_DOC_REPEAT_MAX_DUPLICATE_CHAR_RATIO,
    min_paragraph_count: int = INTRA_DOC_REPEAT_MIN_PARAGRAPH_COUNT,
    min_sentence_chars: int = INTRA_DOC_REPEAT_MIN_SENTENCE_CHARS,
    min_sentence_count: int = INTRA_DOC_REPEAT_MIN_SENTENCE_COUNT,
) -> list[str]:
    """篇内重复/低信息熵门：拦截复读 padding、机械拼接的重复段落/句子。

    判定信号：
    1. 长段落重复 3 次及以上；
    2. 重复段落占正文字符比过高；
    3. 正文段落数足够但唯一段落占比过低（低信息熵）；
    4. 长句子重复 3 次及以上（覆盖单段内复读）。
    """
    issues: list[str] = []
    paras = _paragraphs(text)
    norm_paras = _normalized_blocks(paras, min_chars=min_paragraph_chars)
    if norm_paras:
        counts: dict[str, int] = {}
        for para in norm_paras:
            counts[para] = counts.get(para, 0) + 1
        repeated = [(para, cnt) for para, cnt in counts.items() if cnt >= 2]
        if repeated:
            repeated.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
            top_para, top_count = repeated[0]
            if top_count >= 3:
                issues.append(
                    "intraDocRepetition: repeated paragraph appears "
                    f"{top_count} times (sample='{top_para[:24]}...')"
                )
            total_chars = sum(len(para) for para in norm_paras)
            duplicate_chars = sum(len(para) * (cnt - 1) for para, cnt in repeated)
            if total_chars > 0 and duplicate_chars / total_chars >= max_duplicate_char_ratio:
                issues.append(
                    "intraDocRepetition: duplicated paragraphs occupy too much body text "
                    f"({duplicate_chars / total_chars:.2f} >= {max_duplicate_char_ratio:.2f})"
                )
        if len(norm_paras) >= min_paragraph_count:
            unique_ratio = len(set(norm_paras)) / len(norm_paras)
            if unique_ratio <= max_unique_ratio:
                issues.append(
                    "intraDocRepetition: unique paragraph ratio too low "
                    f"({unique_ratio:.2f} <= {max_unique_ratio:.2f})"
                )

    raw_sentences = re.split(r"[。！？!?；;\n]+", _strip_figures(text or ""))
    norm_sentences = _normalized_blocks(raw_sentences, min_chars=min_sentence_chars)
    if norm_sentences:
        sentence_counts: dict[str, int] = {}
        for sent in norm_sentences:
            sentence_counts[sent] = sentence_counts.get(sent, 0) + 1
        repeated_sentence = next(
            (
                (sent, cnt)
                for sent, cnt in sorted(
                    sentence_counts.items(),
                    key=lambda item: (-item[1], -len(item[0]), item[0]),
                )
                if cnt >= min_sentence_count
            ),
            None,
        )
        if repeated_sentence:
            sent, cnt = repeated_sentence
            issues.append(
                "intraDocRepetition: repeated sentence appears "
                f"{cnt} times (sample='{sent[:24]}...')"
            )

    return list(dict.fromkeys(issues))


# ---------------------------------------------------------------------------
# 结构形态量化门：章节占比 + 历史时间线单调性。
# 关键词命中式软门（情绪词/桶词/转场词）测不到“单源忠实照搬但章节失衡 / 平行
# 时间线拼接未归并”这类结构缺陷。这两道是可量化、低误报的硬结构门：
# 九寨沟「历史沿革」占正文约 70%、且末尾 2007→1979 时间倒错，二者都会被拦。
# ---------------------------------------------------------------------------
# 硬阈值标定（基于四川 scale100 真实样本）：0.55 只拦“单段过半且明显失衡”，
# 九寨沟(82%)/单段 99%/海螺沟(67%) 被拦；概况为主的均衡主页(47-51%)放行，
# 更细的均衡性由 P0-B LLM 语义复核做软判，避免硬门过严造成重生成振荡。
SECTION_BALANCE_MAX_RATIO_HOMEPAGE = 0.55
SECTION_BALANCE_MAX_RATIO_ARTICLE = 0.60
SECTION_BALANCE_MIN_SECTIONS = 2
SECTION_BALANCE_MIN_BODY_CHARS = 240

TIMELINE_MIN_YEARS = 6
TIMELINE_BACKWARD_DROP_YEARS = 12

_ASSET_DIRECTIVE_RE = re.compile(r"\{asset://[^}]*\}")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# 4 位年份（1xxx/20xx）后紧跟“年”，避免误命中“12000年前”这类非纪年数字。
_YEAR_TOKEN_RE = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?=\s*年)")
_SUBHEADING_RE = re.compile(r"(?m)^(#{2,6})\s+(.+?)\s*$")


def _section_units(text: str) -> list[tuple[str, str]]:
    """按 `##`+ 小标题切分正文，含首个小标题前的导语段（heading 为 ''）。

    用于结构形态门：先剥离 frontmatter、`{asset://}` 主页图片指令与 `:::figure` 块，
    再按二级及以下小标题切段；H1（`# 标题`）归入导语段。
    """
    body = _strip_figures(_ASSET_DIRECTIVE_RE.sub("", _FRONTMATTER_RE.sub("", text or "")))
    matches = list(_SUBHEADING_RE.finditer(body))
    if not matches:
        return [("", body.strip())]
    units: list[tuple[str, str]] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        units.append(("", preamble))
    for index, match in enumerate(matches):
        seg_start = match.end()
        seg_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        units.append((match.group(2).strip(), body[seg_start:seg_end].strip()))
    return units


def section_balance_issues(
    text: str,
    *,
    max_ratio: float,
    min_sections: int = SECTION_BALANCE_MIN_SECTIONS,
    min_body_chars: int = SECTION_BALANCE_MIN_BODY_CHARS,
) -> list[str]:
    """章节占比门：任一章节去空白字数 / 正文总字数 > max_ratio 即判结构失衡。

    直击“单源忠实照搬导致某一章节（如「历史沿革」）吞并主体篇幅”。
    章节数不足或正文过短时不判（避免短文误杀）。
    """
    sized = [(heading, len(_compact(body))) for heading, body in _section_units(text)]
    sized = [(heading, count) for heading, count in sized if count > 0]
    total = sum(count for _, count in sized)
    if len(sized) < min_sections or total < min_body_chars:
        return []
    issues: list[str] = []
    for heading, count in sized:
        ratio = count / total
        if ratio > max_ratio:
            issues.append(
                f"sectionBalance: 章节「{heading or '导语'}」占正文 {ratio * 100:.0f}% "
                f"(> {max_ratio * 100:.0f}%)，单章节过长导致结构失衡，"
                "应压缩或拆分，避免一段吞并其余应有章节"
            )
    return issues


def timeline_monotonicity_issues(
    text: str,
    *,
    min_years: int = TIMELINE_MIN_YEARS,
    backward_drop_years: int = TIMELINE_BACKWARD_DROP_YEARS,
) -> list[str]:
    """历史时间线单调门：章节内年份序列出现大幅回跳即判平行时间线未归并。

    直击“多条并列时间线（开发史/保护史/行政沿革）首尾拼接，造成
    2007→1979 这类时间倒错”。仅在章节年份数 >= min_years 时生效。
    """
    issues: list[str] = []
    for heading, body in _section_units(text):
        years = [int(value) for value in _YEAR_TOKEN_RE.findall(body)]
        if len(years) < min_years:
            continue
        running_max = years[0]
        worst_drop = 0
        worst_pair: tuple[int, int] | None = None
        for year in years[1:]:
            drop = running_max - year
            if drop > worst_drop:
                worst_drop = drop
                worst_pair = (running_max, year)
            running_max = max(running_max, year)
        if worst_drop > backward_drop_years and worst_pair is not None:
            hi, lo = worst_pair
            issues.append(
                f"timelineOrder: 章节「{heading or '导语'}」时间线非单调，"
                f"出现 {hi}→{lo} 的回跳（{worst_drop} 年），疑似平行时间线拼接未归并，"
                "请按时间顺序归并为单一叙事"
            )
    return issues


# ---------------------------------------------------------------------------
# 门 1：图文引用闭环硬门——有 assets 就必须进正文，不只做封面。
# ---------------------------------------------------------------------------
def image_reference_closure_issues(
    article: str,
    assets: Sequence[Mapping[str, Any]],
    *,
    carrier: str = "article",
    route_node_count: int = 0,
) -> list[str]:
    """当存在可用图片资产时，正文必须以 asset:// 引用至少一张图。

    - article 载体：assets 非空 → 正文至少 1 处 asset:// 引用。
    - route 文（route_node_count>=3）：正文 figure/asset 引用数应 >= min(节点数, 可用图数)，
      鼓励按节点插图，不允许全部图片只做封面。
    """
    usable = [a for a in (assets or []) if a.get("assetId")]
    if not usable:
        return []
    refs = _ASSET_REF_RE.findall(article or "")
    issues: list[str] = []
    if carrier == "gallery":
        return issues  # gallery 由 carrierConsistency/galleryCaption 管控
    if not refs:
        issues.append(
            f"imageReferenceClosure: {len(usable)} usable asset(s) but body references none "
            f"(image only used as cover is not allowed)"
        )
        return issues
    if route_node_count >= 3:
        want = min(route_node_count, len(usable))
        if len(set(refs)) < min(want, 2):
            issues.append(
                f"imageReferenceClosure: route article references {len(set(refs))} image(s) in body "
                f"but should bind images to nodes (want>= {min(want, 2)})"
            )
    return issues


# ---------------------------------------------------------------------------
# 门 2：写作主线一致性——writingIntent 与正文结构匹配。
# ---------------------------------------------------------------------------
def writing_intent_consistency_issues(article: str, writing_intent: Any) -> list[str]:
    intent = normalize_writing_intent(writing_intent)
    if intent is None:
        # 契约门已在别处校验非法值；此处仅在合法时做一致性检查。
        return []
    spec = WRITING_INTENTS[intent]
    compact = _compact(_strip_figures(article or ""))
    hit_buckets = 0
    missing: list[str] = []
    for bucket, cues in spec["buckets"].items():
        if any(cue in compact for cue in cues):
            hit_buckets += 1
        else:
            missing.append(bucket)
    need = int(spec.get("requireBuckets", 3))
    if hit_buckets < need:
        return [
            f"writingIntentConsistency: intent={intent} expects >= {need} structural buckets, "
            f"hit {hit_buckets} (missing: {', '.join(missing)})"
        ]
    return []


# ---------------------------------------------------------------------------
# 门 3：模板骨架相似度（跨篇）——换实体名同骨架。
# ---------------------------------------------------------------------------
def skeleton_similarity_issues(article: str, peers: Iterable[str]) -> list[str]:
    """比较本篇与同批其它文章的章节序列/结尾段/段落 n-gram 相似度。

    peers 为同批其它文章正文（不含本篇）。任一维度超阈值即判模板骨架复用。
    """
    issues: list[str] = []
    my_heads = "›".join(_headings(article))
    my_paras = _paragraphs(article)
    my_ending = my_paras[-1] if my_paras else ""
    my_body = "\n".join(my_paras)
    for peer in peers:
        if not peer:
            continue
        peer_heads = "›".join(_headings(peer))
        if my_heads and peer_heads:
            sim = _char_jaccard(my_heads, peer_heads)
            if sim >= SKELETON_HEADING_SIMILARITY:
                issues.append(f"skeletonSimilarity: heading sequence too similar to a peer ({sim:.2f})")
                break
        peer_paras = _paragraphs(peer)
        peer_ending = peer_paras[-1] if peer_paras else ""
        if my_ending and peer_ending and _char_jaccard(my_ending, peer_ending) >= SKELETON_ENDING_SIMILARITY:
            issues.append("skeletonSimilarity: ending paragraph too similar to a peer")
            break
        peer_body = "\n".join(peer_paras)
        if my_body and peer_body and _ngram_jaccard(my_body, peer_body, SKELETON_NGRAM_SIZE) >= SKELETON_NGRAM_SIMILARITY:
            issues.append("skeletonSimilarity: paragraph n-gram overlap too high with a peer")
            break
    return issues


# ---------------------------------------------------------------------------
# 门 4：编辑语域门——词表由垂类 SOP 提供，公共层不写死。
# ---------------------------------------------------------------------------
def register_lexicon_issues(article: str, banned_register_terms: Sequence[str]) -> list[str]:
    """命中 SOP 提供的禁用语域词即报问题（如户外景区出现"看展/展厅/展陈"）。"""
    if not banned_register_terms:
        return []
    compact = _compact(_strip_figures(article or ""))
    hits = sorted({term for term in banned_register_terms if term and term in compact})
    if hits:
        return [f"registerMismatch: banned register terms for this subject: {', '.join(hits)}"]
    return []


# ---------------------------------------------------------------------------
# 门 5：source reject 阻断——禁止引用被判 Reject 的来源。
# ---------------------------------------------------------------------------
def source_reject_block_issues(
    cited_source_refs: Sequence[str],
    reject_source_refs: Iterable[str],
) -> list[str]:
    """正文/manifest 引用的来源不得命中 source screen 判 Reject 的集合。"""
    rejected = {str(r) for r in reject_source_refs if r}
    if not rejected:
        return []
    hits = sorted({str(c) for c in cited_source_refs if str(c) in rejected})
    if hits:
        return [f"sourceRejectBlock: cited source(s) were screened as reject: {', '.join(hits)}"]
    return []


# ---------------------------------------------------------------------------
# 门 8：联系方式门——拦截私人电话/微信/QQ，仅放行公共号码（白名单由调用方传入）。
# 白名单真相源：_common/public_contacts.py（templates/_registry/catalogs/public_contacts.yaml）。
# 本模块只依赖标准库，allowed_numbers 由调用方加载后传入。
# ---------------------------------------------------------------------------
_DIGITS_ONLY_RE = re.compile(r"\D+")
# 手机号 / 座机（带区号）/ 全国服务号段。
_PHONE_RES = [
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),          # 手机号 11 位
    re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)"),  # 座机 区号-号码
    re.compile(r"(?<!\d)(?:400|800)[-\s]?\d{3,4}[-\s]?\d{3,4}(?!\d)"),  # 400/800
]
# 微信 / QQ 等私人即时通讯账号：任何情况下都不允许出现在编辑正文。
_WECHAT_RE = re.compile(r"(?:微信|wechat|weixin|加微|vx|VX)\s*[:：]?\s*[A-Za-z0-9_-]{4,}", re.IGNORECASE)
_QQ_RE = re.compile(r"(?:QQ|qq)\s*[:：]?\s*\d{5,12}")
# 短号紧急号（110/120/119/122/12301 等）在白名单内单独命中。
_SHORT_NUM_RE = re.compile(r"(?<!\d)(?:1\d{2,4})(?!\d)")


def _normalize_number(raw: str) -> str:
    return _DIGITS_ONLY_RE.sub("", str(raw or ""))


def contact_info_issues(
    article: str,
    *,
    allowed_numbers: Iterable[str] = (),
) -> list[str]:
    """联系方式门：拦截正文中的私人电话/微信/QQ。

    - 微信/QQ 账号：一律拦截（私人联系方式，不得出现在编辑内容）。
    - 电话号码：归一化后不在 allowed_numbers（公共短号 + 核实的景区官方电话）即拦截。
    allowed_numbers 已归一化为纯数字串集合（由 _common/public_contacts.allowed_numbers 提供）。
    """
    body = _strip_figures(article or "")
    issues: list[str] = []
    allowed = {_normalize_number(n) for n in allowed_numbers if _normalize_number(n)}

    if _WECHAT_RE.search(body):
        issues.append("contactInfo: 正文出现微信号（私人联系方式），禁止出现在编辑内容")
    if _QQ_RE.search(body):
        issues.append("contactInfo: 正文出现 QQ 号（私人联系方式），禁止出现在编辑内容")

    blocked: set[str] = set()
    for rex in _PHONE_RES:
        for m in rex.finditer(body):
            num = _normalize_number(m.group(0))
            if num and num not in allowed:
                blocked.add(m.group(0).strip())
    if blocked:
        issues.append(
            "contactInfo: 正文出现非公开电话 " + ", ".join(sorted(blocked))
            + "（仅放行紧急/公共服务短号与 source 核实的景区官方电话）"
        )
    return issues


# ---------------------------------------------------------------------------
# 门 9：机械标题门——拦截清单式/工程式小标题，要求口语化人性化表达。
# 反例（拦截）："节点顺序""实用信息""注意事项""行程安排""门票信息"；
# 正例（放行）："先去哪后去哪：我推荐的顺序""去之前我踩过的坑"。
# 词表可由调用方 extra 扩展（SOP / wording catalog）。
# ---------------------------------------------------------------------------
MECHANICAL_HEADING_TERMS: tuple[str, ...] = (
    "节点顺序",
    "实用信息",
    "注意事项",
    "行程安排",
    "交通指南",
    "交通信息",
    "门票信息",
    "门票价格",
    "最佳时间",
    "最佳时节",
    "周边推荐",
    "基本信息",
    "概况介绍",
    "景点介绍",
    "游玩攻略",
    "温馨提示",
    "出行贴士",
)


def mechanical_heading_issues(
    article: str,
    *,
    extra_terms: Iterable[str] = (),
) -> list[str]:
    """机械标题门：正文小标题（## ）命中清单式/工程式词即拦截。

    命中后要求改写成口语化、有视角的小标题（带"我/你/为什么/怎么"或叙事感）。
    """
    terms = set(MECHANICAL_HEADING_TERMS) | {str(t).strip() for t in extra_terms if str(t).strip()}
    hits: list[str] = []
    for heading in _headings(article):
        norm = _WS_RE.sub("", heading)
        for term in terms:
            if term and term in norm:
                hits.append(heading)
                break
    if hits:
        return [
            "mechanicalHeading: 小标题过于清单化/工程化，请改成口语化有视角的表达："
            + " | ".join(hits)
        ]
    return []


# ---------------------------------------------------------------------------
# 门 6：语义去重（SimHash 第二指标）——覆盖"换实体名同骨架"。
# n-gram jaccard 对换名敏感；SimHash 对局部改写鲁棒，两者互补构成双指标。
# ---------------------------------------------------------------------------
SIMHASH_NGRAM = 4
SIMHASH_BITS = 64
# golden set 标定：换名同骨架对 ~0.81，次高（非同骨架）≤0.61，good 对 ≤0.60。
# 取 0.80 在两簇之间留裕度，既拦换名同骨架又不误杀。
SEMANTIC_DUP_SIMHASH = 0.80


def simhash64(text: str) -> int:
    tokens = _ngrams(_strip_figures(text or ""), SIMHASH_NGRAM)
    if not tokens:
        return 0
    weights = [0] * SIMHASH_BITS
    for tok in tokens:
        h = int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(SIMHASH_BITS):
            weights[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(SIMHASH_BITS):
        if weights[i] > 0:
            out |= 1 << i
    return out


def simhash_similarity(a: str, b: str) -> float:
    ha, hb = simhash64(a), simhash64(b)
    return simhash_similarity_from_hashes(ha, hb)


def simhash_similarity_from_hashes(ha: int, hb: int) -> float:
    if ha == 0 or hb == 0:
        return 0.0
    hamming = bin(ha ^ hb).count("1")
    return 1.0 - hamming / SIMHASH_BITS


def semantic_duplicate_issues(
    article: str,
    peers: Iterable[str],
    *,
    threshold: float = SEMANTIC_DUP_SIMHASH,
    article_hash: int | None = None,
    peer_hashes: Iterable[int] | None = None,
) -> list[str]:
    """SimHash 语义去重：与任一 peer 相似度 >= 阈值即判语义重复（换名同骨架）。"""
    ha = simhash64(article) if article_hash is None else article_hash
    if peer_hashes is None:
        peer_hash_iter = (simhash64(peer) for peer in peers if peer)
    else:
        peer_hash_iter = (int(peer_hash or 0) for peer_hash in peer_hashes)
    for hb in peer_hash_iter:
        sim = simhash_similarity_from_hashes(ha, hb)
        if sim >= threshold:
            return [f"semanticDuplicate: simhash similarity to a peer too high ({sim:.2f} >= {threshold})"]
    return []


# ---------------------------------------------------------------------------
# 门 7：rubric 评审稳定性（双轨软质量的判官可信度）。
# rubric 评分由会话模型（LLM-as-judge）产出；本函数只校验判官稳定性，
# 不替代评审本身。同输入多次评分方差过大 → 判官不可信，门失效。
# ---------------------------------------------------------------------------
RUBRIC_MAX_STDEV = 1.0  # rubric 评分按 0-10，标准差上限


def rubric_consistency_issues(scores: Sequence[float], *, max_stdev: float = RUBRIC_MAX_STDEV) -> list[str]:
    vals = [float(s) for s in scores if s is not None]
    if len(vals) < 2:
        return []
    mean = sum(vals) / len(vals)
    stdev = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5
    if stdev > max_stdev:
        return [f"rubricConsistency: judge stdev {stdev:.2f} exceeds {max_stdev} (judge unstable, gate untrusted)"]
    return []
