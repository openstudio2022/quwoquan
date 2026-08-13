// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-003
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	eventrecord "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	httpadapter "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	recoveryfailure "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
)

func TestRecoveryFailureAcceptsOnlyTenFieldsAndSanitizes(t *testing.T) {
	reporter := &captureRecoveryReporter{}
	handler := httpadapter.NewHandler(recoveryfailure.NewService(reporter), writeTestError)
	mux := http.NewServeMux()
	handler.Register(mux)
	payload := recoveryPayload()
	payload["errorMessage"] = "authorization=secret user@example.com"
	payload["stackTrace"] = "at /Users/alice/app.dart https://quwoquan.com/p?token=secret"

	response := postRecoveryFailure(t, mux, payload)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if reporter.fields["errorMessage"] != "" {
		t.Fatal("internal runtime record must use message, not duplicate errorMessage")
	}
	combined := reporter.fields["message"] + reporter.fields["stackTrace"]
	for _, forbidden := range []string{"secret", "user@example.com", "/Users/alice", "token=secret"} {
		if strings.Contains(combined, forbidden) {
			t.Fatalf("sanitized record still contains %q: %s", forbidden, combined)
		}
	}
}

func TestRecoveryFailureRejectsUnknownOrOversizedFields(t *testing.T) {
	handler := httpadapter.NewHandler(
		recoveryfailure.NewService(&captureRecoveryReporter{}),
		writeTestError,
	)
	mux := http.NewServeMux()
	handler.Register(mux)

	withForbidden := recoveryPayload()
	withForbidden["startupAttemptId"] = "forbidden"
	if response := postRecoveryFailure(t, mux, withForbidden); response.Code != http.StatusBadRequest {
		t.Fatalf("unknown field status=%d body=%s", response.Code, response.Body.String())
	}

	oversized := recoveryPayload()
	oversized["stackTrace"] = strings.Repeat("x", 33<<10)
	if response := postRecoveryFailure(t, mux, oversized); response.Code != http.StatusBadRequest {
		t.Fatalf("oversized field status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestRecoveryFailureBoundaryEmitsCanonicalErrorCodes(t *testing.T) {
	reporter := &captureRecoveryReporter{}
	handler := httpadapter.NewHandler(recoveryfailure.NewService(reporter), writeTestError)
	mux := http.NewServeMux()
	handler.Register(mux)

	unknownField := recoveryPayload()
	unknownField["accountId"] = "must-not-be-accepted"
	invalid := postRecoveryFailure(t, mux, unknownField)
	assertRecoveryFailureErrorCode(
		t,
		invalid,
		http.StatusBadRequest,
		"OPS.USER.recovery_failure_invalid",
	)

	reporter.reportErr = errors.New("elasticsearch unavailable")
	unavailable := postRecoveryFailure(t, mux, recoveryPayload())
	assertRecoveryFailureErrorCode(
		t,
		unavailable,
		http.StatusServiceUnavailable,
		"OPS.SYSTEM.recovery_failure_unavailable",
	)
}

func assertRecoveryFailureErrorCode(
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

func recoveryPayload() map[string]any {
	return map[string]any{
		"occurredAt":   time.Now().UTC().Format(time.RFC3339Nano),
		"appVersion":   "1.8.2",
		"buildNumber":  "18201",
		"platform":     "android",
		"osVersion":    "15",
		"deviceModel":  "Pixel",
		"errorSource":  "flutter",
		"errorType":    "DatabaseOpenException",
		"errorMessage": "Failed to open local database",
		"stackTrace":   "Database.open database.dart:10",
	}
}

func postRecoveryFailure(t *testing.T, handler http.Handler, payload map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/ops/recovery-failures", bytes.NewReader(body))
	request.RemoteAddr = "192.0.2.1:1234"
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func writeTestError(
	w http.ResponseWriter,
	_ *http.Request,
	status int,
	userMessage string,
	_ string,
) {
	http.Error(w, userMessage, status)
}

type captureRecoveryReporter struct {
	batchKey  string
	fields    map[string]string
	reportErr error
}

func (r *captureRecoveryReporter) ReportRecoveryFailure(
	_ context.Context,
	batchKey string,
	fields map[string]string,
) (eventrecord.EventBatchAck, error) {
	if r.reportErr != nil {
		return eventrecord.EventBatchAck{}, r.reportErr
	}
	r.batchKey = batchKey
	r.fields = fields
	return eventrecord.EventBatchAck{AcceptedCount: 1}, nil
}
