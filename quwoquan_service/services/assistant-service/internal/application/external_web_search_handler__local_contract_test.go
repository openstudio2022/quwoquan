package application

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type recordingExternalSearchProvider struct {
	result  ExternalSearchResult
	request ExternalSearchRequest
}

func (p *recordingExternalSearchProvider) Search(
	_ context.Context,
	request ExternalSearchRequest,
) (ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func (p *recordingExternalSearchProvider) Lookup(
	_ context.Context,
	request ExternalSearchRequest,
) (ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func TestExternalWebSearchHandlerUsesTypedWeatherPort(t *testing.T) {
	weather := &recordingExternalSearchProvider{result: ExternalSearchResult{
		Summary: "杭州晴",
		References: []ExternalReference{{
			Title: "中国天气网", URL: "https://www.weather.com.cn/", Source: "weather_com_cn",
		}},
	}}
	handler := NewExternalWebSearchHandler(nil, weather, nil)
	result, err := handler(t.Context(), toolpkg.Request{
		ToolName: "web_search",
		Input: map[string]any{
			"query":              "杭州明天天气",
			"location":           "杭州",
			"locationSearchName": "Hangzhou",
			"skillId":            "weather",
		},
	})
	if err != nil {
		t.Fatalf("handler() error = %v", err)
	}
	if weather.request.LocationSearchName != "Hangzhou" {
		t.Fatalf("typed weather request=%+v", weather.request)
	}
	if _, exists := result.Output["provider"]; exists {
		t.Fatalf("tool output must not expose provider: %#v", result.Output)
	}
	payload, err := json.Marshal(result.Output)
	if err != nil {
		t.Fatalf("marshal tool output: %v", err)
	}
	for _, forbidden := range []string{"provider", "endpoint", "credential", "api_key", "secret"} {
		if strings.Contains(strings.ToLower(string(payload)), forbidden) {
			t.Fatalf("tool payload leaks %q: %s", forbidden, payload)
		}
	}
	references, ok := result.Output["references"].([]map[string]any)
	if !ok || len(references) != 1 || references[0]["source"] != "weather_com_cn" {
		t.Fatalf("references=%#v", result.Output["references"])
	}
}

func TestExternalWebSearchHandlerMapsProviderFailureToStructuredCode(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		NewExternalWebSearchHandler(
			providerFailureSearchProvider{},
			nil,
			nil,
		),
	)
	coordinator := DefaultToolCoordinator{Registry: registry}
	execution, err := coordinator.Execute(t.Context(), ToolRequest{
		Turn:     assistantTurnForExternalProviderTest(),
		Skill:    SkillSelection{SkillID: "knowledge_general"},
		ToolName: "web_search",
		Input:    map[string]any{"query": "公开资料"},
	})
	if err != nil {
		t.Fatalf("coordinator.Execute() error = %v", err)
	}
	if execution.Failure == nil {
		t.Fatal("provider failure must become a structured tool failure")
	}
	if execution.Failure.Code != "ASSISTANT.MIDDLEWARE.public_search_provider_unavailable" {
		t.Fatalf("failure code=%q", execution.Failure.Code)
	}
}

func TestExternalWebSearchHandlerDoesNotFallbackAcrossCapabilities(t *testing.T) {
	public := &recordingExternalSearchProvider{}
	handler := NewExternalWebSearchHandler(
		public,
		providerFailureWeatherProvider{},
		nil,
	)
	_, err := handler(t.Context(), toolpkg.Request{
		ToolName: "web_search",
		Input: map[string]any{
			"query":   "杭州天气",
			"skillId": "weather",
		},
	})
	var failure ProviderFailure
	if !errors.As(err, &failure) {
		t.Fatalf("error = %v, want ProviderFailure", err)
	}
	if failure.Capability != "weather" {
		t.Fatalf("failure = %+v", failure)
	}
	if public.request.Query != "" {
		t.Fatalf("weather failure must not fall back to public search: %+v", public.request)
	}
}

type providerFailureSearchProvider struct{}

func (providerFailureSearchProvider) Search(
	context.Context,
	ExternalSearchRequest,
) (ExternalSearchResult, error) {
	return ExternalSearchResult{}, ProviderFailure{
		Capability: "public_search",
		Reason:     ProviderFailureUnavailable,
	}
}

type providerFailureWeatherProvider struct{}

func (providerFailureWeatherProvider) Lookup(
	context.Context,
	ExternalSearchRequest,
) (ExternalSearchResult, error) {
	return ExternalSearchResult{}, ProviderFailure{
		Capability: "weather",
		Reason:     ProviderFailureUnavailable,
	}
}

func assistantTurnForExternalProviderTest() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:  "atn_external_provider",
		TraceID: "trace_external_provider",
		Input:   assistant.AssistantTurnInput{Text: "公开资料"},
	}
}
