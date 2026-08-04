// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	eventhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestStartupTelemetryHTTPAcceptsOneStrictTypedBatchAndReplaysReceipt(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	service := eventapp.NewTelemetryService(store, store)
	accepted := 0
	mux := http.NewServeMux()
	eventhttp.NewStartupTelemetryHandler(
		service,
		func(event eventhttp.StartupTelemetryEventInput) {
			accepted++
			if event.Phase != "terminal" {
				t.Fatalf("accepted phase = %q", event.Phase)
			}
		},
	).Register(mux)
	body := []byte(`{"events":[{"eventId":"attempt_1234567890123456_1","attemptId":"attempt_1234567890123456","sequence":1,"phase":"terminal","phaseDurationMs":10,"elapsedMs":1000,"outcome":"success","occurredAt":"2026-07-28T00:00:00Z","platform":"android","runtimeEnv":"gamma","appVersion":"1.0.0","networkClass":"wifi","recoverySurface":"","failureCode":"","failureSource":"","deadlineOrigin":"android_process"}]}`)

	first := reportStartupTelemetry(t, mux, body, "proof_123456789012345678901234")
	if first.Code != http.StatusOK {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	var firstReceipt struct {
		AcceptedCount  int  `json:"acceptedCount"`
		DuplicateBatch bool `json:"duplicateBatch"`
	}
	if err := json.Unmarshal(first.Body.Bytes(), &firstReceipt); err != nil {
		t.Fatalf("decode first receipt: %v", err)
	}
	if firstReceipt.AcceptedCount != 1 || firstReceipt.DuplicateBatch {
		t.Fatalf("first receipt=%+v", firstReceipt)
	}

	replayed := reportStartupTelemetry(t, mux, body, "proof_123456789012345678901234")
	if replayed.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replayed.Code, replayed.Body.String())
	}
	var replayReceipt struct {
		AcceptedCount  int  `json:"acceptedCount"`
		DuplicateBatch bool `json:"duplicateBatch"`
	}
	if err := json.Unmarshal(replayed.Body.Bytes(), &replayReceipt); err != nil {
		t.Fatalf("decode replay receipt: %v", err)
	}
	if replayReceipt.AcceptedCount != 1 || !replayReceipt.DuplicateBatch {
		t.Fatalf("replay receipt=%+v", replayReceipt)
	}
	if accepted != 1 {
		t.Fatalf("accepted observer calls=%d; want one", accepted)
	}
}

func TestStartupTelemetryHTTPRejectsUnknownWireFieldAndMissingProof(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	mux := http.NewServeMux()
	eventhttp.NewStartupTelemetryHandler(
		eventapp.NewTelemetryService(store, store),
		nil,
	).Register(mux)

	unknown := reportStartupTelemetry(
		t,
		mux,
		[]byte(`{"events":[],"accountId":"must-not-be-accepted"}`),
		"proof_123456789012345678901234",
	)
	if unknown.Code != http.StatusBadRequest {
		t.Fatalf("unknown field status=%d body=%s", unknown.Code, unknown.Body.String())
	}

	missingProof := reportStartupTelemetry(t, mux, []byte(`{"events":[]}`), "")
	if missingProof.Code != http.StatusBadRequest {
		t.Fatalf("missing proof status=%d body=%s", missingProof.Code, missingProof.Body.String())
	}
}

func reportStartupTelemetry(
	t *testing.T,
	handler http.Handler,
	body []byte,
	proof string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/ops/startup-events", bytes.NewReader(body))
	if proof != "" {
		request.Header.Set("X-Qwq-Startup-Proof", proof)
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
