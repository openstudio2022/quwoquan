"""底稿（base draft）选取、批次级占用账本与贴合度度量。

复用策略按来源权利语义分轨：

- `licensed_adaptation` 可作为表达底稿轻改，并由 `baseDraftFidelity` 防换稿与零加工照搬。
- `factual_reference_only` 只提供可核验事实、路线顺序与必要专有名词；成稿必须独立组织和
  表达，不承担最低底稿留存率，并继续由 `commercialNearCopy` 阻断近抄与连续长句复现。
- 仅 `blocked` 来源不可作底稿（且不会进入底稿路径）。
- 普通网页/UGC（攻略/游记/评论）只有在对象级 source/rights 证据满足
  `runtime-data-engineering/article-commercial-scale-closure` 的准入合同后才可进入发布；
  不得用“产品承担风险”绕过权利门禁。

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

from content.post.article.evidence_text import SOURCE_BOILERPLATE_MARKERS, source_line_is_boilerplate
from core.io import read_json, write_json
from core.paths import execution_root, execution_shared_dir, relative_execution_ref
from content.source.source_unit import iter_source_units, resolve_entity_object_dir

BASE_DRAFT_LEDGER = "base_draft_ledger.json"
LEDGER_SCHEMA = "quwoquan_data.base_draft_ledger"


# 只有明确允许改编的来源可作为表达骨架轻改。事实参考来源仍可通过 baseSourceRef
# 提供事实证据，但不得因此取得复用原句/自然段的许可。
ADAPTABLE_SOURCE_USE_MODES = ("licensed_adaptation",)
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
    return {"schema": LEDGER_SCHEMA, "assignments": {}}


def save_base_draft_ledger(execution_id: str, ledger: Mapping[str, Any]) -> None:
    payload = dict(ledger)
    payload.setdefault("schema", LEDGER_SCHEMA)
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
def _base_draft_source_candidates(
    execution_id: str, base_source_ref: str | None
) -> list[Path]:
    """底稿引用可能指向的清洗正文文件，按优先级排列。

    候选顺序是底稿正文的唯一解析规则：读全文的 `load_base_draft_text` 与只要文件
    路径的 `base_draft_source_path` 必须落到同一个文件，否则「判据看的正文」与
    「issue 指的行号」会来自两份不同的稿子。
    """
    if not base_source_ref:
        return []
    candidate = execution_root(execution_id) / str(base_source_ref)
    # 兼容指向 source.clean.md / source.md / 来源目录三种情况；review 与 prompt 都应优先消费清洗正文。
    if candidate.name == "source.clean.md":
        return [candidate, candidate.parent / "source.md"]
    if candidate.name == "source.md":
        return [candidate.parent / "source.clean.md", candidate]
    if candidate.suffix:
        return [
            candidate,
            candidate.parent / "source.clean.md",
            candidate.parent / "source.md",
        ]
    return [candidate / "source.clean.md", candidate / "source.md"]


def base_draft_source_path(execution_id: str, base_source_ref: str | None) -> Path | None:
    """底稿正文所在文件；引用不在场或候选文件都不存在时返回 `None`。"""
    for path in _base_draft_source_candidates(execution_id, base_source_ref):
        if path.is_file():
            return path
    return None


def load_base_draft_text(execution_id: str, base_source_ref: str | None) -> str:
    """读底稿正文：优先 source.clean.md，回退 source.md。"""
    for path in _base_draft_source_candidates(execution_id, base_source_ref):
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

# 平台/站点尾缀（出现在标题尾部、跟随分隔符），剥离以去平台痕迹；不含"攻略/游记"等内容词。
# 形如 `03.gws_ctrip` / `source_1` 的来源 id，不是真实标题。










# ─── 底稿中心 1:1：fidelity 对整篇单一底稿度量 ─────────────────────────────
# 旧模型按 writingIntent 桶 + 实体名收窄底稿作分母（intent_aligned_base_text），
# 在"实体×角度"配额模型下用于避免整篇多主题游记误杀聚焦文章。底稿中心 1:1 后，
# 成品本就只来自单一底稿、实体退化为多标签，分母必须是整篇底稿（load_base_draft_text）：
# 整篇度量既不会因离题段落把 fidelity 拉低误杀（消除 28.4% 类误判），高相似仍触顶防照搬。
# 收窄逻辑（intent_aligned_base_text / load_intent_aligned_base_draft_text）已整体删除。






















# 注入 prompt 的底稿正文上限：fidelity 门按整篇底稿判，prompt 必须给整篇（否则 agent 看不到
# 的内容无法保留 → 必然低保真）。仅对极端超长底稿（书籍级）设安全上限，避免 prompt 失控。
BASE_DRAFT_PROMPT_MAX_CHARS = 24000




