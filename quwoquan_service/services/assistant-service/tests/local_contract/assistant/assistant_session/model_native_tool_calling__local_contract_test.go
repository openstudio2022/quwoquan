// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/native-tool-calling-model-routing/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/modelprovider"
)

type capturedToolCallingRequest struct {
	Model    string `json:"model"`
	Messages []struct {
		Role    string `json:"role"`
		Content string `json:"content"`
	} `json:"messages"`
	Tools []struct {
		Type     string `json:"type"`
		Function struct {
			Name        string         `json:"name"`
			Description string         `json:"description"`
			Parameters  map[string]any `json:"parameters"`
		} `json:"function"`
	} `json:"tools"`
	ToolChoice string `json:"tool_choice"`
}

func reasoningToolCatalog() []ports.ModelToolDefinition {
	return []ports.ModelToolDefinition{{
		Name:        "web_search",
		Description: "检索公开网络信息。",
		Parameters: map[string]any{
			"type":       "object",
			"properties": map[string]any{"query": map[string]any{"type": "string"}},
			"required":   []string{"query"},
		},
	}}
}

func TestModelProviderSubmitsNativeToolCallsWhenEnabled(t *testing.T) {
	captured := make(chan capturedToolCallingRequest, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		var body capturedToolCallingRequest
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Errorf("decode request: %v", err)
			return
		}
		captured <- body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"model":"served-reasoning-model","choices":[{"message":{"content":"{\"nextAction\":\"tool_call\",\"stageNarrative\":\"你想确认的是杭州本周末的天气与出行安排。\"}","tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"web_search","arguments":"{\"query\":\"杭州 周末 天气\",\"location\":\"杭州\"}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":30,"completion_tokens":12,"total_tokens":42}}`))
	}))
	defer server.Close()

	backend, err := modelprovider.New(
		modelprovider.Config{
			CompletionURL:     server.URL,
			APIKey:            "test-key",
			Models:            modelprovider.TierModels{Balanced: "balanced-model", Reasoning: "reasoning-model"},
			NativeToolCalling: true,
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	if !ports.SupportsNativeToolCalling(backend) {
		t.Fatal("adapter must declare native tool calling support")
	}
	provider := orchestration.ProviderBackedModelProvider{Backend: backend}
	response, err := provider.Complete(context.Background(), orchestration.ModelRequest{
		Stage:           "reasoning",
		Prompt:          "规划检索",
		UserQuestion:    "杭州周末适合出行吗",
		ProblemClass:    "complex_reasoning",
		SearchIntensity: "medium",
		ToolCatalog:     reasoningToolCatalog(),
	})
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}

	request := <-captured
	if request.ToolChoice != string(ports.ModelToolChoiceAuto) {
		t.Fatalf("tool_choice=%q want auto so the model can still ask the user", request.ToolChoice)
	}
	if len(request.Tools) != 1 || request.Tools[0].Function.Name != "web_search" {
		t.Fatalf("tools=%+v want a single web_search declaration", request.Tools)
	}
	if request.Tools[0].Function.Parameters["type"] != "object" {
		t.Fatalf("tool parameters must be a JSON Schema object, got %+v", request.Tools[0].Function.Parameters)
	}
	if request.Model != "reasoning-model" {
		t.Fatalf("model=%q want reasoning-model for complex_reasoning", request.Model)
	}

	if len(response.ToolCalls) != 1 || response.ToolCalls[0].Name != "web_search" {
		t.Fatalf("toolCalls=%+v want web_search", response.ToolCalls)
	}
	if response.StructuredDelta["toolName"] != "web_search" {
		t.Fatalf("structured toolName=%v want web_search", response.StructuredDelta["toolName"])
	}
	toolInput, ok := response.StructuredDelta["toolInput"].(map[string]any)
	if !ok || toolInput["query"] != "杭州 周末 天气" || toolInput["location"] != "杭州" {
		t.Fatalf("toolInput=%#v want decoded native arguments", response.StructuredDelta["toolInput"])
	}
	if response.StructuredDelta["stageNarrative"] == nil {
		t.Fatal("stageNarrative must survive alongside native tool calls")
	}
	if response.ClientModelInteraction["modelId"] != "served-reasoning-model" {
		t.Fatalf("modelId=%v, want provider-served identity", response.ClientModelInteraction["modelId"])
	}
}

func TestModelProviderFallsBackToStructuredOutputWhenToolCallingUnsupported(t *testing.T) {
	captured := make(chan capturedToolCallingRequest, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		var body capturedToolCallingRequest
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Errorf("decode request: %v", err)
			return
		}
		captured <- body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"model":"served-balanced-model","choices":[{"message":{"content":"{\"nextAction\":\"tool_call\",\"toolName\":\"web_search\",\"toolInput\":{\"query\":\"杭州 天气\"},\"stageNarrative\":\"叙事\"}"},"finish_reason":"stop"}],"usage":{"prompt_tokens":20,"completion_tokens":10,"total_tokens":30}}`))
	}))
	defer server.Close()

	backend, err := modelprovider.New(
		modelprovider.Config{
			CompletionURL: server.URL,
			APIKey:        "test-key",
			Models:        modelprovider.TierModels{Balanced: "balanced-model"},
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	if ports.SupportsNativeToolCalling(backend) {
		t.Fatal("adapter must not claim native tool calling when it is not configured")
	}
	provider := orchestration.ProviderBackedModelProvider{Backend: backend}
	response, err := provider.Complete(context.Background(), orchestration.ModelRequest{
		Stage:           "reasoning",
		Prompt:          "规划检索",
		UserQuestion:    "杭州天气",
		ProblemClass:    "realtime_info",
		SearchIntensity: "medium",
		ToolCatalog:     reasoningToolCatalog(),
	})
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	request := <-captured
	if len(request.Tools) != 0 || request.ToolChoice != "" {
		t.Fatalf("unsupported adapter must not send tools, got tools=%+v choice=%q", request.Tools, request.ToolChoice)
	}
	if response.StructuredDelta["toolName"] != "web_search" {
		t.Fatalf("structured fallback toolName=%v want web_search", response.StructuredDelta["toolName"])
	}
	if len(response.ToolCalls) != 0 {
		t.Fatalf("structured fallback must not report native tool calls, got %+v", response.ToolCalls)
	}
}

func TestModelProviderAssemblesStreamedToolCallFragments(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte("data: {\"model\":\"served-balanced-model\",\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"call_1\",\"function\":{\"name\":\"web_search\",\"arguments\":\"{\\\"query\\\":\"}}]}}]}\n\n"))
		_, _ = w.Write([]byte("data: {\"model\":\"served-balanced-model\",\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"function\":{\"arguments\":\"\\\"杭州\\\"}\"}}]},\"finish_reason\":\"tool_calls\"}],\"usage\":{\"prompt_tokens\":8,\"completion_tokens\":2,\"total_tokens\":10}}\n\n"))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	backend, err := modelprovider.New(
		modelprovider.Config{
			CompletionURL:     server.URL,
			APIKey:            "test-key",
			Models:            modelprovider.TierModels{Balanced: "balanced-model"},
			NativeToolCalling: true,
		},
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	result, err := backend.Stream(
		context.Background(),
		ports.ModelCompletionRequest{
			Stage:      ports.ModelStageFinal,
			Tier:       ports.ModelTierBalanced,
			Stream:     true,
			Tools:      []ports.ModelToolDefinition{{Name: "web_search"}},
			ToolChoice: ports.ModelToolChoiceAuto,
			Messages:   []ports.ModelMessage{{Role: "user", Content: "杭州天气"}},
		},
		func(ports.ModelTextDelta) error { return nil },
	)
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}
	if len(result.ToolCalls) != 1 || result.ToolCalls[0].Name != "web_search" {
		t.Fatalf("toolCalls=%+v want a single assembled web_search call", result.ToolCalls)
	}
	if result.ToolCalls[0].Arguments != `{"query":"杭州"}` {
		t.Fatalf("arguments=%q want fragments assembled in order", result.ToolCalls[0].Arguments)
	}
}
