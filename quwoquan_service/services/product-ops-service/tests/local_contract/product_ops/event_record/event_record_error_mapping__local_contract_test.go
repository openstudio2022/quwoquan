// EventRecord HTTP 边界的错误码契约：errors.yaml 声明的对象错误必须经
// runtime error envelope 以稳定 code 发射（含依赖失败 fail-closed 路径）。
//
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
package local_contract

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	controlplanetest "quwoquan_service/runtime/controlplane/testsupport"
	"quwoquan_service/runtime/operation"
	eventhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestReportEventBatchHTTPBoundaryMapsDeclaredErrorCodes(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	mux := http.NewServeMux()
	eventhttp.NewHandler(eventapp.NewTelemetryService(store, store), nil, nil).Register(mux)

	emptyBatch := []byte(`{"events":[]}`)
	invalidBatch := performEventReport(
		t, mux, emptyBatch,
		canonicalEventBodyDigest(t, emptyBatch),
	)
	assertEventRecordErrorCode(
		t,
		invalidBatch,
		http.StatusUnprocessableEntity,
		"OPS.USER.event_batch_invalid",
	)

	mismatchedKey := performEventReport(t, mux, emptyBatch, "not-the-canonical-digest")
	assertEventRecordErrorCode(
		t,
		mismatchedKey,
		http.StatusBadRequest,
		"OPS.USER.idempotency_key_invalid",
	)

	memory := eventpersistence.NewMemoryTelemetryStore()
	failingMux := http.NewServeMux()
	eventhttp.NewHandler(
		eventapp.NewTelemetryService(
			&failingPutEventStore{MemoryTelemetryStore: memory},
			memory,
		),
		nil,
		nil,
	).Register(failingMux)
	validBatch, err := json.Marshal(map[string]any{
		"events": []eventapp.EventRecordInput{
			validEvent("page_open", "event", time.Now().UTC().Add(-2*time.Minute)),
		},
	})
	if err != nil {
		t.Fatalf("marshal ReportEventBatch body: %v", err)
	}
	unavailable := performEventReport(
		t, failingMux, validBatch,
		canonicalEventBodyDigest(t, validBatch),
	)
	assertEventRecordErrorCode(
		t,
		unavailable,
		http.StatusServiceUnavailable,
		"OPS.SYSTEM.logstore_unavailable",
	)
}

func TestEventRecordQueryOperationsMapDeclaredErrorCodes(t *testing.T) {
	runtimeStore := eventpersistence.NewMemoryTelemetryStore()
	stateStore := failingWorkflowStateStore{
		StateStore: controlplanetest.NewFileStore(t.TempDir() + "/state.json"),
	}
	mux := newEventErrorMappingOperationsMux(t, runtimeStore, stateStore)

	invalidWindow := httptest.NewRequest(
		http.MethodGet,
		"/ops/events/summary?from=not-a-time",
		nil,
	)
	invalidWindowResponse := httptest.NewRecorder()
	mux.ServeHTTP(invalidWindowResponse, invalidWindow)
	assertEventRecordErrorCode(
		t,
		invalidWindowResponse,
		http.StatusBadRequest,
		"OPS.USER.query_window_invalid",
	)

	sensitiveDrilldown := httptest.NewRequest(
		http.MethodGet,
		"/ops/events/drilldown?sessionId=s.Z3Vlc3RfdGVzdA.1",
		nil,
	)
	sensitiveDrilldown = sensitiveDrilldown.WithContext(rtauth.WithPrincipal(
		sensitiveDrilldown.Context(),
		rtauth.Principal{Actor: operation.ActorContext{AccountID: "operator-plain"}},
	))
	forbiddenResponse := httptest.NewRecorder()
	mux.ServeHTTP(forbiddenResponse, sensitiveDrilldown)
	assertEventRecordErrorCode(
		t,
		forbiddenResponse,
		http.StatusForbidden,
		"OPS.USER.event_drilldown_forbidden",
	)

	projection := httptest.NewRequest(
		http.MethodGet,
		"/control-plane/product/workflows",
		nil,
	)
	projectionResponse := httptest.NewRecorder()
	mux.ServeHTTP(projectionResponse, projection)
	assertEventRecordErrorCode(
		t,
		projectionResponse,
		http.StatusServiceUnavailable,
		"OPS.SYSTEM.event_projection_unavailable",
	)
}

func TestReportRuntimeLogBatchStoreFailureMapsToRuntimeLogstoreUnavailable(t *testing.T) {
	runtimeStore := &failingRuntimeLogWriteStore{
		MemoryTelemetryStore: eventpersistence.NewMemoryTelemetryStore(),
	}
	mux := newEventErrorMappingOperationsMux(
		t,
		runtimeStore,
		controlplanetest.NewFileStore(t.TempDir()+"/state.json"),
	)

	body, err := json.Marshal(map[string]any{
		"records": []map[string]any{
			canonicalRuntimeOperationRecord(time.Now().UTC().Truncate(time.Second)),
		},
	})
	if err != nil {
		t.Fatalf("marshal ReportRuntimeLogBatch body: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/ops/runtime-logs", bytes.NewReader(body))
	request.Header.Set("Idempotency-Key", canonicalEventBodyDigest(t, body))
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{PersonaID: "persona-error-mapping"}},
	))
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	assertEventRecordErrorCode(
		t,
		response,
		http.StatusServiceUnavailable,
		"OPS.SYSTEM.runtime_logstore_unavailable",
	)
}

func newEventErrorMappingOperationsMux(
	t *testing.T,
	runtimeStore eventapp.RuntimeLogStore,
	stateStore controlplane.StateStore,
) *http.ServeMux {
	t.Helper()
	telemetryStore := eventpersistence.NewMemoryTelemetryStore()
	telemetry := eventapp.NewTelemetryService(telemetryStore, telemetryStore)
	handler := eventhttp.NewOperationsHandler(eventhttp.OperationsDependencies{
		Telemetry:       telemetry,
		RuntimeLogs:     eventapp.NewRuntimeLogService(runtimeStore, telemetryStore),
		RuntimeLogStore: runtimeStore,
		Growth: eventapp.NewGrowthService(
			eventpersistence.NewMemoryGrowthStore(),
			telemetryStore,
		),
		Metrics:      eventapp.NewMetricQueryService(telemetry, fixedPrometheusReader{}),
		ControlPlane: eventapp.NewControlPlaneQueryService(stateStore, telemetry, fixedVisitStore{}),
	})
	mux := http.NewServeMux()
	handler.Register(mux)
	return mux
}

func performEventReport(
	t *testing.T,
	handler http.Handler,
	body []byte,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/ops/events", bytes.NewReader(body))
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{PersonaID: "persona-error-mapping"}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

// canonicalEventBodyDigest 复算 HTTP 边界的 canonical body digest,
// 与 handler 侧 canonicalJSON + sha256 的幂等键口径一致。
func canonicalEventBodyDigest(t *testing.T, body []byte) string {
	t.Helper()
	var value any
	if err := json.Unmarshal(body, &value); err != nil {
		t.Fatalf("normalize request body: %v", err)
	}
	canonical, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("canonicalize request body: %v", err)
	}
	digest := sha256.Sum256(canonical)
	return hex.EncodeToString(digest[:])
}

func assertEventRecordErrorCode(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response %s: %v", recorder.Body.String(), err)
	}
	if response.Code != code {
		t.Fatalf("code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}

// failingRuntimeLogWriteStore 模拟诊断日志存储写入故障：写入恒失败且不可确认。
type failingRuntimeLogWriteStore struct {
	*eventpersistence.MemoryTelemetryStore
}

func (*failingRuntimeLogWriteStore) PutRuntimeLogBatch(
	context.Context,
	string,
	[]eventapp.RuntimeLogRecord,
) error {
	return errors.New("runtime logstore write failed")
}

func (*failingRuntimeLogWriteStore) HasRuntimeLogBatch(
	context.Context,
	string,
	int,
) (bool, error) {
	return false, nil
}

// failingWorkflowStateStore 模拟运营投影存储不可用：workflow 列表读取恒失败。
type failingWorkflowStateStore struct {
	controlplane.StateStore
}

func (failingWorkflowStateStore) ListWorkflows() ([]controlplane.WorkflowState, error) {
	return nil, errors.New("control plane projection store unavailable")
}
