package main

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	io_prometheus_client "github.com/prometheus/client_model/go"
)

func TestStartupTelemetryMetricsExposeBoundedStartupPhaseLabels(t *testing.T) {
	event := startupTelemetryEventInput{
		EventID:         "startup_event_metrics_000001",
		AttemptID:       "startup_attempt_metrics_000001",
		Sequence:        1,
		Phase:           "flutter_first_frame",
		PhaseDurationMs: 120,
		ElapsedMs:       120,
		Outcome:         "painted",
		OccurredAt:      "2026-07-17T10:00:00Z",
		Platform:        "android",
		RuntimeEnv:      "alpha",
	}
	recordStartupTelemetryMetrics(event)

	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather startup metrics: %v", err)
	}
	var hasCounter, hasHistogram bool
	for _, family := range families {
		switch family.GetName() {
		case "ops_startup_phase_total":
			hasCounter = startupMetricFamilyContains(
				family.GetMetric(),
				"phase",
				"flutter_first_frame",
			)
		case "ops_startup_phase_duration_seconds":
			hasHistogram = startupMetricFamilyContains(
				family.GetMetric(),
				"phase",
				"flutter_first_frame",
			)
		}
	}
	if !hasCounter || !hasHistogram {
		t.Fatalf(
			"startup producer must expose both counter and duration histogram: counter=%t histogram=%t",
			hasCounter,
			hasHistogram,
		)
	}
}

func startupMetricFamilyContains(metrics []*io_prometheus_client.Metric, name, value string) bool {
	for _, metric := range metrics {
		for _, label := range metric.GetLabel() {
			if label.GetName() == name && label.GetValue() == value {
				return true
			}
		}
	}
	return false
}
