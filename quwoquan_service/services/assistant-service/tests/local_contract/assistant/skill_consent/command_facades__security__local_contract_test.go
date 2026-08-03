// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

func TestSkillConsentFacadesFailClosedWithoutStore(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	queries := application.NewQueryFacade(nil)
	commands := application.NewCommandFacade(nil, nil)
	if _, err := queries.List(ctx, "account-a"); err == nil {
		t.Fatal("List() error=nil, want unavailable")
	}
	if _, err := commands.Grant(
		ctx,
		"grant-command",
		"account-a",
		"personal_content_access",
		[]string{"personal_content_access"},
	); err == nil {
		t.Fatal("Grant() error=nil, want unavailable")
	}
	if _, err := commands.Revoke(
		ctx,
		"revoke-command",
		"account-a",
		"personal_content_access",
	); err == nil {
		t.Fatal("Revoke() error=nil, want unavailable")
	}
}

func TestSkillConsentLifecycleUsesAuthoritativeStore(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := skillconsenttest.NewMemoryStore()
	now := time.Date(2026, 7, 31, 8, 0, 0, 0, time.UTC)
	queries := application.NewQueryFacade(store)
	commands := application.NewCommandFacade(store, func() time.Time { return now })

	granted, err := commands.Grant(
		ctx,
		"grant-command",
		"account-a",
		"personal_content_access",
		[]string{"personal_content_access", "travel.trip.read"},
	)
	if err != nil || granted.Consent == nil {
		t.Fatalf("Grant() result=%+v error=%v", granted, err)
	}
	if granted.Consent.AccountID != "account-a" ||
		granted.Consent.SkillID != "personal_content_access" ||
		len(granted.Consent.GrantedScopes) != 2 ||
		granted.Consent.GrantedScopes[0] != "personal_content_access" ||
		granted.Consent.GrantedScopes[1] != "travel.trip.read" ||
		!granted.Consent.IsGranted() {
		t.Fatalf("Grant()=%+v", granted)
	}
	replayed, err := commands.Grant(
		ctx,
		"grant-command",
		"account-a",
		"personal_content_access",
		[]string{"travel.trip.read", "personal_content_access"},
	)
	if err != nil || !replayed.Replayed || replayed.Consent == nil ||
		replayed.Consent.ID != granted.Consent.ID {
		t.Fatalf("Grant() replay=%+v error=%v", replayed, err)
	}
	noOp, err := commands.Grant(
		ctx,
		"grant-command-distinct",
		"account-a",
		"personal_content_access",
		[]string{"personal_content_access", "travel.trip.read"},
	)
	if err != nil || noOp.Changed || noOp.Replayed || noOp.Consent == nil ||
		noOp.Consent.ID != granted.Consent.ID {
		t.Fatalf("Grant() distinct no-op=%+v error=%v", noOp, err)
	}
	items, err := queries.List(ctx, "account-a")
	if err != nil || len(items) != 1 {
		t.Fatalf("List() items=%+v error=%v", items, err)
	}
	if _, err := commands.Grant(
		ctx,
		"grant-command",
		"account-a",
		"another_skill",
		[]string{"another_scope"},
	); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("Grant() reused command error=%v, want idempotency conflict", err)
	}
	if _, err := commands.Grant(
		ctx,
		"blank-scope-command",
		"account-a",
		"personal_content_access",
		[]string{},
	); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("Grant() blank scope error=%v, want invalid argument", err)
	}
	if _, err := commands.Grant(
		ctx,
		"duplicate-scope-command",
		"account-a",
		"personal_content_access",
		[]string{"travel.trip.read", "travel.trip.read"},
	); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("Grant() duplicate scope error=%v, want invalid argument", err)
	}
	if _, err := commands.Grant(
		ctx,
		"scope-conflict-command",
		"account-a",
		"personal_content_access",
		[]string{"personal_content_access", "travel.trip.read", "travel.stay.read"},
	); !errors.Is(err, model.ErrScopeConflict) {
		t.Fatalf("Grant() changed scope set error=%v, want scope conflict", err)
	}
	if _, err := commands.Revoke(
		ctx,
		"revoke-command",
		"account-a",
		"personal_content_access",
	); err != nil {
		t.Fatalf("Revoke() error=%v", err)
	}
	items, err = queries.List(ctx, "account-a")
	if err != nil || len(items) != 0 {
		t.Fatalf("List() after revoke items=%+v error=%v", items, err)
	}
}
