"""主页商用质量硬门（P2 单一真相源，100% deterministic、可对任意 page.md 重放）。

审计 P0 逃逸样本驱动（M1 实测）：
- 罗泉古镇：360/百科编辑壳（「折叠编辑本段」）、infobox 键值堆（「## 基本信息」+
  中文名/车牌代码/邮政编码…）作为正文穿透 approved；
- 隆昌石牌坊/泸沽湖：模型在 `[[IMG:fig_NN]]` 占位行尾追加图注，违反独占行协议；
- 浙江多成品缺 H1；
- factual_reference_only 与 licensed_adaptation 同策略（近逐字复用 99.5% fidelity）。

分层：
- `final_page_hard_issues`：成品 page.md 最终页硬门（结构/污染/乱码/重复/最小信息量）。
- `draft_placeholder_issues`：author 产出 draft 的占位符协议硬门（独占行、ID 集不可变）。
- `copyright_mode_issues`：版权模式分离硬门（factual_reference_only 强制重写+压缩）。
- `map_like_asset_issues`：isMapLike 最终兜底。
- `independent_review_issues`：review 独立性硬门（独立 run、非同源、异模型族）。

既有 `core/entity_page_quality.py`（工程短语/重复/章节均衡）与
`build/homepage_validation.py`（三段结构/资产闭环）仍然生效；本模块是商用收口
新增维度，`evaluate_commercial_page` 聚合三者为唯一商用判定入口。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from core import quality_gates as qg

_H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")
_H2_SECTION_RE = re.compile(r"(?ms)^##\s+([^\n]+)\n(.*?)(?=^##\s|\Z)")
_PLACEHOLDER_LINE_RE = re.compile(r"^\[\[IMG:(fig_[0-9]{2,})\]\]$")
_PLACEHOLDER_ANY_RE = re.compile(r"\[\[IMG:(fig_[0-9]{2,})\]\]")
_FOOTNOTE_RE = re.compile(r"\[\d{1,3}\]")
_HTML_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d{2,6}|[a-zA-Z]{2,8});")
_HTML_TAG_RE = re.compile(r"</?(?:div|span|table|td|tr|th|ul|li|a|img|p|br)\b[^>]*>", re.I)

# 百科编辑壳与导航/登录/推荐残留（360 百科、百度百科抓取壳特征）。
BAIKE_SHELL_MARKERS: tuple[str, ...] = (
    "折叠编辑本段",
    "编辑本段",
    "折叠 编辑本段",
    "查看我的收藏",
    "有用+1",
    "已投票",
    "词条统计",
    "浏览次数",
    "编辑次数",
    "最近更新",
    "词条创建者",
    "百科名片",
    "免责声明",
    "登录后查看",
    "展开全部",
    "收起全部",
    "点击加载更多",
    "相关推荐",
    "猜你喜欢",
    "百度首页",
    "进入词条",
    "全站搜索",
    "秒懂百科",
)

# infobox 键值堆特征字段：正文独立成行出现 ≥3 个即判定 infobox 未转事实列表。
INFOBOX_FIELD_MARKERS: tuple[str, ...] = (
    "中文名",
    "外文名",
    "别    名",
    "别名",
    "电话区号",
    "车牌代码",
    "邮政编码",
    "行政区类别",
    "地理位置",
    "气候条件",
    "占地面积",
    "开放时间",
    "门票价格",
    "著名景点",
    "所属城市",
    "所属国家",
    "建议游玩时长",
    "适宜游玩季节",
    "景点级别",
    "拼    音",
    "方    言",
)

_EMPTY_REFERENCE_HEADINGS = ("参考资料", "参考来源", "参考文献", "外部链接")

# factual_reference_only 抄写硬门：5-gram 字符重合率上限。
FACTUAL_REFERENCE_MAX_FIDELITY = 0.55
# factual_reference_only 压缩硬门：len(page)/len(source) 上限（按 source 长度分档）。
FACTUAL_COMPRESSION_TIERS: tuple[tuple[int, float], ...] = (
    (2000, 0.65),  # source > 2000 字：目标压缩约 50%，上限 0.65
    (1000, 0.85),  # 1000–2000 字：中度压缩
    (0, 1.0),      # <1000 字：少压缩但仍必须重写（fidelity 门管住）
)

MIN_SECTION_CHARS = 40
MIN_BODY_CHARS = 200


def _body_without_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :]
    return text


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def final_page_hard_issues(
    page_text: str,
    *,
    entity_name: str = "",
    label: str = "",
) -> list[str]:
    """成品 page.md 最终页硬门（deterministic，可重放）。"""
    prefix = f"{label}: " if label else ""
    issues: list[str] = []
    body = _body_without_frontmatter(page_text)

    # H1 硬门：恰好一个，且与实体名一致（实体名给出时）。
    h1s = _H1_RE.findall(body)
    if len(h1s) != 1:
        issues.append(f"{prefix}H1 必须恰好一个（实得 {len(h1s)}）")
    elif entity_name and _compact(h1s[0]) != _compact(entity_name):
        issues.append(f"{prefix}H1 「{h1s[0]}」与实体名「{entity_name}」不一致")

    # 百科编辑壳/导航/登录/推荐残留。
    for marker in BAIKE_SHELL_MARKERS:
        if marker in body:
            issues.append(f"{prefix}正文残留百科编辑壳/导航文案: {marker!r}")

    # infobox 键值堆（未转事实列表）。
    lines = [line.strip() for line in body.splitlines()]
    infobox_hits = [
        marker
        for marker in INFOBOX_FIELD_MARKERS
        if any(line == marker or line.replace(" ", "") == marker.replace(" ", "") for line in lines)
    ]
    if len(infobox_hits) >= 3:
        issues.append(
            f"{prefix}正文残留 infobox 键值堆（{'、'.join(infobox_hits[:5])}…），"
            "必须转为事实列表或剔除"
        )

    # 脚注/HTML 实体/HTML 标签穿透。
    footnotes = _FOOTNOTE_RE.findall(body)
    if len(footnotes) >= 2:
        issues.append(f"{prefix}正文残留百科脚注标记 {footnotes[:4]}")
    entities = _HTML_ENTITY_RE.findall(body)
    if entities:
        issues.append(f"{prefix}正文残留 HTML 实体 {sorted(set(entities))[:4]}")
    tags = _HTML_TAG_RE.findall(body)
    if tags:
        issues.append(f"{prefix}正文残留 HTML 标签 {sorted(set(tags))[:4]}")

    # 乱码：Unicode 替换符或私用区字符。
    bad_chars = {ch for ch in body if ch == "\ufffd" or unicodedata.category(ch) in ("Co", "Cn")}
    if bad_chars:
        issues.append(f"{prefix}正文含乱码字符 {sorted(bad_chars)[:4]}")

    # 占位符残留（最终页禁止任何 [[IMG:*]]）。
    leftover = _PLACEHOLDER_ANY_RE.findall(body)
    if leftover:
        issues.append(f"{prefix}最终页残留图片占位符 {sorted(set(leftover))[:4]}")

    # 空壳参考来源章节。
    for heading, section_body in _H2_SECTION_RE.findall(body):
        title = heading.strip()
        if any(marker in title for marker in _EMPTY_REFERENCE_HEADINGS):
            if len(_compact(section_body)) < 10:
                issues.append(f"{prefix}「{title}」为空壳章节（必须删除或补真实来源）")

    # 章节最小信息量 + 正文最小体量。
    plain_body = _PLACEHOLDER_ANY_RE.sub("", body)
    for heading, section_body in _H2_SECTION_RE.findall(plain_body):
        title = heading.strip()
        if title == "相关图片":
            continue
        compact_len = len(_compact(re.sub(r":::[a-z]+[^\n]*\n|:::", "", section_body)))
        if compact_len < MIN_SECTION_CHARS:
            issues.append(
                f"{prefix}章节「{title}」信息量不足（{compact_len} 字 < {MIN_SECTION_CHARS}）"
            )
    if len(_compact(plain_body)) < MIN_BODY_CHARS:
        issues.append(f"{prefix}正文总量不足 {MIN_BODY_CHARS} 字")

    # 重复段落（复用共同层实现，保持单一真相源）。
    issues.extend(f"{prefix}{issue}" for issue in qg.intra_doc_repetition_issues(body))
    return issues


def draft_placeholder_issues(
    draft_text: str,
    expected_fig_ids: Sequence[str],
    *,
    label: str = "",
) -> list[str]:
    """author draft 占位符协议硬门。

    - 每个 `[[IMG:fig_NN]]` 必须独占一行（行内不得有图注/文字——隆昌石牌坊/泸沽湖违规态）；
    - 占位 ID 集合与顺序必须与 writing pack 注入的 expected_fig_ids 完全一致
      （不得增删、不得重排、不得改写 ID）。
    """
    prefix = f"{label}: " if label else ""
    issues: list[str] = []
    seen_ids: list[str] = []
    for line_no, line in enumerate(draft_text.splitlines(), start=1):
        stripped = line.strip()
        hits = _PLACEHOLDER_ANY_RE.findall(stripped)
        if not hits:
            continue
        if len(hits) > 1:
            issues.append(f"{prefix}L{line_no} 一行出现多个占位符 {hits}")
            seen_ids.extend(hits)
            continue
        if not _PLACEHOLDER_LINE_RE.match(stripped):
            issues.append(
                f"{prefix}L{line_no} 占位符未独占一行（禁止行尾追加图注/文字）: {stripped[:60]!r}"
            )
        seen_ids.extend(hits)
    expected = [str(f) for f in expected_fig_ids]
    if seen_ids != expected:
        issues.append(
            f"{prefix}占位符 ID 序列漂移: draft={seen_ids} expected={expected}"
            "（集合与顺序均不可变）"
        )
    return issues


def _char_ngrams(text: str, n: int = 5) -> set[str]:
    compact = _compact(text)
    return {compact[i : i + n] for i in range(max(0, len(compact) - n + 1))}


def source_fidelity(page_text: str, source_text: str) -> float:
    """page 相对 source 的 5-gram 字符重合率（page 视角 containment）。"""
    page_grams = _char_ngrams(_body_without_frontmatter(page_text))
    source_grams = _char_ngrams(source_text)
    if not page_grams:
        return 0.0
    return len(page_grams & source_grams) / len(page_grams)


def copyright_mode_issues(
    page_text: str,
    source_text: str,
    source_use_mode: str,
    *,
    label: str = "",
) -> list[str]:
    """版权模式分离硬门。

    - `licensed_adaptation`：允许署名/许可证下轻润色（fidelity 不设上限，
      署名/许可证证据由 manifest 资产门校验）；
    - `factual_reference_only`：只抽取事实并强制重写——fidelity 超过
      FACTUAL_REFERENCE_MAX_FIDELITY 或压缩不足即 BLOCK；禁止沿用 99.5% 上限。
    """
    prefix = f"{label}: " if label else ""
    mode = str(source_use_mode or "").strip()
    if mode == "licensed_adaptation":
        return []
    if mode != "factual_reference_only":
        return [f"{prefix}未知 sourceUseMode {mode!r}（fail-closed，允许值见 source_inputs）"]
    issues: list[str] = []
    fidelity = source_fidelity(page_text, source_text)
    if fidelity > FACTUAL_REFERENCE_MAX_FIDELITY:
        issues.append(
            f"{prefix}factual_reference_only 抄写超限: fidelity={fidelity:.3f} > "
            f"{FACTUAL_REFERENCE_MAX_FIDELITY}（必须事实抽取后重写）"
        )
    source_len = len(_compact(source_text))
    page_len = len(_compact(_body_without_frontmatter(page_text)))
    if source_len > 0:
        ratio = page_len / source_len
        for threshold, max_ratio in FACTUAL_COMPRESSION_TIERS:
            if source_len > threshold:
                if ratio > max_ratio:
                    issues.append(
                        f"{prefix}factual_reference_only 压缩不足: source={source_len}字 "
                        f"page={page_len}字 ratio={ratio:.2f} > {max_ratio}"
                    )
                break
    return issues


def map_like_asset_issues(
    manifest_payload: Mapping[str, Any],
    *,
    label: str = "",
) -> list[str]:
    """isMapLike 最终兜底：任何标记为地图态的资产不得进入成品 manifest。"""
    prefix = f"{label}: " if label else ""
    issues: list[str] = []
    for raw in manifest_payload.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        asset_id = str(raw.get("assetId") or raw.get("fileName") or "<unknown>")
        if bool(raw.get("isMapLike")):
            issues.append(f"{prefix}asset {asset_id} 标记 isMapLike，禁止进入成品")
        caption = str(raw.get("originalCaption") or raw.get("caption") or "")
        if re.search(r"(?:导览图|平面图|路线图|地图|示意图)$", caption.strip()):
            issues.append(
                f"{prefix}asset {asset_id} 图注疑似地图态（{caption.strip()[:20]!r}），"
                "需 isMapLike 复核"
            )
    return issues


def independent_review_issues(
    review_payload: Mapping[str, Any],
    author_envelope: Mapping[str, Any],
    *,
    label: str = "",
) -> list[str]:
    """review 独立性硬门：独立 run、非同源布尔自证、异模型族。"""
    prefix = f"{label}: " if label else ""
    issues: list[str] = []
    review_run = str(review_payload.get("runId") or "").strip()
    author_run = str(author_envelope.get("runId") or "").strip()
    if not author_run:
        issues.append(f"{prefix}author 缺独立 runId（无法证明 review 非同源）")
    if not review_run:
        issues.append(f"{prefix}review 缺独立 runId（不得复用 author issues 布尔值自证）")
    elif author_run and review_run == author_run:
        issues.append(f"{prefix}review runId 与 author 相同（非独立 run）")
    review_family = str(review_payload.get("modelFamily") or "").strip()
    author_family = str(author_envelope.get("modelFamily") or "").strip()
    if not author_family:
        issues.append(f"{prefix}author 缺 modelFamily")
    if not review_family:
        issues.append(f"{prefix}review 缺 modelFamily")
    elif author_family and review_family == author_family:
        issues.append(
            f"{prefix}review 模型族 {review_family} 与 author 相同（reviewer 必须异模型族）"
        )
    if "issues" not in review_payload and "findings" not in review_payload:
        issues.append(f"{prefix}review 缺独立 findings（不得只回填 approved 布尔）")
    return issues


def provenance_checksum_issues(
    page_text: str,
    provenance_payload: Mapping[str, Any] | None,
    *,
    label: str = "",
) -> list[str]:
    """finalize checksum 一致性硬门（隆昌石牌坊/泸沽湖 SHA 漂移回归）。

    - 成品缺 provenance → BLOCK（商用页必须可追溯）；
    - provenance.final.articleDigest 与当前 page.md digest 不一致 → BLOCK
      （finalize 之后被改写 / 图注注入发生在 provenance 之后）。
    """
    from core.article_package import compute_document_sha256

    prefix = f"{label}: " if label else ""
    if not provenance_payload:
        return [f"{prefix}缺 provenance（商用页必须具备 finalize 证据链）"]
    expected = str(
        ((provenance_payload.get("final") or {}).get("articleDigest"))
        or provenance_payload.get("articleMarkdownDigest")
        or ""
    ).strip()
    if not expected:
        return [f"{prefix}provenance 缺 final.articleDigest（无法校验 finalize checksum）"]
    actual = compute_document_sha256(page_text)
    if actual != expected:
        return [
            f"{prefix}page.md digest 与 provenance 漂移: actual={actual[:12]}… "
            f"expected={expected[:12]}…（finalize 后被改写）"
        ]
    return []


def evaluate_commercial_page(
    entity_dir: Path,
    *,
    entity_name: str = "",
    source_text: str = "",
    source_use_mode: str = "",
    provenance_payload: Mapping[str, Any] | None = None,
    require_provenance: bool = False,
    label: str = "",
) -> dict[str, Any]:
    """商用最终页综合判定唯一入口（组合新硬门 + 既有质量门/结构门）。"""
    import json

    from core.entity_page_quality import entity_page_quality_issues
    from content.homepage.homepage_validation import homepage_structure_issues

    page_path = Path(entity_dir) / "page.md"
    manifest_path = Path(entity_dir) / "manifest.json"
    name = entity_name or Path(entity_dir).name
    tag = label or name
    issues: list[str] = []
    if not page_path.is_file():
        return {"entity": name, "passed": False, "issues": [f"{tag}: page.md 缺失"]}
    page_text = page_path.read_text(encoding="utf-8")
    manifest_payload: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            issues.append(f"{tag}: manifest.json 不可解析")
    else:
        issues.append(f"{tag}: manifest.json 缺失")

    issues.extend(final_page_hard_issues(page_text, entity_name=name, label=tag))
    issues.extend(entity_page_quality_issues(page_path, label=tag))
    if manifest_payload:
        issues.extend(homepage_structure_issues(Path(entity_dir), manifest_payload, tag))
        issues.extend(map_like_asset_issues(manifest_payload, label=tag))
    if source_text and source_use_mode:
        issues.extend(
            copyright_mode_issues(page_text, source_text, source_use_mode, label=tag)
        )
    if provenance_payload is not None or require_provenance:
        issues.extend(
            provenance_checksum_issues(page_text, provenance_payload, label=tag)
        )
    return {"entity": name, "passed": not issues, "issues": issues}
