// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006
// readiness_case: list-config-instance-reports-local
// readiness_case: report-config-instance-local
// readiness_case: list-release-candidate-acks-local
// readiness_case: list-runtime-services-local
// readiness_case: list-runtime-instances-local
// readiness_case: ingest-alertmanager-webhook-local
// readiness_case: list-active-alerts-local
// readiness_case: acknowledge-alert-local
// readiness_case: list-platform-audits-local
// readiness_case: list-platform-approvals-local
// readiness_case: get-platform-projection-summary-local
// readiness_case: get-platform-triage-summary-local
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	reporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportstore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	"quwoquan_service/runtime/controlplane/testsupport"
	"quwoquan_service/runtime/operation"
)

func TestConfigInstanceReportCommitsAtomicObjectPacket(t *testing.T) {
	t.Parallel()
	path := t.TempDir() + "/platform-ops.json"
	store := testsupport.NewFileStore(path)
	stateStore, err := reportstore.NewStateStore(store, store)
	if err != nil {
		t.Fatal(err)
	}
	desired := reportapp.DesiredHashReaderFunc(func(
		context.Context,
		string,
		string,
	) (string, error) {
		return "desired-config-hash", nil
	})
	const candidate = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	handler, err := reporthttp.NewHandler(
		reportapp.NewCommandFacade(stateStore, desired, nil),
		reportapp.NewQueryFacade(stateStore),
		candidate,
	)
	if err != nil {
		t.Fatal(err)
	}
	requestBody := `{"environment":"beta","cluster":"beta-control-a","service":"content-service","releaseManifestDigest":"` + candidate + `","effectiveHash":"desired-config-hash","source":"release-package"}`
	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/control-plane/platform/configs/instances/content-service-beta-control-a-0:report",
			bytes.NewBufferString(requestBody),
		)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "service:content-service@beta"},
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
	if len(listPayload.Items) != 1 || listPayload.Items[0]["instanceId"] != "content-service-beta-control-a-0" {
		t.Fatalf("list items=%+v", listPayload.Items)
	}
	if listPayload.Summary["inSyncInstances"] != float64(1) || listPayload.Summary["outOfSyncInstances"] != float64(0) {
		t.Fatalf("list summary=%+v", listPayload.Summary)
	}
	if document, found, err := store.GetDocument(
		"config_instance_reports",
		"content-service-beta-control-a-0",
	); err != nil || !found || document["inSync"] != true {
		t.Fatalf("document found=%v value=%+v err=%v", found, document, err)
	}
	if workflow, found, err := store.GetWorkflow(
		"config_instance_report",
		"content-service-beta-control-a-0",
	); err != nil || !found || workflow.State != "in_sync" {
		t.Fatalf("workflow found=%v value=%+v err=%v", found, workflow, err)
	}
	audits, err := store.ListAudits()
	if err != nil || len(audits) != 1 {
		t.Fatalf("audits=%+v err=%v", audits, err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var state testsupport.FileState
	if err := json.Unmarshal(raw, &state); err != nil {
		t.Fatal(err)
	}
	if len(state.MutationReceipts) != 1 || len(state.MutationOutbox) != 1 {
		t.Fatalf("receipts=%d outbox=%d", len(state.MutationReceipts), len(state.MutationOutbox))
	}
	if state.MutationOutbox[0].EventType != "ConfigInstanceReported" {
		t.Fatalf("outbox=%+v", state.MutationOutbox)
	}
}

func TestConfigInstanceReportRuntimeOperationsUseObjectFacades(t *testing.T) {
	t.Parallel()
	store := testsupport.NewFileStore(t.TempDir() + "/platform-runtime.json")
	const candidate = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	if err := store.PutDocument("config_instance_reports", "content-service-beta-control-a-0", map[string]any{
		"id": "content-service-beta-control-a-0", "instanceId": "content-service-beta-control-a-0",
		"environment": "beta", "cluster": "beta-control-a", "service": "content-service",
		"configVersion": "config-current", "releaseManifestDigest": candidate,
		"desiredHash": "expected", "effectiveHash": "actual", "inSync": false,
		"source": "disk-fallback", "lastError": "stale", "updatedAt": "2026-08-06T08:00:00Z",
	}); err != nil {
		t.Fatal(err)
	}
	if err := store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "config_instance_report", ObjectID: "content-service-beta-control-a-0",
		Mode: "single", Actor: "operator-1", Decision: "approved", At: "2026-08-06T08:00:00Z",
	}); err != nil {
		t.Fatal(err)
	}
	topology := reportapp.RuntimeTopologyReaderFunc(func(context.Context) (reportapp.RuntimeTopology, error) {
		return reportapp.RuntimeTopology{
			Environments: map[string]reportapp.RuntimeTopologyEnvironment{
				"beta": {Workloads: []reportapp.RuntimeTopologyWorkload{{
					ID: "content-service", Plane: "service",
					DeploymentRef: "quwoquan_service/services/content-service/environments/beta/deploy",
				}}},
			},
			Targets: map[string]reportapp.RuntimeTopologyTarget{
				"beta-local": {Environment: "beta"},
			},
		}, nil
	})
	facade, err := reportapp.NewRuntimeFacade(
		store,
		topology,
		candidate,
		func() time.Time { return time.Date(2026, 8, 6, 8, 30, 0, 0, time.UTC) },
	)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := reporthttp.NewRuntimeHandler(facade)
	if err != nil {
		t.Fatal(err)
	}

	releases := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/releases", "", nil)
	assertItemsCount(t, releases, 1)
	services := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/topology/services", "", nil)
	assertItemsCount(t, services, 1)
	instances := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/topology/instances", "", nil)
	assertItemsCount(t, instances, 1)

	alertPayload := `{"version":"4","groupKey":"platform","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"ConfigDrift","severity":"critical","service":"content-service"},"annotations":{"summary":"drift"},"startsAt":"2026-08-06T08:00:00Z","fingerprint":"fp-config-drift"}]}`
	ingest := serveRuntimeJSON(t, handler, http.MethodPost, "/control-plane/platform/alerts/ingest", alertPayload, nil)
	if ingest["ingested"] != float64(1) {
		t.Fatalf("ingest=%+v", ingest)
	}
	active := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/alerts/active", "", nil)
	assertItemsCount(t, active, 1)
	principal := rtauth.Principal{Actor: operation.ActorContext{AccountID: "operator-1"}}
	ack := serveRuntimeJSON(t, handler, http.MethodPost, "/control-plane/platform/alerts/fp-config-drift:ack", "", &principal)
	if ack["status"] != "acknowledged" || ack["ackedBy"] != "operator-1" {
		t.Fatalf("ack=%+v", ack)
	}
	audits := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/audits", "", nil)
	assertItemsCount(t, audits, 1)
	approvals := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/approvals", "", nil)
	assertItemsCount(t, approvals, 1)
	projection := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/projections/summary", "", nil)
	if projection["activeAlerts"] != float64(1) || projection["auditCount"] != float64(1) {
		t.Fatalf("projection=%+v", projection)
	}
	triage := serveRuntimeJSON(t, handler, http.MethodGet, "/control-plane/platform/triage/summary?env=beta&cluster=beta-control-a&service=content-service", "", nil)
	if triage["runtimeReady"] != false || len(triage["backlogCandidates"].([]any)) == 0 {
		t.Fatalf("triage=%+v", triage)
	}
}

func serveRuntimeJSON(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	principal *rtauth.Principal,
) map[string]any {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	request.Header.Set("X-Request-Id", "req-platform-runtime")
	request.Header.Set("X-Trace-Id", "trace-platform-runtime")
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

func assertItemsCount(t *testing.T, payload map[string]any, expected int) {
	t.Helper()
	items, ok := payload["items"].([]any)
	if !ok || len(items) != expected {
		t.Fatalf("items=%+v expected=%d", payload["items"], expected)
	}
}
