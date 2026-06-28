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

from _common.content_evidence import SOURCE_BOILERPLATE_MARKERS, source_line_is_boilerplate
from _common.io import read_json, write_json
from _common.paths import batch_root, batch_shared_dir, relative_batch_ref
from _common.source_unit import iter_source_units, resolve_entity_object_dir

BASE_DRAFT_LEDGER = "base_draft_ledger.json"
LEDGER_SCHEMA = "quwoquan_data.base_draft_ledger"

FIDELITY_MIN = 0.55
FIDELITY_MAX = 0.995
_NGRAM = 3

# 可作"以底稿为骨架轻改"的权利模式（产品裁定 full light-edit，licensed 与 factual 同等对待）。
# 仅 blocked 不可作底稿；rights 准入校验另在 download/content_plan 层执行，与此复用策略解耦。
ADAPTABLE_SOURCE_USE_MODES = ("licensed_adaptation", "factual_reference_only")


def base_draft_is_adaptable(source_use_mode: str | None) -> bool:
    """生产/review 复用层：该来源是否可作为以底稿为骨架轻改的表达底稿。"""
    return str(source_use_mode or "").strip() in ADAPTABLE_SOURCE_USE_MODES
# 样板/噪声行标记唯一真相源在 content_evidence.SOURCE_BOILERPLATE_MARKERS，禁止在此另起一份。
_NOISE_LINE_MARKERS = SOURCE_BOILERPLATE_MARKERS
_RELEVANT_BASE_MIN_CHARS = 320
_RELEVANT_BASE_MIN_RATIO = 0.55
_RELEVANT_BASE_MULTI_TOPIC_MIN_RATIO = 0.25
_RELEVANT_LINE_MIN_SIMILARITY = 0.18
_ARTICLE_BASE_BODY_RATIO = 0.72


# ─── 账本（一源仅一稿）────────────────────────────────────────────────
def _ledger_path(task_id: str, batch_id: str) -> Path:
    return batch_shared_dir(task_id, batch_id) / BASE_DRAFT_LEDGER


def load_base_draft_ledger(task_id: str, batch_id: str) -> dict[str, Any]:
    path = _ledger_path(task_id, batch_id)
    if path.is_file():
        try:
            data = read_json(path)
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("assignments"), dict):
            return data
    return {"schemaVersion": LEDGER_SCHEMA, "assignments": {}}


def save_base_draft_ledger(task_id: str, batch_id: str, ledger: Mapping[str, Any]) -> None:
    payload = dict(ledger)
    payload.setdefault("schemaVersion", LEDGER_SCHEMA)
    payload.setdefault("assignments", {})
    write_json(_ledger_path(task_id, batch_id), payload)


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


def base_draft_candidates(
    task_id: str, batch_id: str, brief: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """该篇主体的底稿候选（来源单元 source.md），按质量分→长度降序。

    每项：{sourceRef(相对 batch 根的 source.md), score, length, unitDir}。
    """
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for entity_ref in _entity_refs(brief):
        object_dir = resolve_entity_object_dir(task_id, batch_id, entity_ref)
        for unit in iter_source_units(object_dir):
            source_md = unit / "source.md"
            if not source_md.is_file():
                continue
            source_ref = relative_batch_ref(source_md, task_id, batch_id)
            if source_ref in seen:
                continue
            seen.add(source_ref)
            score, length = _unit_quality_score(unit)
            if not _is_candidate_eligible(score, length):
                continue
            rows.append(
                {"sourceRef": source_ref, "score": score, "length": length, "unitDir": unit}
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
    task_id: str, batch_id: str, post_ref: str, brief: Mapping[str, Any]
) -> str | None:
    """为某篇认领唯一底稿并落账本，返回 sourceRef；无可用底稿返回 None。

    - 若 brief 已声明 baseSourceRef：仅在该源未被其它篇占用时优先认领；若已占用则自动改派。
    - 否则在候选里挑质量分最高、尚未被其它篇占用的来源单元。
    """
    ledger = load_base_draft_ledger(task_id, batch_id)
    assignments: dict[str, str] = dict(ledger.get("assignments") or {})
    taken = occupied_source_refs(ledger, exclude_post=post_ref)
    candidates = base_draft_candidates(task_id, batch_id, brief)

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
    save_base_draft_ledger(task_id, batch_id, ledger)
    return chosen


# ─── 底稿正文读取与贴合度 ──────────────────────────────────────────────
def load_base_draft_text(task_id: str, batch_id: str, base_source_ref: str | None) -> str:
    """读底稿正文：优先 source.clean.md，回退 source.md。"""
    if not base_source_ref:
        return ""
    candidate = batch_root(task_id, batch_id) / str(base_source_ref)
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
    task_id: str, batch_id: str, base_source_ref: str | None
) -> dict[str, str]:
    """同一内容对象 `1.download/sources/` 下、除底稿外的其它 source unit 原文。

    单底稿零参考反拼接门用：{sourceRef(relative): text}，供 `cross_source_overlap_issues`
    扫描正文是否从「非底稿来源单元」长串照搬（如把同实体其它天行程/其它来源段落拼进来）。
    """
    if not base_source_ref:
        return {}
    candidate = batch_root(task_id, batch_id) / str(base_source_ref)
    base_unit_dir = candidate if candidate.is_dir() else candidate.parent
    sources_dir = base_unit_dir.parent
    if sources_dir.name != "sources" or not sources_dir.is_dir():
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
            rel = (unit_dir / "source.md").relative_to(batch_root(task_id, batch_id)).as_posix()
        except ValueError:
            rel = unit_dir.name
        out[rel] = text
    return out


def base_source_unit_meta(task_id: str, batch_id: str, base_source_ref: str | None) -> dict[str, Any]:
    """读取来源单元 meta.json（sourceId/platform/sourceUseMode 等），缺失返回空 dict。

    作为来源单元元信息的唯一读取入口：base_source_use_mode 取权利模式、
    works_gate 取 sourceId/platform 解析来源专业度，共享同一份路径解析，
    避免重复推导来源目录（R25）。
    """
    if not base_source_ref:
        return {}
    candidate = batch_root(task_id, batch_id) / str(base_source_ref)
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


def base_source_use_mode(task_id: str, batch_id: str, base_source_ref: str | None) -> str:
    """读取来源单元权利模式；旧来源默认按事实参考处理，禁止误启用轻改门。"""
    mode = str(base_source_unit_meta(task_id, batch_id, base_source_ref).get("sourceUseMode") or "").strip()
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


# ─── writingIntent 主线对齐底稿（prompt 与 review 门共享单一真相源）──────────
# 长多主题游记（跨城支线/广告/无关主题）若整篇灌进 baseDraftText，会逼 agent
# 要么照搬无关段、要么大改导致低贴合度，且 review 门以整篇作分母，聚焦文章永远
# 摸不到下限。这里按 writingIntent 桶（WRITING_INTENTS 为唯一来源）+ 实体名挑出
# 主线对齐段，prompt 与门必须消费同一份对齐底稿，避免双轨/第二坐标链（R24/R-CS01）。
_INTENT_ALIGNED_TARGET_CHARS = 4000
# 仅当聚焦底稿自身有效字 >= 该下限才收窄；否则原样返回整篇。
# 取 640（发布门 MIN_ARTICLE_BASE_DRAFT_CHARS=600 之上留小余量），避免收窄后跌破发布门。
_INTENT_ALIGNED_MIN_CHARS = 640


def _intent_is_relevant(paragraph: str, bucket_terms: Sequence[Sequence[str]], entity_name: str) -> bool:
    """段落是否与本篇 writingIntent 主线或本实体直接相关。"""
    if entity_name and entity_name in paragraph:
        return True
    return any(any(term in paragraph for term in terms) for terms in bucket_terms)


def intent_aligned_base_text(
    base_text: str,
    *,
    writing_intent: str | None,
    entity_name: str = "",
    target_chars: int = _INTENT_ALIGNED_TARGET_CHARS,
    min_chars: int = _INTENT_ALIGNED_MIN_CHARS,
) -> str:
    """按 writingIntent 桶关键词 + 实体名，从清洗底稿里挑主线对齐段落。

    - 未知/缺失 intent 或段落过少时，原样返回整篇正文（不冒险收窄）。
    - 只保留命中 intent 桶或含本实体名的段落，按原文顺序拼回保持叙事连贯。
    - 绝不用无关段补长：聚焦底稿 < min_chars（源对该 intent 太薄）时原样返回整篇，
      既不污染聚焦度，也不新增 thin-source 误丢（薄源由源采集充分率门 T3 处置）。
    - prompt 侧 baseDraftText 与 review 门 baseDraftFidelity 分母消费同一份对齐底稿，
      避免整篇多主题游记作分母误杀聚焦文章（R-CS01 单一真相源）。
    """
    from _common.quality_gates import WRITING_INTENTS

    body = extract_base_draft_body(base_text)
    if not body:
        return ""
    spec = WRITING_INTENTS.get(str(writing_intent or "").strip())
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not spec or len(paragraphs) <= 4:
        return body[:target_chars]
    bucket_terms = [list(terms) for terms in (spec.get("buckets") or {}).values()]
    picked: list[str] = []
    total = 0
    for paragraph in paragraphs:
        if not _intent_is_relevant(paragraph, bucket_terms, entity_name):
            continue
        chars = len(re.sub(r"\s+", "", paragraph))
        if picked and total + chars > target_chars:
            break
        picked.append(paragraph)
        total += chars
    excerpt = "\n\n".join(picked).strip()
    if excerpt and len(re.sub(r"\s+", "", excerpt)) >= min_chars:
        return excerpt[:target_chars]
    return body[:target_chars]


def load_intent_aligned_base_draft_text(
    task_id: str,
    batch_id: str,
    base_source_ref: str | None,
    *,
    writing_intent: str | None = None,
    entity_name: str = "",
) -> str:
    """读取底稿正文并按 writingIntent 收窄到主线对齐段（prompt 与门共用）。"""
    text = load_base_draft_text(task_id, batch_id, base_source_ref)
    if not text:
        return ""
    return intent_aligned_base_text(
        text, writing_intent=writing_intent, entity_name=entity_name
    )


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


def _base_excerpt_for_gallery(text: str, *, body_len: int) -> str:
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
    if carrier == "gallery" and filtered:
        filtered = _base_excerpt_for_gallery(filtered, body_len=body_len)
        return re.sub(r"\s+", "", filtered)
    return _relevant_base_excerpt(base_lines, body)


def _char_ngrams(text: str, n: int = _NGRAM) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def base_draft_similarity(article: str, base_text: str, *, carrier: str = "article") -> float:
    """底稿留存率：底稿 char 三连里有多少在成品中出现（单向覆盖，与成品长度无关）。"""
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)
    base_grams = _char_ngrams(base)
    if not body or not base_grams:
        return 0.0
    body_grams = _char_ngrams(body)
    return len(base_grams & body_grams) / len(base_grams)


def base_draft_fidelity_issues(
    article: str,
    base_text: str,
    *,
    min_ratio: float = FIDELITY_MIN,
    max_ratio: float = FIDELITY_MAX,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> list[str]:
    """底稿贴合度门：对所有可作底稿的来源生效（licensed_adaptation 与 factual_reference_only）。

    产品裁定 full light-edit 后，两类来源都以底稿为骨架轻改：下限防脱离底稿/从零另写，
    上限防零加工整篇逐字照搬。仅 blocked（不会进入底稿路径）跳过。
    """
    if not base_draft_is_adaptable(source_use_mode):
        return []
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)
    if not base or not body:
        return []
    sim = base_draft_similarity(article, base_text, carrier=carrier)
    pct = round(sim * 100, 1)
    if sim < min_ratio:
        return [
            f"base draft fidelity {pct}% < {int(min_ratio * 100)}% "
            "(底稿留存率过低，疑似脱离底稿/从零另写，应在底稿基础上适度润色而非重写)"
        ]
    if sim > max_ratio:
        return [
            f"base draft fidelity {pct}% > {int(max_ratio * 100)}% "
            "(零加工整篇逐字照搬，至少需完成去语病/错字、私人信息脱敏替代与作者人设用词语气适配)"
        ]
    return []


# ─── 反脱稿 / 反拼接度量（fidelity 的反向与跨源补强）──────────────────────
# baseDraftFidelity 是“底稿留存了多少”的单向指标，测不到“正文里多少来自底稿之外/
# 逐字搬自别的源”。以下两个函数补这块盲区：
# - out_of_draft_ratio：正文 char 三连里不在底稿中的占比（底稿外补写量）。
# - cross_source_overlap_issues：正文与某个“非底稿来源”出现长串逐字重合（拼接照搬）。
OUT_OF_DRAFT_MAX_RATIO = 0.78
CROSS_SOURCE_OVERLAP_MIN_RUN = 80


def out_of_draft_ratio(article: str, base_text: str, *, carrier: str = "article") -> float:
    """正文里有多少（按 char 三连）不来自底稿——base_draft_similarity 的反向指标。

    底稿常为主线对齐节选，正文合理扩写会抬高该值，故阈值放宽、仅兜底极端脱稿；
    细粒度“大块补写/拼接观感”交给 LLM 语义复核与跨源重叠门。
    """
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)
    body_grams = _char_ngrams(body)
    if not body_grams:
        return 0.0
    base_grams = _char_ngrams(base)
    return len(body_grams - base_grams) / len(body_grams)


def out_of_draft_issues(
    article: str,
    base_text: str,
    *,
    max_ratio: float = OUT_OF_DRAFT_MAX_RATIO,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> list[str]:
    """底稿外补写量门：正文里不来自底稿的 char 三连占比 > max_ratio 即判脱稿过度。"""
    if not base_draft_is_adaptable(source_use_mode):
        return []
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)
    if not base or not body:
        return []
    ratio = out_of_draft_ratio(article, base_text, carrier=carrier)
    if ratio > max_ratio:
        return [
            f"out-of-draft content ratio {ratio * 100:.1f}% > {int(max_ratio * 100)}% "
            "(底稿外补写过多，疑似大块脱稿/拼接，应回到底稿基础轻改而非另起炉灶)"
        ]
    return []


def cross_source_overlap_issues(
    article: str,
    base_text: str,
    other_source_texts: Mapping[str, str],
    *,
    min_run: int = CROSS_SOURCE_OVERLAP_MIN_RUN,
    carrier: str = "article",
) -> list[str]:
    """反拼接门：正文出现 >= min_run 连续字、与某个“非底稿来源”逐字重合即判拼接照搬。

    会先扣除与底稿本身重合的片段（合规轻改保留底稿原句不应被误判），只检测来自
    底稿之外来源的长串逐字搬运。other_source_texts: {sourceRef: 原文}（不含底稿源）。
    """
    body = _readable_body(article)
    if len(body) < min_run:
        return []
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)
    body_runs = {body[i : i + min_run] for i in range(len(body) - min_run + 1)}
    if len(base) >= min_run:
        base_runs = {base[i : i + min_run] for i in range(len(base) - min_run + 1)}
        body_runs -= base_runs
    if not body_runs:
        return []
    for ref, text in (other_source_texts or {}).items():
        compact = re.sub(r"\s+", "", _normalize_embedded_newlines(str(text or "")))
        if len(compact) < min_run:
            continue
        other_runs = {compact[i : i + min_run] for i in range(len(compact) - min_run + 1)}
        hit = body_runs & other_runs
        if hit:
            sample = next(iter(hit))
            return [
                f"crossSourceOverlap: 正文出现 >= {min_run} 连续字与非底稿来源 {ref} 逐字重合"
                f"（疑似拼接照搬非底稿来源），样本『{sample[:24]}…』"
            ]
    return []


__all__ = [
    "FIDELITY_MIN",
    "FIDELITY_MAX",
    "OUT_OF_DRAFT_MAX_RATIO",
    "CROSS_SOURCE_OVERLAP_MIN_RUN",
    "out_of_draft_ratio",
    "out_of_draft_issues",
    "cross_source_overlap_issues",
    "ADAPTABLE_SOURCE_USE_MODES",
    "base_draft_is_adaptable",
    "load_base_draft_ledger",
    "save_base_draft_ledger",
    "occupied_source_refs",
    "base_draft_candidates",
    "assign_base_draft",
    "extract_base_draft_body",
    "intent_aligned_base_text",
    "load_base_draft_text",
    "sibling_source_texts",
    "load_intent_aligned_base_draft_text",
    "base_source_use_mode",
    "base_draft_similarity",
    "base_draft_fidelity_issues",
]
