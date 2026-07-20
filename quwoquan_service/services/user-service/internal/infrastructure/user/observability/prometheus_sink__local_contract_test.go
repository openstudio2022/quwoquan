package observability

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"

	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
)

func TestPrometheusSink_ExportsProfileAndPersonaMetricFamilies(t *testing.T) {
	sink := PrometheusSink{}
	sink.ObserveProfileSubjectPublicReadLatency(14)
	sink.IncrementProfileSubjectCounter(
		usertelemetry.MetricProfileSubjectVisibilityNotFoundCount,
	)
	sink.ObservePersonaSwitchLatency(20)
	sink.IncrementPersonaRolloutCounter(
		usertelemetry.MetricPersonaAttributionMismatchCount,
	)

	assertMetricFamilies(t, map[string]bool{
		"quwoquan_profile_subject_public_read_latency_ms": false,
		"quwoquan_profile_subject_events_total":           false,
		"quwoquan_persona_switch_latency_ms":              false,
		"quwoquan_persona_rollout_events_total":           false,
	})
}

func assertMetricFamilies(t *testing.T, wanted map[string]bool) {
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
