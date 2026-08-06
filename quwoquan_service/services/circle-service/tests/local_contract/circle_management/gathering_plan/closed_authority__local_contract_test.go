// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-003
// readiness_case: gathering-plan-closed-authority-local
package gathering_plan_test

import (
	"errors"
	"testing"

	app "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

func TestClosedGatheringRejectsWritesWithoutMutatingPlanHistory(t *testing.T) {
	store := newMemoryPlanStore()
	authority := newAuthorityState()
	authority.set("host-1", ports.GatheringAuthority{GatheringID: "gathering-plan-3", Exists: true, CollaborationOpen: true, CurrentHost: true})
	commands := app.NewGatheringPlanCommandFacet(store, authority)
	created, err := commands.CreateGatheringPlan(commandContext("host-1", "create-closed"), app.CreateGatheringPlanCommand{
		GatheringID: "gathering-plan-3", Items: agendaItems("关闭前计划"), AcknowledgementPolicy: noAcknowledgement(),
	})
	if err != nil {
		t.Fatal(err)
	}
	before, _, _ := store.Load(queryContext("host-1"), created.PlanID)
	authority.set("host-1", ports.GatheringAuthority{GatheringID: "gathering-plan-3", Exists: true, CollaborationOpen: false, CurrentHost: true})
	_, err = commands.ProposeGatheringPlan(commandContext("host-1", "after-close"), app.ProposeGatheringPlanCommand{
		PlanID: before.ID, ExpectedPlanVersion: before.Version,
		BaseRevisionID: before.CurrentRevisionID, BaseRevisionNumber: before.CurrentRevisionNumber,
		BaseRevisionDigest: before.CurrentRevisionDigest, Items: agendaItems("关闭后写入"),
		AcknowledgementPolicy: noAcknowledgement(),
	})
	if !errors.Is(err, model.ErrGatheringUnavailable) {
		t.Fatalf("closed Gathering proposal err=%v", err)
	}
	after, _, _ := store.Load(queryContext("host-1"), created.PlanID)
	if after.Version != before.Version || len(after.Revisions) != len(before.Revisions) || len(after.Proposals) != 0 || len(store.eventLog) != 1 {
		t.Fatalf("closed authority mutated Plan: before=%#v after=%#v eventLog=%d", before, after, len(store.eventLog))
	}
	queries := app.NewGatheringPlanQueryFacet(store, authority)
	read, err := queries.GetGatheringPlan(queryContext("host-1"), "gathering-plan-3")
	if err != nil || read.CurrentRevisionDigest != before.CurrentRevisionDigest {
		t.Fatalf("immutable closed Plan history unavailable: read=%#v err=%v", read, err)
	}
}
