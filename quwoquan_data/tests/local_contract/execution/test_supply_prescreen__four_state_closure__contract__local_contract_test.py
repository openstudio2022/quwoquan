"""GWT-001/GWT-002 的四态预筛契约：不塌陷、归并有序、四类计量互不并入、阈值不得默认。

判据集中在不依赖标定取值的那一半——态的闭集、子原因、归并优先级、恢复方向与
实体级计量在阈值落定之前就必须成立；阈值本身只验「缺标定时判否」，不验具体数值。
"""
from __future__ import annotations

import pytest

from content.execution.planning.supply_prescreen import (
    CandidateVerdict,
    EntitySupplyOutcome,
    PrescreenCalibrationError,
    PrescreenThresholds,
    SupplyRecoveryDirection,
    SupplyState,
    SupplySubReason,
    classify_rejection,
    merge_candidate_verdicts,
    probe_budget_exhausted,
    probe_interrupted,
    project_for_selector,
    tally_primary_reasons,
    verdict_receipt_document,
)
from core.data_issue import DataIssueCode


def _usable() -> CandidateVerdict:
    return CandidateVerdict(state=SupplyState.PRESENT_USABLE, sub_reason=None)


class TestSixCandidateClassesStayApart:
    """GWT-001：六类实体分别得到自己的态与子原因，没有两类共用一个终态。"""

    def test_an_anchored_long_source_is_usable_and_carries_no_sub_reason(self) -> None:
        verdict = _usable()
        assert verdict.state is SupplyState.PRESENT_USABLE
        assert verdict.sub_reason is None

    def test_a_short_body_is_present_insufficient_rather_than_absent(self) -> None:
        verdict = classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE)
        assert verdict.state is SupplyState.PRESENT_INSUFFICIENT
        assert verdict.sub_reason is SupplySubReason.LENGTH_BELOW_THRESHOLD

    def test_an_off_entity_source_is_present_insufficient_not_no_candidate(self) -> None:
        """抓到了东西但不是本实体——来源在场，只是没锚定，不能记成无候选。"""
        verdict = classify_rejection(DataIssueCode.SOURCE_PAGE_TYPE_INVALID)
        assert verdict.state is SupplyState.PRESENT_INSUFFICIENT
        assert verdict.sub_reason is SupplySubReason.NOT_THIS_ENTITY

    def test_an_unreachable_candidate_is_absent_by_retrievability(self) -> None:
        verdict = classify_rejection(DataIssueCode.SOURCE_UNREADABLE)
        assert verdict.state is SupplyState.ABSENT
        assert verdict.sub_reason is SupplySubReason.NOT_LEGALLY_RETRIEVABLE

    def test_no_candidate_at_all_is_absent_by_emptiness(self) -> None:
        verdict = classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING)
        assert verdict.state is SupplyState.ABSENT
        assert verdict.sub_reason is SupplySubReason.NO_CANDIDATE

    def test_an_interrupted_probe_is_its_own_state_and_never_an_absence(self) -> None:
        verdict = probe_interrupted("worker lost its lease mid probe", resume_refs=("probe/1",))
        assert verdict.state is SupplyState.PROBE_FAILED
        assert verdict.sub_reason is SupplySubReason.PROBE_INTERRUPTED
        assert verdict.state is not SupplyState.ABSENT

    def test_the_four_states_are_four_distinct_members(self) -> None:
        """闭集不得因为「反正都进不了工作单元」而把三个非成功态并成一个。"""
        assert len(set(SupplyState)) == 4

    def test_no_state_is_expressed_as_an_empty_or_zero_shape(self) -> None:
        """GWT-001：任一态都不表述为空值、空集合或零计数。"""
        for state in SupplyState:
            assert state.value
            assert state.value not in {"", "0", "none", "null"}


class TestNonUsableVerdictsAlwaysNameASubReason:
    def test_a_non_usable_verdict_without_a_sub_reason_is_refused(self) -> None:
        for state in (
            SupplyState.PRESENT_INSUFFICIENT,
            SupplyState.ABSENT,
            SupplyState.PROBE_FAILED,
        ):
            with pytest.raises(ValueError, match="requires a sub-reason"):
                CandidateVerdict(state=state, sub_reason=None)

    def test_a_usable_verdict_carrying_a_sub_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="carries no sub-reason"):
            CandidateVerdict(
                state=SupplyState.PRESENT_USABLE,
                sub_reason=SupplySubReason.NO_CANDIDATE,
            )


class TestMergeOrder:
    """GWT-001：混合候选按归并优先级取一个首要态。"""

    def test_a_pending_probe_outranks_a_settled_shortfall(self) -> None:
        """未完成的判定不得被报告为确定的在场不足。"""
        outcome = merge_candidate_verdicts(
            "青城山",
            (
                classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
                probe_interrupted("provider timed out", resume_refs=("probe/1",)),
            ),
        )
        assert outcome.state is SupplyState.PROBE_FAILED
        assert outcome.state is not SupplyState.PRESENT_INSUFFICIENT

    def test_a_pending_probe_outranks_an_absence(self) -> None:
        outcome = merge_candidate_verdicts(
            "峨眉山",
            (
                classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
                probe_interrupted("probe cancelled", resume_refs=("probe/1",)),
            ),
        )
        assert outcome.state is SupplyState.PROBE_FAILED

    def test_one_usable_source_settles_the_entity_despite_other_failures(self) -> None:
        """已经找得到能写的来源，其余候选的失败不改变该实体可生产。"""
        outcome = merge_candidate_verdicts(
            "都江堰",
            (
                classify_rejection(DataIssueCode.SOURCE_UNREADABLE),
                probe_interrupted("probe cancelled", resume_refs=("probe/1",)),
                _usable(),
            ),
        )
        assert outcome.state is SupplyState.PRESENT_USABLE
        assert outcome.enters_frozen_work_unit is True

    def test_a_shortfall_outranks_an_absence(self) -> None:
        """看到过东西比什么都没看到信息量高，首要原因取在场不足。"""
        outcome = merge_candidate_verdicts(
            "武侯祠",
            (
                classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
                classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
            ),
        )
        assert outcome.state is SupplyState.PRESENT_INSUFFICIENT

    def test_merge_order_is_independent_of_the_order_candidates_arrive(self) -> None:
        probed = (
            probe_interrupted("timeout", resume_refs=("probe/1",)),
            classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
        )
        forward = merge_candidate_verdicts("锦里", probed)
        backward = merge_candidate_verdicts("锦里", tuple(reversed(probed)))
        assert forward.state is backward.state is SupplyState.PROBE_FAILED

    def test_an_entity_with_nothing_probed_is_a_verdict_not_an_empty_result(self) -> None:
        outcome = merge_candidate_verdicts("无候选实体", ())
        assert outcome.state is SupplyState.ABSENT
        assert outcome.sub_reason is SupplySubReason.NO_CANDIDATE


class TestUnclassifiedRejectionFailsClosed:
    """GWT-001：闭集之外的拒绝原因以 `探测失败` fail closed 并点名。"""

    _REFS = ("prescreen/probe/17",)

    def test_an_unknown_code_lands_on_probe_failed_and_names_itself(self) -> None:
        verdict = classify_rejection(
            "DATA.SOURCE.SOMETHING_NEW", resume_refs=self._REFS
        )
        assert verdict.state is SupplyState.PROBE_FAILED
        assert verdict.sub_reason is SupplySubReason.UNCLASSIFIED_REJECTION
        assert "DATA.SOURCE.SOMETHING_NEW" in verdict.detail

    def test_an_unknown_code_is_not_folded_into_absence_or_shortfall(self) -> None:
        verdict = classify_rejection(
            "DATA.SOURCE.SOMETHING_NEW", resume_refs=self._REFS
        )
        assert verdict.state not in {
            SupplyState.ABSENT,
            SupplyState.PRESENT_INSUFFICIENT,
        }

    def test_an_unclassified_rejection_never_admits_the_entity(self) -> None:
        """未归类不等价于放行：归类表有洞时不得把实体放进冻结工作单元。"""
        outcome = merge_candidate_verdicts(
            "未知原因实体",
            (classify_rejection("DATA.SOURCE.SOMETHING_NEW", resume_refs=self._REFS),),
        )
        assert outcome.enters_frozen_work_unit is False

    def test_a_data_issue_code_outside_the_table_also_fails_closed(self) -> None:
        """`SOURCE_MISSING` 字面像缺席，但没显式归类就不替它选缺席这个态。"""
        verdict = classify_rejection(
            DataIssueCode.SOURCE_MISSING, resume_refs=self._REFS
        )
        assert verdict.state is SupplyState.PROBE_FAILED
        assert verdict.sub_reason is SupplySubReason.UNCLASSIFIED_REJECTION
        assert verdict.state is not SupplyState.ABSENT
        assert DataIssueCode.SOURCE_MISSING.value in verdict.detail

    def test_classifying_an_unknown_code_without_refs_is_refused(self) -> None:
        """读不懂的原因又给不出续跑入口，实体就等于被一个无人能复查的结论丢掉。"""
        with pytest.raises(ValueError, match="resume refs"):
            classify_rejection("DATA.SOURCE.SOMETHING_NEW")

    def test_a_classified_code_needs_no_refs(self) -> None:
        """归类得了的拒绝是已判定的，不该被要求提供续跑入口。"""
        verdict = classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE)
        assert verdict.resume_refs == ()
        assert verdict.settled_evidence


class TestOnlyUsableEntersTheFrozenWorkUnit:
    def test_the_other_three_states_do_not_enter(self) -> None:
        for verdict in (
            classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
            classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
            probe_interrupted("cancelled", resume_refs=("probe/1",)),
        ):
            outcome = merge_candidate_verdicts("某实体", (verdict,))
            assert outcome.enters_frozen_work_unit is False


class TestResumabilityAndRecoveryDirection:
    """GWT-001：只有 `探测失败` 可续跑，其余两态带不可续跑的判定依据。"""

    def test_probe_failure_is_resumable(self) -> None:
        outcome = merge_candidate_verdicts("待续跑", (probe_interrupted("timeout", resume_refs=("probe/1",)),))
        assert outcome.resumable is True
        assert outcome.recovery is SupplyRecoveryDirection.RESUME_PROBE

    def test_settled_states_are_not_resumable(self) -> None:
        for verdict in (
            classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
            classify_rejection(DataIssueCode.SOURCE_PAGE_TYPE_INVALID),
            classify_rejection(DataIssueCode.SOURCE_UNREADABLE),
            classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
        ):
            outcome = merge_candidate_verdicts("已判定", (verdict,))
            assert outcome.resumable is False

    def test_the_two_absence_sub_reasons_point_at_different_actions(self) -> None:
        """不可取得指向修来源闭集，无候选指向换实体——两者不是同一件事。"""
        unreachable = merge_candidate_verdicts(
            "甲", (classify_rejection(DataIssueCode.SOURCE_UNREADABLE),)
        )
        empty = merge_candidate_verdicts(
            "乙", (classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),)
        )
        assert unreachable.recovery is SupplyRecoveryDirection.WIDEN_SOURCE_CLOSURE
        assert empty.recovery is SupplyRecoveryDirection.SWAP_ENTITY
        assert unreachable.recovery is not empty.recovery

    def test_the_two_shortfall_sub_reasons_point_at_different_actions(self) -> None:
        short = merge_candidate_verdicts(
            "丙", (classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),)
        )
        off_entity = merge_candidate_verdicts(
            "丁", (classify_rejection(DataIssueCode.SOURCE_PAGE_TYPE_INVALID),)
        )
        assert (
            short.recovery
            is SupplyRecoveryDirection.ADJUST_LENGTH_THRESHOLD_OR_SWAP_ENTITY
        )
        assert off_entity.recovery is SupplyRecoveryDirection.WIDEN_SOURCE_CLOSURE
        assert short.recovery is not off_entity.recovery

    def test_every_sub_reason_has_a_recovery_direction(self) -> None:
        """新增子原因却不给恢复方向，运营者就只拿到一个无处下手的终态。"""
        for sub_reason in SupplySubReason:
            pending = sub_reason in {
                SupplySubReason.PROBE_INTERRUPTED,
                SupplySubReason.UNCLASSIFIED_REJECTION,
            }
            verdict = CandidateVerdict(
                state=SupplyState.PROBE_FAILED if pending else SupplyState.ABSENT,
                sub_reason=sub_reason,
                resume_refs=("probe/1",) if pending else (),
                settled_evidence="" if pending else "graded from the probe result",
            )
            outcome = merge_candidate_verdicts("戊", (verdict,))
            assert outcome.recovery is not None


class TestResumeRefsAndSettledEvidenceAreMutuallyExclusive:
    """DEC-007：可续跑 refs 与不可续跑判定依据由同一约束互斥，不得同时在场或同时缺席。"""

    def test_a_probe_failure_without_refs_is_refused(self) -> None:
        with pytest.raises(ValueError, match="non-empty resume refs"):
            CandidateVerdict(
                state=SupplyState.PROBE_FAILED,
                sub_reason=SupplySubReason.PROBE_INTERRUPTED,
                resume_refs=(),
            )

    def test_a_probe_failure_carrying_settled_evidence_is_refused(self) -> None:
        """未完成的判定不得同时声称自己是据某个依据判定的。"""
        with pytest.raises(ValueError, match="verdict is pending"):
            CandidateVerdict(
                state=SupplyState.PROBE_FAILED,
                sub_reason=SupplySubReason.PROBE_INTERRUPTED,
                resume_refs=("probe/1",),
                settled_evidence="graded",
            )

    def test_a_settled_state_carrying_resume_refs_is_refused(self) -> None:
        with pytest.raises(ValueError, match="carries no resume refs"):
            CandidateVerdict(
                state=SupplyState.ABSENT,
                sub_reason=SupplySubReason.NO_CANDIDATE,
                resume_refs=("probe/1",),
                settled_evidence="graded",
            )

    def test_a_settled_state_without_evidence_is_refused(self) -> None:
        with pytest.raises(ValueError, match="evidence it was settled on"):
            CandidateVerdict(
                state=SupplyState.PRESENT_INSUFFICIENT,
                sub_reason=SupplySubReason.LENGTH_BELOW_THRESHOLD,
            )

    def test_the_outcome_cannot_claim_resumability_it_has_no_refs_for(self) -> None:
        with pytest.raises(ValueError, match="disagree"):
            EntitySupplyOutcome(
                entity_name="己",
                state=SupplyState.PROBE_FAILED,
                sub_reason=SupplySubReason.PROBE_INTERRUPTED,
                resumable=True,
                recovery=SupplyRecoveryDirection.RESUME_PROBE,
                resume_refs=(),
            )

    def test_refs_survive_the_merge_onto_the_entity(self) -> None:
        """归并后 refs 必须还在，否则续跑入口在聚合那一步就丢了。"""
        outcome = merge_candidate_verdicts(
            "庚", (probe_interrupted("timeout", resume_refs=("prescreen/probe/9",)),)
        )
        assert outcome.resume_refs == ("prescreen/probe/9",)
        assert outcome.settled_evidence == ""

    def test_settled_evidence_survives_the_merge_onto_the_entity(self) -> None:
        outcome = merge_candidate_verdicts(
            "辛", (classify_rejection(DataIssueCode.SOURCE_UNREADABLE),)
        )
        assert outcome.settled_evidence
        assert outcome.resume_refs == ()


class TestSelectorProjectionIsOneWayAndLossy:
    """DEC-009：四态单向投影给选择器，投影有损且不可反推。"""

    def test_only_usable_projects_to_admission(self) -> None:
        usable = merge_candidate_verdicts("壬", (_usable(),))
        assert project_for_selector(usable) is True

    def test_all_three_non_usable_states_project_the_same_way(self) -> None:
        """三个非成功态投影后不可区分——这正是它们不能只靠布尔面呈现的原因。"""
        projections = {
            project_for_selector(merge_candidate_verdicts("癸", (verdict,)))
            for verdict in (
                classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
                classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
                probe_interrupted("timeout", resume_refs=("probe/1",)),
            )
        }
        assert projections == {False}

    def test_the_verdict_keeps_the_distinction_the_projection_drops(self) -> None:
        """投影丢掉的区分必须仍能从 verdict 读到，否则就是把四态塌成两态。"""
        outcomes = [
            merge_candidate_verdicts("子", (verdict,))
            for verdict in (
                classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),
                classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),
                probe_interrupted("timeout", resume_refs=("probe/1",)),
            )
        ]
        assert len({outcome.state for outcome in outcomes}) == 3
        assert len({project_for_selector(outcome) for outcome in outcomes}) == 1


class TestBudgetExhaustionIsUnfinishedNotAbsent:
    def test_exhausted_budget_reports_undetermined(self) -> None:
        verdict = probe_budget_exhausted(budget=3, resume_refs=("probe/1",))
        assert verdict.state is SupplyState.PROBE_FAILED
        assert verdict.state is not SupplyState.ABSENT
        assert "3" in verdict.detail


class TestPrimaryReasonTally:
    """GWT-002：四类分子分母可算，判定未完成单独计量。"""

    def _outcomes(self):
        return (
            merge_candidate_verdicts("u1", (_usable(),)),
            merge_candidate_verdicts("u2", (_usable(),)),
            merge_candidate_verdicts(
                "a1", (classify_rejection(DataIssueCode.SOURCE_UNREADABLE),)
            ),
            merge_candidate_verdicts(
                "a2",
                (classify_rejection(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING),),
            ),
            merge_candidate_verdicts(
                "s1", (classify_rejection(DataIssueCode.SOURCE_CONTENT_INCOMPLETE),)
            ),
            merge_candidate_verdicts(
                "o1", (classify_rejection(DataIssueCode.SOURCE_PAGE_TYPE_INVALID),)
            ),
            merge_candidate_verdicts("p1", (probe_interrupted("timeout", resume_refs=("probe/1",)),)),
        )

    def test_each_entity_lands_in_exactly_one_class(self) -> None:
        tally = tally_primary_reasons(self._outcomes())
        assert tally.graded == 7

    def test_undetermined_is_counted_apart_from_the_three_settled_classes(self) -> None:
        tally = tally_primary_reasons(self._outcomes())
        assert tally.undetermined == 1
        assert tally.no_retrievable_source == 2
        assert tally.body_below_threshold == 1
        assert tally.not_this_entity == 1
        assert tally.usable == 2

    def test_an_undetermined_entity_does_not_inflate_absence(self) -> None:
        """把未完成并进缺席，会让供给命中率看起来是测出来的，其实有一部分没测完。"""
        settled_only = tally_primary_reasons(
            (merge_candidate_verdicts("p1", (probe_interrupted("timeout", resume_refs=("probe/1",)),)),)
        )
        assert settled_only.no_retrievable_source == 0
        assert settled_only.undetermined == 1

    def test_a_share_over_zero_graded_entities_is_refused(self) -> None:
        """零分母不得报成 0%——那会把「没筛过」读成「一个都没落空」。"""
        empty = tally_primary_reasons(())
        with pytest.raises(ValueError, match="no graded entity"):
            empty.share(0)

    def test_shares_are_computed_against_the_graded_total(self) -> None:
        tally = tally_primary_reasons(self._outcomes())
        assert tally.share(tally.usable) == pytest.approx(2 / 7)


class TestThresholdsRefuseToDefault:
    """OPEN-001：阈值只能来自 calibration receipt，缺标定判否而不是回落常量。"""

    _CALIBRATED = {
        "articleBodyMinCharacters": 1200,
        "entityAnchorMinConfidence": 0.82,
        "perEntityProbeBudget": 4,
        "imageSupplyMinCandidates": 2,
    }

    def test_a_receipt_without_the_block_is_refused(self) -> None:
        with pytest.raises(PrescreenCalibrationError, match="no frozenPrescreen"):
            PrescreenThresholds.from_calibration_receipt(
                {"frozenCapacity": {"fleetMaxConcurrentWorkers": 8}}
            )

    def test_the_refusal_says_the_values_cannot_be_borrowed(self) -> None:
        """成稿字数门槛与容量取值都不是预筛阈值的合法来源，判否文本要说清。"""
        with pytest.raises(PrescreenCalibrationError) as caught:
            PrescreenThresholds.from_calibration_receipt({})
        message = str(caught.value)
        assert "GATE_BLOCK" in message
        assert "default" in message

    def test_a_partially_calibrated_block_is_refused_and_names_the_gap(self) -> None:
        partial = dict(self._CALIBRATED)
        del partial["perEntityProbeBudget"]
        with pytest.raises(PrescreenCalibrationError) as caught:
            PrescreenThresholds.from_calibration_receipt({"frozenPrescreen": partial})
        assert "perEntityProbeBudget" in str(caught.value)

    def test_a_complete_block_yields_the_calibrated_values(self) -> None:
        thresholds = PrescreenThresholds.from_calibration_receipt(
            {"frozenPrescreen": dict(self._CALIBRATED)}
        )
        assert thresholds.article_body_min_characters == 1200
        assert thresholds.entity_anchor_min_confidence == pytest.approx(0.82)
        assert thresholds.per_entity_probe_budget == 4
        assert thresholds.image_supply_min_candidates == 2

    def test_a_zero_probe_budget_is_refused_rather_than_read_as_unbounded(self) -> None:
        broken = dict(self._CALIBRATED) | {"perEntityProbeBudget": 0}
        with pytest.raises(PrescreenCalibrationError, match="at least one probe"):
            PrescreenThresholds.from_calibration_receipt({"frozenPrescreen": broken})

    def test_a_confidence_outside_the_unit_interval_is_refused(self) -> None:
        for value in (0, 1.5, -0.2):
            broken = dict(self._CALIBRATED) | {"entityAnchorMinConfidence": value}
            with pytest.raises(PrescreenCalibrationError, match="0, 1"):
                PrescreenThresholds.from_calibration_receipt(
                    {"frozenPrescreen": broken}
                )

    def test_thresholds_cannot_be_built_without_naming_every_bound(self) -> None:
        with pytest.raises(TypeError):
            PrescreenThresholds(article_body_min_characters=1200)  # type: ignore[call-arg]


class TestVerdictReceiptDocument:
    """DEC-008：预筛终态落 create-once receipt，四态与四类计量都从同一批 outcome 派生。"""

    _DIGEST = "sha256:" + "a" * 64

    def _document(self, outcomes) -> dict:
        return verdict_receipt_document(
            execution_id="20260828--travel-homepage-m10--sichuan--pilot-009",
            carrier="article",
            calibration_receipt_digest=self._DIGEST,
            prescreened_at="2026-08-28T08:00:00Z",
            outcomes=outcomes,
        )

    def _mixed(self):
        return (
            merge_candidate_verdicts("u1", (_usable(),)),
            merge_candidate_verdicts(
                "a1", (classify_rejection(DataIssueCode.SOURCE_UNREADABLE),)
            ),
            merge_candidate_verdicts(
                "p1", (probe_interrupted("timeout", resume_refs=("probe/3",)),)
            ),
        )

    def test_the_document_validates_against_the_receipt_schema(self) -> None:
        from core.schema import assert_valid

        assert_valid(
            self._document(self._mixed()),
            "execution",
            "source_prescreen_verdict_receipt",
        )

    def test_out_of_frozen_entities_are_still_rows_in_the_receipt(self) -> None:
        """出局实体不在冻结集里，它们的首要原因只有这里能读到。"""
        document = self._document(self._mixed())
        assert [row["entityName"] for row in document["verdicts"]] == ["u1", "a1", "p1"]

    def test_counts_are_derived_from_the_same_outcomes_as_the_rows(self) -> None:
        document = self._document(self._mixed())
        counts = document["primaryReasonCounts"]
        assert sum(counts.values()) == len(document["verdicts"])
        assert counts["undetermined"] == 1
        assert counts["noRetrievableSource"] == 1
        assert counts["usable"] == 1

    def test_a_pending_row_keeps_its_refs_and_carries_no_settled_evidence(self) -> None:
        document = self._document(self._mixed())
        pending = next(
            row for row in document["verdicts"] if row["state"] == "probe_failed"
        )
        assert pending["resumeRefs"] == ["probe/3"]
        assert "settledEvidence" not in pending
        assert pending["recovery"] == "resume_probe"

    def test_a_settled_row_carries_evidence_and_no_refs(self) -> None:
        document = self._document(self._mixed())
        settled = next(row for row in document["verdicts"] if row["state"] == "absent")
        assert settled["settledEvidence"]
        assert "resumeRefs" not in settled

    def test_a_usable_row_carries_no_sub_reason_and_no_recovery(self) -> None:
        document = self._document(self._mixed())
        usable = next(
            row for row in document["verdicts"] if row["state"] == "present_usable"
        )
        assert "subReason" not in usable
        assert usable["recovery"] == "none"

    def test_an_empty_candidate_set_is_refused_rather_than_written_as_zero(self) -> None:
        """零行 receipt 会把「没筛过」写成「候选集为空」，两者不是同一件事。"""
        with pytest.raises(ValueError, match="unscreened"):
            self._document(())

    def test_the_schema_refuses_a_pending_row_without_refs(self) -> None:
        from core.schema import assert_valid

        document = self._document(self._mixed())
        for row in document["verdicts"]:
            if row["state"] == "probe_failed":
                del row["resumeRefs"]
        with pytest.raises(ValueError, match="schema violation"):
            assert_valid(
                document, "execution", "source_prescreen_verdict_receipt"
            )

    def test_the_schema_refuses_a_settled_row_carrying_refs(self) -> None:
        from core.schema import assert_valid

        document = self._document(self._mixed())
        for row in document["verdicts"]:
            if row["state"] == "absent":
                row["resumeRefs"] = ["probe/9"]
        with pytest.raises(ValueError, match="schema violation"):
            assert_valid(
                document, "execution", "source_prescreen_verdict_receipt"
            )

    def test_the_schema_refuses_a_state_outside_the_closed_set(self) -> None:
        from core.schema import assert_valid

        document = self._document(self._mixed())
        document["verdicts"][0]["state"] = "probably_fine"
        with pytest.raises(ValueError, match="schema violation"):
            assert_valid(
                document, "execution", "source_prescreen_verdict_receipt"
            )

    def test_the_receipt_points_back_at_the_calibration_it_used(self) -> None:
        """指不回一份标定回执的 verdict 不成立——阈值就没有来源。"""
        document = self._document(self._mixed())
        assert document["calibrationReceiptDigest"] == self._DIGEST


class TestClassificationDoesNotBorrowFromDraftQualityGates:
    def test_the_table_only_maps_the_four_prescreen_codes(self) -> None:
        """归类表扩张就是塌陷的入口：新 code 必须显式归类而不是顺手挂上一个态。"""
        from content.execution.planning import supply_prescreen

        assert set(supply_prescreen._CODE_CLASSIFICATION) == {
            DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
            DataIssueCode.SOURCE_UNREADABLE,
            DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
            DataIssueCode.SOURCE_PAGE_TYPE_INVALID,
        }
