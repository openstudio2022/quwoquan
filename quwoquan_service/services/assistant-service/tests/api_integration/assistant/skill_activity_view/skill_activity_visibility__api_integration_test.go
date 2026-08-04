// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
package api_integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/infrastructure/persistence"
)

func TestSkillActivityVisibilityWatermarkIsOwnerScopedAndMonotonic(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		startupCtx, "assistant_skill_activity_api_integration",
	)
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := persistence.NewMongoVisibilityStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("EnsureIndexes() error=%v", err)
	}
	first := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	if err := store.HideBefore(
		startupCtx, "account-a", "travel_companion", first,
	); err != nil {
		t.Fatalf("HideBefore(first) error=%v", err)
	}
	if err := store.HideBefore(
		startupCtx, "account-a", "travel_companion", first.Add(-time.Hour),
	); err != nil {
		t.Fatalf("HideBefore(older) error=%v", err)
	}
	watermark, err := store.HiddenBefore(
		startupCtx, "account-a", "travel_companion",
	)
	if err != nil || watermark == nil || !watermark.Equal(first) {
		t.Fatalf("HiddenBefore()=%v error=%v", watermark, err)
	}
	foreign, err := store.HiddenBefore(
		startupCtx, "account-b", "travel_companion",
	)
	if err != nil || foreign != nil {
		t.Fatalf("foreign HiddenBefore()=%v error=%v", foreign, err)
	}
}
