"""Campaign homepage receipt must preserve the typed execution-spec boundary."""

from __future__ import annotations

from content.execution.campaign import receipt as campaign_receipt
from content.execution.planning.active_spec import active_spec
from content.execution.controller import homepage_authoring
from content.execution.spec_contract import ExecutionSpec
from support.execution_manifest_fixture import ExecutionFixtureBuilder


EXECUTION_ID = (
    "20260728--travel-homepage-copy-ready--hangzhou-west-lake--pilot-999"
)


def test_homepage_review_receipt_uses_typed_effective_spec(monkeypatch) -> None:
    spec = ExecutionFixtureBuilder(EXECUTION_ID).spec()
    observed: list[dict[str, object]] = []
    receipts: list[dict[str, object]] = []
    monkeypatch.setattr(
        campaign_receipt.store,
        "load_spec_model",
        lambda _execution_id: spec,
    )

    def quota_verdict(ctx):
        assert isinstance(ctx.spec, ExecutionSpec)
        observed.append(active_spec(ctx))
        return homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=("地点/景区/测试实体",),
            discarded={},
        )

    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        quota_verdict,
    )
    monkeypatch.setattr(
        campaign_receipt,
        "_write_immutable_receipt",
        lambda path, payload: receipts.append(payload) or path,
    )

    campaign_receipt.write_review_receipt(
        root_execution_id=EXECUTION_ID,
        execution_id=EXECUTION_ID,
    )

    assert observed == [spec.to_dict()]
    assert len(receipts) == 1
    assert receipts[0]["approvedQuota"] == 1
    assert receipts[0]["qualifiedCount"] == 1
    assert receipts[0]["selectedCount"] == 1
