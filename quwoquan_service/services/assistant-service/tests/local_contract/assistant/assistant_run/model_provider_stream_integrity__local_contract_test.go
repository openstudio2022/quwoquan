// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-002
package assistant_run_test

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/modelprovider"
)

func TestModelProviderStreamRequiresTerminalAndRejectsErrorEnvelope(t *testing.T) {
	const receiptChunk = "data: {\"model\":\"served-balanced\",\"choices\":[{\"delta\":{\"content\":\"partial\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2}}\n\n"
	tests := []struct {
		name        string
		body        string
		wantFailure bool
	}{
		{
			name: "explicit terminal succeeds",
			body: receiptChunk + "data: [DONE]\n\n",
		},
		{
			name:        "clean eof before terminal fails closed",
			body:        receiptChunk,
			wantFailure: true,
		},
		{
			name: "provider error after receipt fails closed",
			body: receiptChunk +
				"data: {\"error\":{\"message\":\"provider failed\"}}\n\n" +
				"data: [DONE]\n\n",
			wantFailure: true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				_ *http.Request,
			) {
				writer.Header().Set("Content-Type", "text/event-stream")
				_, _ = writer.Write([]byte(test.body))
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
			var emitted strings.Builder
			result, err := client.Stream(t.Context(), ports.ModelCompletionRequest{
				Stage:    ports.ModelStageFinal,
				Tier:     ports.ModelTierBalanced,
				Stream:   true,
				Messages: []ports.ModelMessage{{Role: "user", Content: "hello"}},
			}, func(delta ports.ModelTextDelta) error {
				emitted.WriteString(delta.Text)
				return nil
			})
			if emitted.String() != "partial" {
				t.Fatalf("emitted=%q, want partial", emitted.String())
			}
			if !test.wantFailure {
				if err != nil {
					t.Fatalf("Stream() error = %v", err)
				}
				if result.ModelID != "served-balanced" || result.Usage.TotalTokens != 2 {
					t.Fatalf("result=%+v, want validated provider receipt", result)
				}
				return
			}
			if err == nil {
				t.Fatalf("Stream() result=%+v, want invalid response", result)
			}
			var failure ports.ProviderFailure
			if !errors.As(err, &failure) ||
				failure.Capability != "model" ||
				failure.Reason != ports.ProviderFailureInvalidResponse {
				t.Fatalf("Stream() error=%v, want model invalid_response", err)
			}
			if result.ModelID != "" || result.Usage.TotalTokens != 0 {
				t.Fatalf("failed stream returned a success receipt: %+v", result)
			}
		})
	}
}

func TestModelProviderNonRetryableHTTPStatusDoesNotDegrade(t *testing.T) {
	for _, operation := range []string{"complete", "stream"} {
		t.Run(operation, func(t *testing.T) {
			var mutex sync.Mutex
			requestedModels := []string{}
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				var payload struct {
					Model string `json:"model"`
				}
				if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
					t.Errorf("decode model request: %v", err)
					return
				}
				mutex.Lock()
				requestedModels = append(requestedModels, payload.Model)
				mutex.Unlock()
				writer.WriteHeader(http.StatusUnauthorized)
				_, _ = writer.Write([]byte(`{"error":{"message":"secret credential detail"}}`))
			}))
			defer server.Close()

			client, err := modelprovider.New(modelprovider.Config{
				CompletionURL: server.URL,
				APIKey:        "test-key",
				Models: modelprovider.TierModels{
					Fast: "fast-model", Balanced: "balanced-model", Reasoning: "reasoning-model",
				},
			}, server.Client())
			if err != nil {
				t.Fatalf("New() error = %v", err)
			}
			provider := orchestration.TierDegradingModelProvider{Backend: client}
			request := ports.ModelCompletionRequest{
				Stage: ports.ModelStageReasoning,
				Tier:  ports.ModelTierReasoning,
			}
			if operation == "stream" {
				request.Stream = true
				_, err = provider.Stream(t.Context(), request, nil)
			} else {
				_, err = provider.Complete(t.Context(), request)
			}
			var failure ports.ProviderFailure
			if !errors.As(err, &failure) ||
				failure.Reason != ports.ProviderFailureInvalidResponse ||
				strings.Contains(err.Error(), "secret credential detail") {
				t.Fatalf("%s error=%v, want redacted invalid_response", operation, err)
			}
			mutex.Lock()
			models := append([]string{}, requestedModels...)
			mutex.Unlock()
			if len(models) != 1 || models[0] != "reasoning-model" {
				t.Fatalf("%s requested models=%v, want no tier degradation", operation, models)
			}
		})
	}
}

func TestModelProviderRetryableHTTPStatusDegrades(t *testing.T) {
	for _, retryableStatus := range []int{
		http.StatusTooManyRequests,
		http.StatusServiceUnavailable,
	} {
		t.Run(http.StatusText(retryableStatus), func(t *testing.T) {
			var mutex sync.Mutex
			requestedModels := []string{}
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				var payload struct {
					Model string `json:"model"`
				}
				if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
					t.Errorf("decode model request: %v", err)
					return
				}
				mutex.Lock()
				requestedModels = append(requestedModels, payload.Model)
				mutex.Unlock()
				if payload.Model == "reasoning-model" {
					writer.WriteHeader(retryableStatus)
					return
				}
				writer.Header().Set("Content-Type", "application/json")
				_, _ = writer.Write([]byte(`{"model":"served-balanced","choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`))
			}))
			defer server.Close()

			client, err := modelprovider.New(modelprovider.Config{
				CompletionURL: server.URL,
				APIKey:        "test-key",
				Models: modelprovider.TierModels{
					Fast: "fast-model", Balanced: "balanced-model", Reasoning: "reasoning-model",
				},
			}, server.Client())
			if err != nil {
				t.Fatalf("New() error = %v", err)
			}
			result, err := (orchestration.TierDegradingModelProvider{Backend: client}).Complete(
				t.Context(),
				ports.ModelCompletionRequest{Stage: ports.ModelStageReasoning, Tier: ports.ModelTierReasoning},
			)
			if err != nil {
				t.Fatalf("Complete() error = %v", err)
			}
			mutex.Lock()
			models := append([]string{}, requestedModels...)
			mutex.Unlock()
			if len(models) != 2 || models[0] != "reasoning-model" || models[1] != "balanced-model" ||
				result.TierServed != ports.ModelTierBalanced {
				t.Fatalf("requested models=%v result=%+v, want one attempt per declared tier", models, result)
			}
		})
	}
}
