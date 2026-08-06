package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/modelprovider"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
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
		_, _ = w.Write([]byte("data: {\"model\":\"provider-served-v2\",\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\n\n"))
		_, _ = w.Write([]byte("data: {\"model\":\"provider-served-v2\",\"choices\":[{\"delta\":{\"content\":\"，世界\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":8,\"completion_tokens\":2,\"total_tokens\":10}}\n\n"))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	client, err := New(
		Config{
			CompletionURL: server.URL + "/v1/chat/completions",
			APIKey:        "test-key",
			Models:        TierModels{Balanced: "test-balanced"},
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	var deltas []string
	result, err := client.Stream(t.Context(), ports.ModelCompletionRequest{
		Stage: ports.ModelStageFinal,
		Messages: []ports.ModelMessage{
			{Role: "system", Content: "system"},
			{Role: "user", Content: "hello"},
		},
		Stream: true,
	}, func(delta ports.ModelTextDelta) error {
		deltas = append(deltas, delta.Text)
		return nil
	})
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}
	if strings.Join(deltas, "") != "你好，世界" || result.Content != "你好，世界" {
		t.Fatalf("result=%+v deltas=%#v", result, deltas)
	}
	if result.Usage.TotalTokens != 10 || result.ModelID != "provider-served-v2" {
		t.Fatalf("usage=%+v", result.Usage)
	}
}

func TestClientRejectsCompletionWithoutProviderReceiptIdentityOrUsage(t *testing.T) {
	tests := map[string]string{
		"missing model": `{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`,
		"missing usage": `{"model":"provider-served-v2","choices":[{"message":{"content":"ok"}}]}`,
	}
	for name, response := range tests {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(response))
			}))
			defer server.Close()
			client, err := New(Config{
				CompletionURL: server.URL,
				APIKey:        "test-key",
				Models:        TierModels{Balanced: "requested-model"},
			}, server.Client())
			if err != nil {
				t.Fatal(err)
			}
			if _, err := client.Complete(t.Context(), ports.ModelCompletionRequest{
				Stage:    ports.ModelStageFinal,
				Messages: []ports.ModelMessage{{Role: "user", Content: "hello"}},
			}); err == nil || !strings.Contains(err.Error(), "invalid_response") {
				t.Fatalf("Complete() error=%v, want fail-closed provider receipt", err)
			}
		})
	}
}

func TestClientRejectsStreamWithoutUsageReceipt(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte("data: {\"model\":\"provider-served-v2\",\"choices\":[{\"delta\":{\"content\":\"ok\"},\"finish_reason\":\"stop\"}]}\n\n"))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()
	client, err := New(Config{
		CompletionURL: server.URL,
		APIKey:        "test-key",
		Models:        TierModels{Balanced: "requested-model"},
	}, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.Stream(t.Context(), ports.ModelCompletionRequest{
		Stage:    ports.ModelStageFinal,
		Messages: []ports.ModelMessage{{Role: "user", Content: "hello"}},
		Stream:   true,
	}, nil); err == nil || !strings.Contains(err.Error(), "invalid_response") {
		t.Fatalf("Stream() error=%v, want fail-closed usage receipt", err)
	}
}

func TestClientRedactsProviderErrorResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"secret upstream detail"}`))
	}))
	defer server.Close()
	client, err := New(
		Config{
			CompletionURL: server.URL,
			APIKey:        "value",
			Models:        TierModels{Balanced: "test-balanced"},
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	_, err = client.Complete(t.Context(), ports.ModelCompletionRequest{
		Stage:    ports.ModelStageFinal,
		Messages: []ports.ModelMessage{{Role: "user", Content: "sensitive prompt"}},
	})
	if err == nil || strings.Contains(err.Error(), "secret upstream detail") ||
		!strings.Contains(err.Error(), "capability=model") {
		t.Fatalf("provider failure must be redacted, err=%v", err)
	}
}
