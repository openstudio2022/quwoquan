// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"strings"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

type migratedExternalWebSearchHandlerRecordingExternalSearchProvider struct {
	result  ports.ExternalSearchResult
	request ports.ExternalSearchRequest
}

func (p *migratedExternalWebSearchHandlerRecordingExternalSearchProvider) Search(
	_ context.Context,
	request ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func (p *migratedExternalWebSearchHandlerRecordingExternalSearchProvider) Lookup(
	_ context.Context,
	request ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func TestExternalWebSearchHandlerUsesTypedWeatherPort(t *testing.T) {
	weather := &migratedExternalWebSearchHandlerRecordingExternalSearchProvider{result: ports.ExternalSearchResult{
		Summary: "杭州晴",
		References: []ports.ExternalReference{{
			Title: "中国天气网", URL: "https://www.weather.com.cn/", Source: "weather_com_cn",
		}, {
			Title: "不安全来源", URL: "http://example.com/weather", Source: "unsafe",
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
	destination, ok := references[0]["destination"].(map[string]any)
	if !ok ||
		destination["kind"] != "external" ||
		destination["url"] != "https://www.weather.com.cn/" {
		t.Fatalf("destination=%#v", references[0]["destination"])
	}
	if _, retainsURLAlias := references[0]["url"]; retainsURLAlias {
		t.Fatalf("reference must not retain URL-only alias: %#v", references[0])
	}
}

func TestExternalWebSearchHandlerMapsProviderFailureToStructuredCode(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		NewExternalWebSearchHandler(
			migratedExternalWebSearchHandlerProviderFailureSearchProvider{},
			nil,
			nil,
		),
	)
	coordinator := DefaultToolCoordinator{Registry: registry}
	execution, err := coordinator.Execute(t.Context(), ToolRequest{
		Turn:     migratedExternalWebSearchHandlerAssistantTurnForExternalProviderTest(),
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
	public := &migratedExternalWebSearchHandlerRecordingExternalSearchProvider{}
	handler := NewExternalWebSearchHandler(
		public,
		migratedExternalWebSearchHandlerProviderFailureWeatherProvider{},
		nil,
	)
	_, err := handler(t.Context(), toolpkg.Request{
		ToolName: "web_search",
		Input: map[string]any{
			"query":   "杭州天气",
			"skillId": "weather",
		},
	})
	var failure ports.ProviderFailure
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

type migratedExternalWebSearchHandlerProviderFailureSearchProvider struct{}

func (migratedExternalWebSearchHandlerProviderFailureSearchProvider) Search(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "public_search",
		Reason:     ports.ProviderFailureUnavailable,
	}
}

type migratedExternalWebSearchHandlerProviderFailureWeatherProvider struct{}

func (migratedExternalWebSearchHandlerProviderFailureWeatherProvider) Lookup(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "weather",
		Reason:     ports.ProviderFailureUnavailable,
	}
}

func migratedExternalWebSearchHandlerAssistantTurnForExternalProviderTest() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:  "atn_external_provider",
		TraceID: "trace_external_provider",
		Input:   assistant.AssistantTurnInput{Text: "公开资料"},
	}
}
