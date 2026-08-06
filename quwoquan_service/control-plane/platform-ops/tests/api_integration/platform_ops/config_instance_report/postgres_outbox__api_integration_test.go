// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006
// readiness_case: list-config-instance-reports-api
// readiness_case: report-config-instance-api
// readiness_case: list-release-candidate-acks-api
// readiness_case: list-runtime-services-api
// readiness_case: list-runtime-instances-api
// readiness_case: ingest-alertmanager-webhook-api
// readiness_case: list-active-alerts-api
// readiness_case: acknowledge-alert-api
// readiness_case: list-platform-audits-api
// readiness_case: list-platform-approvals-api
// readiness_case: get-platform-projection-summary-api
// readiness_case: get-platform-triage-summary-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	reporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportstore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
)

func TestConfigInstanceReportRealPostgresAtomicOutbox(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	fixture, err := testinfra.StartPostgresFixture(t.TempDir()+"/postgres", 0)
	if err != nil {
		t.Fatalf("start embedded PostgreSQL: %v", err)
	}
	t.Cleanup(func() { _ = fixture.Close() })
	pool, err := pgxpool.New(ctx, fixture.DSN())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	store, err := controlplanepersistence.NewPostgresStore(pool, "platform-ops")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	stateStore, err := reportstore.NewStateStore(store, store)
	if err != nil {
		t.Fatal(err)
	}
	desired := reportapp.DesiredHashReaderFunc(func(
		context.Context,
		string,
		string,
	) (string, error) {
		return "desired-real-postgres", nil
	})
	const candidate = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	handler, err := reporthttp.NewHandler(
		reportapp.NewCommandFacade(stateStore, desired, nil),
		reportapp.NewQueryFacade(stateStore),
		candidate,
	)
	if err != nil {
		t.Fatal(err)
	}
	body := `{"environment":"gamma","cluster":"gamma-control-a","service":"content-service","releaseManifestDigest":"` + candidate + `","effectiveHash":"desired-real-postgres","source":"release-package"}`
	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/control-plane/platform/configs/instances/content-service-gamma-control-a-0:report",
			bytes.NewBufferString(body),
		)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "service:content-service@gamma"},
		}))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt=%d status=%d body=%s", attempt, response.Code, response.Body.String())
		}
	}
	listResponse := httptest.NewRecorder()
	handler.ServeHTTP(
		listResponse,
		httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/instances", nil),
	)
	if listResponse.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listResponse.Code, listResponse.Body.String())
	}
	var listPayload struct {
		Items   []map[string]any `json:"items"`
		Summary map[string]any   `json:"summary"`
	}
	if err := json.Unmarshal(listResponse.Body.Bytes(), &listPayload); err != nil {
		t.Fatalf("decode list response: %v", err)
	}
	if len(listPayload.Items) != 1 || listPayload.Items[0]["instanceId"] != "content-service-gamma-control-a-0" {
		t.Fatalf("list items=%+v", listPayload.Items)
	}
	if listPayload.Summary["inSyncInstances"] != float64(1) || listPayload.Summary["outOfSyncInstances"] != float64(0) {
		t.Fatalf("list summary=%+v", listPayload.Summary)
	}
	var documents, workflows, audits, receipts, outbox int
	queries := []struct {
		query string
		value *int
	}{
		{`SELECT COUNT(*) FROM control_plane_documents WHERE scope='platform-ops' AND namespace='config_instance_reports'`, &documents},
		{`SELECT COUNT(*) FROM control_plane_workflows WHERE scope='platform-ops' AND object_type='config_instance_report'`, &workflows},
		{`SELECT COUNT(*) FROM control_plane_audits WHERE scope='platform-ops' AND object_type='config_instance_report'`, &audits},
		{`SELECT COUNT(*) FROM control_plane_mutation_receipts WHERE scope='platform-ops' AND object_type='config_instance_report'`, &receipts},
		{`SELECT COUNT(*) FROM platform_control_plane_outbox WHERE event_type='ConfigInstanceReported'`, &outbox},
	}
	for _, query := range queries {
		if err := pool.QueryRow(ctx, query.query).Scan(query.value); err != nil {
			t.Fatal(err)
		}
	}
	if documents != 1 || workflows != 1 || audits != 1 || receipts != 1 || outbox != 1 {
		t.Fatalf(
			"atomic packet documents=%d workflows=%d audits=%d receipts=%d outbox=%d",
			documents, workflows, audits, receipts, outbox,
		)
	}
	publisher := &capturingPublisher{}
	dispatcher, err := pgoutbox.NewDispatcher(pool, publisher, "platform_control_plane_outbox")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := dispatcher.DispatchOnce(ctx); err != nil {
		t.Fatal(err)
	}
	if publisher.Count() != 1 {
		t.Fatalf("published events=%d", publisher.Count())
	}
	if err := store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "config_instance_report", ObjectID: "content-service-gamma-control-a-0",
		Mode: "single", Actor: "operator-api", Decision: "approved", At: "2026-08-06T09:00:00Z",
	}); err != nil {
		t.Fatal(err)
	}
	topology := reportapp.RuntimeTopologyReaderFunc(func(context.Context) (reportapp.RuntimeTopology, error) {
		return reportapp.RuntimeTopology{
			Environments: map[string]reportapp.RuntimeTopologyEnvironment{
				"gamma": {Workloads: []reportapp.RuntimeTopologyWorkload{{
					ID: "content-service", Plane: "service",
					DeploymentRef: "quwoquan_service/services/content-service/environments/gamma/deploy",
				}}},
			},
			Targets: map[string]reportapp.RuntimeTopologyTarget{
				"gamma-local": {Environment: "gamma"},
			},
		}, nil
	})
	runtimeFacade, err := reportapp.NewRuntimeFacade(
		store,
		topology,
		candidate,
		func() time.Time { return time.Date(2026, 8, 6, 9, 30, 0, 0, time.UTC) },
	)
	if err != nil {
		t.Fatal(err)
	}
	runtimeHandler, err := reporthttp.NewRuntimeHandler(runtimeFacade)
	if err != nil {
		t.Fatal(err)
	}

	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/releases", "", nil), 1)
	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/topology/services", "", nil), 1)
	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/topology/instances", "", nil), 1)
	alertPayload := `{"version":"4","groupKey":"platform","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"ConfigDrift","severity":"critical","service":"content-service"},"annotations":{"summary":"drift"},"startsAt":"2026-08-06T09:00:00Z","fingerprint":"fp-postgres"}]}`
	if payload := servePostgresRuntimeJSON(t, runtimeHandler, http.MethodPost, "/control-plane/platform/alerts/ingest", alertPayload, nil); payload["ingested"] != float64(1) {
		t.Fatalf("ingest=%+v", payload)
	}
	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/alerts/active", "", nil), 1)
	principal := rtauth.Principal{Actor: operation.ActorContext{AccountID: "operator-api"}}
	if payload := servePostgresRuntimeJSON(t, runtimeHandler, http.MethodPost, "/control-plane/platform/alerts/fp-postgres:ack", "", &principal); payload["status"] != "acknowledged" {
		t.Fatalf("ack=%+v", payload)
	}
	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/audits", "", nil), 2)
	assertPostgresItemsCount(t, servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/approvals", "", nil), 1)
	if payload := servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/projections/summary", "", nil); payload["activeAlerts"] != float64(1) || payload["approvalCount"] != float64(1) {
		t.Fatalf("projection=%+v", payload)
	}
	if payload := servePostgresRuntimeJSON(t, runtimeHandler, http.MethodGet, "/control-plane/platform/triage/summary?env=gamma&cluster=gamma-control-a&service=content-service", "", nil); payload["runtimeReady"] != true || payload["source"] != "control-plane" {
		t.Fatalf("triage=%+v", payload)
	}
}

func servePostgresRuntimeJSON(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	principal *rtauth.Principal,
) map[string]any {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	request.Header.Set("X-Request-Id", "req-platform-postgres")
	request.Header.Set("X-Trace-Id", "trace-platform-postgres")
	if principal != nil {
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), *principal))
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("%s %s status=%d body=%s", method, path, response.Code, response.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("%s %s decode: %v", method, path, err)
	}
	return payload
}

func assertPostgresItemsCount(t *testing.T, payload map[string]any, expected int) {
	t.Helper()
	items, ok := payload["items"].([]any)
	if !ok || len(items) != expected {
		t.Fatalf("items=%+v expected=%d", payload["items"], expected)
	}
}

type capturingPublisher struct {
	mu     sync.Mutex
	events []runtimemessaging.DomainEvent
}

func (publisher *capturingPublisher) Publish(
	_ context.Context,
	event runtimemessaging.DomainEvent,
) error {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	publisher.events = append(publisher.events, event)
	return nil
}

func (publisher *capturingPublisher) Count() int {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	return len(publisher.events)
}
