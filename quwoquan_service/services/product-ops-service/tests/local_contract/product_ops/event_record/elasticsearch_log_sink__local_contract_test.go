package local_contract

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestElasticsearchLogSinkUsesDeterministicDocumentsAndProviderNeutralPrivacy(
	t *testing.T,
) {
	t.Parallel()
	harness := newElasticsearchHarness(nil)
	server := httptest.NewServer(harness)
	t.Cleanup(server.Close)
	store := newTestElasticsearchStore(t, server.URL)
	ctx := context.Background()
	if err := store.EnsureIndices(ctx); err != nil {
		t.Fatalf("EnsureIndices() error = %v", err)
	}

	now := time.Now().UTC().Add(-time.Minute)
	batchKey := strings.Repeat("a", 64)
	input := validEvent("page_open", "event", now)
	record := application.EventRecord{
		EventRecordInput: input,
		BatchKey:         batchKey,
		BatchIndex:       0,
		IngestedAt:       now.Add(time.Second),
	}
	if err := store.PutEventBatch(ctx, batchKey, []application.EventRecord{record}); err != nil {
		t.Fatalf("PutEventBatch() error = %v", err)
	}
	if err := store.PutEventBatch(ctx, batchKey, []application.EventRecord{record}); err != nil {
		t.Fatalf("PutEventBatch() replay error = %v", err)
	}
	complete, err := store.HasEventBatch(ctx, batchKey, 1)
	if err != nil || !complete {
		t.Fatalf("HasEventBatch() = %v, %v; want true, nil", complete, err)
	}

	raw := harness.document("app-product-telemetry-raw", batchKey+":0")
	if got := fmt.Sprint(raw["sessionId"]); got != input.SessionID {
		t.Fatalf("raw sessionId = %q; want %q", got, input.SessionID)
	}
	rollups := harness.documents("app-product-telemetry-hourly")
	if len(rollups) != 1 {
		t.Fatalf("event rollup documents = %d; want 1", len(rollups))
	}
	encodedRollup, _ := json.Marshal(rollups[0])
	for _, forbidden := range []string{
		input.SessionID,
		`"sessionId"`,
		`"sessions"`,
		`"_batchKey"`,
	} {
		if bytes.Contains(encodedRollup, []byte(forbidden)) {
			t.Fatalf("aggregate document leaked %q: %s", forbidden, encodedRollup)
		}
	}
	if _, ok := rollups[0]["sessionHashes"]; !ok {
		t.Fatalf("aggregate document misses privacy-preserving sessionHashes")
	}
	harness.deleteFirstDocument("app-product-telemetry-hourly")
	complete, err = store.HasEventBatch(ctx, batchKey, 1)
	if err != nil || !complete {
		t.Fatalf(
			"HasEventBatch() with repairable rollup = %v, %v; want true, nil",
			complete,
			err,
		)
	}
	if got := harness.documentCount("app-product-telemetry-hourly"); got != 1 {
		t.Fatalf("repaired event rollup documents = %d; want 1", got)
	}
	if err := store.PutEventBatch(ctx, batchKey, []application.EventRecord{record}); err != nil {
		t.Fatalf("PutEventBatch() repair error = %v", err)
	}
	complete, err = store.HasEventBatch(ctx, batchKey, 1)
	if err != nil || !complete {
		t.Fatalf(
			"HasEventBatch() after repair = %v, %v; want true, nil",
			complete,
			err,
		)
	}

	startupBatchKey := strings.Repeat("b", 64)
	if err := store.PutStartupDiagnostics(
		ctx,
		startupBatchKey,
		[]application.StartupDiagnosticRecord{{
			EventID:    "event-1",
			AttemptID:  "attempt-1",
			Phase:      "flutter_first_frame",
			Outcome:    "succeeded",
			OccurredAt: now.Format(time.RFC3339Nano),
			Platform:   "ios",
			RuntimeEnv: "gamma",
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

	runtimeBatchKey := strings.Repeat("c", 64)
	if err := store.PutRuntimeLogBatch(
		ctx,
		runtimeBatchKey,
		[]application.RuntimeLogRecord{{
			Fields: map[string]string{
				"schema":             "runtime-observability/v1",
				"occurredAt":         now.Format(time.RFC3339Nano),
				"logKind":            "error",
				"severity":           "error",
				"signal":             "app.runtime_exception",
				"message":            "redacted failure",
				"resourceSourceType": "app",
				"resourceService":    "quwoquan_app",
				"resourceAppVersion": "1.0.0",
			},
			BatchKey:   runtimeBatchKey,
			BatchIndex: 0,
			IngestedAt: now.Add(2 * time.Second),
		}},
	); err != nil {
		t.Fatalf("PutRuntimeLogBatch() error = %v", err)
	}
	complete, err = store.HasRuntimeLogBatch(ctx, runtimeBatchKey, 1)
	if err != nil || !complete {
		t.Fatalf("HasRuntimeLogBatch() = %v, %v; want true, nil", complete, err)
	}
	if got := harness.documentCount("runtime-diagnostics-raw"); got != 1 {
		t.Fatalf("runtime raw documents = %d; want 1", got)
	}
	if got := harness.documentCount("app-product-telemetry-hourly"); got != 2 {
		t.Fatalf("combined rollup documents = %d; want 2", got)
	}
}

func TestElasticsearchLogSinkProvidesAllReadPortsAndMasksSensitiveFields(
	t *testing.T,
) {
	t.Parallel()
	now := time.Now().UTC().Truncate(time.Second)
	harness := newElasticsearchHarness(
		func(path string, body []byte) ([]byte, int) {
			return elasticsearchReadFixture(t, now, path, body), http.StatusOK
		},
	)
	server := httptest.NewServer(harness)
	t.Cleanup(server.Close)
	store := newTestElasticsearchStore(t, server.URL)
	ctx := context.Background()
	from := now.Add(-2 * time.Hour)
	to := now.Add(time.Minute)

	eventSummary, err := store.GetEventSummary(ctx, application.EventSummaryQuery{
		EventType: "chat_interaction_outcome",
		From:      from,
		To:        to,
	})
	if err != nil {
		t.Fatalf("GetEventSummary() error = %v", err)
	}
	if eventSummary.TotalCount != 3 ||
		eventSummary.SessionCount != 2 ||
		eventSummary.DimensionCounters["eventType"]["chat_interaction_outcome"] != 3 ||
		eventSummary.SourceKind != "hourly_rollup" {
		t.Fatalf("GetEventSummary() = %+v", eventSummary)
	}

	runtimeSummary, err := store.GetRuntimeLogSummary(
		ctx,
		application.RuntimeLogSummaryQuery{
			Signal: "app.runtime_exception",
			From:   from,
			To:     to,
		},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogSummary() error = %v", err)
	}
	if runtimeSummary.TotalCount != 2 ||
		runtimeSummary.DimensionCounters["signal"]["app.runtime_exception"] != 2 {
		t.Fatalf("GetRuntimeLogSummary() = %+v", runtimeSummary)
	}

	eventDrilldown, err := store.GetEventDrilldown(
		ctx,
		application.EventDrilldownQuery{From: from, To: to, Limit: 10},
	)
	if err != nil {
		t.Fatalf("GetEventDrilldown() error = %v", err)
	}
	if len(eventDrilldown.Items) != 1 ||
		eventDrilldown.Items[0].SessionID == "s.c2Vuc2l0aXZl.1" ||
		eventDrilldown.Items[0].SessionID == "" {
		t.Fatalf("GetEventDrilldown() did not mask session: %+v", eventDrilldown)
	}

	runtimeDrilldown, err := store.GetRuntimeLogDrilldown(
		ctx,
		application.RuntimeLogDrilldownQuery{
			From:            from,
			To:              to,
			Limit:           10,
			ActorHash:       "actor-hash",
			MessageContains: "failure",
		},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogDrilldown() error = %v", err)
	}
	if len(runtimeDrilldown.Items) != 1 ||
		len(runtimeDrilldown.Items[0].Correlation) != 0 {
		t.Fatalf(
			"GetRuntimeLogDrilldown() leaked correlation: %+v",
			runtimeDrilldown,
		)
	}

	pageStats, err := store.GetPageExperienceStats(
		ctx,
		application.PageExperienceQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetPageExperienceStats() error = %v", err)
	}
	if len(pageStats) != 1 ||
		pageStats[0].PageName != "chat_detail" ||
		pageStats[0].Opens != 2 ||
		pageStats[0].ReadySamples != 1 {
		t.Fatalf("GetPageExperienceStats() = %+v", pageStats)
	}

	sessions, totalEvents, err := store.ListDistinctSessions(ctx, from, to, 100)
	if err != nil {
		t.Fatalf("ListDistinctSessions() error = %v", err)
	}
	if totalEvents != 3 || len(sessions) != 2 {
		t.Fatalf(
			"ListDistinctSessions() = %v, %d; want two sessions and three events",
			sessions,
			totalEvents,
		)
	}

	rtcSummary, err := store.ReadRtcMediaQoeSummary(
		ctx,
		application.RtcMediaQoeSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("ReadRtcMediaQoeSummary() error = %v", err)
	}
	if rtcSummary.EffectiveSampleCount != 2 ||
		rtcSummary.MediaConnectedCount != 1 ||
		rtcSummary.ConnectionLostCount != 1 ||
		rtcSummary.ConnectP95MS == nil ||
		*rtcSummary.ConnectP95MS != 180 {
		t.Fatalf("ReadRtcMediaQoeSummary() = %+v", rtcSummary)
	}
}

func TestElasticsearchLogSinkRepairsPendingPartialRawBatch(t *testing.T) {
	t.Parallel()
	harness := newElasticsearchHarness(nil)
	server := httptest.NewServer(harness)
	t.Cleanup(server.Close)
	store := newTestElasticsearchStore(t, server.URL)
	now := time.Now().UTC().Add(-time.Minute)
	batchKey := strings.Repeat("f", 64)
	input := validEvent("page_open", "event", now)
	record := application.EventRecord{
		EventRecordInput: input,
		BatchKey:         batchKey,
		BatchIndex:       0,
		IngestedAt:       now,
	}
	if err := store.PutEventBatch(
		context.Background(),
		batchKey,
		[]application.EventRecord{record},
	); err != nil {
		t.Fatalf("seed PutEventBatch() error = %v", err)
	}
	harness.deleteFirstDocument("app-product-telemetry-raw")

	ledger := &pendingRepairLedger{}
	service := application.NewTelemetryService(
		telemetrypersistence.NewMemoryTelemetryStore(),
		store,
		ledger,
	)
	ack, err := service.ReportEventBatch(
		context.Background(),
		batchKey,
		[]application.EventRecordInput{input},
	)
	if err != nil {
		t.Fatalf("ReportEventBatch() repair error = %v", err)
	}
	if !ack.DuplicateBatch || ack.AcceptedCount != 1 || !ledger.accepted {
		t.Fatalf("ReportEventBatch() repair ack=%+v ledger=%+v", ack, ledger)
	}
	complete, err := store.HasEventBatch(context.Background(), batchKey, 1)
	if err != nil || !complete {
		t.Fatalf("HasEventBatch() after pending repair = %v, %v", complete, err)
	}
}

type pendingRepairLedger struct {
	accepted bool
}

func (l *pendingRepairLedger) Begin(
	context.Context,
	string,
	int,
) (application.BatchLedgerState, error) {
	return application.BatchLedgerPending, nil
}

func (l *pendingRepairLedger) MarkAccepted(
	_ context.Context,
	_ string,
	_ int,
) error {
	l.accepted = true
	return nil
}

func newTestElasticsearchStore(
	t *testing.T,
	endpoint string,
) *telemetrypersistence.ElasticsearchEventLogStore {
	t.Helper()
	store, err := telemetrypersistence.NewElasticsearchEventLogStore(
		telemetrypersistence.ElasticsearchConfig{
			Endpoint:               endpoint,
			RawIndex:               "app-product-telemetry-raw",
			StartupDiagnosticIndex: "app-startup-diagnostic-raw",
			RuntimeLogIndex:        "runtime-diagnostics-raw",
			AggregateIndex:         "app-product-telemetry-hourly",
			Timeout:                time.Second,
		},
	)
	if err != nil {
		t.Fatalf("NewElasticsearchEventLogStore() error = %v", err)
	}
	return store
}

type elasticsearchHarness struct {
	mu               sync.Mutex
	indices          map[string]bool
	documentsByIndex map[string]map[string]map[string]any
	search           func(path string, body []byte) ([]byte, int)
}

func newElasticsearchHarness(
	search func(path string, body []byte) ([]byte, int),
) *elasticsearchHarness {
	return &elasticsearchHarness{
		indices:          map[string]bool{},
		documentsByIndex: map[string]map[string]map[string]any{},
		search:           search,
	}
}

func (h *elasticsearchHarness) ServeHTTP(
	writer http.ResponseWriter,
	request *http.Request,
) {
	body, _ := io.ReadAll(request.Body)
	if request.Method == http.MethodHead {
		h.mu.Lock()
		exists := h.indices[strings.Trim(request.URL.Path, "/")]
		h.mu.Unlock()
		if !exists {
			writer.WriteHeader(http.StatusNotFound)
			return
		}
		writer.WriteHeader(http.StatusOK)
		return
	}
	if request.Method == http.MethodPut {
		index := strings.Split(strings.Trim(request.URL.Path, "/"), "/")[0]
		h.mu.Lock()
		h.indices[index] = true
		h.mu.Unlock()
		writeJSON(writer, http.StatusOK, map[string]any{"acknowledged": true})
		return
	}
	switch {
	case request.URL.Path == "/_bulk":
		h.handleBulk(writer, body)
	case strings.HasSuffix(request.URL.Path, "/_mget"):
		h.handleMGet(writer, request.URL.Path, body)
	case strings.HasSuffix(request.URL.Path, "/_search") &&
		bytes.Contains(body, []byte(`"ids"`)):
		h.handleIDSearch(writer, request.URL.Path, body)
	case strings.HasSuffix(request.URL.Path, "/_search") && h.search != nil:
		payload, status := h.search(request.URL.Path, body)
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(status)
		_, _ = writer.Write(payload)
	default:
		writeJSON(writer, http.StatusOK, map[string]any{"status": "yellow"})
	}
}

func (h *elasticsearchHarness) handleBulk(
	writer http.ResponseWriter,
	body []byte,
) {
	scanner := bufio.NewScanner(bytes.NewReader(body))
	items := make([]any, 0)
	h.mu.Lock()
	defer h.mu.Unlock()
	for scanner.Scan() {
		var metadata struct {
			Index struct {
				Index string `json:"_index"`
				ID    string `json:"_id"`
			} `json:"index"`
		}
		if err := json.Unmarshal(scanner.Bytes(), &metadata); err != nil ||
			!scanner.Scan() {
			writeJSON(writer, http.StatusBadRequest, map[string]any{"error": "invalid bulk"})
			return
		}
		var source map[string]any
		if err := json.Unmarshal(scanner.Bytes(), &source); err != nil {
			writeJSON(writer, http.StatusBadRequest, map[string]any{"error": "invalid source"})
			return
		}
		if h.documentsByIndex[metadata.Index.Index] == nil {
			h.documentsByIndex[metadata.Index.Index] = map[string]map[string]any{}
		}
		h.documentsByIndex[metadata.Index.Index][metadata.Index.ID] = source
		items = append(items, map[string]any{
			"index": map[string]any{"status": http.StatusCreated},
		})
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"errors": false,
		"items":  items,
	})
}

func (h *elasticsearchHarness) handleMGet(
	writer http.ResponseWriter,
	path string,
	body []byte,
) {
	index := strings.Split(strings.Trim(path, "/"), "/")[0]
	var input struct {
		IDs []string `json:"ids"`
	}
	_ = json.Unmarshal(body, &input)
	h.mu.Lock()
	defer h.mu.Unlock()
	docs := make([]any, 0, len(input.IDs))
	for _, id := range input.IDs {
		source, found := h.documentsByIndex[index][id]
		docs = append(docs, map[string]any{
			"_id":     id,
			"found":   found,
			"_source": source,
		})
	}
	writeJSON(writer, http.StatusOK, map[string]any{"docs": docs})
}

func (h *elasticsearchHarness) handleIDSearch(
	writer http.ResponseWriter,
	requestPath string,
	body []byte,
) {
	indexPattern := strings.Split(strings.Trim(requestPath, "/"), "/")[0]
	var input struct {
		Query struct {
			IDs struct {
				Values []string `json:"values"`
			} `json:"ids"`
		} `json:"query"`
	}
	_ = json.Unmarshal(body, &input)
	requested := make(map[string]struct{}, len(input.Query.IDs.Values))
	for _, id := range input.Query.IDs.Values {
		requested[id] = struct{}{}
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	hits := make([]any, 0, len(requested))
	for index, documents := range h.documentsByIndex {
		if !matchesElasticsearchIndexPattern(index, indexPattern) {
			continue
		}
		for id, source := range documents {
			if _, selected := requested[id]; !selected {
				continue
			}
			hits = append(hits, map[string]any{
				"_id":     id,
				"_source": source,
			})
		}
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"hits": map[string]any{
			"total": map[string]any{"value": len(hits)},
			"hits":  hits,
		},
	})
}

func (h *elasticsearchHarness) document(
	index string,
	id string,
) map[string]any {
	h.mu.Lock()
	defer h.mu.Unlock()
	for candidate, documents := range h.documentsByIndex {
		if matchesElasticsearchIndexPattern(candidate, index) {
			if document := documents[id]; document != nil {
				return document
			}
		}
	}
	return nil
}

func (h *elasticsearchHarness) documents(index string) []map[string]any {
	h.mu.Lock()
	defer h.mu.Unlock()
	out := make([]map[string]any, 0)
	for candidate, documents := range h.documentsByIndex {
		if !matchesElasticsearchIndexPattern(candidate, index) {
			continue
		}
		for _, document := range documents {
			out = append(out, document)
		}
	}
	return out
}

func (h *elasticsearchHarness) documentCount(index string) int {
	h.mu.Lock()
	defer h.mu.Unlock()
	count := 0
	for candidate, documents := range h.documentsByIndex {
		if matchesElasticsearchIndexPattern(candidate, index) {
			count += len(documents)
		}
	}
	return count
}

func (h *elasticsearchHarness) deleteFirstDocument(index string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	for candidate, documents := range h.documentsByIndex {
		if !matchesElasticsearchIndexPattern(candidate, index) {
			continue
		}
		for id := range documents {
			delete(documents, id)
			return
		}
	}
}

func matchesElasticsearchIndexPattern(index string, pattern string) bool {
	prefix := strings.TrimSuffix(pattern, "*")
	if strings.HasSuffix(pattern, "*") {
		return strings.HasPrefix(index, prefix)
	}
	return index == pattern || strings.HasPrefix(index, pattern+"-")
}

func elasticsearchReadFixture(
	t *testing.T,
	now time.Time,
	path string,
	body []byte,
) []byte {
	t.Helper()
	generatedThrough := now.Add(-time.Second).Format(time.RFC3339Nano)
	switch {
	case strings.Contains(string(body), `"rowKind":"event_dimensions"`):
		return summaryFixture(
			generatedThrough,
			3,
			2,
			[]string{
				"logType",
				"eventType",
				"pageName",
				"appVersion",
				"networkClass",
				"deviceManufacturer",
				"deviceModel",
				"journey",
				"action",
				"result",
				"errorCode",
			},
			map[string]string{
				"logType":   "event",
				"eventType": "chat_interaction_outcome",
			},
		)
	case strings.Contains(string(body), `"rowKind":"runtime_diagnostics"`):
		return summaryFixture(
			generatedThrough,
			2,
			0,
			[]string{
				"logKind",
				"severity",
				"signal",
				"errorCode",
				"fingerprint",
				"resourceSourceType",
				"resourceService",
				"resourceAppVersion",
			},
			map[string]string{"signal": "app.runtime_exception"},
		)
	case strings.Contains(string(body), `"rtc_media_qoe"`):
		return mustJSON(t, map[string]any{
			"hits": map[string]any{"total": map[string]any{"value": 2}, "hits": []any{}},
			"aggregations": map[string]any{
				"connected":         rtcConnectedFixture(1, 1, 180),
				"reconnect":         map[string]any{"value": 2},
				"generated_through": maxDateFixture(generatedThrough),
				"hourly": map[string]any{"buckets": []any{
					map[string]any{
						"key":               now.Add(-time.Hour).Truncate(time.Hour).UnixMilli(),
						"doc_count":         2,
						"connected":         rtcConnectedFixture(1, 1, 180),
						"reconnect":         map[string]any{"value": 2},
						"generated_through": maxDateFixture(generatedThrough),
					},
				}},
			},
		})
	case strings.Contains(string(body), `"pages"`):
		return mustJSON(t, map[string]any{
			"aggregations": map[string]any{
				"pages": map[string]any{"buckets": []any{
					map[string]any{
						"key": "chat_detail",
						"opens": map[string]any{
							"doc_count":     2,
							"avg_ready":     map[string]any{"value": 120},
							"ready_samples": map[string]any{"doc_count": 1},
						},
						"stays": map[string]any{
							"doc_count": 1,
							"avg_stay":  map[string]any{"value": 400},
						},
						"runtime_errors": map[string]any{"doc_count": 1},
					},
				}},
			},
		})
	case strings.Contains(string(body), `"composite"`):
		return mustJSON(t, map[string]any{
			"hits": map[string]any{"total": map[string]any{"value": 3}, "hits": []any{}},
			"aggregations": map[string]any{
				"sessions": map[string]any{"buckets": []any{
					map[string]any{"key": map[string]any{"sessionId": "s.a.1"}},
					map[string]any{"key": map[string]any{"sessionId": "s.b.1"}},
				}},
			},
		})
	case strings.Contains(path, "runtime-diagnostics-raw"):
		return mustJSON(t, map[string]any{
			"hits": map[string]any{
				"total": map[string]any{"value": 1},
				"hits": []any{map[string]any{"_source": map[string]any{
					"_batchKey":          strings.Repeat("d", 64),
					"_batchIndex":        0,
					"occurredAt":         now.Add(-time.Minute).Format(time.RFC3339Nano),
					"observedAt":         now.Format(time.RFC3339Nano),
					"ingestedAt":         generatedThrough,
					"logKind":            "error",
					"severity":           "error",
					"signal":             "app.runtime_exception",
					"message":            "redacted failure",
					"requestId":          "sensitive-request",
					"resourceSourceType": "app",
					"resourceService":    "quwoquan_app",
				}}},
			},
		})
	default:
		return mustJSON(t, map[string]any{
			"hits": map[string]any{
				"total": map[string]any{"value": 1},
				"hits": []any{map[string]any{"_source": map[string]any{
					"_batchKey":      strings.Repeat("e", 64),
					"_batchIndex":    0,
					"logType":        "event",
					"eventType":      "chat_interaction_outcome",
					"sessionId":      "s.c2Vuc2l0aXZl.1",
					"pageName":       "chat_detail",
					"occurredAt":     now.Add(-time.Minute).Format(time.RFC3339Nano),
					"ingestedAt":     generatedThrough,
					"appVersion":     "1.0.0",
					"networkClass":   "wifi",
					"devicePlatform": "ios",
				}}},
			},
		})
	}
}

func summaryFixture(
	generatedThrough string,
	total float64,
	sessions float64,
	dimensions []string,
	values map[string]string,
) []byte {
	aggregations := map[string]any{
		"total_count":       map[string]any{"value": total},
		"session_count":     map[string]any{"value": sessions},
		"generated_through": maxDateFixture(generatedThrough),
	}
	for _, dimension := range dimensions {
		buckets := []any{}
		if value := values[dimension]; value != "" {
			buckets = append(buckets, map[string]any{
				"key":            value,
				"weighted_count": map[string]any{"value": total},
			})
		}
		aggregations["dimension_"+dimension] = map[string]any{"buckets": buckets}
	}
	payload, _ := json.Marshal(map[string]any{"aggregations": aggregations})
	return payload
}

func rtcConnectedFixture(connected, lost int64, p95 float64) map[string]any {
	return map[string]any{
		"doc_count": connected,
		"connect_p95": map[string]any{
			"values": map[string]any{"95.0": p95},
		},
		"connection_lost": map[string]any{"doc_count": lost},
	}
}

func maxDateFixture(value string) map[string]any {
	return map[string]any{
		"value":           float64(time.Now().UnixMilli()),
		"value_as_string": value,
	}
}

func mustJSON(t *testing.T, value any) []byte {
	t.Helper()
	payload, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	return payload
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
