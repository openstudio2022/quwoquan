package main

import (
	"context"
	"strings"
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
	appFrameSamplesTotal      *prometheus.CounterVec
	appJankyFramesTotal       *prometheus.CounterVec
	appFrameWorstDuration     *prometheus.HistogramVec
	videoPlaybackEvents       *prometheus.CounterVec
	videoPlaybackReady        *prometheus.HistogramVec
	videoPlaybackEffective    *prometheus.CounterVec
	videoPlaybackRebuffer     *prometheus.CounterVec
	loginFunnelEvents         *prometheus.CounterVec
	loginOperationEvents      *prometheus.CounterVec
	loginOperationDuration    *prometheus.HistogramVec
	loginStateDwell           *prometheus.HistogramVec
	contentPublicationEvents  *prometheus.CounterVec
	contentPublishVisible     *prometheus.HistogramVec
	articleReaderEvents       *prometheus.CounterVec
	articleReaderEnter        *prometheus.HistogramVec
	articleReaderDwell        *prometheus.HistogramVec
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
		appFrameSamplesTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_app_frame_samples_total",
			Help: "Accepted frame samples used as the App jank-rate denominator.",
		}, []string{"page_name"})
		appJankyFramesTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_app_janky_frames_total",
			Help: "Accepted janky frames used as the App jank-rate numerator.",
		}, []string{"page_name"})
		appFrameWorstDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_app_frame_batch_worst_duration_seconds",
			Help:    "Worst frame duration reported by each complete App frame batch.",
			Buckets: []float64{0.008, 0.016, 0.024, 0.032, 0.05, 0.075, 0.1, 0.2, 0.5, 1},
		}, []string{"page_name"})
		videoPlaybackEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_video_playback_events_total",
			Help: "Accepted video playback QoE terminal facts by bounded result.",
		}, []string{"page_name", "result"})
		videoPlaybackReady = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_video_playback_ready_duration_seconds",
			Help:    "Client-observed video preparation duration through player ready.",
			Buckets: []float64{0.1, 0.25, 0.5, 0.8, 1.2, 2, 3, 4, 6, 10},
		}, []string{"page_name", "result"})
		videoPlaybackEffective = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_video_playback_effective_seconds_total",
			Help: "Accepted effective video playback time used as the rebuffer-ratio denominator.",
		}, []string{"page_name"})
		videoPlaybackRebuffer = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_video_playback_rebuffer_seconds_total",
			Help: "Accepted video rebuffer time used as the rebuffer-ratio numerator.",
		}, []string{"page_name"})
		loginFunnelEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_login_funnel_events_total",
			Help: "Accepted login lifecycle facts using bounded UX dimensions.",
		}, []string{"action", "result", "step", "provider"})
		loginOperationEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_login_operation_events_total",
			Help: "Accepted login operation outcomes using bounded failure dimensions.",
		}, []string{"operation", "result", "failure_kind"})
		loginOperationDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_login_operation_duration_seconds",
			Help:    "Client-observed login operation latency.",
			Buckets: []float64{0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2, 3, 5, 10, 15, 30, 60},
		}, []string{"operation", "result"})
		loginStateDwell = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_login_state_dwell_seconds",
			Help:    "Client-observed time spent in a login step before transition or stall detection.",
			Buckets: []float64{0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 90, 120, 300},
		}, []string{"step", "result"})
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
		articleReaderEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "ops_article_reader_events_total",
			Help: "Accepted article-reader lifecycle facts by catalogued stage and outcome.",
		}, []string{"stage", "result"})
		articleReaderEnter = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_article_reader_enter_duration_seconds",
			Help:    "Client-observed elapsed time until an article reader is usable.",
			Buckets: []float64{0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2, 3, 5, 10},
		}, []string{"result"})
		articleReaderDwell = prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "ops_article_reader_dwell_seconds",
			Help:    "Sampled active article-reader dwell duration.",
			Buckets: []float64{1, 5, 15, 30, 60, 120, 300, 600, 1800},
		}, []string{"result"})
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
		registerCollector(&appFrameSamplesTotal)
		registerCollector(&appJankyFramesTotal)
		registerCollector(&appFrameWorstDuration)
		registerCollector(&videoPlaybackEvents)
		registerCollector(&videoPlaybackReady)
		registerCollector(&videoPlaybackEffective)
		registerCollector(&videoPlaybackRebuffer)
		registerCollector(&loginFunnelEvents)
		registerCollector(&loginOperationEvents)
		registerCollector(&loginOperationDuration)
		registerCollector(&loginStateDwell)
		registerCollector(&contentPublicationEvents)
		registerCollector(&contentPublishVisible)
		registerCollector(&articleReaderEvents)
		registerCollector(&articleReaderEnter)
		registerCollector(&articleReaderDwell)
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
			if record.EventType == "app_frame_jank_outcome" &&
				record.SampledFrames != nil && *record.SampledFrames > 0 &&
				record.JankyFrames != nil && *record.JankyFrames >= 0 &&
				record.WorstFrameMS != nil && *record.WorstFrameMS >= 0 {
				pageName := boundedAppExperiencePage(record.PageName)
				appFrameSamplesTotal.WithLabelValues(pageName).Add(
					float64(*record.SampledFrames),
				)
				// Add(0) intentionally creates the time series for clean batches;
				// absence must never stand in for a zero-jank numerator.
				appJankyFramesTotal.WithLabelValues(pageName).Add(
					float64(*record.JankyFrames),
				)
				appFrameWorstDuration.WithLabelValues(pageName).Observe(
					float64(*record.WorstFrameMS) / 1000,
				)
			}
		case "login_funnel":
			action := boundedLoginAction(telemetryString(record.Action, "unknown"))
			result := boundedLoginResult(telemetryString(record.Result, "unknown"))
			step := boundedLoginStep(telemetryString(record.Step, "unknown"))
			provider := boundedLoginProvider(telemetryString(record.Provider, "none"))
			loginFunnelEvents.WithLabelValues(action, result, step, provider).Inc()
			if action == "login_state_changed" && record.DurationMS != nil && *record.DurationMS >= 0 {
				loginStateDwell.WithLabelValues(step, result).Observe(
					float64(*record.DurationMS) / 1000,
				)
			}
		case "login_operation":
			operation := boundedLoginOperation(
				telemetryString(record.OperationID, "unknown"),
			)
			result := boundedLoginResult(telemetryString(record.Result, "unknown"))
			failureKind := boundedLoginFailureKind(
				telemetryString(record.FailureKind, "none"),
			)
			loginOperationEvents.WithLabelValues(operation, result, failureKind).Inc()
			if record.DurationMS != nil && *record.DurationMS >= 0 {
				loginOperationDuration.WithLabelValues(operation, result).Observe(
					float64(*record.DurationMS) / 1000,
				)
			}
		case "video_playback_qoe":
			pageName := boundedAppExperiencePage(record.PageName)
			result := boundedPlaybackResult(telemetryString(record.Result, "observed"))
			videoPlaybackEvents.WithLabelValues(pageName, result).Inc()
			if record.ReadyMS != nil && *record.ReadyMS >= 0 {
				videoPlaybackReady.WithLabelValues(pageName, result).Observe(
					float64(*record.ReadyMS) / 1000,
				)
			}
			if record.EffectivePlaybackMS != nil && *record.EffectivePlaybackMS >= 0 {
				videoPlaybackEffective.WithLabelValues(pageName).Add(
					float64(*record.EffectivePlaybackMS) / 1000,
				)
			}
			if record.RebufferMS != nil && *record.RebufferMS >= 0 {
				// Add(0) preserves clean playback batches as a real numerator sample.
				videoPlaybackRebuffer.WithLabelValues(pageName).Add(
					float64(*record.RebufferMS) / 1000,
				)
			}
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
		case "article_reader_enter", "article_reader_dwell", "article_reader_exit",
			"article_reader_error", "article_reader_recovery":
			stage := record.EventType[len("article_reader_"):]
			result := telemetryString(record.Result, "unknown")
			articleReaderEvents.WithLabelValues(stage, result).Inc()
			if record.DurationMS != nil && *record.DurationMS >= 0 {
				duration := float64(*record.DurationMS) / 1000
				switch stage {
				case "enter":
					articleReaderEnter.WithLabelValues(result).Observe(duration)
				case "dwell":
					articleReaderDwell.WithLabelValues(result).Observe(duration)
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

func boundedAppExperiencePage(value string) string {
	normalized := strings.ToLower(strings.TrimSpace(value))
	switch {
	case normalized == "home", strings.HasPrefix(normalized, "home:"),
		strings.HasPrefix(normalized, "home_"):
		return "home"
	case strings.Contains(normalized, "works_immersive"),
		strings.Contains(normalized, "video_book"):
		return "video_book"
	default:
		return "other"
	}
}

func boundedPlaybackResult(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "ok", "success", "ready", "completed":
		return "success"
	case "failure", "failed", "error", "timeout":
		return "failure"
	case "cancelled", "canceled":
		return "cancelled"
	default:
		return "observed"
	}
}

func boundedLoginAction(value string) string {
	switch value {
	case "login_flow_exposed", "login_state_changed", "login_action_clicked",
		"login_consent_changed", "login_consent_sheet", "login_otp_send",
		"login_otp_verify", "login_otp_resend_available",
		"login_otp_countdown_recalculated", "login_social_authorization",
		"login_phone_binding", "login_terminal":
		return value
	default:
		return "other"
	}
}

func boundedLoginResult(value string) string {
	switch value {
	case "exposed", "success", "failure", "started", "shown", "cancelled",
		"accepted", "required", "available", "resumed", "dismissed",
		"binding_required", "stalled", "duplicate_suppressed":
		return value
	default:
		return "other"
	}
}

func boundedLoginStep(value string) string {
	switch value {
	case "resolving", "oneTap", "phoneEntry", "otp", "socialAuthorizing",
		"socialFailed", "socialPhoneEntry", "socialPhoneOtp", "blocked",
		"completing":
		return value
	default:
		return "other"
	}
}

func boundedLoginProvider(value string) string {
	switch value {
	case "none", "wechat", "qq", "alipay":
		return value
	default:
		return "other"
	}
}

func boundedLoginOperation(value string) string {
	switch value {
	case "resolve_login_entry", "refresh_remembered_session", "login_one_tap",
		"send_otp", "verify_login_otp", "complete_federated_phone_binding",
		"login_social_wechat", "login_social_qq", "login_social_alipay":
		return value
	default:
		return "other"
	}
}

func boundedLoginFailureKind(value string) string {
	switch value {
	case "none", "network", "timeout", "unavailable", "server", "validation",
		"invalidInput", "cancelled", "conflict", "unauthorized", "notFound",
		"rateLimited":
		return value
	default:
		return "other"
	}
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
