"""Exit gate for verify command（纯决策，逻辑在 _common.post_verify）。"""
from __future__ import annotations

from _common.evidence_contract import quality_payload_contract_issues
from _common.post_verify import verify_scope
from _common.release_integrity import release_integrity_issues
from _common.stage_reports import iter_stage_envelopes
from verify.audit_summary import write_batch_audit_summary


def _publish_gate_issues(release_id: str) -> list[str]:
    from publish.gate import gate_publish

    return gate_publish(release_id)


def gate_verify(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current"):
    """返回 (roots, issues)。issues 非空即门禁失败。"""
    roots, issues = verify_scope(task=task, batch=batch, release=release, scope=scope)
    if task and batch:
        issues.extend(_verify_runtime_stage_payloads(task, batch))
        write_batch_audit_summary(task, batch, roots=roots, issues=issues)
    if release:
        issues.extend(_publish_gate_issues(release))
        issues.extend(release_integrity_issues(release))
    elif not task and not batch:
        seen_releases: set[str] = set()
        for root in roots:
            if root.name != "posts":
                continue
            release_id = root.parent.name
            if release_id in seen_releases:
                continue
            seen_releases.add(release_id)
            issues.extend(_publish_gate_issues(release_id))
            issues.extend(release_integrity_issues(release_id))
    return roots, issues


def _verify_runtime_stage_payloads(task: str, batch: str) -> list[str]:
    issues: list[str] = []
    issues.extend(_verify_quality_analysis(task, batch))
    # 目录与资产证据链静态门（对象同构 + 来源内聚 + 相对路径 + 文风 + 受控来源类目）。
    from verify.verify_directory_evidence_chain import scan_batch, scan_task

    issues.extend(scan_task(task))
    issues.extend(scan_batch(task, batch))
    return issues


def _verify_quality_analysis(task: str, batch: str) -> list[str]:
    issues: list[str] = []
    for ref, envelope in iter_stage_envelopes(task, batch, "produce", "quality_analysis"):
        payload = envelope.get("payload") or {}
        for issue in quality_payload_contract_issues(payload):
            issues.append(f"{ref}.json: {issue}")
    return issues
