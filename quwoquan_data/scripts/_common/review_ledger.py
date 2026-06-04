"""Human-in-loop 标注账本 —— 图片/事实/文章的判定、打分、发布态唯一真相源。

状态字段（每个 ReviewItem）：
- agentJudgment: credible | doubtful           （agent 判定：可信 / 存疑）
- agentScore: 1..5                              （agent 打分）
- humanJudgment: unjudged | credible | doubtful （人判定：未判定 / 可信 / 存疑）
- humanScore: None | 1..5                       （人打分：未打分 / 1-5）
- humanOverride: None | publishable | discard   （人直接置发布态：可发布 / 丢弃）
- reprocessCount: int                            （低质量再加工次数）

派生发布态 publishState ∈ {fix, discard, publishable}（修复存疑或低质量 / 丢弃 / 可发布）：
不持久化为"事实"，统一经 resolve_publish_state 推导。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import batch_command_root

# ─── 词表 ──────────────────────────────────────────────────────────
KIND_IMAGE = "image"
KIND_FACT = "fact"
KIND_ARTICLE = "article"

JUDGE_CREDIBLE = "credible"
JUDGE_DOUBTFUL = "doubtful"
JUDGE_UNJUDGED = "unjudged"

STATE_FIX = "fix"            # 修复存疑或低质量问题
STATE_DISCARD = "discard"    # 丢弃
STATE_PUBLISHABLE = "publishable"  # 可发布

OVERRIDE_PUBLISHABLE = "publishable"
OVERRIDE_DISCARD = "discard"

DEFAULT_POLICY: dict[str, Any] = {
    # autoApprove: agent 可信且分≥agentMinScore 自动放行
    # requireHumanWhenDoubtful: agent 存疑是否一律转人工（HITL 总开关）
    # autoDiscardScoreAtMost: agent 存疑且分≤此阈值视为"明确违规"，自动 discard 不转人工
    #   （image_safety unsafe=水印/平台标记 → 1 分；needs_review 人脸边界 → 2 分）
    # 净效果：明确违规自动丢弃、明确合格自动采纳，只有真正模糊(needs_review)留给人。
    "autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True, "autoDiscardScoreAtMost": 1},
    "reprocess": {"maxAttempts": 3},
}


# ─── 数据模型 ──────────────────────────────────────────────────────
@dataclass
class ReviewItem:
    kind: str
    target: str
    agentJudgment: str = JUDGE_CREDIBLE
    agentScore: int = 3
    humanJudgment: str = JUDGE_UNJUDGED
    humanScore: int | None = None
    humanOverride: str | None = None
    reprocessCount: int = 0
    reasons: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["publishState"] = resolve_publish_state(self, DEFAULT_POLICY)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReviewItem":
        return cls(
            kind=d.get("kind", KIND_IMAGE),
            target=d.get("target", ""),
            agentJudgment=d.get("agentJudgment", JUDGE_CREDIBLE),
            agentScore=int(d.get("agentScore", 3)),
            humanJudgment=d.get("humanJudgment", JUDGE_UNJUDGED),
            humanScore=d.get("humanScore"),
            humanOverride=d.get("humanOverride"),
            reprocessCount=int(d.get("reprocessCount", 0)),
            reasons=list(d.get("reasons", [])),
            notes=d.get("notes", ""),
        )


def resolve_publish_state(item: ReviewItem, policy: dict[str, Any] | None = None) -> str:
    """推导发布态。人判定优先；其次 agent 默认放行；低质量进入可再加工/锁定。"""
    pol = policy or DEFAULT_POLICY
    auto = pol.get("autoApprove", {})
    min_score = int(auto.get("agentMinScore", 3))
    require_human_when_doubtful = bool(auto.get("requireHumanWhenDoubtful", True))
    auto_discard_at_most = auto.get("autoDiscardScoreAtMost", None)

    # 1) 人直接置发布态（最高优先）
    if item.humanOverride == OVERRIDE_DISCARD:
        return STATE_DISCARD
    if item.humanOverride == OVERRIDE_PUBLISHABLE:
        return STATE_PUBLISHABLE

    # 2) 人判定
    if item.humanJudgment == JUDGE_CREDIBLE or (item.humanScore is not None and item.humanScore >= 3):
        return STATE_PUBLISHABLE
    if item.humanJudgment == JUDGE_DOUBTFUL:
        return STATE_FIX

    # 3) 人未判定 → 看 agent
    if item.agentJudgment == JUDGE_DOUBTFUL:
        # 3a) 明确违规（agent 存疑且分≤阈值，如水印/平台标记）→ 自动丢弃，不占用人工
        if auto_discard_at_most is not None and item.agentScore <= int(auto_discard_at_most):
            return STATE_DISCARD
        # 3b) 模糊存疑（needs_review）→ 按总开关决定是否转人工
        if require_human_when_doubtful:
            return STATE_FIX
        return STATE_PUBLISHABLE if item.agentScore >= min_score else STATE_FIX

    # agent 可信
    if item.agentScore >= min_score:
        return STATE_PUBLISHABLE
    # 低质量（agent 可信但分低）→ fix（可再加工或锁定，由 reprocess_exhausted 区分）
    return STATE_FIX


def reprocess_exhausted(item: ReviewItem, policy: dict[str, Any] | None = None) -> bool:
    pol = policy or DEFAULT_POLICY
    max_attempts = int(pol.get("reprocess", {}).get("maxAttempts", 3))
    return item.reprocessCount >= max_attempts


def needs_human(item: ReviewItem, policy: dict[str, Any] | None = None) -> bool:
    """是否需要人工介入：agent 存疑未判定、人判存疑、或低质量再加工耗尽。"""
    state = resolve_publish_state(item, policy)
    if state != STATE_FIX:
        return False
    if item.humanJudgment == JUDGE_DOUBTFUL:
        return True
    if item.agentJudgment == JUDGE_DOUBTFUL and item.humanJudgment == JUDGE_UNJUDGED:
        return True
    if item.agentJudgment == JUDGE_CREDIBLE and reprocess_exhausted(item, policy):
        return True
    return False


# ─── agent 判定映射（image_safety verdict / 事实门 → ReviewItem）─────
def agent_image_item(asset_id: str, verdict: dict[str, Any]) -> ReviewItem:
    """把 image_safety 的逐图 verdict 映射成账本图片项。

    safe→可信4、text_heavy→可信3、needs_review(人脸/后端)→存疑2、unsafe(水印/平台)→存疑1。
    """
    status = str(verdict.get("status") or "needs_review")
    reasons = list(verdict.get("reasons") or [])
    if status == "safe":
        judgment, score = JUDGE_CREDIBLE, 4
    elif status == "text_heavy":
        judgment, score = JUDGE_CREDIBLE, 3
    elif status == "unsafe":
        judgment, score = JUDGE_DOUBTFUL, 1
    else:  # needs_review
        judgment, score = JUDGE_DOUBTFUL, 2
    return ReviewItem(
        kind=KIND_IMAGE,
        target=asset_id,
        agentJudgment=judgment,
        agentScore=score,
        reasons=reasons,
    )


def agent_article_item(ref: str, *, passed: bool, score: int) -> ReviewItem:
    return ReviewItem(
        kind=KIND_ARTICLE,
        target=ref,
        agentJudgment=JUDGE_CREDIBLE if passed else JUDGE_DOUBTFUL,
        agentScore=max(1, min(5, int(score))),
    )


def agent_fact_item(fact: str, *, traceable: bool) -> ReviewItem:
    return ReviewItem(
        kind=KIND_FACT,
        target=fact,
        agentJudgment=JUDGE_CREDIBLE if traceable else JUDGE_DOUBTFUL,
        agentScore=4 if traceable else 2,
        reasons=[] if traceable else ["fact not traceable to source"],
    )


# ─── 账本文档 ──────────────────────────────────────────────────────
@dataclass
class ReviewLedger:
    taskId: str
    batchId: str
    ref: str
    policy: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_POLICY))
    article: ReviewItem | None = None
    images: list[ReviewItem] = field(default_factory=list)
    facts: list[ReviewItem] = field(default_factory=list)

    def all_items(self) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        if self.article is not None:
            items.append(self.article)
        items.extend(self.images)
        items.extend(self.facts)
        return items

    def find_item(self, kind: str, target: str) -> ReviewItem | None:
        if kind == KIND_ARTICLE:
            return self.article
        pool = self.images if kind == KIND_IMAGE else self.facts
        for it in pool:
            if it.target == target:
                return it
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": "quwoquan_data.review_ledger",
            "taskId": self.taskId,
            "batchId": self.batchId,
            "ref": self.ref,
            "policy": self.policy,
            "article": self.article.to_dict() if self.article else None,
            "images": [i.to_dict() for i in self.images],
            "facts": [f.to_dict() for f in self.facts],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReviewLedger":
        return cls(
            taskId=d.get("taskId", ""),
            batchId=d.get("batchId", ""),
            ref=d.get("ref", ""),
            policy=d.get("policy") or dict(DEFAULT_POLICY),
            article=ReviewItem.from_dict(d["article"]) if d.get("article") else None,
            images=[ReviewItem.from_dict(x) for x in d.get("images", [])],
            facts=[ReviewItem.from_dict(x) for x in d.get("facts", [])],
        )


def post_publishability(ledger: ReviewLedger) -> tuple[bool, list[str], list[str]]:
    """返回 (是否可发布, 阻断原因, discard 目标列表)。

    规则：文章必须 publishable；图片/事实须 publishable 或 discard（discard→剔除）；
    任一处于 fix 即阻断。
    """
    pol = ledger.policy
    reasons: list[str] = []
    discards: list[str] = []

    if ledger.article is None:
        reasons.append("article item missing")
    else:
        st = resolve_publish_state(ledger.article, pol)
        if st != STATE_PUBLISHABLE:
            reasons.append(f"article publishState={st}")

    for it in ledger.images + ledger.facts:
        st = resolve_publish_state(it, pol)
        if st == STATE_DISCARD:
            discards.append(it.target)
        elif st != STATE_PUBLISHABLE:
            reasons.append(f"{it.kind}:{it.target} publishState={st}")

    return (not reasons), reasons, discards


# ─── sidecar 路径与读写 ────────────────────────────────────────────
def review_dir(task_id: str, batch_id: str) -> Path:
    return batch_command_root(task_id, batch_id, "produce") / "review"


def ledger_path(task_id: str, batch_id: str, ref: str) -> Path:
    return review_dir(task_id, batch_id) / "ledger" / f"{ref}.json"


def entities_path(task_id: str, batch_id: str, ref: str) -> Path:
    return review_dir(task_id, batch_id) / "entities" / f"{ref}.json"


def policy_path(task_id: str, batch_id: str) -> Path:
    return review_dir(task_id, batch_id) / "policy.json"


def load_policy(task_id: str, batch_id: str) -> dict[str, Any]:
    p = policy_path(task_id, batch_id)
    if p.exists():
        return read_json(p)
    return dict(DEFAULT_POLICY)


def load_ledger(task_id: str, batch_id: str, ref: str) -> ReviewLedger | None:
    p = ledger_path(task_id, batch_id, ref)
    if not p.exists():
        return None
    return ReviewLedger.from_dict(read_json(p))


def save_ledger(ledger: ReviewLedger) -> Path:
    p = ledger_path(ledger.taskId, ledger.batchId, ledger.ref)
    write_json(p, ledger.to_dict())
    return p


def iter_ledgers(task_id: str, batch_id: str) -> list[ReviewLedger]:
    d = review_dir(task_id, batch_id) / "ledger"
    if not d.is_dir():
        return []
    out: list[ReviewLedger] = []
    for f in sorted(d.glob("*.json")):
        out.append(ReviewLedger.from_dict(read_json(f)))
    return out
