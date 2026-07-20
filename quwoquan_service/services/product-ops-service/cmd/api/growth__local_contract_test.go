package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func growthSessionID(actorID string, at time.Time) string {
	return "s." + base64.RawURLEncoding.EncodeToString([]byte(actorID)) + "." + strconv.FormatInt(at.UnixMilli(), 10)
}

// TestGrowthAggregationAndOverview 覆盖运营总览黄金链路：
// 事件（sessionId actor 段）→ user_activity_daily 聚合 → DAU/PV/WAU/MAU 与
// D1 留存（cohort ∩ 次日活跃）；全链路无合成数据。
func TestGrowthAggregationAndOverview(t *testing.T) {
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	growthStore := telemetrypersistence.NewMemoryGrowthStore()
	growth := application.NewGrowthService(growthStore, telemetryStore)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(24 * time.Hour).Add(12 * time.Hour)
	yesterday := now.AddDate(0, 0, -1)

	seedEvents := func(day time.Time, actors []string, eventsPerActor int) {
		records := make([]application.EventRecord, 0, len(actors)*eventsPerActor)
		for _, actor := range actors {
			for index := 0; index < eventsPerActor; index++ {
				occurredAt := day.Add(time.Duration(index) * time.Minute)
				records = append(records, application.EventRecord{
					EventRecordInput: application.EventRecordInput{
						LogType:    "event",
						EventType:  "page_open",
						SessionID:  growthSessionID(actor, occurredAt),
						PageName:   "home",
						OccurredAt: occurredAt.Format(time.RFC3339Nano),
						AppVersion: "1.0.0",
					},
				})
			}
		}
		if err := telemetryStore.PutEventBatch(ctx, "growth-"+day.Format("20060102"), records); err != nil {
			t.Fatalf("seed events: %v", err)
		}
	}

	// 昨日：alice/bob 首见；今日：alice 留存 + carol 新增。
	seedEvents(yesterday, []string{"actor-alice", "actor-bob"}, 3)
	seedEvents(now, []string{"actor-alice", "actor-carol"}, 2)

	if err := growth.AggregateDay(ctx, yesterday); err != nil {
		t.Fatalf("aggregate yesterday: %v", err)
	}
	if err := growth.AggregateDay(ctx, now); err != nil {
		t.Fatalf("aggregate today: %v", err)
	}
	// 幂等：重复聚合不得翻倍。
	if err := growth.AggregateDay(ctx, now); err != nil {
		t.Fatalf("re-aggregate today: %v", err)
	}

	overview, err := growth.Overview(ctx, 30)
	if err != nil {
		t.Fatalf("overview: %v", err)
	}
	if overview.TodayDAU != 2 {
		t.Fatalf("today dau=%d want 2", overview.TodayDAU)
	}
	// 每个 actor 每天 sessionId 按分钟变化 → 今日 2 actor × 2 事件 = 4 PV。
	if overview.TodayPV != 4 {
		t.Fatalf("today pv=%d want 4", overview.TodayPV)
	}
	if overview.WAU != 3 || overview.MAU != 3 {
		t.Fatalf("wau=%d mau=%d want 3/3 (alice+bob+carol)", overview.WAU, overview.MAU)
	}
	// D1 留存：昨日新增 {alice,bob}，今日活跃含 alice → 50%。
	if overview.D1Retention != 50 {
		t.Fatalf("d1 retention=%.1f want 50", overview.D1Retention)
	}
	var today application.DailyActivity
	for _, day := range overview.Days {
		if day.Date == now.Format("2006-01-02") {
			today = day
		}
	}
	if today.NewActors != 1 {
		t.Fatalf("today newActors=%d want 1 (carol)", today.NewActors)
	}
	if len(today.ActorHashes) != 0 {
		t.Fatalf("wire payload must not expose actor hash sets")
	}
}

// TestPageExperienceHeatmap 覆盖页面体验热力图数据源：
// page_open（含逐页 TTI readyMs）、page_return 停留与 runtime_exception 按
// pageName 聚合；无数据页面不合成行。
func TestPageExperienceHeatmap(t *testing.T) {
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	service := newTestProductService(t)
	service.telemetry = application.NewTelemetryServiceWithStores(telemetryStore, telemetryStore, telemetryStore)
	server := newTestServerMux(service)

	now := time.Now().UTC().Add(-time.Hour)
	intPtr := func(v int) *int { return &v }
	records := []application.EventRecord{
		{EventRecordInput: application.EventRecordInput{
			LogType: "event", EventType: "page_open", PageName: "home",
			SessionID: growthSessionID("actor-a", now), AppVersion: "1.0.0",
			OccurredAt: now.Format(time.RFC3339Nano), ReadyMS: intPtr(300),
		}},
		{EventRecordInput: application.EventRecordInput{
			LogType: "event", EventType: "page_open", PageName: "home",
			SessionID: growthSessionID("actor-b", now), AppVersion: "1.0.0",
			OccurredAt: now.Add(time.Minute).Format(time.RFC3339Nano), ReadyMS: intPtr(500),
		}},
		{EventRecordInput: application.EventRecordInput{
			LogType: "event", EventType: "page_return", PageName: "home",
			SessionID: growthSessionID("actor-a", now), AppVersion: "1.0.0",
			OccurredAt: now.Add(2 * time.Minute).Format(time.RFC3339Nano), DurationMS: intPtr(60000),
		}},
		{EventRecordInput: application.EventRecordInput{
			LogType: "event", EventType: "runtime_exception", PageName: "earth",
			SessionID: growthSessionID("actor-a", now), AppVersion: "1.0.0",
			OccurredAt: now.Add(3 * time.Minute).Format(time.RFC3339Nano),
		}},
	}
	if err := telemetryStore.PutEventBatch(context.Background(), "page-exp-batch", records); err != nil {
		t.Fatalf("seed events: %v", err)
	}

	from := now.Add(-time.Minute).Format(time.RFC3339Nano)
	to := now.Add(10 * time.Minute).Format(time.RFC3339Nano)
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/control-plane/product/experience/pages?from="+from+"&to="+to, nil))
	if response.Code != http.StatusOK {
		t.Fatalf("page experience status=%d body=%s", response.Code, response.Body.String())
	}
	var payload struct {
		Items  []application.PageExperienceStat `json:"items"`
		Source string                           `json:"source"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode page experience: %v", err)
	}
	if payload.Source != "telemetry_events" || len(payload.Items) != 2 {
		t.Fatalf("unexpected page experience payload: %+v", payload)
	}
	byPage := map[string]application.PageExperienceStat{}
	for _, item := range payload.Items {
		byPage[item.PageName] = item
	}
	home := byPage["home"]
	if home.Opens != 2 || home.ReadySamples != 2 || home.AvgReadyMs != 400 {
		t.Fatalf("home TTI aggregation mismatch: %+v", home)
	}
	if home.StaySamples != 1 || home.AvgStayMs != 60000 {
		t.Fatalf("home stay aggregation mismatch: %+v", home)
	}
	earth := byPage["earth"]
	if earth.RuntimeErrors != 1 || earth.Opens != 0 {
		t.Fatalf("earth error aggregation mismatch: %+v", earth)
	}
}

// TestGrowthOverviewEndpoint 覆盖 /control-plane/product/growth/overview 契约。
func TestGrowthOverviewEndpoint(t *testing.T) {
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	growthStore := telemetrypersistence.NewMemoryGrowthStore()
	service := newTestProductService(t)
	service.growth = application.NewGrowthService(growthStore, telemetryStore)
	server := newTestServerMux(service)

	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/control-plane/product/growth/overview?days=7", nil))
	if response.Code != http.StatusOK {
		t.Fatalf("growth overview status=%d body=%s", response.Code, response.Body.String())
	}
	var payload application.GrowthOverview
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode growth overview: %v", err)
	}
	if payload.Source != "user_activity_daily" || len(payload.Days) != 7 {
		t.Fatalf("unexpected overview payload: source=%s days=%d", payload.Source, len(payload.Days))
	}

	invalid := httptest.NewRecorder()
	server.ServeHTTP(invalid, httptest.NewRequest(http.MethodGet, "/control-plane/product/growth/overview?days=365", nil))
	if invalid.Code == http.StatusOK {
		t.Fatalf("days out of range must be rejected")
	}
}
