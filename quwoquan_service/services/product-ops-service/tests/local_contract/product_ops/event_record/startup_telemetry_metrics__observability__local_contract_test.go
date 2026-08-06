// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
package local_contract

import (
	"slices"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	eventobservability "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/observability"
)

func TestStartupRecoveryMetricsExposeOnlyBoundedRecoveryLabels(t *testing.T) {
	registry := prometheus.NewRegistry()
	metrics, err := eventobservability.NewStartupTelemetryMetrics(registry)
	if err != nil {
		t.Fatalf("construct startup telemetry metrics: %v", err)
	}
	metrics.Observe(eventobservability.StartupTelemetryObservation{
		Phase:             "recovery",
		Outcome:           "observed",
		Platform:          "android",
		RuntimeEnv:        "gamma",
		RecoverySurface:   "page.app.startup_recovery",
		RecoveryLifecycle: "phase_change",
		RecoveryMount:     "runtime_boundary",
		PhaseDurationMS:   25,
	})

	families, err := registry.Gather()
	if err != nil {
		t.Fatalf("gather startup recovery metrics: %v", err)
	}
	wantLabels := []string{
		"outcome", "phase", "platform", "recovery_lifecycle",
		"recovery_mount", "recovery_surface", "runtime_env",
	}
	found := map[string]bool{}
	for _, family := range families {
		if family.GetName() != "ops_startup_phase_total" &&
			family.GetName() != "ops_startup_phase_duration_seconds" {
			continue
		}
		found[family.GetName()] = true
		if len(family.Metric) != 1 {
			t.Fatalf("%s metric count = %d, want 1", family.GetName(), len(family.Metric))
		}
		labels := make([]string, 0, len(family.Metric[0].Label))
		for _, label := range family.Metric[0].Label {
			labels = append(labels, label.GetName())
		}
		slices.Sort(labels)
		if !slices.Equal(labels, wantLabels) {
			t.Fatalf("%s labels = %v, want %v", family.GetName(), labels, wantLabels)
		}
	}
	for _, metricName := range []string{
		"ops_startup_phase_total",
		"ops_startup_phase_duration_seconds",
	} {
		if !found[metricName] {
			t.Fatalf("metric family %s was not registered", metricName)
		}
	}
}

func TestStartupTelemetryMetricsReuseCollectorsForOneRegistry(t *testing.T) {
	registry := prometheus.NewRegistry()
	first, err := eventobservability.NewStartupTelemetryMetrics(registry)
	if err != nil {
		t.Fatalf("construct first startup telemetry metrics: %v", err)
	}
	second, err := eventobservability.NewStartupTelemetryMetrics(registry)
	if err != nil {
		t.Fatalf("construct second startup telemetry metrics: %v", err)
	}
	first.Observe(eventobservability.StartupTelemetryObservation{Phase: "terminal", Outcome: "success"})
	second.Observe(eventobservability.StartupTelemetryObservation{Phase: "terminal", Outcome: "success"})

	families, err := registry.Gather()
	if err != nil {
		t.Fatalf("gather reused startup metrics: %v", err)
	}
	for _, family := range families {
		if family.GetName() == "ops_startup_phase_total" {
			if got := family.Metric[0].Counter.GetValue(); got != 2 {
				t.Fatalf("startup phase count = %v, want 2", got)
			}
			return
		}
	}
	t.Fatal("ops_startup_phase_total was not registered")
}
