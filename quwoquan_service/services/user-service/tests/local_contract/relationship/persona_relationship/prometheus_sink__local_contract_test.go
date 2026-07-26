package local_contract

import (
	. "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/observability"
	"testing"

	"github.com/prometheus/client_golang/prometheus"

	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

func TestPrometheusSink_ExportsRelationshipMetricFamilies(t *testing.T) {
	sink := PrometheusSink{}
	sink.ObserveCommandLatency(12)
	sink.ObserveListLatency(18)
	sink.ObserveCounterProjectionLag(24)
	sink.IncrementCounter(reltelemetry.MetricCounterMismatchCount)

	migratedPrometheusSinkAssertMetricFamilies(t, map[string]bool{
		"quwoquan_persona_relationship_command_latency_ms":        false,
		"quwoquan_persona_relationship_list_latency_ms":           false,
		"quwoquan_persona_relationship_counter_projection_lag_ms": false,
		"quwoquan_persona_relationship_events_total":              false,
	})
}

func migratedPrometheusSinkAssertMetricFamilies(t *testing.T, wanted map[string]bool) {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather Prometheus metrics: %v", err)
	}
	for _, family := range families {
		if _, ok := wanted[family.GetName()]; ok {
			wanted[family.GetName()] = true
		}
	}
	for name, found := range wanted {
		if !found {
			t.Errorf("metric family %q was not exported", name)
		}
	}
}
