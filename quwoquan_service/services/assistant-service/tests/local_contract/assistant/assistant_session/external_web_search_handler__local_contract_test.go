// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"strings"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider struct {
	result  ports.ExternalSearchResult
	request ports.ExternalSearchRequest
}

func (p *assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider) Search(
	_ context.Context,
	request ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func (p *assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider) Lookup(
	_ context.Context,
	request ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	p.request = request
	return p.result, nil
}

func TestExternalWebSearchHandlerUsesTypedWeatherPort(t *testing.T) {
	weather := &assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider{result: ports.ExternalSearchResult{
		Summary: "杭州晴",
		References: []ports.ExternalReference{{
			Title: "中国天气网", URL: "https://www.weather.com.cn/", Source: "weather_com_cn",
		}, {
			Title: "不安全来源", URL: "http://example.com/weather", Source: "unsafe",
		}},
	}}
	handler := NewWeatherLookupHandler(weather)
	result, err := handler(t.Context(), toolpkg.Request{
		ToolName: "weather_lookup",
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

func TestFinanceQuoteUsesTypedFinancePortWithoutSkillRouting(t *testing.T) {
	finance := &assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider{
		result: ports.ExternalSearchResult{Summary: "BABA public quote"},
	}
	handler := NewFinanceQuoteHandler(finance)
	_, err := handler(t.Context(), toolpkg.Request{
		ToolName: "finance_quote",
		Input: map[string]any{
			"query":   "核验阿里巴巴行情",
			"symbols": []any{"BABA", "9988.HK"},
		},
	})
	if err != nil || len(finance.request.Symbols) != 2 ||
		finance.request.Symbols[0] != "BABA" {
		t.Fatalf("finance request=%+v error=%v", finance.request, err)
	}
}

func TestExternalWebSearchHandlerMapsProviderFailureToStructuredCode(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		NewPublicWebSearchHandler(
			assistantSessionExternalWebSearchHandlerProviderFailureSearchProvider{},
		),
	)
	coordinator := DefaultToolCoordinator{Registry: registry}
	execution, err := coordinator.Execute(t.Context(), ToolRequest{
		Turn:     assistantSessionExternalWebSearchHandlerAssistantTurnForExternalProviderTest(),
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

func TestPublicWebSearchNeverInfersWeatherCapabilityFromTextOrSkill(t *testing.T) {
	public := &assistantSessionExternalWebSearchHandlerRecordingExternalSearchProvider{
		result: ports.ExternalSearchResult{Summary: "public weather pages"},
	}
	handler := NewPublicWebSearchHandler(public)
	_, err := handler(t.Context(), toolpkg.Request{
		ToolName: "web_search",
		Input: map[string]any{
			"query":   "杭州天气",
			"skillId": "weather",
		},
	})
	if err != nil || public.request.Query != "杭州天气" {
		t.Fatalf("public request=%+v error=%v", public.request, err)
	}
}

func TestWeatherLookupFailureCannotFallbackToAnotherCapability(t *testing.T) {
	handler := NewWeatherLookupHandler(
		assistantSessionExternalWebSearchHandlerProviderFailureWeatherProvider{},
	)
	_, err := handler(t.Context(), toolpkg.Request{
		ToolName: "weather_lookup",
		Input:    map[string]any{"query": "杭州天气"},
	})
	var failure ports.ProviderFailure
	if !errors.As(err, &failure) || failure.Capability != "weather" {
		t.Fatalf("error=%v failure=%+v", err, failure)
	}
}

type assistantSessionExternalWebSearchHandlerProviderFailureSearchProvider struct{}

func (assistantSessionExternalWebSearchHandlerProviderFailureSearchProvider) Search(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "public_search",
		Reason:     ports.ProviderFailureUnavailable,
	}
}

type assistantSessionExternalWebSearchHandlerProviderFailureWeatherProvider struct{}

func (assistantSessionExternalWebSearchHandlerProviderFailureWeatherProvider) Lookup(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "weather",
		Reason:     ports.ProviderFailureUnavailable,
	}
}

func assistantSessionExternalWebSearchHandlerAssistantTurnForExternalProviderTest() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:  "atn_external_provider",
		TraceID: "trace_external_provider",
		Input:   assistant.AssistantTurnInput{Text: "公开资料"},
	}
}
