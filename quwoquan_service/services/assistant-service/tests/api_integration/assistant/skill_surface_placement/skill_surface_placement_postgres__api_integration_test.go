// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
package api_integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
)

type allowSurfaceAuthority struct{}

func (allowSurfaceAuthority) RequireMember(context.Context, string, string, string) error { return nil }
func (allowSurfaceAuthority) RequireAdmin(context.Context, string, string, string) error  { return nil }

type allowSharedCatalog struct{}

func (allowSharedCatalog) ValidateSharedSkillIDs(context.Context, string, []string) error { return nil }

func TestSkillSurfacePlacementPostgresCommitsCASReceiptAndOutboxAtomically(t *testing.T) {
	resetPlacementState(t)
	now := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		placementStore,
		allowSurfaceAuthority{},
		allowSharedCatalog{},
		func() time.Time { return now },
	)
	input := model.PutInput{
		SurfaceKind:      model.SurfaceConversation,
		SurfaceID:        "conversation-a",
		ActorAccountID:   "account-admin",
		ActorPersonaID:   "persona-admin",
		Policy:           model.PolicyAllSharedEligible,
		DisabledSkillIDs: []string{"travel_companion"},
		Status:           model.StatusActive,
		ExpectedRevision: 0,
		IdempotencyKey:   "placement-command-create",
	}
	created, err := commands.Put(context.Background(), input)
	if err != nil || !created.Changed || created.Placement.Revision != 1 {
		t.Fatalf("create result=%+v error=%v", created, err)
	}
	replayed, err := commands.Put(context.Background(), input)
	if err != nil || !replayed.Replayed || replayed.Placement.ID != created.Placement.ID {
		t.Fatalf("replay result=%+v error=%v", replayed, err)
	}
	input.DisabledSkillIDs = []string{}
	if _, err := commands.Put(context.Background(), input); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict error=%v", err)
	}
	input.IdempotencyKey = "placement-command-update"
	input.ExpectedRevision = 1
	updated, err := commands.Put(context.Background(), input)
	if err != nil || updated.Placement.Revision != 2 || len(updated.Placement.DisabledSkillIDs) != 0 {
		t.Fatalf("update result=%+v error=%v", updated, err)
	}
	queries := application.NewQueryFacade(placementStore, allowSurfaceAuthority{})
	allowed, err := queries.AllowsSkill(
		context.Background(),
		model.SurfaceConversation,
		"conversation-a",
		"travel_companion",
	)
	if err != nil || !allowed {
		t.Fatalf("effective allowed=%v error=%v", allowed, err)
	}
	var placements, receipts, outbox int
	if err := placementPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM skill_surface_placements),
  (SELECT COUNT(*) FROM skill_surface_placement_command_receipts),
  (SELECT COUNT(*) FROM skill_surface_placement_outbox)`).Scan(&placements, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if placements != 1 || receipts != 2 || outbox != 2 {
		t.Fatalf("placement/receipt/outbox=%d/%d/%d, want 1/2/2", placements, receipts, outbox)
	}
}
