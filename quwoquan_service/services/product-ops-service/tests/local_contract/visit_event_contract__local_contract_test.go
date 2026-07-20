package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	sls "github.com/aliyun/aliyun-log-go-sdk"

	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func TestTelemetryServiceAcceptsStrictBatchAndMasksSession(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store, store)
	now := time.Now().UTC().Add(-2 * time.Minute)
	events := []application.EventRecordInput{
		validEvent("page_open", "event", now),
		validEvent("page_return", "event", now.Add(time.Second)),
	}
	events[0].NetworkClass = "5g"
	events[1].NetworkClass = "4g"
	duration := 1200
	events[1].DurationMS = &duration
	batchKey := digestKey("strict-batch")

	ack, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil || ack.AcceptedCount != 2 || ack.DuplicateBatch {
		t.Fatalf("first batch ack=%+v err=%v", ack, err)
	}
	duplicate, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil || !duplicate.DuplicateBatch || duplicate.AcceptedCount != 2 {
		t.Fatalf("duplicate batch ack=%+v err=%v", duplicate, err)
	}

	drilldown, err := service.GetEventDrilldown(context.Background(), application.EventDrilldownQuery{
		From:  now.Add(-time.Minute),
		To:    now.Add(time.Minute),
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("drilldown: %v", err)
	}
	if drilldown.TotalCount != 2 || len(drilldown.Items) != 2 {
		t.Fatalf("drilldown=%+v", drilldown)
	}
	if !strings.HasPrefix(drilldown.Items[0].SessionID, "s.***.") {
		t.Fatalf("sessionId must be masked: %q", drilldown.Items[0].SessionID)
	}
}

func TestTelemetryServiceRejectsWholeBatchBeforeWrite(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store, store)
	now := time.Now().UTC().Add(-time.Minute)
	valid := validEvent("page_open", "event", now)
	invalid := validEvent("page_open", "event", now)
	invalid.NetworkClass = "vpn"

	if _, err := service.ReportEventBatch(context.Background(), digestKey("invalid-batch"), []application.EventRecordInput{valid, invalid}); err == nil {
		t.Fatal("unknown networkClass must reject the whole batch")
	}
	summary, err := service.GetEventSummary(context.Background(), application.EventSummaryQuery{
		From: now.Add(-time.Hour),
		To:   time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if summary.TotalCount != 0 {
		t.Fatalf("invalid batch must not partially write: %+v", summary)
	}
}

func TestTelemetryIngestionAcceptsCellularGenerationsAndRejectsRemovedVPNValue(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "page_open",
		SessionID:          "s.Z3Vlc3RfaW50ZWdyYXRpb24." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		PageName:           "home",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "5g",
		DevicePlatform:     "ios",
	}
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("cellular-generation"),
		[]application.EventRecordInput{event},
	); err != nil {
		t.Fatalf("5g telemetry event must be accepted: %v", err)
	}

	event.NetworkClass = "vpn"
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("removed-vpn"),
		[]application.EventRecordInput{event},
	); err == nil {
		t.Fatal("removed networkClass vpn must be rejected")
	}
}

func TestTelemetryServiceRejectsCatalogSessionTimeAndRequiredExtensionViolations(t *testing.T) {
	now := time.Now().UTC()
	tests := map[string]application.EventRecordInput{
		"unknown event": func() application.EventRecordInput {
			event := validEvent("not_registered", "event", now)
			return event
		}(),
		"unknown page": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.PageName = "not_registered"
			return event
		}(),
		"unknown device platform": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.DevicePlatform = "phone_brand"
			return event
		}(),
		"invalid session": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.SessionID = "s.raw.user.1"
			return event
		}(),
		"expired event": func() application.EventRecordInput {
			return validEvent("page_open", "event", now.Add(-73*time.Hour))
		}(),
		"missing errorCode": func() application.EventRecordInput {
			return validEvent("runtime_exception", "error", now)
		}(),
	}
	for name, event := range tests {
		t.Run(name, func(t *testing.T) {
			store := telemetrypersistence.NewMemoryTelemetryStore()
			service := application.NewTelemetryService(store, store, store)
			if _, err := service.ReportEventBatch(context.Background(), digestKey(name), []application.EventRecordInput{event}); err == nil {
				t.Fatalf("%s must be rejected", name)
			}
		})
	}
}

func TestStartupDiagnosticsUseIndependentIdempotentBatch(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store, store)
	records := []application.StartupDiagnosticRecord{{
		EventID: "attempt_000000000001_1", AttemptID: "attempt_000000000001",
		Phase: "router_ready", Outcome: "ready", OccurredAt: time.Now().UTC().Format(time.RFC3339Nano),
		Platform: "ios", RuntimeEnv: "alpha", Sequence: 1, PhaseDurationMS: 120, ElapsedMS: 200,
	}}
	first, err := service.ReportStartupDiagnostics(context.Background(), "proof_000000000000000001", records)
	if err != nil || first.DuplicateBatch {
		t.Fatalf("first startup batch=%+v err=%v", first, err)
	}
	second, err := service.ReportStartupDiagnostics(context.Background(), "proof_000000000000000001", records)
	if err != nil || !second.DuplicateBatch {
		t.Fatalf("duplicate startup batch=%+v err=%v", second, err)
	}
}

func TestStartupDiagnosticsSameProofDoesNotCollapseDistinctBatch(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store, store)
	now := time.Now().UTC().Add(-time.Minute)
	firstRecord := application.StartupDiagnosticRecord{
		EventID: "attempt_000000000002_1", AttemptID: "attempt_000000000002",
		Phase: "dart_bootstrap", Outcome: "started", OccurredAt: now.Format(time.RFC3339Nano),
		Platform: "android", RuntimeEnv: "alpha", Sequence: 1,
	}
	secondRecord := firstRecord
	secondRecord.EventID = "attempt_000000000002_2"
	secondRecord.Sequence = 2
	secondRecord.Phase = "router_ready"

	first, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_attempt_flushes",
		[]application.StartupDiagnosticRecord{firstRecord},
	)
	if err != nil || first.DuplicateBatch {
		t.Fatalf("first batch=%+v err=%v", first, err)
	}
	second, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_attempt_flushes",
		[]application.StartupDiagnosticRecord{secondRecord},
	)
	if err != nil || second.DuplicateBatch {
		t.Fatalf("distinct batch must not be duplicate=%+v err=%v", second, err)
	}
}

func TestSLSEventProtocolWritesOnceAndConfirmsTimeoutAfterWrite(t *testing.T) {
	client := newRecordingSLSClient()
	client.failAfterWriteOnce = true
	config := localSLSConfig()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, config)
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	ledger := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryServiceWithStores(ledger, store, ledger)
	event := validEvent("page_open", "event", time.Now().UTC().Add(-time.Minute))
	batchKey := digestKey("timeout-after-write")

	ack, err := service.ReportEventBatch(context.Background(), batchKey, []application.EventRecordInput{event})
	if err != nil || ack.AcceptedCount != 1 || ack.DuplicateBatch {
		t.Fatalf("write-after-timeout ack=%+v err=%v", ack, err)
	}
	duplicate, err := service.ReportEventBatch(context.Background(), batchKey, []application.EventRecordInput{event})
	if err != nil || !duplicate.DuplicateBatch {
		t.Fatalf("duplicate ack=%+v err=%v", duplicate, err)
	}
	raw := client.logs(config.RawLogstore)
	if len(raw) != 1 {
		t.Fatalf("same sealed batch must land once, rows=%d", len(raw))
	}
	for _, field := range []string{"logType", "eventType", "sessionId", "pageName", "occurredAt", "deviceManufacturer", "deviceModel", "appVersion", "networkClass", "devicePlatform", "_batchKey", "_batchIndex", "ingestedAt"} {
		if raw[0][field] == "" {
			t.Fatalf("SLS row missing %s: %+v", field, raw[0])
		}
	}
}

func TestTelemetryServicePersistsTypedVideoPlaybackQoeWithoutContentAttribution(t *testing.T) {
	client := newRecordingSLSClient()
	config := localSLSConfig()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, config)
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	ledger := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryServiceWithStores(ledger, store, ledger)
	now := time.Now().UTC().Add(-time.Minute)
	readyMS, rebufferCount, rebufferMS, seekCount := 420, 1, 180, 2
	effectivePlaybackMS := 12000
	seekFailureCount, seekCommandMaxMS, seekSettleMaxMS := 0, 80, 120
	droppedFrames, processedVideoFrames, audioUnderrunCount := 2, 300, 0
	rendererMode, decoderQueueMode, decoderFallbackEnabled := "platform_view", "synchronous", true
	seekEvidenceSource, playbackMode, result := "controller_command_completion", "autoplay", "success"
	event := validEvent("video_playback_qoe", "event", now)
	event.ReadyMS = &readyMS
	event.RebufferCount = &rebufferCount
	event.RebufferMS = &rebufferMS
	event.EffectivePlaybackMS = &effectivePlaybackMS
	event.SeekCount = &seekCount
	event.SeekFailureCount = &seekFailureCount
	event.SeekCommandMaxMS = &seekCommandMaxMS
	event.SeekSettleMaxMS = &seekSettleMaxMS
	event.DroppedFrames = &droppedFrames
	event.ProcessedVideoFrames = &processedVideoFrames
	event.AudioUnderrunCount = &audioUnderrunCount
	event.RendererMode = &rendererMode
	event.DecoderQueueMode = &decoderQueueMode
	event.DecoderFallbackEnabled = &decoderFallbackEnabled
	event.SeekEvidenceSource = &seekEvidenceSource
	event.PlaybackMode = &playbackMode
	event.Result = &result

	if _, err := service.ReportEventBatch(context.Background(), digestKey("video-qoe"), []application.EventRecordInput{event}); err != nil {
		t.Fatalf("report video qoe: %v", err)
	}
	rows := client.logs(config.RawLogstore)
	if len(rows) != 1 {
		t.Fatalf("expected one qoe row, got %d", len(rows))
	}
	row := rows[0]
	for field, expected := range map[string]string{
		"eventType":              "video_playback_qoe",
		"readyMs":                "420",
		"rebufferCount":          "1",
		"rebufferMs":             "180",
		"effectivePlaybackMs":    "12000",
		"seekCount":              "2",
		"seekFailureCount":       "0",
		"seekCommandMaxMs":       "80",
		"seekSettleMaxMs":        "120",
		"droppedFrames":          "2",
		"processedVideoFrames":   "300",
		"audioUnderrunCount":     "0",
		"rendererMode":           "platform_view",
		"decoderQueueMode":       "synchronous",
		"decoderFallbackEnabled": "true",
		"seekEvidenceSource":     "controller_command_completion",
		"devicePlatform":         "android",
		"playbackMode":           "autoplay",
	} {
		if row[field] != expected {
			t.Fatalf("qoe %s=%q, want %q; row=%+v", field, row[field], expected, row)
		}
	}
	for _, forbidden := range []string{"postId", "feedRequestId", "rankingVersion", "tagRefs"} {
		if _, ok := row[forbidden]; ok {
			t.Fatalf("Ops QoE must not contain %s: %+v", forbidden, row)
		}
	}
}

func TestTelemetryServiceRejectsUnknownVideoSeekEvidenceSource(t *testing.T) {
	client := newRecordingSLSClient()
	config := localSLSConfig()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, config)
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	ledger := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryServiceWithStores(ledger, store, ledger)
	now := time.Now().UTC().Add(-time.Minute)
	readyMS, rebufferCount, rebufferMS, seekCount := 420, 1, 180, 2
	effectivePlaybackMS := 12000
	seekFailureCount, seekCommandMaxMS, seekSettleMaxMS := 0, 80, 0
	seekEvidenceSource, playbackMode := "unregistered_source", "autoplay"
	event := validEvent("video_playback_qoe", "event", now)
	event.ReadyMS = &readyMS
	event.RebufferCount = &rebufferCount
	event.RebufferMS = &rebufferMS
	event.EffectivePlaybackMS = &effectivePlaybackMS
	event.SeekCount = &seekCount
	event.SeekFailureCount = &seekFailureCount
	event.SeekCommandMaxMS = &seekCommandMaxMS
	event.SeekSettleMaxMS = &seekSettleMaxMS
	event.SeekEvidenceSource = &seekEvidenceSource
	event.PlaybackMode = &playbackMode

	if _, err := service.ReportEventBatch(context.Background(), digestKey("invalid-video-qoe"), []application.EventRecordInput{event}); err == nil {
		t.Fatal("unregistered seek evidence source must be rejected")
	}
}

func TestSLSStartupDiagnosticsStayInRestrictedLogstore(t *testing.T) {
	client := newRecordingSLSClient()
	config := localSLSConfig()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, config)
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	ledger := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryServiceWithStores(ledger, store, ledger)
	record := application.StartupDiagnosticRecord{
		EventID: "startup_attempt_000001_1", AttemptID: "startup_attempt_000001", Sequence: 1,
		Phase: "router_ready", PhaseDurationMS: 100, ElapsedMS: 200, Outcome: "ready",
		OccurredAt: time.Now().UTC().Format(time.RFC3339Nano), Platform: "ios", RuntimeEnv: "gamma",
	}
	if _, err := service.ReportStartupDiagnostics(context.Background(), "startup_proof_000000000001", []application.StartupDiagnosticRecord{record}); err != nil {
		t.Fatalf("report startup diagnostic: %v", err)
	}
	if len(client.logs(config.RawLogstore)) != 0 || len(client.logs(config.StartupDiagnosticLogstore)) != 1 {
		t.Fatalf("startup diagnostics crossed logstore boundary")
	}
	row := client.logs(config.StartupDiagnosticLogstore)[0]
	for _, forbidden := range []string{"sessionId", "userId", "pageName", "callStack"} {
		if _, ok := row[forbidden]; ok {
			t.Fatalf("restricted startup row contains %s: %+v", forbidden, row)
		}
	}
}

func TestSLSRuntimeDiagnosticsUseDedicatedLogstoreAndCanonicalFields(t *testing.T) {
	client := newRecordingSLSClient()
	config := localSLSConfig()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, config)
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	ledger := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewRuntimeLogService(store, ledger)
	now := time.Now().UTC().Add(-time.Minute)
	record := map[string]any{
		"schema":     "observability.slim",
		"recordId":   "r.sls.runtime",
		"occurredAt": now.Format(time.RFC3339Nano),
		"observedAt": now.Format(time.RFC3339Nano),
		"logKind":    "exception",
		"severity":   "ERROR",
		"signal":     "app.exception.flutter",
		"message":    "uncaught exception",
		"resource": map[string]any{
			"sourceType": "app",
			"service":    "quwoquan_app",
			"appVersion": "1.0.0",
		},
		"errorCode": "APP.RUNTIME.uncaught_exception",
		"attributes": map[string]any{
			"source":        "flutter",
			"exceptionType": "StateError",
		},
	}
	if _, err := service.ReportRuntimeLogBatch(
		context.Background(),
		digestKey("runtime-sls"),
		[]map[string]any{record},
	); err != nil {
		t.Fatalf("report runtime diagnostics: %v", err)
	}
	if len(client.logs(config.RawLogstore)) != 0 ||
		len(client.logs(config.RuntimeLogstore)) != 1 {
		t.Fatalf("runtime diagnostics crossed logstore boundary")
	}
	row := client.logs(config.RuntimeLogstore)[0]
	for _, required := range []string{
		"schema",
		"recordId",
		"logKind",
		"severity",
		"signal",
		"resourceAppVersion",
		"errorCode",
		"attributes",
		"_batchKey",
	} {
		if row[required] == "" {
			t.Fatalf("runtime diagnostics row misses %s: %+v", required, row)
		}
	}
	for _, forbidden := range []string{"schemaVersion", "releaseId", "sessionId"} {
		if _, ok := row[forbidden]; ok {
			t.Fatalf("runtime diagnostics row contains forbidden %s: %+v", forbidden, row)
		}
	}
}

func TestSLSDrilldownScansIngestWindowThenFiltersOccurredAt(t *testing.T) {
	client := newRecordingSLSClient()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, localSLSConfig())
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	from := time.Now().UTC().Add(-24 * time.Hour)
	to := from.Add(time.Hour)
	if _, err := store.GetEventDrilldown(context.Background(), application.EventDrilldownQuery{
		From: from, To: to, Limit: 25,
	}); err != nil {
		t.Fatalf("query SLS drilldown: %v", err)
	}
	request := client.lastRequest()
	if request == nil {
		t.Fatal("SLS drilldown request was not recorded")
	}
	if request.To-request.From < int64((71 * time.Hour).Seconds()) {
		t.Fatalf("raw outer window must scan ingestion retention: %+v", request)
	}
	for _, marker := range []string{
		"from_iso8601_timestamp(occurredAt)",
		from.Format(time.RFC3339Nano),
		to.Format(time.RFC3339Nano),
		"LIMIT 25",
	} {
		if !strings.Contains(request.Query, marker) {
			t.Fatalf("raw query missing %q: %s", marker, request.Query)
		}
	}
}

func TestSLSSummaryQueriesFilterSingleRollupRowKind(t *testing.T) {
	client := newRecordingSLSClient()
	store, err := telemetrypersistence.NewSLSEventLogStore(client, localSLSConfig())
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	now := time.Now().UTC()
	if _, err := store.GetEventSummary(context.Background(), application.EventSummaryQuery{
		From: now.Add(-time.Hour), To: now,
	}); err != nil {
		t.Fatalf("event summary: %v", err)
	}
	eventRequest := client.lastRequest()
	if eventRequest == nil || !strings.Contains(eventRequest.Query, `rowKind:"event_dimensions"`) {
		t.Fatalf("event summary must filter event_dimensions rowKind: %+v", eventRequest)
	}
	if _, err := store.GetRuntimeLogSummary(context.Background(), application.RuntimeLogSummaryQuery{
		From: now.Add(-time.Hour), To: now,
	}); err != nil {
		t.Fatalf("runtime summary: %v", err)
	}
	runtimeRequest := client.lastRequest()
	if runtimeRequest == nil || !strings.Contains(runtimeRequest.Query, `rowKind:"runtime_diagnostics"`) {
		t.Fatalf("runtime summary must filter runtime_diagnostics rowKind: %+v", runtimeRequest)
	}
}

type recordingSLSClient struct {
	mu                 sync.Mutex
	byLogstore         map[string][]map[string]string
	failAfterWriteOnce bool
	requests           []*sls.GetLogRequest
}

func newRecordingSLSClient() *recordingSLSClient {
	return &recordingSLSClient{byLogstore: map[string][]map[string]string{}}
}

func (c *recordingSLSClient) PostLogStoreLogs(_ string, logstore string, group *sls.LogGroup, _ *string) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, logEntry := range group.Logs {
		row := map[string]string{}
		for _, content := range logEntry.Contents {
			row[content.GetKey()] = content.GetValue()
		}
		c.byLogstore[logstore] = append(c.byLogstore[logstore], row)
	}
	if c.failAfterWriteOnce {
		c.failAfterWriteOnce = false
		return errors.New("simulated timeout after durable write")
	}
	return nil
}

func (c *recordingSLSClient) GetLogsV2(_ string, logstore string, request *sls.GetLogRequest) (*sls.GetLogsResponse, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	requestCopy := *request
	c.requests = append(c.requests, &requestCopy)
	if strings.Contains(request.Query, "SELECT count(*) AS count") {
		batchKey := queryBatchKey(request.Query)
		count := 0
		for _, row := range c.byLogstore[logstore] {
			if row["_batchKey"] == batchKey {
				count++
			}
		}
		return &sls.GetLogsResponse{Logs: []map[string]string{{"count": strconv.Itoa(count)}}}, nil
	}
	rows := append([]map[string]string(nil), c.byLogstore[logstore]...)
	return &sls.GetLogsResponse{Logs: rows, Count: int64(len(rows))}, nil
}

func (c *recordingSLSClient) lastRequest() *sls.GetLogRequest {
	c.mu.Lock()
	defer c.mu.Unlock()
	if len(c.requests) == 0 {
		return nil
	}
	requestCopy := *c.requests[len(c.requests)-1]
	return &requestCopy
}

func (c *recordingSLSClient) logs(logstore string) []map[string]string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]map[string]string(nil), c.byLogstore[logstore]...)
}

func queryBatchKey(query string) string {
	prefix := `_batchKey:"`
	start := strings.Index(query, prefix)
	if start < 0 {
		return ""
	}
	start += len(prefix)
	end := strings.Index(query[start:], `"`)
	if end < 0 {
		return ""
	}
	return query[start : start+end]
}

func localSLSConfig() telemetrypersistence.SLSConfig {
	return telemetrypersistence.SLSConfig{
		Region: "cn-hangzhou", Endpoint: "example.invalid", Project: "test-project",
		RawLogstore:               "app-product-telemetry-raw",
		StartupDiagnosticLogstore: "app-startup-diagnostic-raw",
		RuntimeLogstore:           "runtime-diagnostics-raw",
		AggregateLogstore:         "app-product-telemetry-hourly", Timeout: 1200 * time.Millisecond,
	}
}

func validEvent(eventType, logType string, occurredAt time.Time) application.EventRecordInput {
	return application.EventRecordInput{
		LogType: logType, EventType: eventType,
		SessionID: "s.Z3Vlc3RfdGVzdA." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		PageName:  "home", OccurredAt: occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple", DeviceModel: "iPhone",
		AppVersion: "1.0.0", NetworkClass: "wifi", DevicePlatform: "android",
	}
}

func digestKey(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}
