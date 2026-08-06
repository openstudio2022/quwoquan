// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001
// readiness_case: gathering-plan-create-propose-commit-local
package gathering_plan_test

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
)

func TestCreateProposalCommitKeepsImmutableRevisionHistory(t *testing.T) {
	now := fixedTime()
	affected := []model.ParticipationRef{{GatheringID: "gathering-plan-1", PersonaID: "participant-1"}}
	plan, err := model.Create(model.CreateInput{
		PlanID: "plan-1", GatheringID: "gathering-plan-1", ActorPersonaID: "host-1",
		Items: agendaItems("集合与出发"), AcknowledgementPolicy: model.AcknowledgementPolicy{
			Mode: model.PlanAcknowledgementModeAffectedParticipations,
		},
		AffectedParticipationRefs: affected, OccurredAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	initialJSON, _ := json.Marshal(plan.Revisions[0])
	next, proposal, err := model.RecordProposal(plan, model.ProposeInput{
		ProposalID: "proposal-1", ActorPersonaID: "participant-1",
		ExpectedPlanVersion: plan.Version, BaseRevisionID: plan.CurrentRevisionID,
		BaseRevisionNumber: plan.CurrentRevisionNumber, BaseRevisionDigest: plan.CurrentRevisionDigest,
		Items: agendaItems("集合、补给与出发"), AcknowledgementPolicy: model.AcknowledgementPolicy{
			Mode: model.PlanAcknowledgementModeAffectedParticipations,
		},
		AffectedParticipationRefs: affected, OccurredAt: now.Add(1),
	})
	if err != nil {
		t.Fatal(err)
	}
	committed, proposal, revision, err := model.CommitProposal(next, model.CommitInput{
		ProposalID: proposal.ProposalID, ActorPersonaID: "host-1",
		ExpectedPlanVersion: next.Version, ExpectedProposalDigest: proposal.ProposalDigest,
		ExpectedBaseRevisionDigest: next.CurrentRevisionDigest, OccurredAt: now.Add(2),
	})
	if err != nil {
		t.Fatal(err)
	}
	if committed.Version != 3 || len(committed.Revisions) != 2 || revision.RevisionNumber != 2 ||
		committed.CurrentRevisionID != revision.RevisionID || proposal.Status != model.ProposalStatusCommitted {
		t.Fatalf("unexpected committed Plan: version=%d revisions=%d current=%s proposal=%s",
			committed.Version, len(committed.Revisions), committed.CurrentRevisionID, proposal.Status)
	}
	unchangedJSON, _ := json.Marshal(committed.Revisions[0])
	if string(initialJSON) != string(unchangedJSON) {
		t.Fatalf("immutable revision changed\nbefore=%s\nafter=%s", initialJSON, unchangedJSON)
	}
	encoded, _ := json.Marshal(committed)
	for _, forbidden := range []string{"\"title\"", "\"schedule\"", "\"hostBinding\"", "\"participations\"", "\"capacity\"", "\"lifecycleStatus\"", "\"conversationId\""} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("GatheringPlan copied forbidden Gathering fact %s: %s", forbidden, encoded)
		}
	}
	if len(committed.Acknowledgements) != 2 || committed.Acknowledgements[1].RevisionID != revision.RevisionID {
		t.Fatalf("Plan-level acknowledgement records not revision-scoped: %#v", committed.Acknowledgements)
	}
}

func TestPlanItemsAreClosedTypedPayloads(t *testing.T) {
	minutes := 30
	items := []model.PlanItem{
		{ItemID: "agenda", Kind: model.PlanItemKindAgenda, Order: 0, Agenda: &model.AgendaItem{Content: "议程", DurationMinutes: &minutes}},
		{ItemID: "place", Kind: model.PlanItemKindPlace, Order: 1, Place: &model.PlaceItem{PlaceRef: model.SourceRef{ObjectTypeRef: "entity.homepage", ObjectID: "place-1"}}},
		{ItemID: "route", Kind: model.PlanItemKindRouteSegment, Order: 2, RouteSegment: &model.RouteSegmentItem{
			FromPlaceRef: model.SourceRef{ObjectTypeRef: "entity.homepage", ObjectID: "place-1"},
			ToPlaceRef:   model.SourceRef{ObjectTypeRef: "entity.homepage", ObjectID: "place-2"},
			TravelMode:   model.PlanTravelModeTransit,
		}},
		{ItemID: "task", Kind: model.PlanItemKindTask, Order: 3, Task: &model.TaskItem{Content: "准备补给"}},
		{ItemID: "checklist", Kind: model.PlanItemKindChecklist, Order: 4, Checklist: &model.ChecklistItem{Entries: []model.ChecklistEntry{{EntryID: "water", Content: "饮水"}}}},
		{ItemID: "note", Kind: model.PlanItemKindNote, Order: 5, Note: &model.NoteItem{Content: "只保存计划事实"}},
	}
	for index := range items {
		items[index].SourceRefs = []model.SourceRef{}
	}
	if _, err := model.Create(model.CreateInput{
		PlanID: "plan-typed", GatheringID: "gathering-typed", ActorPersonaID: "host-typed",
		Items: items, AcknowledgementPolicy: noAcknowledgement(), OccurredAt: fixedTime(),
	}); err != nil {
		t.Fatalf("six canonical PlanItem variants rejected: %v", err)
	}
	invalid := items[0]
	invalid.Note = &model.NoteItem{Content: "second payload"}
	if _, err := model.Create(model.CreateInput{
		PlanID: "plan-invalid-union", GatheringID: "gathering-typed", ActorPersonaID: "host-typed",
		Items: []model.PlanItem{invalid}, AcknowledgementPolicy: noAcknowledgement(), OccurredAt: fixedTime(),
	}); !errors.Is(err, model.ErrInvalid) {
		t.Fatalf("multi-payload PlanItem err=%v", err)
	}
}
