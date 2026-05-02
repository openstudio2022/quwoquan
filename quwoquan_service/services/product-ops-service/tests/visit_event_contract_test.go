package tests

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

type failingMirror struct {
	called chan struct{}
}

func (m failingMirror) MirrorEvents(context.Context, []application.EventDrilldownItem) error {
	close(m.called)
	return errors.New("es unavailable")
}

func TestTelemetryStore_RecordVisitAndStats(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()

	for range 3 {
		if _, err := store.RecordVisit(context.Background(), application.VisitInput{
			UserID:     "user-1",
			TargetType: "page",
			TargetKey:  "page_home",
			SessionID:  "sess_1",
			Source:     "page_access",
		}); err != nil {
			t.Fatalf("record visit: %v", err)
		}
	}

	stats, err := store.GetVisitStats(context.Background(), application.VisitStatsQuery{
		TargetType: "page",
		TargetKey:  "page_home",
	})
	if err != nil {
		t.Fatalf("get visit stats: %v", err)
	}
	if stats.TotalVisits != 3 {
		t.Fatalf("expected totalVisits=3, got %d", stats.TotalVisits)
	}
	if len(stats.Items) != 1 || stats.Items[0].VisitCount != 3 {
		t.Fatalf("unexpected visit stats: %+v", stats.Items)
	}
}

func TestTelemetryStore_ReportEventBatchIdempotent(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()

	events := []application.EventRecordInput{
		{
			EventID:      "evt-1",
			EventType:    "experience",
			EventName:    "page_open",
			EventVersion: "v1",
			Priority:     "P0",
			Producer:     "app.page_access",
			PageName:     "home",
			OccurredAt:   "2026-04-01T00:00:00Z",
		},
	}

	ack1, _, err := store.ReportEventBatch(context.Background(), events)
	if err != nil {
		t.Fatalf("report first batch: %v", err)
	}
	ack2, _, err := store.ReportEventBatch(context.Background(), events)
	if err != nil {
		t.Fatalf("report duplicate batch: %v", err)
	}
	if ack1.AcceptedCount != 1 || ack2.DuplicateCount != 1 {
		t.Fatalf("unexpected batch ack: first=%+v second=%+v", ack1, ack2)
	}

	drilldown, err := store.GetEventDrilldown(context.Background(), application.EventDrilldownQuery{
		EventName: "page_open",
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("get event drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 || drilldown.Items[0].EventID != "evt-1" {
		t.Fatalf("expected single idempotent event record, got %+v", drilldown)
	}
}

func TestTelemetryService_ExceptionMirrorFailureDoesNotBlockAck(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	mirror := failingMirror{called: make(chan struct{})}
	service := application.NewTelemetryServiceWithMirror(store, nil, mirror)

	ack, err := service.ReportEventBatch(context.Background(), []application.EventRecordInput{
		{
			EventID:        "evt-exception-1",
			EventType:      "exception",
			EventName:      "runtime_exception",
			Producer:       "app.exception",
			SessionID:      "sess-1",
			PageVisitID:    "visit-1",
			RequestID:      "req-1",
			TraceID:        "trace-1",
			PageName:       "global.app.runtime",
			ErrorCode:      "APP.RUNTIME.uncaught_exception",
			ErrorModule:    "APP",
			ErrorKind:      "RUNTIME",
			ErrorReason:    "uncaught_exception",
			Nature:         "bug",
			BusinessObject: "app_runtime",
			FunctionModule: "global_error_handler",
			AppRuntimeEnv:  "alpha",
			AppVersion:     "test",
			Platform:       "ios",
			OccurredAt:     "2026-04-01T00:00:00Z",
		},
	})
	if err != nil {
		t.Fatalf("report event batch should not fail on mirror error: %v", err)
	}
	if ack.AcceptedCount != 1 {
		t.Fatalf("expected accepted count 1, got %+v", ack)
	}
	select {
	case <-mirror.called:
	case <-time.After(time.Second):
		t.Fatalf("mirror was not called")
	}
}
