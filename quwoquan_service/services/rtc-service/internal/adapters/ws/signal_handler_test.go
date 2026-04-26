package ws

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSignalHandler_InvalidUpgradeWritesRuntimeErrorResponse(t *testing.T) {
	handler := NewSignalHandler(nil, slog.Default())
	req := httptest.NewRequest(http.MethodGet, "/ws?userId=u1", nil)
	req.Header.Set("X-Request-Id", "req-ws")
	req.Header.Set("X-Trace-Id", "trace-ws")
	rec := httptest.NewRecorder()

	handler.HandleSignal(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("unexpected status: %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("expected runtime error json: %v body=%q", err, rec.Body.String())
	}
	if body["code"] != "RTC.USER.invalid_argument" {
		t.Fatalf("unexpected code: %+v", body)
	}
	if body["requestId"] != "req-ws" || body["traceId"] != "trace-ws" {
		t.Fatalf("missing request/trace ids: %+v", body)
	}
}
