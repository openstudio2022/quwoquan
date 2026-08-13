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
		pageViews: 3,
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
	sessions  []string
	pageViews int64
}

func (lister readinessGrowthSessionLister) ListDistinctSessions(
	context.Context,
	time.Time,
	time.Time,
	int,
) ([]string, int64, error) {
	return append([]string(nil), lister.sessions...), lister.pageViews, nil
}

func (lister readinessGrowthSessionLister) ListDistinctSessionsByEvent(
	context.Context,
	string,
	time.Time,
	time.Time,
	int,
) ([]string, error) {
	return append([]string(nil), lister.sessions...), nil
}

// 跨轨漏斗产品轨段（DEC-002）：今日窗口按事件类型 actor 去重；
// exposed 段属于行为归因轨，在归因端点扩展前显式 unavailable。
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/design.md#dec-002
func TestGrowthOverviewFunnelCountsProductTrackActorsAndKeepsExposedUnavailable(t *testing.T) {
	store := persistence.NewMemoryTelemetryStore()
	now := time.Now().UTC()
	makeEvent := func(eventType, session string) application.EventRecordInput {
		event := validEvent(eventType, "event", now.Add(-time.Minute))
		event.SessionID = session
		if eventType == "page_return" {
			durationMS := 900
			event.DurationMS = &durationMS
		}
		if eventType == "content_publication" {
			stage := "published"
			contentType := "article"
			objectState := "published"
			surfaceID := "create"
			result := "success"
			event.PublicationStage = &stage
			event.ContentType = &contentType
			event.ObjectState = &objectState
			event.SurfaceID = &surfaceID
			event.Result = &result
		}
		return event
	}
	events := []application.EventRecordInput{
		makeEvent("page_open", "s.YWN0b3ItMQ.1"),
		makeEvent("page_open", "s.YWN0b3ItMg.1"),
		makeEvent("page_open", "s.YWN0b3ItMQ.2"), // 同 actor 第二会话，去重后仍 2
		makeEvent("content_publication", "s.YWN0b3ItMQ.1"),
		makeEvent("page_return", "s.YWN0b3ItMg.1"),
	}
	telemetry := application.NewTelemetryService(store, store)
	if _, err := telemetry.ReportEventBatch(
		context.Background(), digestKey("growth-funnel-product-track"), events,
	); err != nil {
		t.Fatalf("ReportEventBatch() error = %v", err)
	}

	service := application.NewGrowthService(persistence.NewMemoryGrowthStore(), store)
	overview, err := service.Overview(context.Background(), 1)
	if err != nil {
		t.Fatalf("Overview() error = %v", err)
	}
	funnel := overview.Funnel
	if funnel.SourceTrack != "product_telemetry" {
		t.Fatalf("funnel source track drifted: %+v", funnel)
	}
	if funnel.ConsumedActors != 2 || funnel.PublishedActors != 1 || funnel.ReturnedActors != 1 {
		t.Fatalf(
			"funnel actor counts = consumed:%d published:%d returned:%d; want 2/1/1",
			funnel.ConsumedActors, funnel.PublishedActors, funnel.ReturnedActors,
		)
	}
	if funnel.ExposedActors != nil || funnel.ExposedNote == "" {
		t.Fatalf("exposed segment must stay explicitly unavailable: %+v", funnel)
	}
}

// PV 唯一口径 = page_open 事件数：memory double 必须与生产 Elasticsearch
// reader 的过滤语义一致，混入行为/诊断事件不得抬高 PV。
func TestMemoryDistinctSessionsCountOnlyPageOpenAsPageViews(t *testing.T) {
	store := persistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-time.Minute)
	firstOpen := validEvent("page_open", "event", now)
	firstOpen.SessionID = "s.YWNjb3VudC1h.1"
	secondOpen := validEvent("page_open", "event", now)
	secondOpen.SessionID = "s.YWNjb3VudC1i.2"
	pageReturn := validEvent("page_return", "event", now)
	pageReturn.SessionID = "s.YWNjb3VudC1h.1"
	returnDurationMS := 1200
	pageReturn.DurationMS = &returnDurationMS
	service := application.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("growth-pv-page-open-only"),
		[]application.EventRecordInput{firstOpen, secondOpen, pageReturn},
	); err != nil {
		t.Fatalf("ReportEventBatch() error = %v", err)
	}
	sessions, pageViews, err := store.ListDistinctSessions(
		context.Background(), now.Add(-time.Hour), now.Add(time.Hour), 100,
	)
	if err != nil {
		t.Fatalf("ListDistinctSessions() error = %v", err)
	}
	if len(sessions) != 2 || pageViews != 2 {
		t.Fatalf("sessions=%d pageViews=%d, want sessions=2 pageViews=2", len(sessions), pageViews)
	}
}
