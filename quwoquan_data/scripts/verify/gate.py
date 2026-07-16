"""Exit gate for verify command（纯决策，逻辑在 verify.post_verify）。"""
from __future__ import annotations

from core.evidence_contract import quality_payload_contract_issues
from verify.post_verify import verify_scope
from content.release.canonical.integrity import release_integrity_issues
from content.execution.stage_reports import iter_stage_envelopes
from verify.audit_summary import write_execution_audit_summary


def _publish_gate_issues(release_id: str) -> list[str]:
    from content.release.canonical.gate import gate_publish

    return gate_publish(release_id)


def gate_verify(*, execution_id: str | None = None, release: str | None = None, scope: str = "current"):
    """返回 (roots, issues)。issues 非空即门禁失败。"""
    roots, issues = verify_scope(execution_id=execution_id, release=release, scope=scope)
    if execution_id:
        issues.extend(_verify_runtime_stage_payloads(execution_id))
        write_execution_audit_summary(execution_id, roots=roots, issues=issues)
    if release:
        issues.extend(_publish_gate_issues(release))
        issues.extend(release_integrity_issues(release))
    elif not execution_id:
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


def _verify_runtime_stage_payloads(execution_id: str) -> list[str]:
    issues: list[str] = []
    issues.extend(_verify_quality_analysis(execution_id))
    # 目录与资产证据链静态门（对象同构 + 来源内聚 + 相对路径 + 文风 + 受控来源类目）。
    from verify.verify_directory_evidence_chain import scan_execution, scan_execution_root

    issues.extend(scan_execution_root(execution_id))
    issues.extend(scan_execution(execution_id))
    return issues


def _verify_quality_analysis(execution_id: str) -> list[str]:
    issues: list[str] = []
    for ref, envelope in iter_stage_envelopes(execution_id, "post", "quality_analysis"):
        payload = envelope.get("payload") or {}
        for issue in quality_payload_contract_issues(payload):
            issues.append(f"{ref}.json: {issue}")
    return issues
