package main

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	eventrecordhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	eventrecordobservability "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/observability"
)

var startupTelemetryMetrics = sync.OnceValue(func() *eventrecordobservability.StartupTelemetryMetrics {
	metrics, err := eventrecordobservability.NewStartupTelemetryMetrics(prometheus.DefaultRegisterer)
	if err != nil {
		panic(err)
	}
	return metrics
})

func recordStartupTelemetryMetrics(event eventrecordhttp.StartupTelemetryEventInput) {
	startupTelemetryMetrics().Observe(eventrecordobservability.StartupTelemetryObservation{
		Phase:             event.Phase,
		Outcome:           event.Outcome,
		Platform:          event.Platform,
		RuntimeEnv:        event.RuntimeEnv,
		RecoverySurface:   event.RecoverySurface,
		RecoveryLifecycle: event.RecoveryLifecycle,
		RecoveryMount:     event.RecoveryMount,
		PhaseDurationMS:   event.PhaseDurationMs,
	})
}
