// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
package api_integration

import (
	"context"
	"slices"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestEventRecordGrowthProjectionsAreIdempotentAndRebuildable(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "event_record_growth_projection")
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

	store := persistence.NewMongoGrowthStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure EventRecord growth projection indexes: %v", err)
	}
	if err := store.EnsureActorFirstSeen(startupCtx, "2026-08-01", []string{"actor-b", "actor-a"}); err != nil {
		t.Fatalf("project first-seen cohort: %v", err)
	}
	if err := store.EnsureActorFirstSeen(startupCtx, "2026-08-02", []string{"actor-a", "actor-c"}); err != nil {
		t.Fatalf("replay first-seen cohort: %v", err)
	}
	firstDay, err := store.ListActorFirstSeen(startupCtx, "2026-08-01")
	if err != nil {
		t.Fatalf("list first cohort: %v", err)
	}
	secondDay, err := store.ListActorFirstSeen(startupCtx, "2026-08-02")
	if err != nil {
		t.Fatalf("list second cohort: %v", err)
	}
	slices.Sort(firstDay)
	slices.Sort(secondDay)
	if !slices.Equal(firstDay, []string{"actor-a", "actor-b"}) ||
		!slices.Equal(secondDay, []string{"actor-c"}) {
		t.Fatalf("first-seen setOnInsert drifted: day1=%v day2=%v", firstDay, secondDay)
	}

	updatedAt := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	activity := application.DailyActivity{
		Date:         "2026-08-02",
		ActorHashes:  []string{"actor-a", "actor-c"},
		DAU:          2,
		PV:           5,
		SessionCount: 3,
		NewActors:    1,
		UpdatedAt:    updatedAt,
	}
	if err := store.UpsertDailyActivity(startupCtx, activity); err != nil {
		t.Fatalf("upsert daily projection: %v", err)
	}
	activity.PV = 7
	activity.SessionCount = 4
	activity.UpdatedAt = updatedAt.Add(time.Minute)
	if err := store.UpsertDailyActivity(startupCtx, activity); err != nil {
		t.Fatalf("rebuild daily projection: %v", err)
	}
	items, err := store.ListDailyActivity(startupCtx, "2026-08-02", "2026-08-02")
	if err != nil {
		t.Fatalf("read rebuilt daily projection: %v", err)
	}
	if len(items) != 1 || items[0].PV != 7 || items[0].SessionCount != 4 ||
		!items[0].UpdatedAt.Equal(activity.UpdatedAt) {
		t.Fatalf("daily projection is not a single rebuilt row: %+v", items)
	}

	today := time.Now().UTC().Truncate(24 * time.Hour)
	todayActivity := application.DailyActivity{
		Date:         today.Format("2006-01-02"),
		ActorHashes:  []string{"actor-current-a", "actor-current-b"},
		DAU:          2,
		PV:           3,
		SessionCount: 2,
		NewActors:    2,
		UpdatedAt:    today.Add(time.Hour),
	}
	if err := store.UpsertDailyActivity(startupCtx, todayActivity); err != nil {
		t.Fatalf("upsert current growth projection: %v", err)
	}
	service := application.NewGrowthService(store, readinessGrowthSessions{})
	overview, err := service.Overview(startupCtx, 1)
	if err != nil {
		t.Fatalf("GetGrowthOverview application query: %v", err)
	}
	if overview.TodayDAU != 2 || overview.TodayPV != 3 ||
		overview.Source != "user_activity_daily" || len(overview.Days) != 1 {
		t.Fatalf("growth overview = %+v", overview)
	}
}

type readinessGrowthSessions struct{}

func (readinessGrowthSessions) ListDistinctSessions(
	context.Context,
	time.Time,
	time.Time,
	int,
) ([]string, int64, error) {
	return nil, 0, nil
}
