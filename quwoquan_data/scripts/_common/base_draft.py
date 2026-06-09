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
    quality_path = unit_dir / "source.quality.json"
    if quality_path.is_file():
        try:
            data = read_json(quality_path)
            raw = data.get("score") if isinstance(data, dict) else None
            if isinstance(raw, (int, float)):
                score = float(raw)
        except (OSError, ValueError):
            pass
    source_md = unit_dir / "source.md"
    length = 0
    if source_md.is_file():
        try:
            length = len(re.sub(r"\s+", "", source_md.read_text(encoding="utf-8")))
        except OSError:
            length = 0
    return score, length


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
            rows.append(
                {"sourceRef": source_ref, "score": score, "length": length, "unitDir": unit}
            )
    rows.sort(key=lambda r: (r["score"], r["length"]), reverse=True)
    return rows


def _normalize_to_source_ref(declared: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    """把 content_plan 里可能为「来源单元名」(如 03.gws_ctrip) 的 baseSourceRef 归一为完整 source.md 相对路径。"""
    if not declared:
        return ""
    for cand in candidates:
        ref = str(cand["sourceRef"])
        if ref == declared or ref.endswith(declared) or f"/sources/{declared}/" in ("/" + ref):
            return ref
    # 已是完整 source.md 路径或无法匹配时，原样返回（load_base_draft_text 会再尝试 .parent/source.md）。
    return declared


def assign_base_draft(
    task_id: str, batch_id: str, post_ref: str, brief: Mapping[str, Any]
) -> str | None:
    """为某篇认领唯一底稿并落账本，返回 sourceRef；无可用底稿返回 None。

    - 若 brief 已声明 baseSourceRef：尊重之，并登记账本（同一源不会被两篇认领）。
    - 否则在候选里挑质量分最高、尚未被其它篇占用的来源单元。
    """
    ledger = load_base_draft_ledger(task_id, batch_id)
    assignments: dict[str, str] = dict(ledger.get("assignments") or {})
    taken = occupied_source_refs(ledger, exclude_post=post_ref)
    candidates = base_draft_candidates(task_id, batch_id, brief)

    declared = str(brief.get("baseSourceRef") or "").strip()
    chosen = _normalize_to_source_ref(declared, candidates)
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
    """读底稿正文：优先 source.md；其相对路径以 batch 根解析。"""
    if not base_source_ref:
        return ""
    candidate = batch_root(task_id, batch_id) / str(base_source_ref)
    paths = [candidate]
    # 兼容指向 source.clean.md / 目录的情况，回退同目录 source.md。
    if candidate.name != "source.md":
        paths.append(candidate.parent / "source.md")
    for path in paths:
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                continue
    return ""


_FIGURE_RE = re.compile(r"(?ms)^:::figure.*?:::")
_ASSET_RE = re.compile(r"asset://[^\s)]+")


def _readable_body(article: str) -> str:
    """剥离 figure 块/asset 引用/标题井号后的可读正文（用于贴合度比较）。"""
    text = _FIGURE_RE.sub("", article)
    text = _ASSET_RE.sub("", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return re.sub(r"\s+", "", text)


def _strip_source_meta(text: str) -> str:
    """去掉底稿里的 license/credit/url 等元信息行，只留正文，便于公平比相似度。"""
    kept: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(("license", "alloweduse", "credit", "url", "source", "title:", "图片来源", "授权")):
            continue
        kept.append(line)
    return re.sub(r"\s+", "", "\n".join(kept))


def _char_ngrams(text: str, n: int = _NGRAM) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def base_draft_similarity(article: str, base_text: str) -> float:
    """底稿留存率：底稿 char 三连里有多少在成品中出现（单向覆盖，与成品长度无关）。"""
    body = _readable_body(article)
    base = _strip_source_meta(base_text)
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
) -> list[str]:
    """底稿贴合度区间门：仅当存在可读底稿时生效；底稿留存率落区间外报问题。"""
    base = _strip_source_meta(base_text)
    body = _readable_body(article)
    if not base or not body:
        return []
    sim = base_draft_similarity(article, base_text)
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
