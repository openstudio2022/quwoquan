package main

import (
	"context"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"quwoquan_service/services/product-ops-service/internal/application"
	"quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func TestTelemetryMetricsUseOnlyBoundedNonSensitiveLabels(t *testing.T) {
	recordTelemetryIngestMetrics("accepted", 2, 10*time.Millisecond)
	detected := "detected"
	recordAppExperienceEvents([]application.EventRecordInput{{
		EventType: "app_anr_outcome",
		Result:    &detected,
	}, {
		EventType:               "content_publication",
		PublicationStage:        stringPointer("published"),
		ContentType:             stringPointer("video"),
		ObjectState:             stringPointer("published"),
		Result:                  stringPointer("success"),
		BackgroundRetryTerminal: stringPointer("published"),
		DurationMS:              intPointer(1200),
	}, {
		EventType:  "video_preview_track_load",
		Result:     stringPointer("success"),
		DurationMS: intPointer(50),
	}})
	store := instrumentEventLogStore(persistence.NewMemoryTelemetryStore())
	_, _ = store.GetEventSummary(context.Background(), application.EventSummaryQuery{
		From: time.Now().Add(-time.Hour),
		To:   time.Now(),
	})

	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather telemetry metrics: %v", err)
	}
	allowed := map[string]bool{
		"result": true, "operation": true, "event_type": true,
		"publication_stage": true, "content_type": true, "object_state": true,
		"background_retry_terminal": true,
	}
	found := map[string]bool{}
	for _, family := range families {
		name := family.GetName()
		if name != "ops_telemetry_ingest_batches_total" &&
			name != "ops_telemetry_ingest_events_total" &&
			name != "ops_telemetry_ingest_duration_seconds" &&
			name != "ops_telemetry_logstore_operation_duration_seconds" &&
			name != "ops_app_experience_events_total" &&
			name != "ops_content_publication_events_total" &&
			name != "ops_content_publish_to_visible_seconds" &&
			name != "ops_video_preview_track_loads_total" &&
			name != "ops_video_preview_track_load_duration_seconds" {
			continue
		}
		found[name] = true
		for _, metric := range family.Metric {
			for _, label := range metric.Label {
				if !allowed[label.GetName()] {
					t.Fatalf("metric %s exposes forbidden label %s", name, label.GetName())
				}
			}
		}
	}
	if len(found) != 9 {
		t.Fatalf("missing telemetry metric families: %+v", found)
	}
}

func stringPointer(value string) *string { return &value }

func intPointer(value int) *int { return &value }
