package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	controlplanetest "quwoquan_service/runtime/controlplane/testsupport"
	rthealth "quwoquan_service/runtime/health"
	messaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func newTestProductService(t *testing.T) *productService {
	t.Helper()
	return newProductService(
		controlplanetest.NewFileStore(t.TempDir()+"/product-ops-state.json"),
		application.NewTelemetryService(telemetrypersistence.NewMemoryTelemetryStore(), nil),
		newTestExperimentFacade(t),
	)
}

func newTestProductServiceWithPublisher(t *testing.T, publisher messaging.EventPublisher) *productService {
	t.Helper()
	return newProductService(
		controlplanetest.NewFileStore(t.TempDir()+"/product-ops-state.json"),
		application.NewTelemetryService(telemetrypersistence.NewMemoryTelemetryStore(), nil),
		newTestExperimentFacade(t),
		publisher,
	)
}

type capturePublisher struct {
	events []messaging.DomainEvent
}

func (p *capturePublisher) Publish(_ context.Context, event messaging.DomainEvent) error {
	p.events = append(p.events, event)
	return nil
}

func newTestServerMux(service *productService) *http.ServeMux {
	return newServerMux(service, rthealth.NewChecker())
}

func withTestTelemetryPrincipal(request *http.Request) *http.Request {
	principal := rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "persona-test-telemetry"},
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

func newTelemetryBatchRequest(t *testing.T, events []map[string]any) *http.Request {
	t.Helper()
	body, err := json.Marshal(map[string]any{"events": events})
	if err != nil {
		t.Fatalf("marshal telemetry batch: %v", err)
	}
	canonical, err := canonicalJSON(body)
	if err != nil {
		t.Fatalf("canonicalize telemetry batch: %v", err)
	}
	digest := sha256.Sum256(canonical)
	request := httptest.NewRequest(http.MethodPost, "/ops/events", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", hex.EncodeToString(digest[:]))
	return withTestTelemetryPrincipal(request)
}

func telemetryEvent(eventType, logType string, occurredAt time.Time) map[string]any {
	return map[string]any{
		"logType":            logType,
		"eventType":          eventType,
		"sessionId":          "s.Z3Vlc3RfdGVzdA." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		"pageName":           "home",
		"occurredAt":         occurredAt.UTC().Format(time.RFC3339Nano),
		"deviceManufacturer": "Apple",
		"deviceModel":        "iPhone",
		"appVersion":         "1.0.0",
		"networkClass":       "wifi",
	}
}

func TestValidateRequiredRuntimeConfigRejectsMissingMongo(t *testing.T) {
	cfg := config{}
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "127.0.0.1:6379"

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "mongodb.uri is required") {
		t.Fatalf("expected missing mongodb uri failure, got %v", err)
	}
}

func TestValidateRequiredRuntimeConfigRejectsMissingRedisEndpoint(t *testing.T) {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "product_ops"
	cfg.Postgres.DSN = "postgres://quwoquan:quwoquan@127.0.0.1:5432/quwoquan?sslmode=disable"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	setTestSLSConfig(&cfg)

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "redis.general standalone addr is required") {
		t.Fatalf("expected missing redis endpoint failure, got %v", err)
	}
}

func setTestSLSConfig(cfg *config) {
	cfg.SLS.Region = "cn-hangzhou"
	cfg.SLS.Endpoint = "cn-hangzhou.log.aliyuncs.com"
	cfg.SLS.Project = "test-project"
	cfg.SLS.RawLogstore = "app-product-telemetry-raw"
	cfg.SLS.StartupDiagnosticLogstore = "app-startup-diagnostic-raw"
	cfg.SLS.AggregateLogstore = "app-product-telemetry-hourly"
	cfg.SLS.TimeoutMS = 1200
}

func TestValidateRequiredRuntimeConfigRejectsMissingPostgres(t *testing.T) {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "product_ops"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "127.0.0.1:6379"

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "postgres.dsn is required") {
		t.Fatalf("expected missing postgres dsn failure, got %v", err)
	}
}

func TestBuildRedisSceneConfigUsesClusterAddressOverride(t *testing.T) {
	scene, err := buildRedisSceneConfig("general", redisSceneCfg{
		Mode: "cluster",
		Addr: "redis-a:6379, redis-b:6379",
	})
	if err != nil {
		t.Fatalf("build cluster redis scene: %v", err)
	}
	if scene.Mode != "cluster" || len(scene.Addrs) != 2 || scene.Addr != "" {
		t.Fatalf("unexpected cluster redis scene: %+v", scene)
	}
}

func TestExperimentEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	assignReq := httptest.NewRequest(http.MethodPost, "/ops/experiments/discovery_feed_v3/assignment", nil)
	assignReq.Header.Set("Content-Type", "application/json")
	assignReq = withTestTelemetryPrincipal(assignReq)
	assignResp := httptest.NewRecorder()
	server.ServeHTTP(assignResp, assignReq)
	if assignResp.Code != http.StatusCreated {
		t.Fatalf("assign experiment status=%d body=%s", assignResp.Code, assignResp.Body.String())
	}

	var assignment map[string]any
	if err := json.Unmarshal(assignResp.Body.Bytes(), &assignment); err != nil {
		t.Fatalf("unmarshal assign response: %v", err)
	}
	if assignment["experimentId"] != "discovery_feed_v3" {
		t.Fatalf("unexpected experimentId: %v", assignment["experimentId"])
	}
	if assignment["subjectKey"] != "persona:persona-test-telemetry" {
		t.Fatalf("assignment subject must derive from verified persona: %v", assignment)
	}
	if assignment["variant"] == "" {
		t.Fatalf("variant should not be empty: %v", assignment)
	}
	assignedAt := assignment["assignedAt"]

	replayReq := httptest.NewRequest(http.MethodPost, "/ops/experiments/discovery_feed_v3/assignment", nil)
	replayReq.Header.Set("Content-Type", "application/json")
	replayReq = withTestTelemetryPrincipal(replayReq)
	replayResp := httptest.NewRecorder()
	server.ServeHTTP(replayResp, replayReq)
	if replayResp.Code != http.StatusOK {
		t.Fatalf("replay assignment status=%d body=%s", replayResp.Code, replayResp.Body.String())
	}
	var replayed map[string]any
	if err := json.Unmarshal(replayResp.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("unmarshal replay response: %v", err)
	}
	if replayed["id"] != assignment["id"] || replayed["assignedAt"] != assignedAt {
		t.Fatalf("idempotent replay changed immutable fact: first=%v replay=%v", assignment, replayed)
	}

	getReq := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/assignment", nil)
	getReq = withTestTelemetryPrincipal(getReq)
	getResp := httptest.NewRecorder()
	server.ServeHTTP(getResp, getReq)
	if getResp.Code != http.StatusOK {
		t.Fatalf("get assignment status=%d body=%s", getResp.Code, getResp.Body.String())
	}
	unauthorizedGet := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/assignment", nil)
	unauthorizedResp := httptest.NewRecorder()
	server.ServeHTTP(unauthorizedResp, unauthorizedGet)
	if unauthorizedResp.Code != http.StatusUnauthorized {
		t.Fatalf("assignment without verified actor status=%d body=%s", unauthorizedResp.Code, unauthorizedResp.Body.String())
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/stats", nil)
	statsResp := httptest.NewRecorder()
	server.ServeHTTP(statsResp, statsReq)
	if statsResp.Code != http.StatusOK {
		t.Fatalf("stats status=%d body=%s", statsResp.Code, statsResp.Body.String())
	}

	var stats map[string]any
	if err := json.Unmarshal(statsResp.Body.Bytes(), &stats); err != nil {
		t.Fatalf("unmarshal stats response: %v", err)
	}
	if stats["assignedSubjects"] != float64(1) {
		t.Fatalf("expected assignedSubjects=1, got %v", stats["assignedSubjects"])
	}
}

func TestVisitEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	for range 2 {
		recordReq := httptest.NewRequest(http.MethodPost, "/ops/visits", bytes.NewBufferString(`{"targetType":"page","targetKey":"platform-onboarding"}`))
		recordReq.Header.Set("Content-Type", "application/json")
		recordReq = withTestTelemetryPrincipal(recordReq)
		recordResp := httptest.NewRecorder()
		server.ServeHTTP(recordResp, recordReq)
		if recordResp.Code != http.StatusOK {
			t.Fatalf("record visit status=%d body=%s", recordResp.Code, recordResp.Body.String())
		}
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/ops/visits/stats?targetType=page&targetKey=platform-onboarding", nil)
	statsResp := httptest.NewRecorder()
	server.ServeHTTP(statsResp, statsReq)
	if statsResp.Code != http.StatusOK {
		t.Fatalf("visit stats status=%d body=%s", statsResp.Code, statsResp.Body.String())
	}

	var stats struct {
		TotalVisits float64 `json:"totalVisits"`
		Items       []struct {
			TargetKey  string `json:"targetKey"`
			VisitCount int    `json:"visitCount"`
		} `json:"items"`
	}
	if err := json.Unmarshal(statsResp.Body.Bytes(), &stats); err != nil {
		t.Fatalf("unmarshal visit stats response: %v", err)
	}
	if stats.TotalVisits != 2 {
		t.Fatalf("expected totalVisits=2, got %v", stats.TotalVisits)
	}
	if len(stats.Items) != 1 || stats.Items[0].VisitCount != 2 {
		t.Fatalf("unexpected visit items: %+v", stats.Items)
	}
}

func TestEventEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	occurredAt := time.Now().UTC().Add(-2 * time.Hour)
	pageOpen := telemetryEvent("page_open", "event", occurredAt)
	pageReturn := telemetryEvent("page_return", "event", occurredAt.Add(time.Second))
	pageOpen["networkClass"] = "5g"
	pageReturn["networkClass"] = "4g"
	pageReturn["durationMs"] = 1200
	req := newTelemetryBatchRequest(t, []map[string]any{pageOpen, pageReturn})
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("report events status=%d body=%s", resp.Code, resp.Body.String())
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/ops/events/summary?pageName=home&from="+occurredAt.Add(-time.Minute).Format(time.RFC3339Nano)+"&to="+occurredAt.Add(time.Hour).Format(time.RFC3339Nano), nil)
	summaryResp := httptest.NewRecorder()
	server.ServeHTTP(summaryResp, summaryReq)
	if summaryResp.Code != http.StatusOK {
		t.Fatalf("event summary status=%d body=%s", summaryResp.Code, summaryResp.Body.String())
	}
	var summary struct {
		TotalCount int64                       `json:"totalCount"`
		Dimensions map[string]map[string]int64 `json:"dimensions"`
	}
	if err := json.Unmarshal(summaryResp.Body.Bytes(), &summary); err != nil {
		t.Fatalf("unmarshal event summary: %v", err)
	}
	if summary.TotalCount != 2 {
		t.Fatalf("expected totalCount=2, got %d", summary.TotalCount)
	}
	if got := summary.Dimensions["pageName"]["home"]; got != 2 {
		t.Fatalf("expected pageName.home=2, got %d", got)
	}

	drilldownReq := httptest.NewRequest(http.MethodGet, "/ops/events/drilldown?eventType=page_return&from="+occurredAt.Add(-time.Minute).Format(time.RFC3339Nano)+"&to="+occurredAt.Add(time.Hour).Format(time.RFC3339Nano), nil)
	drilldownResp := httptest.NewRecorder()
	server.ServeHTTP(drilldownResp, drilldownReq)
	if drilldownResp.Code != http.StatusOK {
		t.Fatalf("event drilldown status=%d body=%s", drilldownResp.Code, drilldownResp.Body.String())
	}
	var drilldown struct {
		TotalCount int64 `json:"totalCount"`
		Items      []struct {
			RowKey    string `json:"rowKey"`
			EventType string `json:"eventType"`
			SessionID string `json:"sessionId"`
		} `json:"items"`
	}
	if err := json.Unmarshal(drilldownResp.Body.Bytes(), &drilldown); err != nil {
		t.Fatalf("unmarshal event drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 || drilldown.Items[0].EventType != "page_return" || drilldown.Items[0].RowKey == "" || !strings.Contains(drilldown.Items[0].SessionID, "***") {
		t.Fatalf("unexpected drilldown payload: %+v", drilldown)
	}

	removedVPN := telemetryEvent("page_open", "event", occurredAt)
	removedVPN["networkClass"] = "vpn"
	removedVPNReq := newTelemetryBatchRequest(t, []map[string]any{removedVPN})
	removedVPNResp := httptest.NewRecorder()
	server.ServeHTTP(removedVPNResp, removedVPNReq)
	if removedVPNResp.Code != http.StatusUnprocessableEntity {
		t.Fatalf(
			"removed networkClass vpn must be rejected, status=%d body=%s",
			removedVPNResp.Code,
			removedVPNResp.Body.String(),
		)
	}
}

func TestStartupTelemetryEndpointIsAnonymousRestrictedAndIdempotent(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	body := `{"events":[{"eventId":"startup_attempt_000001_1","attemptId":"startup_attempt_000001","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","deadlineOrigin":"android_process"}]}`

	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/ops/startup-events",
			bytes.NewBufferString(body),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000001")
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("startup telemetry status=%d body=%s", response.Code, response.Body.String())
		}
		var ack application.EventBatchAck
		if err := json.Unmarshal(response.Body.Bytes(), &ack); err != nil {
			t.Fatalf("decode startup telemetry ack: %v", err)
		}
		if attempt == 0 && ack.AcceptedCount != 1 {
			t.Fatalf("first startup telemetry ack=%+v", ack)
		}
		if attempt == 1 && !ack.DuplicateBatch {
			t.Fatalf("retry startup telemetry ack=%+v", ack)
		}
	}

	genericRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/events",
		bytes.NewBufferString(`{"events":[{"eventId":"generic-event","eventType":"experience","eventName":"page_open","eventVersion":"v1","priority":"normal","producer":"app","occurredAt":"2026-07-17T10:00:00Z"}]}`),
	)
	genericResponse := httptest.NewRecorder()
	server.ServeHTTP(genericResponse, genericRequest)
	if genericResponse.Code != http.StatusUnauthorized {
		t.Fatalf("generic telemetry must remain authenticated, got %d", genericResponse.Code)
	}
}

func TestStartupTelemetryEndpointRejectsUnknownAndPIILikeFields(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000001_1","attemptId":"startup_attempt_000001","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","userId":"must_not_be_accepted"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000002")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unknown/PII field must be rejected, got %d body=%s", response.Code, response.Body.String())
	}
	var invalidResponse struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &invalidResponse); err != nil {
		t.Fatalf("decode startup invalid response: %v", err)
	}
	if invalidResponse.Code != "OPS.USER.startup_event_invalid" {
		t.Fatalf("startup invalid response code=%q", invalidResponse.Code)
	}

	failureCodeRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000004_1","attemptId":"startup_attempt_000004","sequence":1,"phase":"recovery","phaseDurationMs":12,"elapsedMs":12,"outcome":"shown","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","failureCode":"token_like_diagnostic_must_not_escape"}]}`),
	)
	failureCodeRequest.Header.Set("Content-Type", "application/json")
	failureCodeRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000005",
	)
	failureCodeResponse := httptest.NewRecorder()
	server.ServeHTTP(failureCodeResponse, failureCodeRequest)
	if failureCodeResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"unallowlisted failure code must be rejected, got %d body=%s",
			failureCodeResponse.Code,
			failureCodeResponse.Body.String(),
		)
	}

	networkClassRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000005_1","attemptId":"startup_attempt_000005","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","networkClass":"user@example.com"}]}`),
	)
	networkClassRequest.Header.Set("Content-Type", "application/json")
	networkClassRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000006",
	)
	networkClassResponse := httptest.NewRecorder()
	server.ServeHTTP(networkClassResponse, networkClassRequest)
	if networkClassResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"unallowlisted network class must be rejected, got %d body=%s",
			networkClassResponse.Code,
			networkClassResponse.Body.String(),
		)
	}

	whitespaceLabelRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000006_1","attemptId":"startup_attempt_000006","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":" android ","runtimeEnv":"alpha"}]}`),
	)
	whitespaceLabelRequest.Header.Set("Content-Type", "application/json")
	whitespaceLabelRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000007",
	)
	whitespaceLabelResponse := httptest.NewRecorder()
	server.ServeHTTP(whitespaceLabelResponse, whitespaceLabelRequest)
	if whitespaceLabelResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"whitespace metric label must be rejected, got %d body=%s",
			whitespaceLabelResponse.Code,
			whitespaceLabelResponse.Body.String(),
		)
	}

	mismatchedEventIDRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000006_99","attemptId":"startup_attempt_000006","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha"}]}`),
	)
	mismatchedEventIDRequest.Header.Set("Content-Type", "application/json")
	mismatchedEventIDRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000007",
	)
	mismatchedEventIDResponse := httptest.NewRecorder()
	server.ServeHTTP(mismatchedEventIDResponse, mismatchedEventIDRequest)
	if mismatchedEventIDResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"eventId must be derived from attemptId and sequence, got %d body=%s",
			mismatchedEventIDResponse.Code,
			mismatchedEventIDResponse.Body.String(),
		)
	}
}

func TestStartupTelemetryEndpointRejectsUnboundedMetricLabels(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000002_1","attemptId":"startup_attempt_000002","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"attacker_controlled_label","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000003")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unbounded metric label must be rejected, got %d body=%s", response.Code, response.Body.String())
	}
}

func TestStartupTelemetryEndpointAcceptsBoundedJournalDropTerminal(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000003_3","attemptId":"startup_attempt_000003","sequence":3,"phase":"terminal","phaseDurationMs":0,"elapsedMs":120,"outcome":"journal_drop","occurredAt":"2026-07-17T10:00:00Z","platform":"web","runtimeEnv":"alpha","recoverySurface":"native_recovery","failureCode":"OPS.SYSTEM.startup_native_first_frame_timeout","failureSource":"native_watchdog","deadlineOrigin":"web_bootstrap"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000004")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("bounded journal_drop terminal must be accepted, got %d body=%s", response.Code, response.Body.String())
	}
}

func TestStartupTelemetryRateLimitCannotBeBypassedByChangingProof(t *testing.T) {
	limiter := newStartupTelemetryLimiter()
	now := time.Date(2026, time.July, 17, 10, 0, 0, 0, time.UTC)
	request := httptest.NewRequest(http.MethodPost, "/ops/startup-events", nil)
	request.RemoteAddr = "203.0.113.42:54321"

	if !limiter.allow(
		startupTelemetryRateLimitKey(request, "startup_proof_000000000101"),
		startupTelemetryMaxPerMinute,
		now,
	) {
		t.Fatal("first source window should be allowed")
	}
	if limiter.allow(
		startupTelemetryRateLimitKey(request, "startup_proof_000000000102"),
		1,
		now,
	) {
		t.Fatal("changing an untrusted proof must not bypass source rate limit")
	}
}

func TestControlPlaneWorkflowEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	reviewReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/moderation/cases/case_post_901:startReview", nil)
	reviewReq.Header.Set("X-Actor", "reviewer-1")
	reviewResp := httptest.NewRecorder()
	server.ServeHTTP(reviewResp, reviewReq)
	if reviewResp.Code != http.StatusOK {
		t.Fatalf("start review status=%d body=%s", reviewResp.Code, reviewResp.Body.String())
	}

	applyBody := bytes.NewBufferString(`{"action":"take_down","actor":"reviewer-1"}`)
	applyReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/moderation/cases/case_post_901:applyAction", applyBody)
	applyReq.Header.Set("Content-Type", "application/json")
	applyResp := httptest.NewRecorder()
	server.ServeHTTP(applyResp, applyReq)
	if applyResp.Code != http.StatusOK {
		t.Fatalf("apply action status=%d body=%s", applyResp.Code, applyResp.Body.String())
	}

	secondApplyBody := bytes.NewBufferString(`{"action":"take_down","actor":"reviewer-2"}`)
	secondApplyReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/moderation/cases/case_post_901:applyAction", secondApplyBody)
	secondApplyReq.Header.Set("Content-Type", "application/json")
	secondApplyResp := httptest.NewRecorder()
	server.ServeHTTP(secondApplyResp, secondApplyReq)
	if secondApplyResp.Code != http.StatusOK {
		t.Fatalf("second apply action status=%d body=%s", secondApplyResp.Code, secondApplyResp.Body.String())
	}

	recoveryBody := bytes.NewBufferString(`{"decision":"recovered","actor":"approver-1"}`)
	recoveryReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recovery/cases/recovery_user_1827:submitDecision", recoveryBody)
	recoveryReq.Header.Set("Content-Type", "application/json")
	recoveryResp := httptest.NewRecorder()
	server.ServeHTTP(recoveryResp, recoveryReq)
	if recoveryResp.Code != http.StatusOK {
		t.Fatalf("submit recovery decision status=%d body=%s", recoveryResp.Code, recoveryResp.Body.String())
	}

	policyReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/policies/policy_discovery_rank_v12:activate", nil)
	policyReq.Header.Set("X-Actor", "ops-approver")
	policyResp := httptest.NewRecorder()
	server.ServeHTTP(policyResp, policyReq)
	if policyResp.Code != http.StatusOK {
		t.Fatalf("activate recommendation policy status=%d body=%s", policyResp.Code, policyResp.Body.String())
	}

	appealBody := bytes.NewBufferString(`{"decision":"approved","actor":"appeal-reviewer"}`)
	appealReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/appeal/cases/appeal_case_301:submitDecision", appealBody)
	appealReq.Header.Set("Content-Type", "application/json")
	appealResp := httptest.NewRecorder()
	server.ServeHTTP(appealResp, appealReq)
	if appealResp.Code != http.StatusOK {
		t.Fatalf("submit appeal decision status=%d body=%s", appealResp.Code, appealResp.Body.String())
	}

	workflowReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/workflows", nil)
	workflowResp := httptest.NewRecorder()
	server.ServeHTTP(workflowResp, workflowReq)
	if workflowResp.Code != http.StatusOK {
		t.Fatalf("list workflows status=%d body=%s", workflowResp.Code, workflowResp.Body.String())
	}

	var workflowPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(workflowResp.Body.Bytes(), &workflowPayload); err != nil {
		t.Fatalf("unmarshal workflows: %v", err)
	}
	if len(workflowPayload.Items) == 0 {
		t.Fatalf("expected workflows to be populated")
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/audits", nil)
	auditResp := httptest.NewRecorder()
	server.ServeHTTP(auditResp, auditReq)
	if auditResp.Code != http.StatusOK {
		t.Fatalf("list audits status=%d body=%s", auditResp.Code, auditResp.Body.String())
	}

	var auditPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(auditResp.Body.Bytes(), &auditPayload); err != nil {
		t.Fatalf("unmarshal audits: %v", err)
	}
	if len(auditPayload.Items) < 3 {
		t.Fatalf("expected audit events, got %+v", auditPayload.Items)
	}

	approvalReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/approvals", nil)
	approvalResp := httptest.NewRecorder()
	server.ServeHTTP(approvalResp, approvalReq)
	if approvalResp.Code != http.StatusOK {
		t.Fatalf("list approvals status=%d body=%s", approvalResp.Code, approvalResp.Body.String())
	}

	var approvalPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(approvalResp.Body.Bytes(), &approvalPayload); err != nil {
		t.Fatalf("unmarshal approvals: %v", err)
	}
	if len(approvalPayload.Items) < 4 {
		t.Fatalf("expected approvals, got %+v", approvalPayload.Items)
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/projections/summary", nil)
	summaryResp := httptest.NewRecorder()
	server.ServeHTTP(summaryResp, summaryReq)
	if summaryResp.Code != http.StatusOK {
		t.Fatalf("projection summary status=%d body=%s", summaryResp.Code, summaryResp.Body.String())
	}

	var summaryPayload map[string]any
	if err := json.Unmarshal(summaryResp.Body.Bytes(), &summaryPayload); err != nil {
		t.Fatalf("unmarshal projection summary: %v", err)
	}
	if summaryPayload["workflowCount"] == nil || summaryPayload["approvalCount"] == nil {
		t.Fatalf("unexpected projection summary: %+v", summaryPayload)
	}
	if cards, ok := summaryPayload["l1l4Cards"].([]any); !ok || len(cards) == 0 {
		t.Fatalf("expected l1l4 cards, got %+v", summaryPayload["l1l4Cards"])
	}
}

func TestPremiumPoolControlPlaneEndpoints(t *testing.T) {
	publisher := &capturePublisher{}
	service := newTestProductServiceWithPublisher(t, publisher)
	server := newTestServerMux(service)
	expiresAt := time.Now().UTC().Add(24 * time.Hour).Format(time.RFC3339)

	invalidScopeReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/product/recommendation/premium-pool",
		bytes.NewBufferString(`{"contentId":"post_bad","scope":"circle","qualityScore":0.95,"qualityAdmission":"approved","auditId":"audit_bad","expiresAt":"`+expiresAt+`"}`),
	)
	invalidScopeResp := httptest.NewRecorder()
	server.ServeHTTP(invalidScopeResp, invalidScopeReq)
	if invalidScopeResp.Code != http.StatusBadRequest {
		t.Fatalf("circle scoped premium pool must be rejected, status=%d body=%s", invalidScopeResp.Code, invalidScopeResp.Body.String())
	}

	lowQualityReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/product/recommendation/premium-pool",
		bytes.NewBufferString(`{"contentId":"post_low","scope":"global","qualityScore":0.5,"qualityAdmission":"approved","auditId":"audit_low","expiresAt":"`+expiresAt+`"}`),
	)
	lowQualityResp := httptest.NewRecorder()
	server.ServeHTTP(lowQualityResp, lowQualityReq)
	if lowQualityResp.Code != http.StatusBadRequest {
		t.Fatalf("low quality premium pool must be rejected, status=%d body=%s", lowQualityResp.Code, lowQualityResp.Body.String())
	}

	createBody := `{"contentId":"post_premium_1","scope":"global","qualityScore":0.92,"qualityAdmission":"approved","supplySource":"data_engineering","sourceTaskId":"task_1","auditId":"audit_premium_1","rollbackToken":"rbk-premium-1","expiresAt":"` + expiresAt + `"}`
	createReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool", bytes.NewBufferString(createBody))
	createReq.Header.Set("X-Actor", "premium-editor")
	createResp := httptest.NewRecorder()
	server.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusOK {
		t.Fatalf("create premium pool status=%d body=%s", createResp.Code, createResp.Body.String())
	}
	var created premiumPoolEntry
	if err := json.Unmarshal(createResp.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal create response: %v", err)
	}
	if created.Scope != "global" || created.Status != "active" || created.RollbackToken == "" {
		t.Fatalf("premium entry missing commercial governance fields: %+v", created)
	}

	listReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/recommendation/premium-pool?activeOnly=true", nil)
	listResp := httptest.NewRecorder()
	server.ServeHTTP(listResp, listReq)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list premium pool status=%d body=%s", listResp.Code, listResp.Body.String())
	}
	var listPayload struct {
		Items []premiumPoolEntry `json:"items"`
	}
	if err := json.Unmarshal(listResp.Body.Bytes(), &listPayload); err != nil {
		t.Fatalf("unmarshal list response: %v", err)
	}
	if len(listPayload.Items) != 1 || listPayload.Items[0].ContentID != "post_premium_1" {
		t.Fatalf("expected active premium entry, got %+v", listPayload.Items)
	}

	rollbackReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_premium_1:rollback", nil)
	rollbackResp := httptest.NewRecorder()
	server.ServeHTTP(rollbackResp, rollbackReq)
	if rollbackResp.Code != http.StatusOK {
		t.Fatalf("rollback premium pool status=%d body=%s", rollbackResp.Code, rollbackResp.Body.String())
	}
	var rolledBack premiumPoolEntry
	if err := json.Unmarshal(rollbackResp.Body.Bytes(), &rolledBack); err != nil {
		t.Fatalf("unmarshal rollback response: %v", err)
	}
	if rolledBack.Status != "rolled_back" {
		t.Fatalf("rollback status=%q", rolledBack.Status)
	}

	createBody2 := `{"contentId":"post_premium_2","scope":"global","qualityScore":0.91,"qualityAdmission":"approved","auditId":"audit_premium_2","expiresAt":"` + expiresAt + `"}`
	createReq2 := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool", bytes.NewBufferString(createBody2))
	createResp2 := httptest.NewRecorder()
	server.ServeHTTP(createResp2, createReq2)
	if createResp2.Code != http.StatusOK {
		t.Fatalf("create second premium pool status=%d body=%s", createResp2.Code, createResp2.Body.String())
	}
	takedownReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_premium_2:takedown", nil)
	takedownResp := httptest.NewRecorder()
	server.ServeHTTP(takedownResp, takedownReq)
	if takedownResp.Code != http.StatusOK {
		t.Fatalf("takedown premium pool status=%d body=%s", takedownResp.Code, takedownResp.Body.String())
	}
	var ejected premiumPoolEntry
	if err := json.Unmarshal(takedownResp.Body.Bytes(), &ejected); err != nil {
		t.Fatalf("unmarshal takedown response: %v", err)
	}
	if !ejected.TakedownEjected || ejected.Status != "takedown_ejected" {
		t.Fatalf("takedown must eject premium entry, got %+v", ejected)
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/audits", nil)
	auditResp := httptest.NewRecorder()
	server.ServeHTTP(auditResp, auditReq)
	if auditResp.Code != http.StatusOK {
		t.Fatalf("audit status=%d body=%s", auditResp.Code, auditResp.Body.String())
	}
	var auditPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(auditResp.Body.Bytes(), &auditPayload); err != nil {
		t.Fatalf("unmarshal audits: %v", err)
	}
	if len(auditPayload.Items) < 4 {
		t.Fatalf("premium pool must audit create/rollback/takedown, got %+v", auditPayload.Items)
	}
	if got, want := premiumPoolEventTypes(publisher.events), []string{
		premiumPoolEntryUpsertedEvent,
		premiumPoolEntryRolledBackEvent,
		premiumPoolEntryUpsertedEvent,
		premiumPoolEntryTakedownEjectedEvent,
	}; !equalStrings(got, want) {
		t.Fatalf("premium pool events=%v want %v", got, want)
	}
	if sourceTaskID, _ := publisher.events[0].Payload["sourceTaskId"].(string); sourceTaskID != "task_1" {
		t.Fatalf("premium pool event must keep sourceTaskId for data-engineering attribution, payload=%+v", publisher.events[0].Payload)
	}
}

func premiumPoolEventTypes(events []messaging.DomainEvent) []string {
	out := make([]string, 0, len(events))
	for _, event := range events {
		out = append(out, event.Type)
	}
	return out
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestL1L4MetricsEndpoint(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	occurredAt := time.Now().UTC().Add(-2 * time.Hour)
	performance := telemetryEvent("performance_sample", "event", occurredAt)
	performance["operationId"] = "feed_first_content_ready"
	performance["durationMs"] = 1300
	errorEvent := telemetryEvent("runtime_exception", "error", occurredAt.Add(time.Second))
	errorEvent["errorCode"] = "OPS.SYSTEM.test_failure"
	recordReq := newTelemetryBatchRequest(t, []map[string]any{performance, errorEvent})
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record metrics events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/control-plane/product/metrics/l1l4?env=beta&level=L3", nil)
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("l1l4 metrics status=%d body=%s", resp.Code, resp.Body.String())
	}

	var payload struct {
		Source    string `json:"source"`
		Freshness string `json:"freshness"`
		Window    string `json:"window"`
		Coverage  struct {
			TotalMetrics    int `json:"totalMetrics"`
			LiveMetrics     int `json:"liveMetrics"`
			FallbackMetrics int `json:"fallbackMetrics"`
			EventSignals    int `json:"eventSignals"`
		} `json:"coverage"`
		Alerts []struct {
			ID           string `json:"id"`
			State        string `json:"state"`
			Metric       string `json:"metric"`
			Source       string `json:"source"`
			RunbookID    string `json:"runbookId"`
			RunbookRoute string `json:"runbookRoute"`
			RepairEntry  string `json:"repairEntry"`
			AlertID      string `json:"alertId"`
			Owner        string `json:"owner"`
		} `json:"alerts"`
		Items []struct {
			Level       string `json:"level"`
			Environment string `json:"environment"`
			Metric      string `json:"metric"`
			Source      string `json:"source"`
		} `json:"items"`
	}
	if err := json.Unmarshal(resp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal l1l4 metrics: %v", err)
	}
	if payload.Source == "" || payload.Freshness == "" || payload.Window == "" {
		t.Fatalf("expected live metadata, got %+v", payload)
	}
	if payload.Coverage.TotalMetrics == 0 {
		t.Fatalf("expected coverage totals, got %+v", payload.Coverage)
	}
	if len(payload.Items) == 0 {
		t.Fatalf("expected l1l4 metric items")
	}
	for _, item := range payload.Items {
		if item.Level != "L3" {
			t.Fatalf("expected only L3 items, got %+v", payload.Items)
		}
		if item.Environment != "beta" {
			t.Fatalf("expected beta environment, got %+v", payload.Items)
		}
		if item.Source == "" {
			t.Fatalf("expected metric source, got %+v", payload.Items)
		}
	}
	if len(payload.Alerts) == 0 {
		t.Fatalf("expected derived alerts, got %+v", payload)
	}
	if payload.Alerts[0].RunbookRoute == "" || payload.Alerts[0].RepairEntry == "" || payload.Alerts[0].AlertID == "" || payload.Alerts[0].Owner == "" {
		t.Fatalf("expected alert repair semantics, got %+v", payload.Alerts[0])
	}
}

func TestProductTriageSummaryEndpoint(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	occurredAt := time.Now().UTC().Add(-5 * time.Minute)
	pageOpen := telemetryEvent("page_open", "event", occurredAt)
	pageReturn := telemetryEvent("page_return", "event", occurredAt.Add(time.Second))
	pageReturn["durationMs"] = 1300
	recordReq := newTelemetryBatchRequest(t, []map[string]any{pageOpen, pageReturn})
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/control-plane/product/triage/summary?pageName=home", nil)
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("product triage summary status=%d body=%s", resp.Code, resp.Body.String())
	}

	var payload struct {
		EventSummary struct {
			TotalCount int `json:"totalCount"`
		} `json:"eventSummary"`
		RecentEvents []struct {
			RowKey   string `json:"rowKey"`
			PageName string `json:"pageName"`
		} `json:"recentEvents"`
		BacklogCandidates []struct {
			ID           string `json:"id"`
			Category     string `json:"category"`
			Title        string `json:"title"`
			NextAction   string `json:"nextAction"`
			RunbookRoute string `json:"runbookRoute"`
			RepairEntry  string `json:"repairEntry"`
			AlertID      string `json:"alertId"`
			AuditRoute   string `json:"auditRoute"`
		} `json:"backlogCandidates"`
		RuntimeReady bool   `json:"runtimeReady"`
		Source       string `json:"source"`
	}
	if err := json.Unmarshal(resp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal product triage summary: %v", err)
	}
	if payload.Source == "" {
		t.Fatalf("expected triage source, got %+v", payload)
	}
	if len(payload.RecentEvents) == 0 {
		t.Fatalf("expected recent events, got %+v", payload)
	}
	if payload.RecentEvents[0].RowKey == "" {
		t.Fatalf("recent events must use temporary row keys, got %+v", payload.RecentEvents)
	}
	if len(payload.BacklogCandidates) > 0 && (payload.BacklogCandidates[0].ID == "" || payload.BacklogCandidates[0].NextAction == "" || payload.BacklogCandidates[0].RunbookRoute == "" || payload.BacklogCandidates[0].RepairEntry == "" || payload.BacklogCandidates[0].AlertID == "" || payload.BacklogCandidates[0].AuditRoute == "") {
		t.Fatalf("expected backlog candidate details, got %+v", payload.BacklogCandidates[0])
	}
}
