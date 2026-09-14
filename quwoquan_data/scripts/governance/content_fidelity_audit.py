"""只读 canonical 内容池 fidelity 基线与机械扫描。语义信号只生成复核队列。"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit, urlunsplit

SCHEMA = "quwoquan_data.content_fidelity_audit.v2"
ISSUE_CODES = (
    "carrier_mismatch", "source_incomplete", "semantic_fidelity_loss",
    "table_or_reference_loss", "media_loss", "article_no_independent_intent",
    "review_false_positive", "rights_gap",
)
SEVERITY = {code: "high" for code in ISSUE_CODES} | {"table_or_reference_loss": "medium"}
_TOKEN = re.compile(r"[A-Za-z0-9]+|[\u3400-\u9fff]")


class AuditError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _regular(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"DATA.FIDELITY.FILE_INVALID: {path}")
    if path.stat().st_size > limit:
        raise AuditError(f"DATA.FIDELITY.FILE_BOUND_EXCEEDED: {path}")
    return path.read_bytes()


def _json(path: Path, limit: int) -> tuple[dict, bytes]:
    raw = _regular(path, limit)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"DATA.FIDELITY.JSON_INVALID: {path}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"DATA.FIDELITY.DOCUMENT_INVALID: {path}")
    return value, raw


def _relative(root: Path, ref: str) -> Path:
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()):
        raise AuditError(f"DATA.FIDELITY.REF_ESCAPE: {ref}")
    return path


def _ratio(n: int, d: int) -> dict:
    return {"numerator": n, "denominator": d, "rate": round(n / d, 6) if d else None}


def _tokens(text: str) -> set[str]:
    return {v.casefold() for v in _TOKEN.findall(text)}


def _headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", text)]


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]", "", unquote(str(value or "")).casefold())


def _norm_url(value: Any) -> str:
    try:
        p = urlsplit(unquote(str(value or "")))
        return urlunsplit((p.scheme.casefold(), p.netloc.casefold(), p.path.rstrip("/"), p.query, ""))
    except ValueError:
        return ""


def _similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _carrier(ref: str) -> str:
    parts = ref.split("/")
    return "homepage" if parts[0] == "entities" else parts[1]


def _manifest_paths(root: Path) -> Iterable[Path]:
    for prefix in ("entities", "posts"):
        base = root / prefix
        if base.is_dir():
            yield from sorted(base.rglob("manifest.json"), key=lambda p: p.relative_to(root).as_posix())


def _issue(code: str, ref: str, detail: str, **facts: Any) -> dict:
    return {"code": code, "severity": SEVERITY[code], "objectRef": ref, "detail": detail, "facts": facts}


def _finding(code: str, ref: str, **facts: Any) -> dict:
    return {"code": code, "objectRef": ref, "facts": facts}


def _queue(code: str, ref: str, **signals: Any) -> dict:
    return {"reason": code, "objectRef": ref, "status": "semantic_review_required", "signals": signals}


def _source_rows(root: Path, refs: list, limit: int) -> tuple[list, list, str, int, int]:
    rows, failures, texts = [], [], []
    declared = verified = 0
    for raw_ref in refs:
        ref = str(raw_ref)
        try:
            path = _relative(root, ref)
            doc, raw = _json(path, limit)
        except (AuditError, OSError) as exc:
            failures.append({"ref": ref, "reason": str(exc)})
            continue
        evidence = []
        for item in doc.get("evidence") or []:
            declared += 1
            ev_ref = str(item.get("path") or "")
            try:
                ev = _regular(_relative(path.parent, ev_ref), limit)
                actual = _sha(ev)
                ok = actual == item.get("sha256") and len(ev) == item.get("bytes")
                verified += int(ok)
                if ok:
                    try: texts.append(ev.decode())
                    except UnicodeDecodeError: pass
                else: failures.append({"ref": f"{ref}/{ev_ref}", "reason": "digest_or_size_drift"})
                evidence.append({"ref": f"{ref}/{ev_ref}", "id": item.get("id"), "kind": item.get("kind"),
                                 "sha256": actual, "declaredSha256": item.get("sha256"), "verified": ok})
            except (AuditError, OSError) as exc:
                failures.append({"ref": f"{ref}/{ev_ref}", "reason": str(exc)})
        capture = doc.get("sourceWork", {}).get("capture", {})
        coverage = str(capture.get("coverage") or "unknown")
        method, scope = str(capture.get("method") or "unknown"), str(capture.get("scope") or "")
        ids = {str(e.get("id") or "").casefold() for e in evidence if e["verified"]}
        exact_revision = bool(re.search(r"revision|wikitext", scope, re.I)) or any("wikitext" in x for x in ids)
        parsoid = bool(re.search(r"parsoid", scope, re.I)) or any("parsoid" in x for x in ids)
        rows.append({"ref": ref, "sha256": _sha(raw), "sourceId": doc.get("sourceId"),
                     "sourceUrl": doc.get("sourceUrl"), "sourceUseMode": doc.get("sourceUseMode"),
                     "capture": {"coverage": coverage, "method": method, "scope": scope,
                                 "exactRevisionWikitext": exact_revision, "parsoid": parsoid,
                                 "semanticParseReady": coverage == "complete" and exact_revision and parsoid},
                     "sourceAttribution": doc.get("sourceAttribution"), "assets": doc.get("assets") or [],
                     "evidence": evidence})
    return rows, failures, "\n".join(texts), verified, declared


def _attribution_urls(attribution: Any) -> set[str]:
    if not isinstance(attribution, dict): return set()
    return {_norm_url(attribution.get(k)) for k in
            ("sourcePostUrl", "originalAssetUrl", "authorizationProofUrl", "termsUrl") if attribution.get(k)}


def _rights_gaps(manifest: dict, sources: list[dict], assets: list[dict]) -> list[str]:
    object_urls = _attribution_urls(manifest.get("sourceAttribution"))
    gaps = []
    for source in sources:
        url = _norm_url(source.get("sourceUrl"))
        covered = url and (url in object_urls or url in _attribution_urls(source.get("sourceAttribution")))
        if not covered and not source.get("assets"):
            gaps.append(source["ref"])
    for index, asset in enumerate(assets):
        refs = asset.get("sourceRefs") or asset.get("sourceAssetRefs") or asset.get("rightsRefs") or []
        if not refs and not object_urls:
            gaps.append(str(asset.get("assetId") or index))
    return gaps


def _inspect(path: Path, root: Path, limit: int) -> tuple[dict, list, list, list, list]:
    obj = path.parent; ref = obj.relative_to(root).as_posix(); carrier = _carrier(ref)
    manifest, manifest_raw = _json(path, limit)
    issues, findings, queue = [], [], []
    expected = carrier
    declared_carrier = str(manifest.get("contentType") or ("homepage" if manifest.get("schema") == "quwoquan_data.entity_object" else ""))
    if declared_carrier != expected:
        issues.append(_issue("carrier_mismatch", ref, "路径载体与 manifest 载体不一致", expected=expected, actual=declared_carrier))
    final_ref = str(manifest.get("finalContentRef") or ("page.md" if carrier == "homepage" else "article.md" if carrier == "article" else ""))
    try: body_raw = _regular(_relative(obj, final_ref), limit) if final_ref else b""
    except (AuditError, OSError): body_raw = b""
    body = body_raw.decode(errors="replace")
    source_refs = list(manifest.get("sourceRefs") or [])
    sources, failures, source_text, captured, declared = _source_rows(obj, source_refs, limit)
    incomplete = [s["ref"] for s in sources if s["capture"]["coverage"] != "complete"]
    if not source_refs or failures or captured < declared or incomplete:
        issues.append(_issue("source_incomplete", ref, "来源捕获或证据闭包不完整",
                             incompleteSourceRefs=incomplete, failures=failures, captureCoverage=_ratio(captured, declared)))
    capture_states = Counter(s["capture"]["coverage"] for s in sources)
    findings.append(_finding("capture_contract", ref, coverage=dict(sorted(capture_states.items())),
                             methods=sorted({s["capture"]["method"] for s in sources}),
                             semanticParseReady=all(s["capture"]["semanticParseReady"] for s in sources) if sources else False))

    source_tokens, body_tokens = _tokens(source_text), _tokens(body)
    semantic = _ratio(len(source_tokens & body_tokens), len(source_tokens))
    semantic_ready = bool(sources) and all(s["capture"]["semanticParseReady"] and
        s.get("sourceUseMode") == "licensed_adaptation" for s in sources)
    if source_tokens and semantic["rate"] is not None and semantic["rate"] < .35:
        if semantic_ready:
            issues.append(_issue("semantic_fidelity_loss", ref, "exact/full licensed adaptation 词元保留低于阈值", semanticCoverage=semantic))
        else:
            queue.append(_queue("semantic_fidelity_candidate", ref, semanticCoverage=semantic,
                                sourceCaptureComplete=not incomplete, exactSemanticParseReady=semantic_ready))

    source_table = bool(re.search(r"(?is)<table\b|\{\|", source_text))
    body_table = bool(re.search(r"<table\b|^\s*\|.+\|\s*$", body, re.I | re.M | re.S))
    source_reference = bool(re.search(r"(?is)<ref\b|\{\{\s*cite|https?://", source_text))
    body_reference = bool(re.search(r"(?is)<ref\b|\[[^]]+\]\([^)]+\)|https?://", body))
    structure_loss = (source_table and not body_table) or (source_reference and not body_reference)
    reference = _ratio(int(not structure_loss), 1)
    if structure_loss:
        if semantic_ready:
            issues.append(_issue("table_or_reference_loss", ref, "exact/full source 的表格或引用结构未保留"))
        else:
            queue.append(_queue("table_or_reference_candidate", ref, sourceHasTable=source_table,
                                bodyHasTable=body_table, sourceHasReference=source_reference,
                                bodyHasReference=body_reference))

    assets = list(manifest.get("assets") or []); media_ok = 0; media_failures = []; payload_assets = []
    for asset in assets:
        asset_ref = str(asset.get("path") or asset.get("fileName") or "")
        try:
            raw = _regular(_relative(obj, asset_ref), limit)
            actual_sha, actual_bytes = _sha(raw), len(raw)
            ok = (not asset.get("sha256") or actual_sha == asset.get("sha256")) and (not asset.get("bytes") or actual_bytes == asset.get("bytes"))
        except (AuditError, OSError):
            actual_sha, actual_bytes, ok = None, None, False
        payload_assets.append({"ref": asset_ref, "sha256": actual_sha, "bytes": actual_bytes})
        media_ok += int(ok)
        if not ok: media_failures.append(asset_ref or str(asset.get("assetId") or "missing_ref"))
    if media_failures: issues.append(_issue("media_loss", ref, "声明媒体缺失或摘要漂移", failures=media_failures))
    rights = _rights_gaps(manifest, sources, assets)
    if rights: issues.append(_issue("rights_gap", ref, "来源或媒体没有可对应的权利绑定", missing=rights))

    if carrier == "article" and not manifest.get("writingIntent"):
        findings.append(_finding("intent_contract_missing", ref, disposition="semantic_review_required_not_no_intent"))
        queue.append(_queue("intent_contract_missing", ref, publishAngle=manifest.get("publishAngle"),
                            experienceClaimMode=manifest.get("experienceClaimMode"), sourceRefs=source_refs,
                            entityRefs=manifest.get("entityRefs") or []))

    try: review, review_raw = _json(obj / "content_review.json", limit)
    except (AuditError, OSError): review, review_raw = {}, b""
    if review.get("decision") == "approved" and issues:
        issues.append(_issue("review_false_positive", ref, "approved review 与确定机械 issue 冲突",
                             conflictingIssues=sorted(i["code"] for i in issues)))
    title = str(manifest.get("title") or manifest.get("label") or manifest.get("publishTitle") or obj.parent.name)
    headings = _headings(body); source_urls = {_norm_url(s.get("sourceUrl")) for s in sources if s.get("sourceUrl")}
    identity_values = [manifest.get("entityId"), manifest.get("entityRef"), manifest.get("label"), title]
    identity_keys = sorted({_norm(v) for v in identity_values if _norm(v)})
    version_identity = {"objectId": manifest.get("entityId") or manifest.get("contentId"), "version": manifest.get("version"), "sourceIdentity": manifest.get("sourceIdentity")}
    row = {"objectRef": ref, "carrier": carrier,
        "identity": {**version_identity, "entityRef": manifest.get("entityRef"), "normalizedKeys": identity_keys},
        "digests": {"object": _sha(manifest_raw), "version": _sha(_canonical(version_identity)),
                    "payload": _sha(_canonical({"body": _sha(body_raw), "assets": payload_assets})),
                    "source": _sha(_canonical([{"ref": s["ref"], "sha256": s["sha256"], "evidence": s["evidence"]} for s in sources])), "review": _sha(review_raw)},
        "sources": sources, "coverage": {"capture": _ratio(captured, declared), "semanticSignal": semantic,
            "semanticAssessment": "mechanically_eligible" if semantic_ready else "semantic_review_required",
            "title": _ratio(len(_tokens(title) & body_tokens), len(_tokens(title))), "outline": _ratio(int(bool(headings)), 1),
            "media": _ratio(media_ok, len(assets)), "referenceSignal": reference},
        "compression": {"sourceCharacters": len(source_text), "bodyCharacters": len(body),
                        "sourceToBodyRatio": round(len(source_text) / len(body), 6) if body else None},
        "format": {"markdownDialect": manifest.get("markdownDialect") or "unknown", "schema": manifest.get("schema"), "version": manifest.get("version")},
        "generation": {"model": manifest.get("generatorModel") or "unknown", "modelBatch": manifest.get("modelBatch") or "unknown",
                       "executionId": manifest.get("executionId") or manifest.get("sourceIdentity", {}).get("executionId") or "unknown",
                       "date": str(manifest.get("createdAt") or manifest.get("publishedAt") or "unknown")[:10]},
        "reviewGate": {"decision": review.get("decision") or manifest.get("reviewDecision") or "unknown", "blockingIssueCount": len(review.get("blockingIssues") or []), "dimensionCount": len(review.get("dimensions") or [])},
        "intentEvidence": {"writingIntent": manifest.get("writingIntent"), "publishAngle": manifest.get("publishAngle"),
                           "experienceClaimMode": manifest.get("experienceClaimMode"), "sourceRefs": source_refs, "entityRefs": manifest.get("entityRefs") or []},
        "features": {"title": title, "headings": headings, "entityRefs": manifest.get("entityRefs") or [],
                     "normalizedEntityKeys": sorted({_norm(v) for v in manifest.get("entityRefs") or [] if _norm(v)}),
                     "sourceUrls": sorted(source_urls), "bodyTokens": sorted(body_tokens),
                     "sourceProviders": sorted({str(s.get("sourceId") or "unknown").split("__", 1)[0] for s in sources}) or ["unknown"],
                     "angle": "homepage" if carrier == "homepage" else str(manifest.get("publishAngle") or ref.split("/")[2]),
                     "mediaProfile": "with_media" if assets else "without_media"},
        "issueCodes": sorted(i["code"] for i in issues)}
    evidence = [e for s in sources for e in s["evidence"]]
    return row, issues, findings, queue, evidence


def _manifest_snapshot(root: Path, limit: int) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for path in _manifest_paths(root):
        raw = _regular(path, limit)
        stat = path.stat()
        snapshot[path.relative_to(root).as_posix()] = {
            "sha256": _sha(raw), "bytes": len(raw), "mtimeNs": stat.st_mtime_ns,
        }
    return snapshot


def _stratum(row: dict) -> dict[str, Any]:
    return {
        "model": row["generation"]["model"],
        "date": row["generation"]["date"],
        "source": row["features"]["sourceProviders"],
        "angle": row["features"]["angle"],
        "media": row["features"]["mediaProfile"],
    }


def _stratum_key(row: dict) -> str:
    return _canonical(_stratum(row)).decode()


def _selection_rank(row: dict) -> str:
    return _sha(_canonical({"objectRef": row["objectRef"], "digests": row["digests"]}))


def _merge_queue(queue: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in queue:
        current = merged.setdefault(item["objectRef"], {
            "objectRef": item["objectRef"], "status": "semantic_review_required",
            "reasons": [], "signals": {},
        })
        if item["reason"] not in current["reasons"]:
            current["reasons"].append(item["reason"])
        current["signals"][item["reason"]] = item["signals"]
    for item in merged.values():
        item["reasons"].sort()
        item["signals"] = dict(sorted(item["signals"].items()))
    return [merged[ref] for ref in sorted(merged)]


def scan_pool(*, publish_root: Path, max_objects: int, max_file_bytes: int) -> dict:
    root = publish_root.expanduser().resolve()
    if not root.is_dir() or root.is_symlink(): raise AuditError(f"DATA.FIDELITY.PUBLISH_ROOT_INVALID: {root}")
    if isinstance(max_objects, bool) or max_objects < 0 or max_file_bytes < 1: raise AuditError("DATA.FIDELITY.BUDGET_INVALID")
    before = _manifest_snapshot(root, max_file_bytes)
    if len(before) > max_objects: raise AuditError(f"DATA.FIDELITY.OBJECT_BOUND_EXCEEDED: limit={max_objects}")
    objects, issues, findings, queue, evidence_rows = [], [], [], [], []
    for ref in before:
        path = root / ref
        row, found, facts, pending, evidence = _inspect(path, root, max_file_bytes)
        objects.append(row); issues += found; findings += facts; queue += pending; evidence_rows += [(row["objectRef"], e) for e in evidence]
    after = _manifest_snapshot(root, max_file_bytes)
    if before != after:
        changed = sorted(set(before) ^ set(after) | {ref for ref in set(before) & set(after) if before[ref] != after[ref]})
        raise AuditError(f"DATA.FIDELITY.PUBLISH_ROOT_DRIFT: {changed[:10]}")
    first_digests = {row["objectRef"]: row["digests"] for row in objects}
    for ref in before:
        replay, *_ = _inspect(root / ref, root, max_file_bytes)
        if replay["digests"] != first_digests[replay["objectRef"]]:
            raise AuditError(f"DATA.FIDELITY.PUBLISH_ROOT_DRIFT: critical object bytes changed: {replay['objectRef']}")

    groups = defaultdict(list)
    for ref, e in evidence_rows: groups[(str(e.get("kind")), str(e.get("sha256")))].append({"objectRef": ref, "ref": e.get("ref")})
    snapshots = [{"kind": k, "sha256": d, "members": m} for (k, d), m in sorted(groups.items()) if k in {"source_snapshot", "source_excerpt"} and len(m) > 1]

    article_index = defaultdict(list)
    for row in objects:
        if row["carrier"] == "article":
            for key in row["features"]["normalizedEntityKeys"]: article_index[key].append(row)
    pairs = []
    for home in (r for r in objects if r["carrier"] == "homepage"):
        candidates = {a["objectRef"]: a for key in home["identity"]["normalizedKeys"] for a in article_index.get(key, [])}
        for article in candidates.values():
            text = _similarity(set(home["features"]["bodyTokens"]), set(article["features"]["bodyTokens"]))
            outline = _similarity({_norm(x) for x in home["features"]["headings"]}, {_norm(x) for x in article["features"]["headings"]})
            title = _similarity(_tokens(home["features"]["title"]), _tokens(article["features"]["title"]))
            overlap = _similarity(set(home["features"]["sourceUrls"]), set(article["features"]["sourceUrls"]))
            pair = {"homepageRef": home["objectRef"], "articleRef": article["objectRef"], "identityKeys": sorted(set(home["identity"]["normalizedKeys"]) & set(article["features"]["normalizedEntityKeys"])),
                    "sourceOverlap": round(overlap, 6), "textSimilarity": round(text, 6), "outlineSimilarity": round(outline, 6), "titleSimilarity": round(title, 6)}
            pairs.append(pair)
            if overlap >= .8 and text >= .9 and outline >= .8 and title >= .8:
                issue = _issue("article_no_independent_intent", article["objectRef"], "同实体文章与主页在来源、正文、结构和标题上均高度近重复", **pair)
                issues.append(issue); article["issueCodes"] = sorted(set(article["issueCodes"] + [issue["code"]]))
            else: queue.append(_queue("article_independent_intent_candidate", article["objectRef"], **pair))

    discovered_models = sorted({str(row["generation"]["model"]) for row in objects})
    grok_models = [model for model in discovered_models if "grok" in model.casefold()]
    grok_refs, high_risk_home_refs = set(), set()
    for row in objects:
        if row["carrier"] == "article" and row["generation"]["model"] in grok_models:
            grok_refs.add(row["objectRef"])
            queue.append(_queue("planned_full_grok_article_review", row["objectRef"], model=row["generation"]["model"]))
        if row["carrier"] == "homepage" and any(i["objectRef"] == row["objectRef"] and i["severity"] == "high" for i in issues):
            high_risk_home_refs.add(row["objectRef"])
            queue.append(_queue("planned_high_risk_homepage_review", row["objectRef"]))

    remaining = [row for row in objects if row["objectRef"] not in grok_refs | high_risk_home_refs]
    strata: dict[str, list[dict]] = defaultdict(list)
    for row in remaining: strata[_stratum_key(row)].append(row)
    strata_evidence = []
    issue_refs = {issue["objectRef"] for issue in issues}
    for key, members in sorted(strata.items()):
        ranked = sorted(members, key=lambda row: (_selection_rank(row), row["objectRef"]))
        initial = ranked[:1]
        escalate = any(row["objectRef"] in issue_refs for row in initial)
        selected = ranked if escalate else initial
        reason = "stratum_full_review_risk_escalation" if escalate else "stratum_deterministic_minimum_sample"
        for row in selected:
            queue.append(_queue(reason, row["objectRef"], stratum=_stratum(row), selectionRank=_selection_rank(row), population=len(members)))
        strata_evidence.append({"key": key, "dimensions": _stratum(members[0]), "population": len(members),
                                "initialSampleRefs": [row["objectRef"] for row in initial], "escalatedToFull": escalate,
                                "selectedRefs": [row["objectRef"] for row in selected]})

    queue = _merge_queue(queue)
    counts = Counter(i["code"] for i in issues)
    risks = {level: sorted({i["objectRef"] for i in issues if i["severity"] == level}) for level in ("high", "medium", "low")}
    manifest_inventory = [{"ref": ref, "sha256": value["sha256"], "bytes": value["bytes"]} for ref, value in before.items()]
    core = {"schema": SCHEMA, "purpose": "offline_read_only_mechanical_baseline",
        "reviewDisclaimer": "scanner_generated_queue_only_semantic_review_not_completed",
        "scanPolicy": {"objectRoots": ["entities", "posts"], "maxObjects": max_objects, "maxFileBytes": max_file_bytes,
                       "baselineDigestScope": "canonical_manifest_without_baselineDigest", "semanticCoverageThreshold": .35,
                       "rootStability": "two_phase_manifest_membership_digest_bytes_mtime_plus_critical_object_digest_replay",
                       "grokModelMatcher": {"field": "generatorModel", "rule": "case_insensitive_substring:grok", "discoveredMatchedValues": grok_models},
                       "stratifiedReview": {"dimensions": ["model", "date", "source", "angle", "media"],
                           "initialSelection": "one_content_addressed_minimum_per_non_priority_stratum",
                           "escalation": "full_stratum_when_initial_sample_has_mechanical_issue"},
                       "independentIntentThresholds": {"sourceOverlap": .8, "textSimilarity": .9, "outlineSimilarity": .8, "titleSimilarity": .8}},
        "manifestInventory": manifest_inventory,
        "reviewScope": {"grokArticleRefs": sorted(grok_refs), "highRiskHomepageRefs": sorted(high_risk_home_refs), "strata": strata_evidence},
        "counts": {"objects": len(objects), "issues": len(issues), "mechanicalFindings": len(findings), "semanticReviewQueue": len(queue),
                   "byCarrier": dict(sorted(Counter(r["carrier"] for r in objects).items())), "byModel": dict(sorted(Counter(r["generation"]["model"] for r in objects).items())),
                   "byIssue": {c: counts[c] for c in ISSUE_CODES},
                   "byReviewReason": dict(sorted(Counter(reason for q in queue for reason in q["reasons"]).items()))},
        "metrics": {c: _ratio(counts[c], len(objects)) for c in ISSUE_CODES}, "riskLayers": risks,
        "duplicates": {"snapshotOrExcerpt": snapshots, "homepageArticleSameEntity": sorted(pairs, key=lambda x: (x["homepageRef"], x["articleRef"]))},
        "mechanicalFindings": sorted(findings, key=lambda x: (x["objectRef"], x["code"])),
        "semanticReviewQueue": queue, "issues": sorted(issues, key=lambda x: (x["objectRef"], x["code"])), "objects": objects}
    return {**core, "baselineDigest": _sha(_canonical(core))}


def _root_receipt(requested: Path, resolved: Path) -> dict:
    stat = resolved.stat()
    return {"requestedPath": str(requested.expanduser().absolute()), "resolvedPath": str(resolved),
            "filesystem": {"device": stat.st_dev, "inode": stat.st_ino, "mtimeNs": stat.st_mtime_ns},
            "identitySemantics": "environment_receipt_only_excluded_from_content_baseline"}


def _summary(document: dict) -> dict:
    queue_by_ref = {q["objectRef"]: q["reasons"] for q in document["semanticReviewQueue"]}
    emperor = []
    for row in document["objects"]:
        if "历代帝王庙" in row["objectRef"] or "历代帝王庙" in row["features"]["title"]:
            emperor.append({"objectRef": row["objectRef"], "issueCodes": row["issueCodes"], "reviewReasons": queue_by_ref.get(row["objectRef"], [])})
    scope = document["reviewScope"]
    selected = {ref for s in scope["strata"] for ref in s["selectedRefs"]}
    grok_queued = sum(ref in queue_by_ref and "planned_full_grok_article_review" in queue_by_ref[ref] for ref in scope["grokArticleRefs"])
    return {"schema": "quwoquan_data.content_fidelity_audit_summary.v1", "baselineDigest": document["baselineDigest"],
            "counts": document["counts"], "byIssue": document["counts"]["byIssue"], "byCarrier": document["counts"]["byCarrier"],
            "byModel": document["counts"]["byModel"], "reviewReasons": document["counts"]["byReviewReason"],
            "highRiskRefs": document["riskLayers"]["high"], "grok": {"total": len(scope["grokArticleRefs"]), "covered": grok_queued},
            "strata": {"count": len(scope["strata"]), "selectedSamples": len(selected),
                       "escalated": sum(s["escalatedToFull"] for s in scope["strata"])},
            "历代帝王庙": emperor,
            "reviewDisclaimer": document["reviewDisclaimer"]}


def audit_and_write(*, publish_root: Path, output_root: Path, max_objects: int, max_file_bytes: int) -> dict:
    document = scan_pool(publish_root=publish_root, max_objects=max_objects, max_file_bytes=max_file_bytes)
    output = output_root.expanduser().resolve(); output.mkdir(parents=True, exist_ok=True)
    stem = document["baselineDigest"].removeprefix("sha256:")
    path = output / f"{stem}.json"
    receipt_path = output / f"{stem}.receipt.json"
    summary_path = output / "summary.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")); handle.write("\n")
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump({"schema": "quwoquan_data.content_fidelity_audit_receipt.v1", "baselineDigest": document["baselineDigest"],
                   "root": _root_receipt(publish_root, publish_root.expanduser().resolve()), "manifestPath": str(path)},
                  handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")); handle.write("\n")
    with summary_path.open("x", encoding="utf-8") as handle:
        json.dump(_summary(document), handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")); handle.write("\n")
    return {"schema": SCHEMA, "baselineDigest": document["baselineDigest"], "manifestPath": str(path),
            "receiptPath": str(receipt_path), "summaryPath": str(summary_path), "counts": document["counts"], "riskLayers": document["riskLayers"]}


def handle(args) -> None:
    print(json.dumps(audit_and_write(publish_root=Path(args.publish_root), output_root=Path(args.output_root),
        max_objects=args.max_objects, max_file_bytes=args.max_file_bytes), ensure_ascii=False, indent=2, sort_keys=True))
