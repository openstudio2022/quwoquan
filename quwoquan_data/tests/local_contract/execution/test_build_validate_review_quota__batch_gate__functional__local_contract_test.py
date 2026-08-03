"""build_validate 的独立审阅结论必须走配额门，而不是见错即停整批。

审阅是逐对象结论：审阅未过的对象应按丢弃处理，只要达标对象数仍满足配额，
    批次就必须继续推进到 publish。审阅装配前置条件属于批次级事实，不可被过采
    候选池吸收。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.controller import homepage_authoring  # noqa: E402
from content.execution.controller import homepage_review_stage  # noqa: E402
from content.execution.controller import stage_download_build  # noqa: E402
from content.homepage import homepage as homepage_module  # noqa: E402
from content.homepage import homepage_release_validation  # noqa: E402
from verify import verify_homepage_media_completeness  # noqa: E402


def _arrange(monkeypatch, *, verdicts, precondition=()):
    """verdicts 依次对应「审阅前采纳门」与「审阅后重算」两次配额判定。"""
    ctx = SimpleNamespace(execution_id="execution")
    monkeypatch.setattr(stage_download_build, "_entity_homepages_per_target", lambda _ctx: 1)
    monkeypatch.setattr(stage_download_build, "_active_spec", lambda _ctx: {})
    monkeypatch.setattr(
        homepage_module, "homepage_runtime_spec", lambda _eid, _spec: {"scope": {}}
    )
    media_scope: list[tuple[str, ...]] = []

    def _media_report(_eid, *, publishable_names):
        media_scope.append(tuple(publishable_names))
        return {"passed": True}

    monkeypatch.setattr(
        verify_homepage_media_completeness,
        "homepage_media_completeness_report",
        _media_report,
    )
    monkeypatch.setattr(
        homepage_review_stage,
        "independent_reviewer_precondition_issues",
        lambda _eid: list(precondition),
    )
    pending = list(verdicts)
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: pending.pop(0) if len(pending) > 1 else pending[0],
    )
    return ctx, media_scope


def test_review_failures_absorbed_when_quota_is_met__functional__local_contract(
    monkeypatch,
) -> None:
    reviewed = []
    monkeypatch.setattr(
        homepage_review_stage,
        "run_homepage_independent_reviews",
        lambda _ctx, _spec: reviewed.append("ran")
        or ["地点/景区/神仙居: 抄写超限", "地点/景区/缙云仙都: review attestation missing"],
    )
    verdict = homepage_authoring.HomepageQuotaVerdict(
        approved_quota=3,
        qualified_refs=(
            "地点/景区/云和梯田",
            "地点/景区/百山祖",
            "地点/景区/台州府城文化旅游区",
        ),
        discarded={"地点/景区/神仙居": ("抄写超限",)},
    )
    ctx, media_scope = _arrange(monkeypatch, verdicts=[verdict])

    result = stage_download_build._run_build_validate(ctx)

    assert reviewed == ["ran"], "审阅仍必须真实执行，只是结论改由配额门判定"
    assert result.status == "done"
    assert "3/3" in result.message
    assert media_scope == [("云和梯田", "百山祖", "台州府城文化旅游区")], (
        "图片完整性门只对准出集合负责，丢弃对象的素材缺口不参与判定"
    )


def test_review_failures_block_when_quota_is_short__functional__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        homepage_review_stage,
        "run_homepage_independent_reviews",
        lambda _ctx, _spec: ["地点/景区/神仙居: 抄写超限"],
    )
    before = homepage_authoring.HomepageQuotaVerdict(
        approved_quota=3,
        qualified_refs=(
            "地点/景区/云和梯田",
            "地点/景区/百山祖",
            "地点/景区/神仙居",
        ),
        discarded={},
    )
    after = homepage_authoring.HomepageQuotaVerdict(
        approved_quota=3,
        qualified_refs=("地点/景区/云和梯田",),
        discarded={
            "地点/景区/神仙居": ("抄写超限",),
            "地点/景区/百山祖": ("review attestation missing",),
        },
    )
    ctx, _ = _arrange(monkeypatch, verdicts=[before, after])

    result = stage_download_build._run_build_validate(ctx)

    assert result.status == "failed"
    assert "独立审阅后未达配额" in result.message
    assert "1/3" in result.message
    assert result.fallback_stage == "build_homepage"


def test_reviewer_binding_precondition_always_blocks__functional__local_contract(
    monkeypatch,
) -> None:
    """批次级装配错误不可被过采吸收，即使配额已满也必须阻断。"""

    def _unexpected(_ctx, _spec):
        raise AssertionError("装配前置条件未过时不得执行审阅")

    monkeypatch.setattr(
        homepage_review_stage, "run_homepage_independent_reviews", _unexpected
    )
    verdict = homepage_authoring.HomepageQuotaVerdict(
        approved_quota=1,
        qualified_refs=("地点/景区/云和梯田",),
        discarded={},
    )
    ctx, _ = _arrange(
        monkeypatch,
        verdicts=[verdict],
        precondition=["independent reviewer frozen model binding is invalid"],
    )

    result = stage_download_build._run_build_validate(ctx)

    assert result.status == "failed"
    assert "装配未就绪" in result.message


_TARGETS = ("云和梯田", "神仙居", "台州府城文化旅游区", "百山祖")


def _arrange_verdict(monkeypatch, *, review_issue_for, review_text, quota=3):
    ctx = SimpleNamespace(execution_id="execution")
    runtime_spec = {
        "scope": {
            "coverageTargets": [
                {"name": name, "entityType": "地点/景区"} for name in _TARGETS
            ]
        }
    }
    monkeypatch.setattr(homepage_authoring, "_active_spec", lambda _ctx: {})
    monkeypatch.setattr(
        homepage_module, "homepage_runtime_spec", lambda _eid, _spec: runtime_spec
    )
    monkeypatch.setattr(
        homepage_release_validation, "validate_entity_pages", lambda _eid, _spec: []
    )
    monkeypatch.setattr(homepage_authoring, "approved_quota", lambda _eid: quota)
    monkeypatch.setattr(
        homepage_authoring,
        "_raw_homepage_independent_review_issues",
        lambda _ctx, _domain, _etype, name: (
            [review_text] if name == review_issue_for else []
        ),
    )
    return ctx


def test_unprefixed_review_issue_is_attributed_to_its_object__functional__local_contract(
    monkeypatch,
) -> None:
    """审阅员写回的是自然语言结论，不带对象前缀也必须归属到该对象。

    归属失败会被判成「不属于任何对象」的批次级问题，把 qualified_refs 整体清空，
    单个对象的抄写超标就会让整批达标数归零——pilot-014 正是这样停摆的。
    """
    ctx = _arrange_verdict(
        monkeypatch,
        review_issue_for="百山祖",
        review_text="正文在 factual_reference_only 模式下对来源抄写度过高，未满足独立重写要求。",
    )

    verdict = homepage_authoring.homepage_quota_verdict(ctx)

    assert verdict.passed
    assert verdict.qualified_count == 3
    assert "地点/景区/百山祖" in verdict.discarded
    assert "<execution>" not in verdict.discarded, (
        "逐对象审阅结论不得升级成批次级问题"
    )


def test_batch_level_issue_still_zeroes_the_verdict__functional__local_contract(
    monkeypatch,
) -> None:
    """真正不属于任何对象的问题（spec/scope 级）仍必须清零，不可被过采吸收。"""
    ctx = _arrange_verdict(monkeypatch, review_issue_for=None, review_text="")
    monkeypatch.setattr(
        homepage_release_validation,
        "validate_entity_pages",
        lambda _eid, _spec: ["execution scope 缺少 coverageTargets"],
    )

    verdict = homepage_authoring.homepage_quota_verdict(ctx)

    assert not verdict.passed
    assert verdict.qualified_count == 0
    assert "<execution>" in verdict.discarded
