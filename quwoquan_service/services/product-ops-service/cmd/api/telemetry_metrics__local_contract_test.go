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
	store := instrumentEventLogStore(persistence.NewMemoryTelemetryStore())
	_, _ = store.GetEventSummary(context.Background(), application.EventSummaryQuery{
		From: time.Now().Add(-time.Hour),
		To:   time.Now(),
	})

	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather telemetry metrics: %v", err)
	}
	allowed := map[string]bool{"result": true, "operation": true}
	found := map[string]bool{}
	for _, family := range families {
		name := family.GetName()
		if name != "ops_telemetry_ingest_batches_total" &&
			name != "ops_telemetry_ingest_events_total" &&
			name != "ops_telemetry_ingest_duration_seconds" &&
			name != "ops_telemetry_logstore_operation_duration_seconds" {
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
	if len(found) != 4 {
		t.Fatalf("missing telemetry metric families: %+v", found)
	}
}
