package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/modelprovider"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
)

func TestClientStreamsTypedModelCompletion(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost || request.URL.Path != "/v1/chat/completions" {
			t.Fatalf("request=%s %s", request.Method, request.URL.Path)
		}
		if request.Header.Get("Authorization") != "Bearer test-key" {
			t.Fatalf("authorization header missing")
		}
		var body struct {
			Stream         bool `json:"stream"`
			ResponseFormat *struct {
				Type string `json:"type"`
			} `json:"response_format"`
		}
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if !body.Stream || body.ResponseFormat != nil {
			t.Fatalf("unexpected wire request: %+v", body)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte("data: {\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\n\n"))
		_, _ = w.Write([]byte("data: {\"choices\":[{\"delta\":{\"content\":\"，世界\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":8,\"completion_tokens\":2,\"total_tokens\":10}}\n\n"))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	client, err := New(
		Config{
			CompletionURL: server.URL + "/v1/chat/completions",
			APIKey:        "test-key",
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	var deltas []string
	result, err := client.Stream(t.Context(), application.ModelCompletionRequest{
		Stage: application.ModelStageFinal,
		Messages: []application.ModelMessage{
			{Role: "system", Content: "system"},
			{Role: "user", Content: "hello"},
		},
		Stream: true,
	}, func(delta application.ModelTextDelta) error {
		deltas = append(deltas, delta.Text)
		return nil
	})
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}
	if strings.Join(deltas, "") != "你好，世界" || result.Content != "你好，世界" {
		t.Fatalf("result=%+v deltas=%#v", result, deltas)
	}
	if result.Usage.TotalTokens != 10 {
		t.Fatalf("usage=%+v", result.Usage)
	}
}

func TestClientRedactsProviderErrorResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"secret upstream detail"}`))
	}))
	defer server.Close()
	client, err := New(
		Config{CompletionURL: server.URL, APIKey: "value"},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	_, err = client.Complete(t.Context(), application.ModelCompletionRequest{
		Stage:    application.ModelStageFinal,
		Messages: []application.ModelMessage{{Role: "user", Content: "sensitive prompt"}},
	})
	if err == nil || strings.Contains(err.Error(), "secret upstream detail") ||
		!strings.Contains(err.Error(), "capability=model") {
		t.Fatalf("provider failure must be redacted, err=%v", err)
	}
}
