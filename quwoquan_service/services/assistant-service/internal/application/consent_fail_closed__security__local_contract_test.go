package application

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

func TestAssistantConsentFailsClosedWithoutStore(t *testing.T) {
	t.Parallel()

	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		nil,
		rtredis.NewMemoryClient(),
	)
	ctx := context.Background()

	if _, err := service.ListConsents(ctx, "account-a"); err == nil {
		t.Fatal("ListConsents() error=nil, want unavailable")
	}
	if _, err := service.GrantSkillConsent(
		ctx,
		"account-a",
		"personal_content_access",
		"personal_content_access",
	); err == nil {
		t.Fatal("GrantSkillConsent() error=nil, want unavailable")
	}
	if err := service.RevokeSkillConsent(
		ctx,
		"account-a",
		"personal_content_access",
	); err == nil {
		t.Fatal("RevokeSkillConsent() error=nil, want unavailable")
	}
}

func TestAssistantConsentLifecycleUsesAuthoritativeStore(t *testing.T) {
	t.Parallel()

	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	ctx := context.Background()

	granted, err := service.GrantSkillConsent(
		ctx,
		"account-a",
		"personal_content_access",
		"personal_content_access",
	)
	if err != nil {
		t.Fatalf("GrantSkillConsent() error=%v", err)
	}
	if granted.UserID != "account-a" || granted.SkillID != "personal_content_access" {
		t.Fatalf("GrantSkillConsent()=%+v", granted)
	}
	items, err := service.ListConsents(ctx, "account-a")
	if err != nil {
		t.Fatalf("ListConsents() error=%v", err)
	}
	if len(items) != 1 {
		t.Fatalf("ListConsents() len=%d, want 1", len(items))
	}
	if err := service.RevokeSkillConsent(
		ctx,
		"account-a",
		"personal_content_access",
	); err != nil {
		t.Fatalf("RevokeSkillConsent() error=%v", err)
	}
	items, err = service.ListConsents(ctx, "account-a")
	if err != nil {
		t.Fatalf("ListConsents() after revoke error=%v", err)
	}
	if len(items) != 0 {
		t.Fatalf("ListConsents() after revoke len=%d, want 0", len(items))
	}
}
