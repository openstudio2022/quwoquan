// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001
// readiness_case: get-gathering-plan-local
// readiness_case: list-gathering-plan-revisions-local
package gathering_plan_test

import (
	"errors"
	"testing"

	app "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

func TestQueryFacetReadsCanonicalPlanAndImmutableRevisionHistory(t *testing.T) {
	store := newMemoryPlanStore()
	authority := newAuthorityState()
	authority.set("host-1", ports.GatheringAuthority{
		GatheringID: "gathering-plan-query", Exists: true,
		CollaborationOpen: true, CurrentHost: true,
	})
	authority.set("participant-1", ports.GatheringAuthority{
		GatheringID: "gathering-plan-query", Exists: true,
		CollaborationOpen: true, ActiveParticipation: true,
	})
	authority.set("outsider-1", ports.GatheringAuthority{
		GatheringID: "gathering-plan-query", Exists: true,
		CollaborationOpen: true,
	})
	commands := app.NewGatheringPlanCommandFacet(store, authority)
	created, err := commands.CreateGatheringPlan(
		commandContext("host-1", "query-create"),
		app.CreateGatheringPlanCommand{
			GatheringID: "gathering-plan-query", Items: agendaItems("初始计划"),
			AcknowledgementPolicy: noAcknowledgement(),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	plan, found, err := store.Load(queryContext("host-1"), created.PlanID)
	if err != nil || !found {
		t.Fatalf("load created plan found=%v err=%v", found, err)
	}
	proposal, err := commands.ProposeGatheringPlan(
		commandContext("participant-1", "query-propose"),
		app.ProposeGatheringPlanCommand{
			PlanID: plan.ID, ExpectedPlanVersion: plan.Version,
			BaseRevisionID: plan.CurrentRevisionID, BaseRevisionNumber: plan.CurrentRevisionNumber,
			BaseRevisionDigest: plan.CurrentRevisionDigest, Items: agendaItems("修订计划"),
			AcknowledgementPolicy: noAcknowledgement(),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	committed, err := commands.CommitGatheringPlanProposal(
		commandContext("host-1", "query-commit"),
		app.CommitGatheringPlanProposalCommand{
			PlanID: plan.ID, ProposalID: proposal.ProposalID,
			ExpectedPlanVersion:        proposal.PlanVersion,
			ExpectedProposalDigest:     proposal.ProposalDigest,
			ExpectedBaseRevisionDigest: plan.CurrentRevisionDigest,
		},
	)
	if err != nil {
		t.Fatal(err)
	}

	queries := app.NewGatheringPlanQueryFacet(store, authority)
	read, err := queries.GetGatheringPlan(
		queryContext("participant-1"),
		"gathering-plan-query",
	)
	if err != nil || read.ID != created.PlanID ||
		read.CurrentRevisionID != committed.CurrentRevisionID {
		t.Fatalf("GetGatheringPlan read=%#v err=%v", read, err)
	}
	revisions, err := queries.ListGatheringPlanRevisions(
		queryContext("participant-1"),
		created.PlanID,
		"",
		20,
	)
	if err != nil || len(revisions.Items) != 2 ||
		revisions.Items[0].RevisionNumber != 1 ||
		revisions.Items[1].RevisionNumber != 2 {
		t.Fatalf("ListGatheringPlanRevisions page=%#v err=%v", revisions, err)
	}
	if _, err := queries.GetGatheringPlan(
		queryContext("outsider-1"),
		"gathering-plan-query",
	); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("unauthorized GetGatheringPlan err=%v", err)
	}
	if _, err := queries.ListGatheringPlanRevisions(
		queryContext("outsider-1"),
		created.PlanID,
		"",
		20,
	); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("unauthorized ListGatheringPlanRevisions err=%v", err)
	}
}
