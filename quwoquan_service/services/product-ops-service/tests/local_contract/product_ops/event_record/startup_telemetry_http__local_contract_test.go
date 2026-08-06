// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
// readiness_case: report-startup-event-batch-local
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
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

func TestStartupTelemetryHTTPAcceptsOnlyCanonicalRecoveryLifecycleMatrix(t *testing.T) {
	type recoveryCase struct {
		name          string
		lifecycle     string
		outcome       string
		action        string
		failureSource string
	}
	tests := []recoveryCase{
		{name: "enter", lifecycle: "enter", outcome: "entered", action: "none"},
		{name: "phase change", lifecycle: "phase_change", outcome: "observed", action: "none"},
		{name: "failure", lifecycle: "failure", outcome: "failed", action: "none", failureSource: "runtime_boundary"},
	}
	for _, outcome := range []string{"started", "success", "failed"} {
		for _, action := range []string{"open_update", "open_web", "external_return"} {
			tests = append(tests, recoveryCase{
				name:      "external action " + outcome + " " + action,
				lifecycle: "external_action",
				outcome:   outcome,
				action:    action,
			})
		}
		tests = append(tests, recoveryCase{
			name:      "runtime reentry " + outcome,
			lifecycle: "runtime_reentry",
			outcome:   outcome,
			action:    "runtime_reentry",
		})
	}
	for _, outcome := range []string{"success", "failed"} {
		tests = append(tests, recoveryCase{
			name:      "exit " + outcome,
			lifecycle: "exit",
			outcome:   outcome,
			action:    "none",
		})
	}
	for index, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			event := canonicalRecoveryTelemetryEvent(index + 1)
			event["recoveryLifecycle"] = test.lifecycle
			event["outcome"] = test.outcome
			event["recoveryAction"] = test.action
			if test.failureSource != "" {
				event["failureSource"] = test.failureSource
			}
			response := reportStartupTelemetry(
				t,
				newStartupTelemetryTestHandler(),
				startupTelemetryBody(t, event),
				"proof_123456789012345678901234",
			)
			if response.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestStartupTelemetryHTTPFailsClosedForRecoveryContractDrift(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{name: "recovery without lifecycle", mutate: func(event map[string]any) {
			delete(event, "recoveryLifecycle")
		}},
		{name: "startup with recovery lifecycle", mutate: func(event map[string]any) {
			event["phase"] = "terminal"
		}},
		{name: "legacy recovery surface", mutate: func(event map[string]any) {
			event["recoverySurface"] = "safe_recovery"
		}},
		{name: "route identity is forbidden", mutate: func(event map[string]any) {
			event["routeId"] = "home"
		}},
		{name: "missing fixed surface", mutate: func(event map[string]any) {
			delete(event, "recoverySurface")
		}},
		{name: "missing mount", mutate: func(event map[string]any) {
			delete(event, "recoveryMount")
		}},
		{name: "missing recovery phase", mutate: func(event map[string]any) {
			delete(event, "recoveryPhase")
		}},
		{name: "missing explicit action", mutate: func(event map[string]any) {
			delete(event, "recoveryAction")
		}},
		{name: "wrong enter outcome", mutate: func(event map[string]any) {
			event["outcome"] = "success"
		}},
		{name: "external action uses none", mutate: func(event map[string]any) {
			event["recoveryLifecycle"] = "external_action"
			event["outcome"] = "started"
		}},
		{name: "failure omits source", mutate: func(event map[string]any) {
			event["recoveryLifecycle"] = "failure"
			event["outcome"] = "failed"
			delete(event, "failureSource")
		}},
		{name: "unknown lifecycle", mutate: func(event map[string]any) {
			event["recoveryLifecycle"] = "background_retry"
		}},
		{name: "unknown mount", mutate: func(event map[string]any) {
			event["recoveryMount"] = "custom_mount"
		}},
		{name: "unknown recovery phase", mutate: func(event map[string]any) {
			event["recoveryPhase"] = "custom_phase"
		}},
		{name: "unknown action", mutate: func(event map[string]any) {
			event["recoveryAction"] = "retry"
		}},
	}
	for index, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			event := canonicalRecoveryTelemetryEvent(index + 1)
			test.mutate(event)
			response := reportStartupTelemetry(
				t,
				newStartupTelemetryTestHandler(),
				startupTelemetryBody(t, event),
				"proof_123456789012345678901234",
			)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestStartupTelemetryHTTPPreservesBoundedRecoveryDimensions(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	var accepted eventhttp.StartupTelemetryEventInput
	mux := http.NewServeMux()
	eventhttp.NewStartupTelemetryHandler(
		eventapp.NewTelemetryService(store, store),
		func(event eventhttp.StartupTelemetryEventInput) { accepted = event },
	).Register(mux)
	event := canonicalRecoveryTelemetryEvent(1)
	response := reportStartupTelemetry(
		t,
		mux,
		startupTelemetryBody(t, event),
		"proof_123456789012345678901234",
	)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if accepted.RecoverySurface != "page.app.startup_recovery" ||
		accepted.RecoveryLifecycle != "enter" || accepted.RecoveryMount != "bootstrap" ||
		accepted.RecoveryPhase != "startup_checking" || accepted.RecoveryAction != "none" {
		t.Fatalf("accepted recovery dimensions = %+v", accepted)
	}
}

func newStartupTelemetryTestHandler() http.Handler {
	store := eventpersistence.NewMemoryTelemetryStore()
	mux := http.NewServeMux()
	eventhttp.NewStartupTelemetryHandler(
		eventapp.NewTelemetryService(store, store),
		nil,
	).Register(mux)
	return mux
}

func canonicalRecoveryTelemetryEvent(sequence int) map[string]any {
	attemptID := "attempt_1234567890123456"
	return map[string]any{
		"eventId":           attemptID + "_" + strconv.Itoa(sequence),
		"attemptId":         attemptID,
		"sequence":          sequence,
		"phase":             "recovery",
		"phaseDurationMs":   10,
		"elapsedMs":         1000,
		"outcome":           "entered",
		"occurredAt":        "2026-07-28T00:00:00Z",
		"platform":          "android",
		"runtimeEnv":        "gamma",
		"recoverySurface":   "page.app.startup_recovery",
		"recoveryLifecycle": "enter",
		"recoveryMount":     "bootstrap",
		"recoveryPhase":     "startup_checking",
		"recoveryAction":    "none",
	}
}

func startupTelemetryBody(t *testing.T, event map[string]any) []byte {
	t.Helper()
	body, err := json.Marshal(map[string]any{"events": []map[string]any{event}})
	if err != nil {
		t.Fatalf("encode startup telemetry body: %v", err)
	}
	return body
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
