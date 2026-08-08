// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-001
package assistant_run_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/modelprovider"
)

func TestModelProviderRequestOmitsUnconfiguredTemperature(t *testing.T) {
	requests := make(chan map[string]json.RawMessage, 2)
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		var payload map[string]json.RawMessage
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Errorf("decode model request: %v", err)
			return
		}
		requests <- payload

		var stream bool
		if raw, ok := payload["stream"]; ok {
			if err := json.Unmarshal(raw, &stream); err != nil {
				t.Errorf("decode stream flag: %v", err)
				return
			}
		}
		if stream {
			writer.Header().Set("Content-Type", "text/event-stream")
			_, _ = writer.Write([]byte("data: {\"model\":\"served-balanced\",\"choices\":[{\"delta\":{\"content\":\"ok\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2}}\n\n"))
			_, _ = writer.Write([]byte("data: [DONE]\n\n"))
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"model":"served-balanced","choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`))
	}))
	defer server.Close()

	client, err := modelprovider.New(modelprovider.Config{
		CompletionURL: server.URL,
		APIKey:        "test-key",
		Models:        modelprovider.TierModels{Balanced: "balanced-model"},
	}, server.Client())
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	request := ports.ModelCompletionRequest{
		Stage:    ports.ModelStageFinal,
		Tier:     ports.ModelTierBalanced,
		Messages: []ports.ModelMessage{{Role: "user", Content: "hello"}},
	}
	if _, err := client.Complete(t.Context(), request); err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	request.Stream = true
	if _, err := client.Stream(t.Context(), request, nil); err != nil {
		t.Fatalf("Stream() error = %v", err)
	}

	for _, operation := range []string{"complete", "stream"} {
		payload := <-requests
		if _, hardcoded := payload["temperature"]; hardcoded {
			t.Fatalf("%s request contains an unconfigured temperature", operation)
		}
		var model string
		if err := json.Unmarshal(payload["model"], &model); err != nil {
			t.Fatalf("decode %s model: %v", operation, err)
		}
		if model != "balanced-model" {
			t.Fatalf("%s model=%q, want environment-configured balanced-model", operation, model)
		}
	}
}
