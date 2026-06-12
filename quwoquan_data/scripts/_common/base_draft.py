"""底稿（base draft）选取、批次级占用账本与贴合度度量。

范式：以一篇真实底稿为锚做「适度加工」（轻改），而非按模板从零拼装。

- 每篇文章/主页只认领一篇底稿（某来源单元的 source.md），一源仅一稿。
- 批次级账本（`batches/<batch>/_shared/base_draft_ledger.json`）记录 sourceRef -> postRef
  一对一映射；已被占用的源在其它篇目里只能进 evidenceRefs 作补充材料，不得再当底稿。
- 贴合度采用「底稿留存率」(单向 char 三连覆盖)，与成品长度无关：
  coverage = |base_trigrams ∩ article_trigrams| / |base_trigrams|
  下限防「从零另写/换稿」(实测：从零重写≈0.24、无关文≈0.0、真实轻改≥0.7)；
  上限防「逐句搬运/未去版权」(几乎原样照搬 coverage≈1.0；另有 ≥28 字逐字命中的反抄袭硬门兜底)。
  注意：不可用对称的 difflib.ratio——底稿(数百字)远短于成品(上千字)时，
  对称比值上限≈2*len(base)/(len(base)+len(body))，永远摸不到 0.70，会误杀所有合规轻改。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, write_json
from _common.paths import batch_root, batch_shared_dir, relative_batch_ref
from _common.source_unit import iter_source_units, resolve_entity_object_dir

BASE_DRAFT_LEDGER = "base_draft_ledger.json"
LEDGER_SCHEMA = "quwoquan_data.base_draft_ledger/1"

FIDELITY_MIN = 0.55
FIDELITY_MAX = 0.97
_NGRAM = 3
_NOISE_LINE_MARKERS = (
    "登录",
    "注册",
    "联系客服",
    "我的订单",
    "举报",
    "点赞",
    "写点评",
    "上一页",
    "下一页",
    "回到顶部",
    "用户问答",
    "附近景点",
    "推荐景点",
    "附近美食",
    "附近购物",
    "热门旅游目的地推荐",
    "旅游攻略导航",
    "微信小程序",
    "扫码前往",
    "值机选座",
    "退票改签",
    "报销凭证",
    "AI行程助手",
    "特价机票",
    "企业商旅",
)


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
        if exclude_post and str(post_ref) == exclude_post:
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


def _looks_like_noise_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    letters = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", compact)
    if not letters:
        return True
    if any(marker in line for marker in _NOISE_LINE_MARKERS):
        return True
    if "http" in compact.lower():
        return True
    if re.fullmatch(r"[\d./:+\-—~～()（） ]+", compact):
        return True
    if compact.startswith(("IP属地", "第", "共")) and any(ch.isdigit() for ch in compact):
        return True
    return False


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
    for line in signal_lines[:18]:
        line_chars = len(re.sub(r"\s+", "", line))
        if total_chars >= 2200 and len(picked) >= 4:
            break
        picked.append(line)
        total_chars += line_chars

    body = "\n\n".join(picked).strip()
    return body or text


_FIGURE_RE = re.compile(r"(?ms)^:::figure.*?:::")
_ASSET_RE = re.compile(r"asset://[^\s)]+")
_GALLERY_BASE_TARGET_CHARS = 1000
_GALLERY_BASE_BODY_RATIO = 0.7


def _readable_body(article: str) -> str:
    """剥离 figure 块/asset 引用/标题井号后的可读正文（用于贴合度比较）。"""
    text = _FIGURE_RE.sub("", article)
    text = _ASSET_RE.sub("", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return re.sub(r"\s+", "", text)


def _base_excerpt_for_gallery(text: str, *, body_len: int) -> str:
    """画报正文较短，只要求贴住底稿前段主线，不强求覆盖整篇长底稿。"""
    target_chars = max(_GALLERY_BASE_TARGET_CHARS, int(body_len * _GALLERY_BASE_BODY_RATIO))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text[:target_chars]
    picked: list[str] = []
    total = 0
    for paragraph in paragraphs:
        chars = len(re.sub(r"\s+", "", paragraph))
        if picked and total >= target_chars:
            break
        picked.append(paragraph)
        total += chars
    return "\n\n".join(picked)


def _strip_source_meta(text: str, *, carrier: str = "article", body_len: int = 0) -> str:
    """去掉底稿里的 license/credit/url 等元信息行，并按载体裁切公平比较窗口。"""
    kept: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(("license", "alloweduse", "credit", "url", "source", "title:", "图片来源", "授权")):
            continue
        kept.append(line)
    filtered = "\n".join(kept).strip()
    if carrier == "gallery" and filtered:
        filtered = _base_excerpt_for_gallery(filtered, body_len=body_len)
    return re.sub(r"\s+", "", filtered)


def _char_ngrams(text: str, n: int = _NGRAM) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def base_draft_similarity(article: str, base_text: str, *, carrier: str = "article") -> float:
    """底稿留存率：底稿 char 三连里有多少在成品中出现（单向覆盖，与成品长度无关）。"""
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body))
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
) -> list[str]:
    """底稿贴合度区间门：仅当存在可读底稿时生效；底稿留存率落区间外报问题。"""
    body = _readable_body(article)
    base = _strip_source_meta(base_text, carrier=carrier, body_len=len(body))
    if not base or not body:
        return []
    sim = base_draft_similarity(article, base_text, carrier=carrier)
    pct = round(sim * 100, 1)
    if sim < min_ratio:
        return [
            f"base draft fidelity {pct}% < {int(min_ratio * 100)}% "
            "(底稿留存率过低，疑似脱离底稿/从零另写，应在底稿基础上轻改而非重写)"
        ]
    if sim > max_ratio:
        return [
            f"base draft fidelity {pct}% > {int(max_ratio * 100)}% "
            "(几乎原样照搬底稿，需进一步改写表达、去版权痕迹)"
        ]
    return []


__all__ = [
    "FIDELITY_MIN",
    "FIDELITY_MAX",
    "load_base_draft_ledger",
    "save_base_draft_ledger",
    "occupied_source_refs",
    "base_draft_candidates",
    "assign_base_draft",
    "load_base_draft_text",
    "base_draft_similarity",
    "base_draft_fidelity_issues",
]
