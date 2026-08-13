// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
// readiness_case: report-event-batch-api
// readiness_case: report-startup-event-batch-api
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	eventhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	testsupport "quwoquan_service/services/product-ops-service/tests/support"
)

func TestElasticsearchLogSinkPersistsAndQueriesCanonicalTelemetry(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	testinfra.ConfigureLocalContainerRuntime()
	endpoint, terminate := testsupport.StartElasticsearch(t, ctx)
	defer terminate()
	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(
		eventRecordRealRedisRouterConfig(redisRuntime),
	)
	if err != nil {
		t.Fatalf("create real Redis router: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRouter.Close(); closeErr != nil {
			t.Errorf("close Redis router: %v", closeErr)
		}
		closeCtx, closeCancel := context.WithTimeout(context.Background(), time.Minute)
		defer closeCancel()
		if closeErr := redisRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})

	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	config := telemetrypersistence.ElasticsearchConfig{
		Endpoint:               endpoint,
		RawIndex:               "qwq-telemetry-raw-" + suffix,
		StartupDiagnosticIndex: "qwq-telemetry-startup-" + suffix,
		RuntimeLogIndex:        "qwq-telemetry-runtime-" + suffix,
		AggregateIndex:         "qwq-telemetry-hourly-" + suffix,
		Timeout:                30 * time.Second,
	}
	store, err := telemetrypersistence.NewElasticsearchEventLogStore(config)
	if err != nil {
		t.Fatalf("NewElasticsearchEventLogStore() error = %v", err)
	}
	if err := store.EnsureIndices(ctx); err != nil {
		t.Fatalf("EnsureIndices() error = %v", err)
	}
	t.Cleanup(func() {
		for _, indexBase := range []string{
			config.RawIndex,
			config.StartupDiagnosticIndex,
			config.RuntimeLogIndex,
			config.AggregateIndex,
		} {
			for _, resource := range []string{
				"/" + indexBase + "-*",
				"/_index_template/" + indexBase + "-template",
			} {
				request, _ := http.NewRequest(
					http.MethodDelete,
					endpoint+resource,
					nil,
				)
				response, requestErr := http.DefaultClient.Do(request)
				if requestErr == nil {
					_ = response.Body.Close()
				}
			}
		}
	})

	now := time.Now().UTC().Add(-2 * time.Minute)
	eventInputs := []application.EventRecordInput{
		integrationElasticsearchPageEvent(now, "page_open", "session-a"),
		integrationElasticsearchPageEvent(now.Add(time.Second), "page_return", "session-a"),
		integrationRtcMediaQoeEvent(now.Add(2*time.Second), "completed", true, 100, 1),
		integrationRtcMediaQoeEvent(now.Add(3*time.Second), "connection_lost", true, 200, 2),
		integrationRtcMediaQoeEvent(now.Add(4*time.Second), "connect_failed", false, 0, 3),
		integrationRtcMediaQoeEvent(now.Add(5*time.Second), "abandoned", true, 9999, 99),
	}
	records := make([]application.EventRecord, len(eventInputs))
	eventBatchKey := strings.Repeat("a", 64)
	for index, input := range eventInputs {
		records[index] = application.EventRecord{
			EventRecordInput: input,
			BatchKey:         eventBatchKey,
			BatchIndex:       index,
			IngestedAt:       now.Add(time.Duration(index+10) * time.Second),
		}
	}
	if err := store.PutEventBatch(ctx, eventBatchKey, records); err != nil {
		t.Fatalf("PutEventBatch() error = %v", err)
	}
	if err := store.PutEventBatch(ctx, eventBatchKey, records); err != nil {
		t.Fatalf("PutEventBatch() replay error = %v", err)
	}
	complete, err := store.HasEventBatch(ctx, eventBatchKey, len(records))
	if err != nil || !complete {
		t.Fatalf("HasEventBatch() = %v, %v; want true, nil", complete, err)
	}

	startupBatchKey := strings.Repeat("b", 64)
	if err := store.PutStartupDiagnostics(
		ctx,
		startupBatchKey,
		[]application.StartupDiagnosticRecord{{
			EventID:           "startup-event",
			AttemptID:         "startup-attempt",
			Phase:             "recovery",
			Outcome:           "failed",
			OccurredAt:        now.Format(time.RFC3339Nano),
			Platform:          "ios",
			RuntimeEnv:        "gamma",
			AppVersion:        "1.0.0",
			NetworkClass:      "wifi",
			RecoverySurface:   "page.app.startup_recovery",
			RecoveryLifecycle: "failure",
			RecoveryMount:     "runtime_boundary",
			RecoveryPhase:     "runtime_unavailable",
			RecoveryAction:    "none",
			FailureSource:     "runtime_boundary",
		}},
	); err != nil {
		t.Fatalf("PutStartupDiagnostics() error = %v", err)
	}
	complete, err = store.HasStartupDiagnosticBatch(ctx, startupBatchKey, 1)
	if err != nil || !complete {
		t.Fatalf(
			"HasStartupDiagnosticBatch() = %v, %v; want true, nil",
			complete,
			err,
		)
	}
	startupSource := readElasticsearchDocumentSource(
		t,
		ctx,
		endpoint,
		config.StartupDiagnosticIndex+"-"+now.Format("2006.01.02"),
		startupBatchKey+":0",
	)
	for field, want := range map[string]string{
		"recoverySurface":   "page.app.startup_recovery",
		"recoveryLifecycle": "failure",
		"recoveryMount":     "runtime_boundary",
		"recoveryPhase":     "runtime_unavailable",
		"recoveryAction":    "none",
		"failureSource":     "runtime_boundary",
	} {
		if got := fmt.Sprint(startupSource[field]); got != want {
			t.Fatalf("startup source %s = %q; want %q", field, got, want)
		}
	}

	runtimeBatchKey := strings.Repeat("c", 64)
	if err := store.PutRuntimeLogBatch(
		ctx,
		runtimeBatchKey,
		[]application.RuntimeLogRecord{{
			Fields: map[string]string{
				"schema":             "observability.slim",
				"occurredAt":         now.Format(time.RFC3339Nano),
				"observedAt":         now.Add(time.Second).Format(time.RFC3339Nano),
				"logKind":            "error",
				"severity":           "error",
				"signal":             "app.runtime_exception",
				"message":            "provider integration failure",
				"actorHash":          "actor-hash",
				"requestId":          "request-sensitive",
				"resourceSourceType": "app",
				"resourceService":    "quwoquan_app",
				"resourceAppVersion": "1.0.0",
			},
			BatchKey:   runtimeBatchKey,
			BatchIndex: 0,
			IngestedAt: now.Add(20 * time.Second),
		}},
	); err != nil {
		t.Fatalf("PutRuntimeLogBatch() error = %v", err)
	}
	complete, err = store.HasRuntimeLogBatch(ctx, runtimeBatchKey, 1)
	if err != nil || !complete {
		t.Fatalf("HasRuntimeLogBatch() = %v, %v; want true, nil", complete, err)
	}
	refreshElasticsearchIndices(t, ctx, endpoint)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.RawIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.StartupDiagnosticIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.RuntimeLogIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.AggregateIndex,
		now,
		"qwq-product-telemetry-hourly-90d",
	)

	from := now.Add(-time.Hour)
	to := now.Add(time.Hour)

	// rollups.yaml 是聚合写侧唯一真相源：同一批事件按 rowKind 产出多份聚合行，
	// 告警评估器 reader 必须能对真实 ES 按 rowKind 读回。
	rtcRows, err := store.ListAggregateAlertRows(ctx, "rtc_qoe", from, to)
	if err != nil {
		t.Fatalf("ListAggregateAlertRows(rtc_qoe) error = %v", err)
	}
	if len(rtcRows) == 0 {
		t.Fatal("rtc_qoe aggregate rows missing from real Elasticsearch")
	}
	rtcTotal := 0.0
	sawConnectHistogram := false
	for _, row := range rtcRows {
		if row["rowKind"] != "rtc_qoe" {
			t.Fatalf("rtc_qoe read-back returned foreign rowKind: %v", row["rowKind"])
		}
		if count, ok := row["count"].(float64); ok {
			rtcTotal += count
		}
		if histogram, ok := row["connectTimeHistogram"].(map[string]any); ok {
			if _, hasCounts := histogram["counts"]; hasCounts {
				sawConnectHistogram = true
			}
		}
	}
	if rtcTotal != 4 {
		t.Fatalf("rtc_qoe aggregate count = %v; want 4", rtcTotal)
	}
	if !sawConnectHistogram {
		t.Fatal("rtc_qoe aggregate rows miss connectTimeHistogram measure")
	}
	eventDimensionRows, err := store.ListAggregateAlertRows(
		ctx, "event_dimensions", from, to,
	)
	if err != nil {
		t.Fatalf("ListAggregateAlertRows(event_dimensions) error = %v", err)
	}
	if len(eventDimensionRows) == 0 {
		t.Fatal("event_dimensions aggregate rows missing from real Elasticsearch")
	}
	runtimeRows, err := store.ListAggregateAlertRows(
		ctx, "runtime_diagnostics", from, to,
	)
	if err != nil {
		t.Fatalf("ListAggregateAlertRows(runtime_diagnostics) error = %v", err)
	}
	if len(runtimeRows) == 0 {
		t.Fatal("runtime_diagnostics aggregate rows missing from real Elasticsearch")
	}
	generatedThrough, hasSamples, err := store.AggregateGeneratedThrough(ctx)
	if err != nil || !hasSamples {
		t.Fatalf(
			"AggregateGeneratedThrough() = %v, %v, %v; want water line with samples",
			generatedThrough, hasSamples, err,
		)
	}
	rawRetentionDays, err := store.RawRetentionDays(ctx)
	if err != nil || rawRetentionDays != 3 {
		t.Fatalf(
			"RawRetentionDays() = %d, %v; want contract 3d from real ILM",
			rawRetentionDays, err,
		)
	}
	eventSummary, err := store.GetEventSummary(
		ctx,
		application.EventSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetEventSummary() error = %v", err)
	}
	if eventSummary.TotalCount != int64(len(records)) ||
		eventSummary.SessionCount != 5 ||
		eventSummary.SourceKind != "hourly_rollup" {
		t.Fatalf("GetEventSummary() = %+v", eventSummary)
	}

	drilldown, err := store.GetEventDrilldown(
		ctx,
		application.EventDrilldownQuery{From: from, To: to, Limit: 20},
	)
	if err != nil {
		t.Fatalf("GetEventDrilldown() error = %v", err)
	}
	if len(drilldown.Items) != len(records) {
		t.Fatalf("GetEventDrilldown() items = %d; want %d", len(drilldown.Items), len(records))
	}
	rawSessionIDs := make(map[string]struct{}, len(eventInputs))
	for _, input := range eventInputs {
		rawSessionIDs[input.SessionID] = struct{}{}
	}
	for _, item := range drilldown.Items {
		_, rawSessionLeaked := rawSessionIDs[item.SessionID]
		if item.SessionID == "" ||
			rawSessionLeaked ||
			!strings.HasPrefix(item.SessionID, "s.***.") {
			t.Fatalf(
				"GetEventDrilldown() sessionId = %q; want masked value",
				item.SessionID,
			)
		}
	}
	qoeDrilldown, err := store.GetEventDrilldown(
		ctx,
		application.EventDrilldownQuery{
			EventType: "rtc_media_qoe",
			SessionID: eventInputs[3].SessionID,
			From:      from,
			To:        to,
			Limit:     1,
		},
	)
	if err != nil {
		t.Fatalf("GetEventDrilldown() for rtc_media_qoe session: %v", err)
	}
	if len(qoeDrilldown.Items) != 1 {
		t.Fatalf(
			"rtc_media_qoe session drilldown items = %d; want 1",
			len(qoeDrilldown.Items),
		)
	}
	qoeItem := qoeDrilldown.Items[0]
	if qoeItem.Result == nil || *qoeItem.Result != "connection_lost" ||
		qoeItem.CallType == nil || *qoeItem.CallType != "video" ||
		qoeItem.ParticipantCount == nil || *qoeItem.ParticipantCount != 2 ||
		qoeItem.ConnectTimeMS == nil || *qoeItem.ConnectTimeMS != 200 ||
		qoeItem.MediaConnected == nil || !*qoeItem.MediaConnected ||
		qoeItem.ReconnectCount == nil || *qoeItem.ReconnectCount != 2 ||
		qoeItem.DisconnectReason == nil ||
		*qoeItem.DisconnectReason != "unexpected_disconnect" ||
		qoeItem.NetworkQuality == nil || *qoeItem.NetworkQuality != "good" {
		t.Fatalf("rtc_media_qoe drilldown lost terminal facts: %+v", qoeItem)
	}
	if qoeItem.SessionID == eventInputs[3].SessionID ||
		!strings.HasPrefix(qoeItem.SessionID, "s.***.") {
		t.Fatalf("rtc_media_qoe drilldown must mask sessionId: %+v", qoeItem)
	}

	pageStats, err := store.GetPageExperienceStats(
		ctx,
		application.PageExperienceQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetPageExperienceStats() error = %v", err)
	}
	if len(pageStats) != 2 {
		t.Fatalf("GetPageExperienceStats() = %+v", pageStats)
	}

	// 黄金指标 percentile/sum_ratio 形态的原始样本统计门面：真实 ES
	// percentiles/sum 聚合读回（单样本 durationMs=500 → P95=500）。
	valueStats, err := store.GetEventValueStats(ctx, application.EventValueStatsQuery{
		EventType:  "page_return",
		ValueField: "durationMs",
		From:       from,
		To:         to,
	})
	if err != nil {
		t.Fatalf("GetEventValueStats() error = %v", err)
	}
	if valueStats.SampleCount != 1 || valueStats.P95 != 500 {
		t.Fatalf("GetEventValueStats() = %+v; want one 500ms sample", valueStats)
	}

	// PV 唯一口径 = page_open 事件数（本批只有一条 page_open）。
	sessions, pageViews, err := store.ListDistinctSessions(ctx, from, to, 100)
	if err != nil {
		t.Fatalf("ListDistinctSessions() error = %v", err)
	}
	if len(sessions) != 5 || pageViews != 1 {
		t.Fatalf(
			"ListDistinctSessions() = %v, %d; want five sessions and one page view",
			sessions, pageViews,
		)
	}

	rtcSummary, err := store.ReadRtcMediaQoeSummary(
		ctx,
		application.RtcMediaQoeSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("ReadRtcMediaQoeSummary() error = %v", err)
	}
	if rtcSummary.EffectiveSampleCount != 3 ||
		rtcSummary.MediaConnectedCount != 2 ||
		rtcSummary.ConnectionLostCount != 1 ||
		rtcSummary.ReconnectCount != 6 ||
		rtcSummary.ConnectP95MS == nil ||
		*rtcSummary.ConnectP95MS < 100 ||
		*rtcSummary.ConnectP95MS > 200 {
		t.Fatalf("ReadRtcMediaQoeSummary() = %+v", rtcSummary)
	}

	runtimeSummary, err := store.GetRuntimeLogSummary(
		ctx,
		application.RuntimeLogSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogSummary() error = %v", err)
	}
	if runtimeSummary.TotalCount != 1 ||
		runtimeSummary.DimensionCounters["signal"]["app.runtime_exception"] != 1 {
		t.Fatalf("GetRuntimeLogSummary() = %+v", runtimeSummary)
	}
	runtimeDrilldown, err := store.GetRuntimeLogDrilldown(
		ctx,
		application.RuntimeLogDrilldownQuery{
			From:            from,
			To:              to,
			Limit:           10,
			ActorHash:       "actor-hash",
			MessageContains: "integration failure",
		},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogDrilldown() error = %v", err)
	}
	if len(runtimeDrilldown.Items) != 1 ||
		len(runtimeDrilldown.Items[0].Correlation) != 0 {
		t.Fatalf("GetRuntimeLogDrilldown() = %+v", runtimeDrilldown)
	}

	// Exercise the canonical inbound routes against this same real
	// Elasticsearch-backed service. Direct store assertions above prove the
	// provider contract; these requests prove the declared HTTP operations
	// actually reach that provider boundary.
	service := application.NewTelemetryService(
		store,
		telemetrypersistence.NewRedisEventBatchLedger(
			redisRouter.Scene("general"),
		),
	)
	mux := http.NewServeMux()
	eventhttp.NewHandler(service, nil, nil).Register(mux)
	eventhttp.NewStartupTelemetryHandler(service, nil).Register(mux)
	eventBody, err := json.Marshal(map[string]any{
		"events": []application.EventRecordInput{
			integrationElasticsearchPageEvent(time.Now().UTC(), "page_open", "http-route"),
		},
	})
	if err != nil {
		t.Fatalf("marshal ReportEventBatch body: %v", err)
	}
	var canonicalEventBody any
	if err := json.Unmarshal(eventBody, &canonicalEventBody); err != nil {
		t.Fatalf("normalize ReportEventBatch body: %v", err)
	}
	canonicalEventJSON, err := json.Marshal(canonicalEventBody)
	if err != nil {
		t.Fatalf("canonicalize ReportEventBatch body: %v", err)
	}
	eventDigest := sha256.Sum256(canonicalEventJSON)
	eventRequest := httptest.NewRequest(http.MethodPost, "/ops/events", bytes.NewReader(eventBody))
	eventRequest = eventRequest.WithContext(rtauth.WithPrincipal(
		eventRequest.Context(),
		rtauth.Principal{Actor: operation.ActorContext{PersonaID: "persona-api-integration"}},
	))
	eventRequest.Header.Set("Idempotency-Key", fmt.Sprintf("%x", eventDigest))
	eventResponse := httptest.NewRecorder()
	mux.ServeHTTP(eventResponse, eventRequest)
	if eventResponse.Code != http.StatusOK {
		t.Fatalf("ReportEventBatch status=%d body=%s", eventResponse.Code, eventResponse.Body)
	}

	startupBody := []byte(fmt.Sprintf(
		`{"events":[{"eventId":"attempt_1234567890123456_1","attemptId":"attempt_1234567890123456","sequence":1,"phase":"terminal","phaseDurationMs":10,"elapsedMs":1000,"outcome":"success","occurredAt":%q,"platform":"android","runtimeEnv":"gamma","appVersion":"1.0.0","networkClass":"wifi","recoverySurface":"","failureCode":"","failureSource":"","deadlineOrigin":"android_process"}]}`,
		time.Now().UTC().Format(time.RFC3339Nano),
	))
	startupRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewReader(startupBody),
	)
	startupRequest.Header.Set("X-Qwq-Startup-Proof", "proof_123456789012345678901234")
	startupResponse := httptest.NewRecorder()
	mux.ServeHTTP(startupResponse, startupRequest)
	if startupResponse.Code != http.StatusOK {
		t.Fatalf(
			"ReportStartupEventBatch status=%d body=%s",
			startupResponse.Code,
			startupResponse.Body,
		)
	}
}

func eventRecordRealRedisRouterConfig(runtime *testinfra.RealRedis) rtredis.RouterConfig {
	scenes := make(map[string]rtredis.SceneConfig, len(rtredis.GeneratedSceneNames()))
	for _, name := range rtredis.GeneratedSceneNames() {
		scenes[name] = rtredis.SceneConfig{
			Mode:     "standalone",
			Addr:     runtime.Addr,
			Password: runtime.Password,
			DB:       0,
			TLS:      runtime.TLS,
		}
	}
	return rtredis.RouterConfig{
		Scenes:       scenes,
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	}
}

func integrationElasticsearchPageEvent(
	occurredAt time.Time,
	eventType string,
	session string,
) application.EventRecordInput {
	readyMS := 120
	durationMS := 500
	input := application.EventRecordInput{
		LogType:            "event",
		EventType:          eventType,
		SessionID:          "s." + session + ".1",
		PageName:           "chat_detail",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
	}
	if eventType == "page_open" {
		input.ReadyMS = &readyMS
	}
	if eventType == "page_return" {
		input.DurationMS = &durationMS
	}
	return input
}

func integrationRtcMediaQoeEvent(
	occurredAt time.Time,
	result string,
	mediaConnected bool,
	connectTimeMS int,
	reconnectCount int,
) application.EventRecordInput {
	callType := "video"
	participantCount := 2
	networkQuality := "good"
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "rtc_media_qoe",
		SessionID:          "s.cXRjLW1lZGlhLXFvZQ." + fmt.Sprint(occurredAt.UnixMilli()),
		PageName:           "rtc_video",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
		CallType:           &callType,
		Result:             &result,
		ConnectTimeMS:      &connectTimeMS,
		MediaConnected:     &mediaConnected,
		ReconnectCount:     &reconnectCount,
		ParticipantCount:   &participantCount,
		NetworkQuality:     &networkQuality,
	}
	if result == "connection_lost" {
		disconnectReason := "unexpected_disconnect"
		event.DisconnectReason = &disconnectReason
	}
	return event
}

func assertElasticsearchLifecycleBinding(
	t *testing.T,
	ctx context.Context,
	endpoint string,
	indexBase string,
	instant time.Time,
	expectedPolicy string,
) {
	t.Helper()
	resources := []string{
		"/_index_template/" + indexBase + "-template",
		"/" + indexBase + "-" + instant.UTC().Format("2006.01.02") + "/_settings",
	}
	for _, resource := range resources {
		request, err := http.NewRequestWithContext(
			ctx,
			http.MethodGet,
			endpoint+resource,
			nil,
		)
		if err != nil {
			t.Fatalf("build Elasticsearch lifecycle request: %v", err)
		}
		response, err := http.DefaultClient.Do(request)
		if err != nil {
			t.Fatalf("read Elasticsearch lifecycle resource %s: %v", resource, err)
		}
		body, readErr := io.ReadAll(io.LimitReader(response.Body, 64<<10))
		_ = response.Body.Close()
		if readErr != nil {
			t.Fatalf("read Elasticsearch lifecycle response %s: %v", resource, readErr)
		}
		if response.StatusCode < http.StatusOK ||
			response.StatusCode >= http.StatusMultipleChoices {
			t.Fatalf(
				"Elasticsearch lifecycle resource %s status=%d: %s",
				resource,
				response.StatusCode,
				body,
			)
		}
		if !bytes.Contains(body, []byte(expectedPolicy)) {
			t.Fatalf(
				"Elasticsearch lifecycle resource %s does not bind policy %s: %s",
				resource,
				expectedPolicy,
				body,
			)
		}
	}
}

func readElasticsearchDocumentSource(
	t *testing.T,
	ctx context.Context,
	endpoint string,
	index string,
	documentID string,
) map[string]any {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		endpoint+"/"+index+"/_doc/"+documentID,
		nil,
	)
	if err != nil {
		t.Fatalf("build Elasticsearch document request: %v", err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("read Elasticsearch document: %v", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 64<<10))
	if err != nil {
		t.Fatalf("read Elasticsearch document response: %v", err)
	}
	if response.StatusCode != http.StatusOK {
		t.Fatalf("Elasticsearch document status=%d body=%s", response.StatusCode, body)
	}
	var document struct {
		Source map[string]any `json:"_source"`
	}
	if err := json.Unmarshal(body, &document); err != nil {
		t.Fatalf("decode Elasticsearch document: %v", err)
	}
	if document.Source == nil {
		t.Fatalf("Elasticsearch document has no _source: %s", body)
	}
	return document.Source
}

func refreshElasticsearchIndices(
	t *testing.T,
	ctx context.Context,
	endpoint string,
) {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		endpoint+"/_refresh",
		nil,
	)
	if err != nil {
		t.Fatalf("build Elasticsearch refresh request: %v", err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("refresh Elasticsearch indices: %v", err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(response.Body, 4096))
	if response.StatusCode < http.StatusOK ||
		response.StatusCode >= http.StatusMultipleChoices {
		t.Fatalf(
			"refresh Elasticsearch indices status=%d: %s",
			response.StatusCode,
			body,
		)
	}
}
