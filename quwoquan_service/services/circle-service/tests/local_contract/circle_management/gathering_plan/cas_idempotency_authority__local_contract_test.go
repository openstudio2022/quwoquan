// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-002
// readiness_case: gathering-plan-cas-idempotency-authority-local
package gathering_plan_test

import (
	"errors"
	"testing"

	app "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

func TestCommandFacetEnforcesCASAuthorityAndIdempotency(t *testing.T) {
	store := newMemoryPlanStore()
	authority := newAuthorityState()
	authority.set("host-1", ports.GatheringAuthority{GatheringID: "gathering-plan-2", Exists: true, CollaborationOpen: true, CurrentHost: true})
	authority.set("participant-1", ports.GatheringAuthority{GatheringID: "gathering-plan-2", Exists: true, CollaborationOpen: true, ActiveParticipation: true})
	authority.set("outsider-1", ports.GatheringAuthority{GatheringID: "gathering-plan-2", Exists: true, CollaborationOpen: true})
	facet := app.NewGatheringPlanCommandFacet(store, authority)
	created, err := facet.CreateGatheringPlan(commandContext("host-1", "create-1"), app.CreateGatheringPlanCommand{
		GatheringID: "gathering-plan-2", Items: agendaItems("原计划"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if err != nil {
		t.Fatal(err)
	}
	replayed, err := facet.CreateGatheringPlan(commandContext("host-1", "create-1"), app.CreateGatheringPlanCommand{
		GatheringID: "gathering-plan-2", Items: agendaItems("原计划"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if err != nil || !replayed.Replayed || replayed.PlanID != created.PlanID || len(store.eventLog) != 1 {
		t.Fatalf("same command replay=%#v err=%v eventLog=%d", replayed, err, len(store.eventLog))
	}
	_, err = facet.CreateGatheringPlan(commandContext("host-1", "create-1"), app.CreateGatheringPlanCommand{
		GatheringID: "gathering-plan-2", Items: agendaItems("不同请求"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("same key/different digest err=%v", err)
	}
	plan, _, _ := store.Load(commandContext("participant-1", "load"), created.PlanID)
	_, err = facet.ProposeGatheringPlan(commandContext("outsider-1", "proposal-outsider"), app.ProposeGatheringPlanCommand{
		PlanID: plan.ID, ExpectedPlanVersion: plan.Version, BaseRevisionID: plan.CurrentRevisionID,
		BaseRevisionNumber: plan.CurrentRevisionNumber, BaseRevisionDigest: plan.CurrentRevisionDigest,
		Items: agendaItems("越权提案"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if !errors.Is(err, model.ErrPermissionDenied) || len(store.eventLog) != 1 {
		t.Fatalf("outsider proposal err=%v eventLog=%d", err, len(store.eventLog))
	}
	proposed, err := facet.ProposeGatheringPlan(commandContext("participant-1", "proposal-1"), app.ProposeGatheringPlanCommand{
		PlanID: plan.ID, ExpectedPlanVersion: plan.Version, BaseRevisionID: plan.CurrentRevisionID,
		BaseRevisionNumber: plan.CurrentRevisionNumber, BaseRevisionDigest: plan.CurrentRevisionDigest,
		Items: agendaItems("参与者提案"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = facet.CommitGatheringPlanProposal(commandContext("host-1", "commit-stale"), app.CommitGatheringPlanProposalCommand{
		PlanID: plan.ID, ProposalID: proposed.ProposalID, ExpectedPlanVersion: plan.Version,
		ExpectedProposalDigest: proposed.ProposalDigest, ExpectedBaseRevisionDigest: plan.CurrentRevisionDigest,
	})
	if !errors.Is(err, model.ErrVersionConflict) || len(store.eventLog) != 2 {
		t.Fatalf("stale commit err=%v eventLog=%d", err, len(store.eventLog))
	}
	committed, err := facet.CommitGatheringPlanProposal(commandContext("host-1", "commit-1"), app.CommitGatheringPlanProposalCommand{
		PlanID: plan.ID, ProposalID: proposed.ProposalID, ExpectedPlanVersion: proposed.PlanVersion,
		ExpectedProposalDigest: proposed.ProposalDigest, ExpectedBaseRevisionDigest: plan.CurrentRevisionDigest,
	})
	if err != nil || committed.CurrentRevisionNumber != 2 || len(store.eventLog) != 3 {
		t.Fatalf("commit=%#v err=%v eventLog=%d", committed, err, len(store.eventLog))
	}
}
