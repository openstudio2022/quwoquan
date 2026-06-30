"""LLM-as-judge 评审严格化（rubric judge rigor）。

确定性硬门（quality_gates）只是 rule 层；rubric_review.json 是 judge 层（创作 agent按
固定 rubric 评分写回）。本模块把 2026 LLM-as-judge 业界纪律固化为可校验的门，
确保软轨判官可信，不靠口头"看起来不错"：

- 判官元数据 pin：modelId + promptHash + temperature 作为 eval 合约一部分，可复算可审计。
- 判官与生成模型不同族（self-preference 偏差 5–15% → 禁止同族自评）。
- 二元 verdict（pass/fail）+ reason-before-score（rationale 必填，留审计轨迹）。
- 偏差缓解声明：position（双序）+ verbosity（控长度）。
- jury-of-judges：高风险维度需 >= JURY_MIN 个判官多数表决。
- 校准指标：与人工 golden 标注的 agreement / Cohen's kappa（供 J 校准门复用）。

本模块只依赖标准库，不 import produce/verify，避免循环依赖；返回 list[str] 问题（空=通过）。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

JURY_MIN = 3
KAPPA_MIN = 0.6
AGREEMENT_MIN = 0.85
ALLOWED_VERDICTS = {"pass", "fail"}
ALLOWED_DECISIONS = {"approved", "revision_needed", "human_review"}


# ---------------------------------------------------------------------------
# jury-of-judges 多数表决
# ---------------------------------------------------------------------------
def jury_majority(verdicts: Sequence[str]) -> str:
    """对一组 pass/fail verdict 做多数表决；平票返回 'tie'（保守转人审）。"""
    norm = [str(v).strip().lower() for v in verdicts if str(v).strip()]
    if not norm:
        return "tie"
    passes = sum(1 for v in norm if v == "pass")
    fails = sum(1 for v in norm if v == "fail")
    if passes == fails:
        return "tie"
    return "pass" if passes > fails else "fail"


# ---------------------------------------------------------------------------
# 偏差检测：position（双序应一致）
# ---------------------------------------------------------------------------
def position_consistency_issues(order_a_verdict: str, order_b_verdict: str) -> list[str]:
    """同一草稿在两种呈现顺序下的判决应一致；不一致 → position bias 暴露，门失效。"""
    a = str(order_a_verdict).strip().lower()
    b = str(order_b_verdict).strip().lower()
    if a in ALLOWED_VERDICTS and b in ALLOWED_VERDICTS and a != b:
        return [f"positionBias: verdict flipped across presentation order ({a} vs {b}); judge untrusted"]
    return []


# ---------------------------------------------------------------------------
# 校准指标（与人工 golden 标注比对）—— J 校准门复用
# ---------------------------------------------------------------------------
def agreement_rate(judge: Sequence[Any], human: Sequence[Any]) -> float:
    pairs = list(zip(judge, human))
    if not pairs:
        return 1.0
    same = sum(1 for j, h in pairs if j == h)
    return same / len(pairs)


def cohen_kappa(judge: Sequence[Any], human: Sequence[Any]) -> float:
    """Cohen's kappa：判官与人工标注的一致性（扣除随机一致）。

    完全一致=1.0；与随机持平=0.0；无样本/单一标签退化时返回 observed agreement。
    """
    pairs = [(j, h) for j, h in zip(judge, human)]
    n = len(pairs)
    if n == 0:
        return 1.0
    po = sum(1 for j, h in pairs if j == h) / n
    labels = {x for pair in pairs for x in pair}
    pe = 0.0
    for label in labels:
        pj = sum(1 for j, _ in pairs if j == label) / n
        ph = sum(1 for _, h in pairs if h == label) / n
        pe += pj * ph
    if pe >= 1.0:
        # 退化：双方都只用同一个标签 → 无随机校正空间，用 observed agreement。
        return round(po, 4)
    return round((po - pe) / (1.0 - pe), 4)


# ---------------------------------------------------------------------------
# 单篇 rubric_review 严格性门
# ---------------------------------------------------------------------------
def review_rigor_issues(
    review: Mapping[str, Any],
    *,
    generation_model_family: str | None = None,
    require_jury: bool = False,
) -> list[str]:
    """校验一份 rubric_review.json 是否满足 LLM-as-judge 严格性纪律。

    generation_model_family：生成正文所用模型族（用于强制 judge ≠ generator 防自评偏差）。
    require_jury：高风险场景要求 >= JURY_MIN 判官多数表决。
    """
    issues: list[str] = []

    # 1) 判官元数据 pin（modelId + promptHash + temperature）
    judges = review.get("judges")
    if not judges:
        judge = review.get("judge")
        judges = [judge] if isinstance(judge, Mapping) else []
    judges = [j for j in judges if isinstance(j, Mapping)]
    if not judges:
        issues.append("judgeMetadata: missing judge block(s) (modelId/promptHash/temperature required)")
    for idx, j in enumerate(judges):
        for field in ("modelId", "promptHash", "temperature"):
            if j.get(field) in (None, ""):
                issues.append(f"judgeMetadata[{idx}]: `{field}` required (eval contract must be pinnable)")

    # 2) judge ≠ generator 模型族（self-preference 偏差）
    gen_family = generation_model_family or review.get("generationModelFamily")
    if gen_family:
        for idx, j in enumerate(judges):
            fam = str(j.get("modelFamily") or "").strip()
            if fam and fam == str(gen_family).strip():
                issues.append(
                    f"judgeFamily[{idx}]: judge family `{fam}` == generation family "
                    "(self-preference bias; use a different model family to judge)"
                )

    # 3) jury-of-judges
    if require_jury and len(judges) < JURY_MIN:
        issues.append(f"jury: high-stakes review needs >= {JURY_MIN} judges, got {len(judges)}")

    # 4) decision 合法
    decision = review.get("decision")
    if decision not in ALLOWED_DECISIONS:
        issues.append(f"decision: invalid {decision!r}; allowed={sorted(ALLOWED_DECISIONS)}")

    # 5) 维度：二元 verdict + reason-before-score（rationale 必填）
    dims = review.get("dimensions") or []
    if not dims:
        issues.append("dimensions: at least one rubric dimension required")
    for dim in dims:
        if not isinstance(dim, Mapping):
            continue
        name = dim.get("name") or "?"
        verdict = str(dim.get("verdict") or "").strip().lower()
        if verdict not in ALLOWED_VERDICTS:
            issues.append(f"dimension[{name}]: binary verdict required (pass/fail), got {dim.get('verdict')!r}")
        if not str(dim.get("rationale") or "").strip():
            issues.append(f"dimension[{name}]: rationale required (reason-before-score / critique-based)")

    # 6) 偏差缓解声明（position 双序 + verbosity 控长度）
    bias = review.get("biasControls") or {}
    if not bias.get("positionSwapApplied"):
        issues.append("biasControls: positionSwapApplied must be true (mitigate position bias)")
    if not bias.get("lengthControlApplied"):
        issues.append("biasControls: lengthControlApplied must be true (mitigate verbosity bias)")

    return issues


__all__ = [
    "JURY_MIN",
    "KAPPA_MIN",
    "AGREEMENT_MIN",
    "ALLOWED_VERDICTS",
    "ALLOWED_DECISIONS",
    "jury_majority",
    "position_consistency_issues",
    "agreement_rate",
    "cohen_kappa",
    "review_rigor_issues",
]
