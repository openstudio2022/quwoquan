"""底稿（base draft）选取、批次级占用账本与贴合度度量。

复用策略（产品裁定：full light-edit，统一以底稿为骨架轻改）：

- `licensed_adaptation` 与 `factual_reference_only` 统一作为表达底稿处理：以底稿为骨架做
  适度润色 + 平台/作者痕迹清理 + 私人信息脱敏 + 人设适配；优质原句/自然段可保留，
  禁止脱离底稿从零另写，也禁止零加工整篇逐字照搬。
- review 对两类来源都启用 `baseDraftFidelity`（下限防换稿/重写，上限防零加工照搬）。
- 仅 `blocked` 来源不可作底稿（且不会进入底稿路径）。
- 注意：普通网页/UGC（攻略/游记/评论）以底稿为骨架轻改用于商用发布存在版权风险，
  该风险由产品侧承担（详见 SKILL「来源权利分层」与 docs/outstanding_risks_backlog）。

- 每篇文章/主页只认领一篇底稿（某来源单元的 source.md），一源仅一稿。
- 批次级账本（`batches/<batch>/_shared/base_draft_ledger.json`）记录 sourceRef -> postRef
  一对一映射；已被占用的源在其它篇目里只能进 evidenceRefs 作补充材料，不得再当底稿。
- 授权改编来源的贴合度采用「底稿留存率」(单向 char 三连覆盖)，与成品长度无关：
  coverage = |base_trigrams ∩ article_trigrams| / |base_trigrams|
  下限防「从零另写/换稿」(实测：从零重写≈0.24、无关文≈0.0、真实适度润色≥0.7)；
  上限（99.5%）只兜底「零加工整篇逐字照搬」——即没做任何去语病/错字、PII 脱敏替代或
  人设用词语气适配。授权范围内的优质原文与自然段可保留，故上限放得很高。
  注意：不可用对称的 difflib.ratio——底稿(数百字)远短于成品(上千字)时，
  对称比值上限≈2*len(base)/(len(base)+len(body))，永远摸不到 0.70，会误杀所有合规润色。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from content.post.evidence_text import SOURCE_BOILERPLATE_MARKERS, source_line_is_boilerplate
from core.io import read_json, write_json
from core.paths import execution_root, execution_shared_dir, relative_execution_ref
from content.source.source_unit import iter_source_units, resolve_entity_object_dir

BASE_DRAFT_LEDGER = "base_draft_ledger.json"
LEDGER_SCHEMA = "quwoquan_data.base_draft_ledger"

FIDELITY_MIN = 0.55
FIDELITY_MAX = 0.995
_NGRAM = 3

# 可作"以底稿为骨架轻改"的权利模式（产品裁定 full light-edit，licensed 与 factual 同等对待）。
# 仅 blocked 不可作底稿；rights 准入校验另在 download/content_plan 层执行，与此复用策略解耦。
ADAPTABLE_SOURCE_USE_MODES = ("licensed_adaptation", "factual_reference_only")
# 字数门唯一真相源（形态自适应）：长文 article 正文≥600；图文混排正文≥200 且
# 有足量内联图与图注（一篇真·图文底稿，而非图片占位）。任何 verify/review/run.py
# 预检都必须经 base_draft_readiness 消费这些阈值，禁止在别处另起一份固定 600。
ARTICLE_MIN_BASE_DRAFT_CHARS = 600
RICH_MIXED_MIN_TEXT_CHARS = 200
RICH_MIXED_MIN_CAPTION_CHARS = 80
RICH_MIXED_MIN_FIGURES = 3


def base_draft_is_adaptable(source_use_mode: str | None) -> bool:
    """生产/review 复用层：该来源是否可作为以底稿为骨架轻改的表达底稿。"""
    return str(source_use_mode or "").strip() in ADAPTABLE_SOURCE_USE_MODES


# 三类彻底解耦各自来源（download researchLane → 可作底稿的内容载体）：
# - 文章/线路：只认 article 研究 lane，不借百科或图集做底稿。
# - 图片作品：只认 image lane（专业图库一源一作品）。
# - 实体主页：只认 homepage / 百科 lane。
_CARRIER_BASE_DRAFT_LANES: dict[str, set[str]] = {
    "article": {"article"},
    "route": {"article"},
    "review": {"article"},
    "image": {"image"},
    "homepage": {"homepage", "encyclopedia"},
    "entity": {"homepage", "encyclopedia"},
}


def base_draft_allowed_lanes(carrier: str | None) -> set[str]:
    """按内容类型(carrier)返回底稿允许的 researchLane 集合。

    把"按内容类型选取各自来源"从下游 content_plan 兜底前移到底稿认领源头：文章载体只
    从 article 研究底稿认领、图片作品只从 image 图库来源认领、实体主页只从百科来源认领，
    源头杜绝"一个实体的来源被跨类型误选为底稿"。
    """
    key = str(carrier or "").strip()
    if key not in _CARRIER_BASE_DRAFT_LANES:
        raise ValueError(f"unsupported or missing content carrier: {key!r}")
    return set(_CARRIER_BASE_DRAFT_LANES[key])


def base_draft_readiness(
    text: str,
    *,
    publish_media_mode: str = "",
) -> dict[str, Any]:
    """Source-form adaptive base readiness for article drafts.

    Pure text/reference-only sources still need 600 effective chars.  A
    same-source rich mixed draft may pass with less prose only when it preserves
    enough inline figures and captions to be a real图文底稿 rather than an image
    placeholder.
    """
    from core.figure_groups import expand_figure_groups

    raw = str(text or "")
    # figuregroup（连续图组）先展开为 N 个单图块再计量，使「连续 N 张合并占位」如实计 N 张图、
    # N 段图注，不因合并占位被低估（P2 图主导底稿 readiness 判据）。
    expanded = expand_figure_groups(raw)
    compact = len(re.sub(r"\s+", "", expanded))
    figure_count = expanded.count(":::figure")
    image_alt_chars = sum(len(re.sub(r"\s+", "", match)) for match in re.findall(r"!\[([^\]]*)\]\(", expanded))
    figure_blocks = re.findall(r"(?s):::figure(.*?):::", expanded)
    caption_text = "\n".join(
        line
        for block in figure_blocks
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("![") and "asset://" not in line
    )
    caption_chars = len(re.sub(r"\s+", "", caption_text)) + image_alt_chars
    prose_without_figures = re.sub(r"(?s):::figure.*?:::", "", expanded)
    prose_chars = len(re.sub(r"\s+", "", prose_without_figures))
    text_ready = compact >= ARTICLE_MIN_BASE_DRAFT_CHARS
    rich_ready = (
        str(publish_media_mode or "").strip() != "text_only"
        and figure_count >= RICH_MIXED_MIN_FIGURES
        and prose_chars >= RICH_MIXED_MIN_TEXT_CHARS
        and caption_chars >= RICH_MIXED_MIN_CAPTION_CHARS
    )
    return {
        "ready": bool(text_ready or rich_ready),
        "sourceForm": "rich_mixed" if rich_ready and not text_ready else "text",
        "effectiveChars": compact,
        "proseChars": prose_chars,
        "inlineFigureCount": figure_count,
        "captionChars": caption_chars,
        "minTextChars": ARTICLE_MIN_BASE_DRAFT_CHARS,
        "richMixedMinTextChars": RICH_MIXED_MIN_TEXT_CHARS,
        "richMixedMinCaptionChars": RICH_MIXED_MIN_CAPTION_CHARS,
        "richMixedMinFigures": RICH_MIXED_MIN_FIGURES,
    }
# 样板/噪声行标记唯一真相源在 content_evidence.SOURCE_BOILERPLATE_MARKERS，禁止在此另起一份。
_NOISE_LINE_MARKERS = SOURCE_BOILERPLATE_MARKERS
_RELEVANT_BASE_MIN_CHARS = 320
_RELEVANT_BASE_MIN_RATIO = 0.55
_RELEVANT_BASE_MULTI_TOPIC_MIN_RATIO = 0.25
_RELEVANT_LINE_MIN_SIMILARITY = 0.18
_ARTICLE_BASE_BODY_RATIO = 0.72


# ─── 账本（一源仅一稿）────────────────────────────────────────────────
def _ledger_path(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / BASE_DRAFT_LEDGER


def load_base_draft_ledger(execution_id: str) -> dict[str, Any]:
    path = _ledger_path(execution_id)
    if path.is_file():
        try:
            data = read_json(path)
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("assignments"), dict):
            return data
    return {"schemaVersion": LEDGER_SCHEMA, "assignments": {}}


def save_base_draft_ledger(execution_id: str, ledger: Mapping[str, Any]) -> None:
    payload = dict(ledger)
    payload.setdefault("schemaVersion", LEDGER_SCHEMA)
    payload.setdefault("assignments", {})
    write_json(_ledger_path(execution_id), payload)


def occupied_source_refs(ledger: Mapping[str, Any], *, exclude_post: str = "") -> set[str]:
    """已被（其它篇目）占用的 sourceRef 集合。exclude_post 用于幂等重跑同一篇。"""
    out: set[str] = set()
    for source_ref, post_ref in (ledger.get("assignments") or {}).items():
        post_refs = (
            [str(item) for item in post_ref if str(item).strip()]
            if isinstance(post_ref, list)
            else [str(post_ref)]
        )
        if exclude_post and all(ref == exclude_post for ref in post_refs):
            continue
        out.add(str(source_ref))
    return out


# ─── 底稿候选枚举与认领 ────────────────────────────────────────────────
def _entity_refs(brief: Mapping[str, Any]) -> list[str]:
    return [str(r) for r in (brief.get("entityRefs") or []) if r]


def _unit_quality_score(unit_dir: Path) -> tuple[float, int]:
    """(质量分, source.md 去空白字符数)；质量分缺失回退 0，长度作次级排序键。"""
    score = 0.0
    quality = ""
    meta_path = unit_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError):
            meta = {}
        if str(meta.get("sourceUseMode") or "") == "blocked":
            return -1.0, 0
    quality_path = unit_dir / "source.quality.json"
    if quality_path.is_file():
        try:
            data = read_json(quality_path)
            quality = str(data.get("quality") or "")
            raw = data.get("score") if isinstance(data, dict) else None
            if isinstance(raw, (int, float)):
                score = float(raw)
        except (OSError, ValueError):
            pass
    if quality == "Reject":
        return -1.0, 0
    source_md = unit_dir / "source.md"
    length = 0
    if source_md.is_file():
        try:
            length = len(re.sub(r"\s+", "", source_md.read_text(encoding="utf-8")))
        except OSError:
            length = 0
    return score, length


def _is_candidate_eligible(score: float, length: int) -> bool:
    return score >= 0.0 and length > 0


def _unit_research_lane(unit_dir: Path) -> str:
    """读取来源单元 meta.json 的 researchLane（缺失/异常返回空串=历史通用底稿）。"""
    meta_path = unit_dir / "meta.json"
    if not meta_path.is_file():
        return ""
    try:
        meta = read_json(meta_path)
    except (OSError, ValueError):
        return ""
    return str(meta.get("researchLane") or "") if isinstance(meta, dict) else ""


def base_draft_candidates(
    execution_id: str, brief: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """该篇主体的底稿候选（来源单元 source.md），按质量分→长度降序。

    每项：{sourceRef(相对 batch 根的 source.md), score, length, unitDir}。
    """
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for entity_ref in _entity_refs(brief):
        object_dir = resolve_entity_object_dir(execution_id, entity_ref)
        for unit in iter_source_units(object_dir):
            source_md = unit / "source.md"
            if not source_md.is_file():
                continue
            source_ref = relative_execution_ref(source_md, execution_id)
            if source_ref in seen:
                continue
            seen.add(source_ref)
            score, length = _unit_quality_score(unit)
            if not _is_candidate_eligible(score, length):
                continue
            rows.append(
                {
                    "sourceRef": source_ref,
                    "score": score,
                    "length": length,
                    "unitDir": unit,
                    "researchLane": _unit_research_lane(unit),
                }
            )
    rows.sort(key=lambda r: (r["score"], r["length"]), reverse=True)
    return rows


def _normalize_to_source_ref(declared: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    """把 content_plan 里可能为「来源单元名」(如 03.gws_ctrip) 的 baseSourceRef 归一为完整 source.md 相对路径。

    只接受当前候选集合里的可用来源；Reject/空正文/失配路径都不得原样透传。
    """
    if not declared:
        return ""
    for cand in candidates:
        ref = str(cand["sourceRef"])
        if ref == declared or ref.endswith(declared) or f"/sources/{declared}/" in ("/" + ref):
            return ref
    return ""


def assign_base_draft(
    execution_id: str, post_ref: str, brief: Mapping[str, Any]
) -> str | None:
    """为某篇认领唯一底稿并落账本，返回 sourceRef；无可用底稿返回 None。

    - 若 brief 已声明 baseSourceRef：仅在该源未被其它篇占用时优先认领；若已占用则自动改派。
    - 否则在候选里挑质量分最高、尚未被其它篇占用的来源单元。
    """
    ledger = load_base_draft_ledger(execution_id)
    assignments: dict[str, str] = dict(ledger.get("assignments") or {})
    taken = occupied_source_refs(ledger, exclude_post=post_ref)
    candidates = base_draft_candidates(execution_id, brief)

    # 三类解耦：按 brief 载体把候选收窄到对应 researchLane（图片作品←image、文章/线路←
    # article、实体主页←百科），源头杜绝跨类型误选底稿；未知载体不限制（兼容）。
    allowed_lanes = base_draft_allowed_lanes(brief.get("carrier") or brief.get("contentType"))
    if allowed_lanes is not None:
        candidates = [
            cand
            for cand in candidates
            if str(cand.get("researchLane") or "") in allowed_lanes
        ]

    declared = str(brief.get("baseSourceRef") or "").strip()
    chosen = _normalize_to_source_ref(declared, candidates)
    if chosen in taken:
        chosen = ""
    if not chosen:
        for cand in candidates:
            if cand["sourceRef"] not in taken:
                chosen = cand["sourceRef"]
                break
    if not chosen:
        return None

    # 清理本篇旧认领，写入新认领（保持一源一稿、一篇一稿）。
    assignments = {s: p for s, p in assignments.items() if p != post_ref}
    assignments[chosen] = post_ref
    ledger["assignments"] = assignments
    save_base_draft_ledger(execution_id, ledger)
    return chosen


# ─── 底稿正文读取与贴合度 ──────────────────────────────────────────────
def load_base_draft_text(execution_id: str, base_source_ref: str | None) -> str:
    """读底稿正文：优先 source.clean.md，回退 source.md。"""
    if not base_source_ref:
        return ""
    candidate = execution_root(execution_id) / str(base_source_ref)
    paths: list[Path] = []
    # 兼容指向 source.clean.md / source.md / 来源目录三种情况；review 与 prompt 都应优先消费清洗正文。
    if candidate.name == "source.clean.md":
        paths.extend([candidate, candidate.parent / "source.md"])
    elif candidate.name == "source.md":
        paths.extend([candidate.parent / "source.clean.md", candidate])
    elif candidate.suffix:
        paths.extend([candidate, candidate.parent / "source.clean.md", candidate.parent / "source.md"])
    else:
        paths.extend([candidate / "source.clean.md", candidate / "source.md"])
    for path in paths:
        if path.is_file():
            try:
                return _extract_base_draft_body(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return ""


def sibling_source_texts(
    execution_id: str, base_source_ref: str | None
) -> dict[str, str]:
    """同一内容对象旧本地 `1.download/sources/` 下、除底稿外的其它 source unit 原文。

    单底稿零参考反拼接门用：{sourceRef(relative): text}，供 `cross_source_overlap_issues`
    扫描正文是否从「非底稿来源单元」长串照搬（如把同实体其它天行程/其它来源段落拼进来）。
    新 canonical `batch/sources/{sourceUnitId}` 是批次级物理池，不代表同内容对象 sibling，
    因此不得在这里扫描整个池。
    """
    if not base_source_ref:
        return {}
    candidate = execution_root(execution_id) / str(base_source_ref)
    base_unit_dir = candidate if candidate.is_dir() else candidate.parent
    sources_dir = base_unit_dir.parent
    if sources_dir.name != "sources" or not sources_dir.is_dir():
        return {}
    if sources_dir.resolve() == (execution_root(execution_id) / "sources").resolve():
        return {}
    out: dict[str, str] = {}
    for unit_dir in sorted(p for p in sources_dir.iterdir() if p.is_dir()):
        if unit_dir.resolve() == base_unit_dir.resolve():
            continue
        text = ""
        for name in ("source.clean.md", "source.md"):
            path = unit_dir / name
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    text = ""
                break
        if not text:
            continue
        try:
            rel = (unit_dir / "source.md").relative_to(execution_root(execution_id)).as_posix()
        except ValueError:
            rel = unit_dir.name
        out[rel] = text
    return out


def base_source_unit_meta(execution_id: str, base_source_ref: str | None) -> dict[str, Any]:
    """读取来源单元 meta.json（sourceId/platform/sourceUseMode 等），缺失返回空 dict。

    作为来源单元元信息的唯一读取入口：base_source_use_mode 取权利模式、
    works_gate 取 sourceId/platform 解析来源专业度，共享同一份路径解析，
    避免重复推导来源目录（R25）。
    """
    if not base_source_ref:
        return {}
    candidate = execution_root(execution_id) / str(base_source_ref)
    unit_dir = candidate if candidate.is_dir() else candidate.parent
    meta_path = unit_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError):
            return {}
        if isinstance(meta, dict):
            return dict(meta)
    return {}


def base_source_use_mode(execution_id: str, base_source_ref: str | None) -> str:
    """读取来源单元权利模式；旧来源默认按事实参考处理，禁止误启用轻改门。"""
    mode = str(base_source_unit_meta(execution_id, base_source_ref).get("sourceUseMode") or "").strip()
    return mode or "factual_reference_only"


def _looks_like_noise_line(line: str) -> bool:
    # 复用唯一样板判定（content_evidence.source_line_is_boilerplate），不再各自实现。
    return source_line_is_boilerplate(line)


def _is_signal_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    letters = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", compact)
    if len(letters) < 10:
        return False
    if _looks_like_noise_line(line):
        return False
    if not (re.search(r"[，。！？；：,.!?]", line) or len(letters) >= 22):
        return False
    return True


def _extract_base_draft_body(text: str) -> str:
    """从清洗来源里提取可写正文，避开整页导航/点评/相关推荐噪声。"""
    lines = [line.strip() for line in (text or "").splitlines()]
    signal_lines = [line for line in lines if _is_signal_line(line)]
    if not signal_lines:
        return text

    picked: list[str] = []
    total_chars = 0
    for line in signal_lines:
        line_chars = len(re.sub(r"\s+", "", line))
        if total_chars >= 6000 and len(picked) >= 4:
            break
        picked.append(line)
        total_chars += line_chars

    body = "\n\n".join(picked).strip()
    return body or text


def extract_base_draft_body(text: str) -> str:
    """公共底稿正文提取入口，供站点供给与生产管线复用同一清洗规则。"""
    return _extract_base_draft_body(text)


# ─── 标题取自底稿（source unit）─────────────────────────────────────────
# 底稿中心模型：发布标题来自底稿（来源单元 meta.title 或正文首个标题），
# 而非 `{实体}·{角度}` 模板。必须剥平台后缀/作者署名痕迹（避免泄露原平台/作者，
# 与 provenanceRewrite 门一致），并做最小/最大长度约束；清洗后无可用标题时返回 ""，
# 由上游对 article 源诚实弃稿（标题取不出来的文章源不成稿）。
SOURCE_TITLE_MIN_CHARS = 4
SOURCE_TITLE_MAX_CHARS = 40

# 平台/站点尾缀（出现在标题尾部、跟随分隔符），剥离以去平台痕迹；不含"攻略/游记"等内容词。
_TITLE_PLATFORM_SUFFIX_RE = re.compile(
    r"[\s_\|｜·–—\-]+("
    r"携程(攻略社区|旅行|旅游)?|马蜂窝|去哪儿(网|旅行)?|途牛(旅游网)?|同程(旅行|旅游)?|"
    r"小红书|知乎(专栏)?|百度(百科|经验|旅游)?|美篇|穷游(网)?|驴妈妈(旅游网)?|飞猪|"
    r"大众点评|新浪(旅游|博客)?|搜狐(旅游|号)?|腾讯(旅游|网|新闻)?|网易(旅游|号)?|"
    r"旅游网|旅行网|景区官网|官方网站|官网|维基百科|wikipedia|wikivoyage|wikitravel"
    r")\s*$",
    re.IGNORECASE,
)
_TITLE_NOISE_RE = re.compile(r"[\u3010\u3008\u300a\[\(（【].*?[\u3011\u3009\u300b\]\)）】]\s*$")
# 形如 `03.gws_ctrip` / `source_1` 的来源 id，不是真实标题。
_SOURCE_ID_LIKE_RE = re.compile(r"^[0-9]+[\._-]|_(base|src|source)_?\d*$|^[a-z0-9]+[._][a-z0-9_]+$")


def _clean_source_title(raw: str) -> str:
    title = re.sub(r"\s+", " ", str(raw or "").strip())
    if not title:
        return ""
    # 反复剥离尾部平台/站点后缀（可能链式：`… - 携程攻略社区`）。
    for _ in range(4):
        stripped = _TITLE_PLATFORM_SUFFIX_RE.sub("", title).strip(" _|｜·–—-")
        if stripped == title:
            break
        title = stripped
    # 去掉尾部括注（如「（图）」「【攻略】」）。
    title = _TITLE_NOISE_RE.sub("", title).strip(" _|｜·–—-")
    if len(re.sub(r"\s+", "", title)) > SOURCE_TITLE_MAX_CHARS:
        title = title[:SOURCE_TITLE_MAX_CHARS].rstrip(" _|｜·–—-，,、")
    return title


def _looks_like_source_id(value: str, *, source_id: str = "") -> bool:
    compact = str(value or "").strip()
    if not compact:
        return True
    if source_id and compact == source_id:
        return True
    return bool(_SOURCE_ID_LIKE_RE.search(compact))


def _first_heading_title(body: str) -> str:
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#{1,4}\s+(.+?)\s*#*$", stripped)
        if heading:
            return heading.group(1).strip()
    return ""


def extract_source_title(execution_id: str, base_source_ref: str | None) -> str:
    """从单一底稿（来源单元）派生发布标题：meta.title → 正文首标题，剥平台痕迹 + 长度约束。

    返回清洗后的可用标题；取不出（空/过短/仅为来源 id）时返回 ""，由上游对 article 源弃稿。
    """
    if not base_source_ref:
        return ""
    meta = base_source_unit_meta(execution_id, base_source_ref)
    source_id = str(meta.get("sourceId") or "").strip()
    candidate = _clean_source_title(str(meta.get("title") or ""))
    if not _looks_like_source_id(candidate, source_id=source_id) and len(
        re.sub(r"\s+", "", candidate)
    ) >= SOURCE_TITLE_MIN_CHARS:
        return candidate
    # 回退：底稿正文首个 markdown 标题。
    body = load_base_draft_text(execution_id, base_source_ref)
    heading = _clean_source_title(_first_heading_title(body))
    if not _looks_like_source_id(heading, source_id=source_id) and len(
        re.sub(r"\s+", "", heading)
    ) >= SOURCE_TITLE_MIN_CHARS:
        return heading
    return ""


# ─── 底稿中心 1:1：fidelity 对整篇单一底稿度量 ─────────────────────────────
# 旧模型按 writingIntent 桶 + 实体名收窄底稿作分母（intent_aligned_base_text），
# 在"实体×角度"配额模型下用于避免整篇多主题游记误杀聚焦文章。底稿中心 1:1 后，
# 成品本就只来自单一底稿、实体退化为多标签，分母必须是整篇底稿（load_base_draft_text）：
# 整篇度量既不会因离题段落把 fidelity 拉低误杀（消除 28.4% 类误判），高相似仍触顶防照搬。
# 收窄逻辑（intent_aligned_base_text / load_intent_aligned_base_draft_text）已整体删除。


_FIGURE_RE = re.compile(r"(?ms)^:::figure.*?:::")
_ASSET_RE = re.compile(r"asset://[^\s)]+")
_GALLERY_BASE_TARGET_CHARS = 1000
_GALLERY_BASE_BODY_RATIO = 0.7


def _normalize_embedded_newlines(text: str) -> str:
    """兼容运行时/测试里以字面量 \\n 落盘或拼接的正文。"""
    if "\\n" not in text:
        return text
    return text.replace("\\r\\n", "\n").replace("\\n", "\n")


def _readable_body(article: str) -> str:
    """剥离 figure 块/asset 引用/标题井号后的可读正文（用于贴合度比较）。"""
    article = _normalize_embedded_newlines(article)
    text = _FIGURE_RE.sub("", article)
    text = _ASSET_RE.sub("", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return re.sub(r"\s+", "", text)


def _base_excerpt_for_image(text: str, *, body_len: int) -> str:
    """画报正文较短，只要求贴住底稿前段主线，不强求覆盖整篇长底稿。"""
    text = _normalize_embedded_newlines(text)
    source_chars = len(re.sub(r"\s+", "", text))
    if _GALLERY_BASE_BODY_RATIO > 0:
        target_chars = int(body_len / _GALLERY_BASE_BODY_RATIO)
    else:
        target_chars = int(body_len or 0)
    target_chars = max(1, min(source_chars, target_chars))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text[:target_chars]
    picked: list[str] = []
    total = 0
    for paragraph in paragraphs:
        chars = len(re.sub(r"\s+", "", paragraph))
        if picked and total >= target_chars:
            break
        if picked and body_len > 0 and total >= int(body_len * 0.9):
            break
        if picked and total + chars > target_chars:
            current_gap = abs(target_chars - total)
            expanded_gap = abs(target_chars - (total + chars))
            if current_gap <= expanded_gap:
                break
        picked.append(paragraph)
        total += chars
    return "\n\n".join(picked)


def _base_comparison_lines(text: str) -> list[str]:
    """用于贴合度比较的底稿行：去掉来源头、平台壳、广告和纯导航噪声。"""
    text = _normalize_embedded_newlines(text)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        low = stripped.lower()
        if low.startswith(("license", "alloweduse", "credit", "url", "source", "title:", "图片来源", "授权")):
            continue
        if _looks_like_noise_line(stripped):
            continue
        kept.append(stripped)
    return kept


def _compact_lines(lines: Sequence[str]) -> str:
    return re.sub(r"\s+", "", "\n".join(lines).strip())


def _cap_relevant_lines_to_body(scored_lines: Sequence[tuple[int, float, str]], *, body_len: int) -> str:
    if not scored_lines:
        return ""
    ordered_lines = [line for _index, _score, line in sorted(scored_lines, key=lambda item: item[0])]
    compact = _compact_lines(ordered_lines)
    if not body_len:
        return compact
    target_chars = int(body_len / _ARTICLE_BASE_BODY_RATIO) if _ARTICLE_BASE_BODY_RATIO > 0 else body_len
    target_chars = max(_RELEVANT_BASE_MIN_CHARS, target_chars)
    if len(compact) <= target_chars:
        return compact
    picked_rows: list[tuple[int, str]] = []
    total = 0
    for index, _score, line in sorted(scored_lines, key=lambda item: item[1], reverse=True):
        chars = len(re.sub(r"\s+", "", line))
        if picked_rows and total >= target_chars:
            break
        if picked_rows and total + chars > target_chars:
            current_gap = abs(target_chars - total)
            expanded_gap = abs(target_chars - (total + chars))
            if current_gap <= expanded_gap:
                break
        picked_rows.append((index, line))
        total += chars
    picked = [line for _index, line in sorted(picked_rows, key=lambda item: item[0])]
    return _compact_lines(picked) or compact[:target_chars]


def _relevant_base_excerpt(base_lines: Sequence[str], body: str) -> str:
    """在长底稿含广告/跨城支线时，用主体保留段落作为比较窗口。

    候选段落覆盖清洗底稿的足够比例时直接启用。对于多城/多主题游记，
    如果相关段占比偏低但自身与正文仍达到贴合度下限，也启用相关段；
    只复用少量关键词的成稿仍会回退到完整清洗底稿并触发低贴合度。
    """
    clean_base = _compact_lines(base_lines)
    if len(clean_base) < _RELEVANT_BASE_MIN_CHARS or not body:
        return clean_base
    body_grams = _char_ngrams(body)
    selected: list[tuple[int, float, str]] = []
    selected_chars = 0
    for index, line in enumerate(base_lines):
        compact = re.sub(r"\s+", "", line)
        grams = _char_ngrams(compact)
        if not grams:
            continue
        overlap = len(grams & body_grams) / len(grams)
        if overlap >= _RELEVANT_LINE_MIN_SIMILARITY:
            selected.append((index, overlap, line))
            selected_chars += len(compact)
    if selected_chars >= _RELEVANT_BASE_MIN_CHARS:
        selected_base = _cap_relevant_lines_to_body(selected, body_len=len(body))
        selected_ratio = selected_chars / len(clean_base)
        selected_grams = _char_ngrams(selected_base)
        selected_similarity = len(selected_grams & body_grams) / len(selected_grams) if selected_grams else 0.0
        if selected_ratio >= _RELEVANT_BASE_MIN_RATIO or (
            selected_ratio >= _RELEVANT_BASE_MULTI_TOPIC_MIN_RATIO
            and selected_similarity >= FIDELITY_MIN
        ):
            return selected_base
    return clean_base


def _strip_source_meta(text: str, *, carrier: str = "article", body_len: int = 0, body: str = "") -> str:
    """去掉底稿里的 license/credit/url/平台噪声，并按载体裁切公平比较窗口。"""
    base_lines = _base_comparison_lines(text)
    filtered = "\n".join(base_lines).strip()
    if carrier == "image" and filtered:
        filtered = _base_excerpt_for_image(filtered, body_len=body_len)
        return re.sub(r"\s+", "", filtered)
    return _relevant_base_excerpt(base_lines, body)


def _char_ngrams(text: str, n: int = _NGRAM) -> set[str]:
    """Shared n-grams for relevance-window selection inside this module."""
    if len(text) < n:
        return {text} if text else set()
    return {text[index : index + n] for index in range(len(text) - n + 1)}


# 注入 prompt 的底稿正文上限：fidelity 门按整篇底稿判，prompt 必须给整篇（否则 agent 看不到
# 的内容无法保留 → 必然低保真）。仅对极端超长底稿（书籍级）设安全上限，避免 prompt 失控。
BASE_DRAFT_PROMPT_MAX_CHARS = 24000


def clean_base_draft_length(base_text: str) -> int:
    """底稿去平台噪声后的可读正文字数（去空白），用于派生 light-edit 字数目标。

    与 `baseDraftFidelity` 清洗口径同源（`_base_comparison_lines`），保证字数目标与保真度
    分母一致：成稿长度 ≈ 清洗底稿长度时，逐句轻改即可达 fidelity 下限。
    """
    return len(_compact_lines(_base_comparison_lines(str(base_text or ""))))


def base_aware_word_count(
    base_text: str,
    *,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> dict[str, int] | None:
    """light-edit 文章字数目标必须跟随底稿长度，否则固定上限会与 `baseDraftFidelity>=55%` 互斥。

    根因实测：底稿 ~8900 字、`wordCount` 上限 1600 时，成稿最多覆盖底稿 ~18% 三连，fidelity
    必崩（成稿被逼压缩+重写）。light-edit 文章应整篇保留清洗底稿，故字数目标按清洗底稿长度派生。
    `image/gallery`（短配文）与非改编源返回 None（沿用默认，不设底稿字数门）。
    """
    if str(carrier or "").lower() == "image":
        return None
    if not base_draft_is_adaptable(source_use_mode):
        return None
    clean_len = clean_base_draft_length(base_text)
    if clean_len < ARTICLE_MIN_BASE_DRAFT_CHARS:
        return None
    lo = max(ARTICLE_MIN_BASE_DRAFT_CHARS, int(clean_len * 0.62))
    hi = max(lo + 600, int(clean_len * 1.12))
    return {"min": lo, "max": hi}


__all__ = [
    "FIDELITY_MIN",
    "FIDELITY_MAX",
    "ADAPTABLE_SOURCE_USE_MODES",
    "base_draft_is_adaptable",
    "base_draft_allowed_lanes",
    "load_base_draft_ledger",
    "save_base_draft_ledger",
    "occupied_source_refs",
    "base_draft_candidates",
    "assign_base_draft",
    "extract_base_draft_body",
    "extract_source_title",
    "load_base_draft_text",
    "sibling_source_texts",
    "base_source_use_mode",
]
