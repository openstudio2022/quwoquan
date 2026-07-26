package main

import (
	"context"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

var (
	telemetryMetricsOnce      sync.Once
	telemetryIngestBatchTotal *prometheus.CounterVec
	telemetryIngestEventTotal *prometheus.CounterVec
	telemetryIngestDuration   *prometheus.HistogramVec
	telemetryLogstoreDuration *prometheus.HistogramVec
	appExperienceEventTotal   *prometheus.CounterVec
	contentPublicationEvents  *prometheus.CounterVec
	contentPublishVisible     *prometheus.HistogramVec
	videoPreviewTrackLoads    *prometheus.CounterVec
	videoPreviewTrackLoadTime *prometheus.HistogramVec
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
			Help:    "Product telemetry log-sink write, confirmation and query duration.",
			Buckets: []float64{0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2, 5},
		}, []string{"operation", "result"})
		appExperienceEventTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_app_experience_events_total",
			Help: "Accepted App experience facts used by ANR, jank, error, and startup SLOs.",
		}, []string{"event_type", "result"})
		contentPublicationEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_content_publication_events_total",
			Help: "Accepted content-publication funnel facts by bounded stage and outcome.",
		}, []string{
			"publication_stage",
			"content_type",
			"object_state",
			"result",
			"background_retry_terminal",
		})
		contentPublishVisible = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_content_publish_to_visible_seconds",
			Help:    "Client-observed elapsed time from publication start to visible result.",
			Buckets: []float64{1, 5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600},
		}, []string{"content_type", "result"})
		videoPreviewTrackLoads = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_video_preview_track_loads_total",
			Help: "Accepted video preview-track manifest loads by bounded result.",
		}, []string{"result"})
		videoPreviewTrackLoadTime = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_video_preview_track_load_duration_seconds",
			Help:    "Client-observed preview-track manifest load latency.",
			Buckets: []float64{0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 30},
		}, []string{"result"})
		registerCollector(&telemetryIngestBatchTotal)
		registerCollector(&telemetryIngestEventTotal)
		registerCollector(&telemetryIngestDuration)
		registerCollector(&telemetryLogstoreDuration)
		registerCollector(&appExperienceEventTotal)
		registerCollector(&contentPublicationEvents)
		registerCollector(&contentPublishVisible)
		registerCollector(&videoPreviewTrackLoads)
		registerCollector(&videoPreviewTrackLoadTime)
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

func recordAppExperienceEvents(records []application.EventRecordInput) {
	registerTelemetryMetrics()
	for _, record := range records {
		switch record.EventType {
		case "app_anr_outcome", "app_frame_jank_outcome", "app_startup",
			"runtime_exception", "page_first_usable":
			result := "observed"
			if record.Result != nil && *record.Result != "" {
				result = *record.Result
			}
			appExperienceEventTotal.WithLabelValues(record.EventType, result).Inc()
		case "content_publication":
			stage := telemetryString(record.PublicationStage, "unknown")
			contentType := telemetryString(record.ContentType, "unknown")
			objectState := telemetryString(record.ObjectState, "unknown")
			result := telemetryString(record.Result, "unknown")
			retryTerminal := telemetryString(
				record.BackgroundRetryTerminal,
				"not_applicable",
			)
			contentPublicationEvents.WithLabelValues(
				stage,
				contentType,
				objectState,
				result,
				retryTerminal,
			).Inc()
			if stage == "published" {
				if record.DurationMS != nil && *record.DurationMS >= 0 {
					contentPublishVisible.WithLabelValues(contentType, result).Observe(
						float64(*record.DurationMS) / 1000,
					)
				}
			}
		case "video_preview_track_load":
			result := telemetryString(record.Result, "unknown")
			videoPreviewTrackLoads.WithLabelValues(result).Inc()
			if record.DurationMS != nil && *record.DurationMS >= 0 {
				videoPreviewTrackLoadTime.WithLabelValues(result).Observe(
					float64(*record.DurationMS) / 1000,
				)
			}
		}
	}
}

func telemetryString(value *string, fallback string) string {
	if value == nil || *value == "" {
		return fallback
	}
	return *value
}

type instrumentedEventLogStore struct {
	inner application.EventLogStore
}

func instrumentEventLogStore(inner application.EventLogStore) application.EventLogStore {
	instrumented := instrumentedEventLogStore{inner: inner}
	repairer, ok := inner.(application.IncompleteEventBatchRepairer)
	if !ok {
		return instrumented
	}
	return instrumentedRepairableEventLogStore{
		instrumentedEventLogStore: instrumented,
		repairer:                  repairer,
	}
}

type instrumentedRepairableEventLogStore struct {
	instrumentedEventLogStore
	repairer application.IncompleteEventBatchRepairer
}

func (s instrumentedRepairableEventLogStore) RepairEventBatch(
	ctx context.Context,
	key string,
	records []application.EventRecord,
) (err error) {
	startedAt := time.Now()
	defer func() { s.observe("repair_event_batch", startedAt, err) }()
	return s.repairer.RepairEventBatch(ctx, key, records)
}

func (s instrumentedRepairableEventLogStore) RepairStartupDiagnosticBatch(
	ctx context.Context,
	key string,
	records []application.StartupDiagnosticRecord,
) (err error) {
	startedAt := time.Now()
	defer func() { s.observe("repair_startup_diagnostic", startedAt, err) }()
	return s.repairer.RepairStartupDiagnosticBatch(ctx, key, records)
}

type instrumentedRtcMediaQoeSummaryReader struct {
	inner application.RtcMediaQoeSummaryReader
}

func instrumentRtcMediaQoeSummaryReader(
	inner application.RtcMediaQoeSummaryReader,
) application.RtcMediaQoeSummaryReader {
	return instrumentedRtcMediaQoeSummaryReader{inner: inner}
}

func (s instrumentedRtcMediaQoeSummaryReader) ReadRtcMediaQoeSummary(
	ctx context.Context,
	query application.RtcMediaQoeSummaryQuery,
) (out application.RtcMediaQoeSummarySlice, err error) {
	startedAt := time.Now()
	defer func() {
		instrumentedEventLogStore{}.observe(
			"query_rtc_media_qoe_raw",
			startedAt,
			err,
		)
	}()
	return s.inner.ReadRtcMediaQoeSummary(ctx, query)
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

func (s instrumentedEventLogStore) GetPageExperienceStats(ctx context.Context, query application.PageExperienceQuery) (out []application.PageExperienceStat, err error) {
	startedAt := time.Now()
	defer func() { s.observe("query_page_experience", startedAt, err) }()
	return s.inner.GetPageExperienceStats(ctx, query)
}

var _ application.EventLogStore = instrumentedEventLogStore{}
var _ application.EventLogStore = instrumentedRepairableEventLogStore{}
var _ application.IncompleteEventBatchRepairer = instrumentedRepairableEventLogStore{}
var _ application.RtcMediaQoeSummaryReader = instrumentedRtcMediaQoeSummaryReader{}
