package telemetry

import (
	"testing"
	"time"
)

func TestPersonaRolloutMetricsSnapshot(t *testing.T) {
	metrics := &PersonaRolloutMetrics{}
	metrics.RecordSwitchLatency(25 * time.Millisecond)
	metrics.RecordAttributionMismatch()
	metrics.RecordPublicLeakage()
	metrics.RecordMigrationFailure()

	snapshot := metrics.Snapshot()
	if snapshot[MetricPersonaSwitchLatencyMs] <= 0 {
		t.Fatal("expected switch latency metric")
	}
	if snapshot[MetricPersonaAttributionMismatchCount] != 1 {
		t.Fatal("expected attribution mismatch metric")
	}
	if snapshot[MetricPersonaPublicLeakageCount] != 1 {
		t.Fatal("expected public leakage metric")
	}
	if snapshot[MetricPersonaMigrationFailedCount] != 1 {
		t.Fatal("expected migration failed metric")
	}
}
