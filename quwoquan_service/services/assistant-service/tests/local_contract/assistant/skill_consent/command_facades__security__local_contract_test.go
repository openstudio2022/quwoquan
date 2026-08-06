// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// readiness_case: grant-skill-consent-local
// readiness_case: revoke-skill-consent-local
// readiness_case: list-consents-local
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

type consentReaderStub struct {
	consents []model.Consent
}

func (stub consentReaderStub) ListActiveConsents(
	context.Context,
	string,
) ([]model.Consent, error) {
	return append([]model.Consent(nil), stub.consents...), nil
}

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
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read"},
	); err == nil {
		t.Fatal("Grant() error=nil, want unavailable")
	}
	if _, err := commands.Revoke(
		ctx,
		"revoke-command",
		"account-a",
		"travel_companion",
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
		"travel_companion",
		[]string{"assistant.memory.preferences.read", "assistant.learning.feedback_context.read"},
	)
	if err != nil || granted.Consent == nil {
		t.Fatalf("Grant() result=%+v error=%v", granted, err)
	}
	if granted.Consent.AccountID != "account-a" ||
		granted.Consent.SkillID != "travel_companion" ||
		len(granted.Consent.GrantedScopes) != 2 ||
		granted.Consent.GrantedScopes[0] != "assistant.learning.feedback_context.read" ||
		granted.Consent.GrantedScopes[1] != "assistant.memory.preferences.read" ||
		!granted.Consent.IsGranted() {
		t.Fatalf("Grant()=%+v", granted)
	}
	replayed, err := commands.Grant(
		ctx,
		"grant-command",
		"account-a",
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read", "assistant.memory.preferences.read"},
	)
	if err != nil || !replayed.Replayed || replayed.Consent == nil ||
		replayed.Consent.ID != granted.Consent.ID {
		t.Fatalf("Grant() replay=%+v error=%v", replayed, err)
	}
	noOp, err := commands.Grant(
		ctx,
		"grant-command-distinct",
		"account-a",
		"travel_companion",
		[]string{"assistant.memory.preferences.read", "assistant.learning.feedback_context.read"},
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
		"travel_companion",
		[]string{},
	); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("Grant() blank scope error=%v, want invalid argument", err)
	}
	if _, err := commands.Grant(
		ctx,
		"duplicate-scope-command",
		"account-a",
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read", "assistant.learning.feedback_context.read"},
	); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("Grant() duplicate scope error=%v, want invalid argument", err)
	}
	if _, err := commands.Grant(
		ctx,
		"scope-conflict-command",
		"account-a",
		"travel_companion",
		[]string{"assistant.memory.preferences.read", "assistant.learning.feedback_context.read", "assistant.unregistered.scope"},
	); !errors.Is(err, model.ErrScopeConflict) {
		t.Fatalf("Grant() changed scope set error=%v, want scope conflict", err)
	}
	if _, err := commands.Revoke(
		ctx,
		"revoke-command",
		"account-a",
		"travel_companion",
	); err != nil {
		t.Fatalf("Revoke() error=%v", err)
	}
	items, err = queries.List(ctx, "account-a")
	if err != nil || len(items) != 0 {
		t.Fatalf("List() after revoke items=%+v error=%v", items, err)
	}
}

func TestSkillConsentRequireUsesCurrentSkillAndRequiredScopes(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := skillconsenttest.NewMemoryStore()
	queries := application.NewQueryFacade(store)
	commands := application.NewCommandFacade(store, func() time.Time {
		return time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)
	})

	// Optional-only ContextProfiles do not touch storage and never block Skill
	// start, even when no consent reader is configured.
	if err := application.NewQueryFacade(nil).Require(
		ctx,
		"account-a",
		"travel_companion",
		nil,
	); err != nil {
		t.Fatalf("optional-only Require() error=%v", err)
	}
	if err := application.NewQueryFacade(nil).Require(
		ctx,
		"account-a",
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read"},
	); !errors.Is(err, model.ErrStorageUnavailable) {
		t.Fatalf("required scope without reader error=%v, want unavailable", err)
	}

	if _, err := commands.Grant(
		ctx,
		"travel-consent",
		"account-a",
		"travel_companion",
		[]string{"assistant.memory.preferences.read", "assistant.learning.feedback_context.read"},
	); err != nil {
		t.Fatalf("Grant() error=%v", err)
	}
	if err := queries.Require(
		ctx,
		"account-a",
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read"},
	); err != nil {
		t.Fatalf("same active consent did not cover required scope: %v", err)
	}
	if err := queries.Require(
		ctx,
		"account-a",
		"another_skill",
		[]string{"assistant.learning.feedback_context.read"},
	); !errors.Is(err, model.ErrConsentRequired) {
		t.Fatalf("foreign Skill consent error=%v, want consent required", err)
	}
	if err := queries.Require(
		ctx,
		"account-a",
		"travel_companion",
		[]string{"assistant.learning.feedback_context.read", "assistant.unregistered.scope"},
	); !errors.Is(err, model.ErrConsentRequired) {
		t.Fatalf("partial scope coverage error=%v, want consent required", err)
	}
	if err := queries.Require(
		ctx,
		"account-a",
		"travel_companion",
		[]string{""},
	); !errors.Is(err, model.ErrConsentRequired) {
		t.Fatalf("invalid required scope error=%v, want consent required", err)
	}

	// Required scopes must be covered by one current aggregate. Multiple stale
	// or corrupt active facts may never be unioned into a broader permission.
	split := application.NewQueryFacade(consentReaderStub{consents: []model.Consent{
		{
			ID:            "consent-a",
			AccountID:     "account-a",
			SkillID:       "travel_companion",
			GrantedScopes: []string{"assistant.learning.feedback_context.read"},
		},
		{
			ID:            "consent-b",
			AccountID:     "account-a",
			SkillID:       "travel_companion",
			GrantedScopes: []string{"assistant.memory.preferences.read"},
		},
	}})
	if err := split.Require(
		ctx,
		"account-a",
		"travel_companion",
		[]string{"assistant.memory.preferences.read", "assistant.learning.feedback_context.read"},
	); !errors.Is(err, model.ErrConsentRequired) {
		t.Fatalf("split active facts error=%v, want consent required", err)
	}
}
