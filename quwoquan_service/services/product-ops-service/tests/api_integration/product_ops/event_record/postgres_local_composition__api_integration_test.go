// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
package api_integration

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestPostgresTelemetryLocalCompositionUsesOnlyEventRecordPorts(t *testing.T) {
	ctx := context.Background()
	schema := fmt.Sprintf("telemetry_local_test_%d", time.Now().UnixNano())
	store, err := telemetrypersistence.NewPostgresTelemetryStore(controlPlanePGPool, schema)
	if err != nil {
		t.Fatalf("new postgres telemetry store: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure telemetry schema: %v", err)
	}
	t.Cleanup(func() {
		_, _ = controlPlanePGPool.Exec(context.Background(), `DROP SCHEMA "`+schema+`" CASCADE`)
	})

	var legacyVisitTable *string
	if err := controlPlanePGPool.QueryRow(
		ctx,
		"SELECT to_regclass($1)::text",
		schema+".telemetry_visits",
	).Scan(&legacyVisitTable); err != nil {
		t.Fatalf("inspect retired postgres visit table: %v", err)
	}
	if legacyVisitTable != nil {
		t.Fatalf("postgres VisitRecord track must be absent, got %q", *legacyVisitTable)
	}

	service := application.NewTelemetryService(store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	callType := "audio"
	connectTimeMS := 120
	mediaConnected := true
	reconnectCount := 0
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "rtc_media_qoe",
		SessionID:          "s.dXNlci0x.1",
		PageName:           "home",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
		CallType:           &callType,
		ConnectTimeMS:      &connectTimeMS,
		MediaConnected:     &mediaConnected,
		ReconnectCount:     &reconnectCount,
	}
	detected := "detected"
	ignored := "ignored"
	event.Result = &detected
	ignoredEvent := event
	ignoredEvent.SessionID = "s.dXNlci0y.1"
	ignoredEvent.Result = &ignored
	if _, err := service.ReportEventBatch(
		ctx,
		strings.Repeat("a", 64),
		[]application.EventRecordInput{event, ignoredEvent},
	); err != nil {
		t.Fatalf("report event batch: %v", err)
	}
	summary, err := service.GetEventSummary(ctx, application.EventSummaryQuery{
		Result: "detected",
		From:   time.Now().UTC().Add(-time.Hour),
		To:     time.Now().UTC().Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("get postgres summary: %v", err)
	}
	if summary.TotalCount != 1 || summary.SessionCount != 1 ||
		summary.SourceKind != "raw_records" {
		t.Fatalf("unexpected postgres summary: %+v", summary)
	}
	drilldown, err := service.GetEventDrilldown(ctx, application.EventDrilldownQuery{
		Result: "detected",
		From:   time.Now().UTC().Add(-time.Hour),
		To:     time.Now().UTC().Add(time.Minute),
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("get postgres drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 {
		t.Fatalf("unexpected postgres drilldown: %+v", drilldown)
	}
}
