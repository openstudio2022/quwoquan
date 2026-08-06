// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestGrowthOverviewUsesTheCanonicalObjectProjection(t *testing.T) {
	now := time.Now().UTC()
	store := persistence.NewMemoryGrowthStore()
	service := application.NewGrowthService(store, readinessGrowthSessionLister{
		sessions: []string{
			"s.YWNjb3VudC1h.1",
			"s.YWNjb3VudC1i.2",
		},
		totalEvents: 3,
	})
	if err := service.AggregateDay(context.Background(), now); err != nil {
		t.Fatalf("AggregateDay() error = %v", err)
	}
	// Overview owns its wall clock. Seed the adjacent UTC dates as the same
	// bounded projection so this contract remains deterministic across midnight.
	for _, offset := range []int{-1, 0, 1} {
		day := now.AddDate(0, 0, offset).UTC().Truncate(24 * time.Hour)
		if err := store.UpsertDailyActivity(context.Background(), application.DailyActivity{
			Date:         day.Format("2006-01-02"),
			ActorHashes:  []string{"actor-a", "actor-b"},
			DAU:          2,
			PV:           3,
			SessionCount: 2,
			NewActors:    2,
			UpdatedAt:    day.Add(time.Hour),
		}); err != nil {
			t.Fatalf("seed adjacent growth projection: %v", err)
		}
	}
	overview, err := service.Overview(context.Background(), 1)
	if err != nil {
		t.Fatalf("Overview() error = %v", err)
	}
	if overview.TodayDAU != 2 || overview.TodayPV != 3 ||
		overview.Source != "user_activity_daily" || len(overview.Days) != 1 {
		t.Fatalf("Overview() = %+v", overview)
	}
}

type readinessGrowthSessionLister struct {
	sessions    []string
	totalEvents int64
}

func (lister readinessGrowthSessionLister) ListDistinctSessions(
	context.Context,
	time.Time,
	time.Time,
	int,
) ([]string, int64, error) {
	return append([]string(nil), lister.sessions...), lister.totalEvents, nil
}
