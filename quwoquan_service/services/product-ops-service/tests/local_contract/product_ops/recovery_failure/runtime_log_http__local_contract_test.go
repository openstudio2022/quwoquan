// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
// readiness_case: report-recovery-failure-local
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	recoveryhttp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	recoveryapp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
	recoveryreporter "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/infrastructure/eventrecord"
)

func TestRecoveryFailureHTTPPersistsOneSanitizedRuntimeFact(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	runtimeLogs := eventapp.NewRuntimeLogService(store, store)
	reporter, err := recoveryreporter.NewReporter(runtimeLogs)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	recoveryhttp.NewHandler(recoveryapp.NewService(reporter), writeRecoveryError).Register(mux)
	now := time.Now().UTC()
	payload := map[string]any{
		"occurredAt": now.Format(time.RFC3339Nano), "appVersion": "1.8.2", "buildNumber": "18201",
		"platform": "android", "osVersion": "15", "deviceModel": "Pixel",
		"errorSource": "flutter", "errorType": "DatabaseOpenException",
		"errorMessage": "authorization=secret user@example.com",
		"stackTrace":   "at /Users/alice/app.dart https://quwoquan.com/p?token=secret",
	}
	body, _ := json.Marshal(payload)
	request := httptest.NewRequest(http.MethodPost, "/ops/recovery-failures", bytes.NewReader(body))
	request.RemoteAddr = "192.0.2.10:1234"
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("report status=%d body=%s", response.Code, response.Body.String())
	}
	drilldown, err := runtimeLogs.GetRuntimeLogDrilldown(context.Background(), eventapp.RuntimeLogDrilldownQuery{
		Signal: "app.exception.flutter", From: now.Add(-time.Minute), To: now.Add(time.Minute), Limit: 10,
	})
	if err != nil || len(drilldown.Items) != 1 {
		t.Fatalf("drilldown items=%d err=%v", len(drilldown.Items), err)
	}
	encoded, _ := json.Marshal(drilldown.Items[0])
	for _, secret := range []string{"secret", "user@example.com", "/Users/alice", "token=secret"} {
		if strings.Contains(string(encoded), secret) {
			t.Fatalf("persisted recovery fact contains %q: %s", secret, encoded)
		}
	}
}

func writeRecoveryError(w http.ResponseWriter, r *http.Request, status int, userMessage, debugMessage string) {
	module, kind, reason := rterr.ModuleOps, rterr.KindSystem, "internal_error"
	if status == http.StatusBadRequest {
		kind, reason = rterr.KindUser, "invalid_argument"
	}
	err := rterr.NewAppError(rterr.NewCode(module, kind, reason), userMessage, debugMessage).WithMetadata(reason, status)
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
