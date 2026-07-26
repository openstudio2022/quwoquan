"""Cross-document similarity, register and semantic quality gates."""
from __future__ import annotations
import hashlib
import re
from typing import Iterable, Sequence
from core.public_contacts import iter_phone_numbers, normalize_number
from core.quality_gates import (
    SKELETON_ENDING_SIMILARITY, SKELETON_HEADING_SIMILARITY,
    SKELETON_NGRAM_SIMILARITY, SKELETON_NGRAM_SIZE, _WS_RE, _char_jaccard,
    _compact, _headings, _ngram_jaccard, _ngrams, _paragraphs, _strip_figures,
)

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

def register_lexicon_issues(article: str, banned_register_terms: Sequence[str]) -> list[str]:
    """命中垂类规则提供的禁用语域词即报问题（如户外景区出现"看展/展厅/展陈"）。"""
    if not banned_register_terms:
        return []
    compact = _compact(_strip_figures(article or ""))
    hits = sorted({term for term in banned_register_terms if term and term in compact})
    if hits:
        return [f"registerMismatch: banned register terms for this subject: {', '.join(hits)}"]
    return []

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

_WECHAT_RE = re.compile(r"(?:微信|wechat|weixin|加微|vx|VX)\s*[:：]?\s*[A-Za-z0-9_-]{4,}", re.IGNORECASE)

_QQ_RE = re.compile(r"(?:QQ|qq)\s*[:：]?\s*\d{5,12}")

_SHORT_NUM_RE = re.compile(r"(?<!\d)(?:1\d{2,4})(?!\d)")

def contact_info_issues(
    article: str,
    *,
    allowed_numbers: Iterable[str] = (),
) -> list[str]:
    """联系方式门：拦截正文中的私人电话/微信/QQ。

    - 微信/QQ 账号：一律拦截（私人联系方式，不得出现在编辑内容）。
    - 电话号码：归一化后不在 allowed_numbers（公共短号 + 核实的景区官方电话）即拦截。
    allowed_numbers 已归一化为纯数字串集合（由 core/public_contacts.allowed_numbers 提供）。
    """
    body = _strip_figures(article or "")
    issues: list[str] = []
    allowed = {normalize_number(n) for n in allowed_numbers if normalize_number(n)}

    if _WECHAT_RE.search(body):
        issues.append("contactInfo: 正文出现微信号（私人联系方式），禁止出现在编辑内容")
    if _QQ_RE.search(body):
        issues.append("contactInfo: 正文出现 QQ 号（私人联系方式），禁止出现在编辑内容")

    blocked: set[str] = set()
    for match in iter_phone_numbers(body):
        num = normalize_number(match.group(0))
        if num and num not in allowed:
            blocked.add(match.group(0).strip())
    if blocked:
        issues.append(
            "contactInfo: 正文出现非公开电话 " + ", ".join(sorted(blocked))
            + "（仅放行紧急/公共服务短号与 source 核实的景区官方电话）"
        )
    return issues

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

SIMHASH_NGRAM = 4

SIMHASH_BITS = 64

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
