package main

import (
	"context"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"quwoquan_service/services/product-ops-service/internal/application"
)

var (
	telemetryMetricsOnce      sync.Once
	telemetryIngestBatchTotal *prometheus.CounterVec
	telemetryIngestEventTotal *prometheus.CounterVec
	telemetryIngestDuration   *prometheus.HistogramVec
	telemetryLogstoreDuration *prometheus.HistogramVec
)

func registerTelemetryMetrics() {
	telemetryMetricsOnce.Do(func() {
		telemetryIngestBatchTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_telemetry_ingest_batches_total",
			Help: "Product telemetry ingest batches by bounded outcome.",
		}, []string{"result"})
		telemetryIngestEventTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_telemetry_ingest_events_total",
			Help: "Product telemetry event records by bounded batch outcome.",
		}, []string{"result"})
		telemetryIngestDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_telemetry_ingest_duration_seconds",
			Help:    "End-to-end product telemetry ingest duration.",
			Buckets: []float64{0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2, 5},
		}, []string{"result"})
		telemetryLogstoreDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_telemetry_logstore_operation_duration_seconds",
			Help:    "SLS telemetry write, confirmation and query duration.",
			Buckets: []float64{0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2, 5},
		}, []string{"operation", "result"})
		registerCollector(&telemetryIngestBatchTotal)
		registerCollector(&telemetryIngestEventTotal)
		registerCollector(&telemetryIngestDuration)
		registerCollector(&telemetryLogstoreDuration)
	})
}

func registerCollector[T prometheus.Collector](collector *T) {
	if err := prometheus.Register(*collector); err != nil {
		if registered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := registered.ExistingCollector.(T); ok {
				*collector = existing
			}
		}
	}
}

func recordTelemetryIngestMetrics(result string, count int, duration time.Duration) {
	registerTelemetryMetrics()
	telemetryIngestBatchTotal.WithLabelValues(result).Inc()
	if count > 0 {
		telemetryIngestEventTotal.WithLabelValues(result).Add(float64(count))
	}
	telemetryIngestDuration.WithLabelValues(result).Observe(duration.Seconds())
}

type instrumentedEventLogStore struct {
	inner application.EventLogStore
}

func instrumentEventLogStore(inner application.EventLogStore) application.EventLogStore {
	return instrumentedEventLogStore{inner: inner}
}

func (s instrumentedEventLogStore) observe(operation string, startedAt time.Time, err error) {
	registerTelemetryMetrics()
	result := "success"
	if err != nil {
		result = "error"
	}
	telemetryLogstoreDuration.WithLabelValues(operation, result).Observe(time.Since(startedAt).Seconds())
}

func (s instrumentedEventLogStore) PutEventBatch(ctx context.Context, key string, records []application.EventRecord) (err error) {
	startedAt := time.Now()
	defer func() { s.observe("put_event_batch", startedAt, err) }()
	return s.inner.PutEventBatch(ctx, key, records)
}

func (s instrumentedEventLogStore) HasEventBatch(ctx context.Context, key string, count int) (found bool, err error) {
	startedAt := time.Now()
	defer func() { s.observe("confirm_event_batch", startedAt, err) }()
	return s.inner.HasEventBatch(ctx, key, count)
}

func (s instrumentedEventLogStore) GetEventSummary(ctx context.Context, query application.EventSummaryQuery) (out application.EventSummary, err error) {
	startedAt := time.Now()
	defer func() { s.observe("query_aggregate", startedAt, err) }()
	return s.inner.GetEventSummary(ctx, query)
}

func (s instrumentedEventLogStore) GetEventDrilldown(ctx context.Context, query application.EventDrilldownQuery) (out application.EventDrilldown, err error) {
	startedAt := time.Now()
	defer func() { s.observe("query_raw", startedAt, err) }()
	return s.inner.GetEventDrilldown(ctx, query)
}

func (s instrumentedEventLogStore) PutStartupDiagnostics(ctx context.Context, key string, records []application.StartupDiagnosticRecord) (err error) {
	startedAt := time.Now()
	defer func() { s.observe("put_startup_diagnostic", startedAt, err) }()
	return s.inner.PutStartupDiagnostics(ctx, key, records)
}

func (s instrumentedEventLogStore) HasStartupDiagnosticBatch(ctx context.Context, key string, count int) (found bool, err error) {
	startedAt := time.Now()
	defer func() { s.observe("confirm_startup_diagnostic", startedAt, err) }()
	return s.inner.HasStartupDiagnosticBatch(ctx, key, count)
}

var _ application.EventLogStore = instrumentedEventLogStore{}
