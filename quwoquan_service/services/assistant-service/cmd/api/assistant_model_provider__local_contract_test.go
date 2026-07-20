package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/application"
)

func TestOpenAICompatibleModelProviderStreamsFinalTextDeltas(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/chat/completions" {
			t.Fatalf("request=%s %s", r.Method, r.URL.Path)
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if body["stream"] != true {
			t.Fatalf("stream=%v, want true", body["stream"])
		}
		if _, exists := body["response_format"]; exists {
			t.Fatalf("final streaming request must emit markdown directly: %#v", body["response_format"])
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte("data: {\"choices\":[{\"delta\":{\"content\":\"你好\"},\"finish_reason\":\"\"}]}\n\n"))
		_, _ = w.Write([]byte("data: {\"choices\":[{\"delta\":{\"content\":\"，世界\"},\"finish_reason\":\"stop\"}]}\n\n"))
		_, _ = w.Write([]byte("data: {\"choices\":[],\"usage\":{\"prompt_tokens\":8,\"completion_tokens\":2}}\n\n"))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	provider := openAICompatibleModelProvider{
		baseURL: server.URL,
		model:   "test-model",
		apiKey:  "test-key",
		client:  &http.Client{Timeout: time.Second},
	}
	var deltas []string
	response, err := provider.Stream(t.Context(), application.ModelRequest{
		TurnID:       "atn_stream",
		TraceID:      "trace_stream",
		SkillID:      "general_qa",
		Stage:        "final",
		Prompt:       "直接回答",
		UserQuestion: "你好",
	}, func(delta application.ModelTextDelta) error {
		deltas = append(deltas, delta.Text)
		return nil
	})
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}
	if strings.Join(deltas, "") != "你好，世界" {
		t.Fatalf("deltas=%#v", deltas)
	}
	if response.Text != "你好，世界" || response.FinishReason != "stop" {
		t.Fatalf("response=%+v", response)
	}
	if response.Usage["provider"] != "openai_compatible" {
		t.Fatalf("usage=%#v", response.Usage)
	}
	trace := response.ClientModelInteraction
	if trace["contentRedactionApplied"] != true {
		t.Fatalf("client trace must be redacted: %#v", trace)
	}
	for _, forbidden := range []string{
		"requestUserPrompt",
		"responseText",
		"structuredDelta",
	} {
		if _, exists := trace[forbidden]; exists {
			t.Fatalf("client trace leaked %s: %#v", forbidden, trace)
		}
	}
}

func TestOpenAICompatibleModelProviderStripsUnbackedSourcesFromStreamFinal(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte(
			"data: {\"choices\":[{\"delta\":{\"content\":\"结论。\\n\\n## 知识来源\\n- [编造来源](https://invalid.example)\"},\"finish_reason\":\"stop\"}]}\n\n",
		))
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
	}))
	defer server.Close()

	provider := openAICompatibleModelProvider{
		baseURL: server.URL,
		model:   "test-model",
		apiKey:  "test-key",
		client:  &http.Client{Timeout: time.Second},
	}
	response, err := provider.Stream(t.Context(), application.ModelRequest{
		TurnID:       "atn_stream_without_refs",
		TraceID:      "trace_stream_without_refs",
		SkillID:      "general_qa",
		Stage:        "final",
		Prompt:       "直接回答",
		UserQuestion: "给出结论",
	}, nil)
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}
	if response.Text != "结论。" {
		t.Fatalf("response.Text=%q, want unbacked sources stripped", response.Text)
	}
	if response.StructuredDelta["userMarkdown"] != "结论。" {
		t.Fatalf("structuredDelta=%#v", response.StructuredDelta)
	}
}
