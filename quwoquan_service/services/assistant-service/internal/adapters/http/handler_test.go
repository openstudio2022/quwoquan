package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

func TestHandleReportInteractionEvent_BatchWrapperAndHeaders(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	body := map[string]any{
		"events": []map[string]any{
			{
				"eventId":  "evt_1",
				"runId":    "run_1",
				"pageType": "assistant_dialog",
			},
		},
	}
	payload, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/assistant/learning/events", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_1")
	req.Header.Set("X-Client-Session-Id", "session_1")
	req.Header.Set("X-Trace-Id", "trace_1")
	req.Header.Set("X-Client-Page-Id", "assistant.reportInteractionEvent")
	req.Header.Set("X-Client-Surface-Id", "assistant_dialog")
	req.Header.Set("X-Client-Route-Id", "assistant-dialog-route")
	req.Header.Set("X-Client-Operation-Id", "ReportInteractionEvent")
	req.Header.Set("X-Client-Experiment-Bucket", "control")
	req.Header.Set("X-Client-Sent-At", "2026-04-01T10:00:00Z")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["resource"] != "interaction_event_batch" {
		t.Fatalf("resource=%v, want interaction_event_batch", resp["resource"])
	}
	items, err := service.ListAssistantMemories(context.Background(), "user_1", 10)
	if err != nil {
		t.Fatalf("ListAssistantMemories error: %v", err)
	}
	if len(items.Items) != 1 {
		t.Fatalf("memories=%d, want 1", len(items.Items))
	}
}

func TestHandleReportScorecard_BatchWrapper(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := NewHandler(service).Routes()

	body := map[string]any{
		"scorecards": []map[string]any{
			{
				"scoreId":     "score_1",
				"eventId":     "evt_1",
				"userId":      "user_1",
				"metricId":    "answer_relevance",
				"scoreValue":  4.2,
				"scoreSource": "implicit",
			},
		},
	}
	payload, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/assistant/learning/scorecards", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["resource"] != "scorecard_batch" {
		t.Fatalf("resource=%v, want scorecard_batch", resp["resource"])
	}
	if resp["acceptedCount"] != float64(1) {
		t.Fatalf("acceptedCount=%v, want 1", resp["acceptedCount"])
	}
}

func TestHandleGetLearningOpsSummary(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	_, err := service.ReportInteractionEvents(context.Background(), []assistant.InteractionEvent{{
		EventID:       "evt_ops_http_1",
		RunID:         "run_ops_http_1",
		UserID:        "user_http_1",
		SessionID:     "session_http_1",
		PageType:      "assistant_dialog",
		DomainID:      "assistant",
		ExplicitThumb: "down",
	}})
	if err != nil {
		t.Fatalf("ReportInteractionEvents error: %v", err)
	}
	handler := NewHandler(service).Routes()
	req := httptest.NewRequest(http.MethodGet, "/v1/assistant/ops/learning-summary", nil)
	req.Header.Set("X-Client-User-Id", "user_http_1")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response error: %v", err)
	}
	if resp["userId"] != "user_http_1" {
		t.Fatalf("userId=%v", resp["userId"])
	}
}
