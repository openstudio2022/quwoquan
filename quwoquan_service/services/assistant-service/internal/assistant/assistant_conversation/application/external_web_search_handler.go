package application

import (
	"context"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
)

// NewExternalWebSearchHandler 把既有动态 tool 信封投影为强类型外部检索请求。
// 该投影是 AgentLoop 协议边界；PublicSearch/Weather/Finance port 本身不接收 map。
func NewExternalWebSearchHandler(
	publicSearch PublicSearchProvider,
	weather WeatherProvider,
	finance FinanceProvider,
) toolpkg.Handler {
	return func(ctx context.Context, request toolpkg.Request) (toolpkg.Result, error) {
		input := externalSearchInputFromTool(request.Input)
		if input.Query == "" {
			return toolpkg.Result{}, ProviderFailure{
				Capability: "public_search",
				Reason:     ProviderFailureInvalidResponse,
			}
		}
		var (
			result ExternalSearchResult
			err    error
		)
		if shouldLookupWeather(input, request.Input) {
			if weather == nil {
				return toolpkg.Result{}, ProviderFailure{
					Capability: "weather",
					Reason:     ProviderFailureUnavailable,
				}
			}
			result, err = weather.Lookup(ctx, input)
			if err != nil {
				return toolpkg.Result{}, err
			}
			return externalSearchToolResult(result), nil
		}
		if shouldLookupFinance(input) {
			if finance == nil {
				return toolpkg.Result{}, ProviderFailure{
					Capability: "finance",
					Reason:     ProviderFailureUnavailable,
				}
			}
			result, err = finance.Lookup(ctx, input)
			if err != nil {
				return toolpkg.Result{}, err
			}
			return externalSearchToolResult(result), nil
		}
		if publicSearch == nil {
			return toolpkg.Result{}, ProviderFailure{
				Capability: "public_search",
				Reason:     ProviderFailureUnavailable,
			}
		}
		result, err = publicSearch.Search(ctx, input)
		if err != nil {
			return toolpkg.Result{}, err
		}
		return externalSearchToolResult(result), nil
	}
}

func externalSearchInputFromTool(input map[string]any) ExternalSearchRequest {
	request := ExternalSearchRequest{
		Query:              toolString(input, "query"),
		SkillID:            toolString(input, "skillId"),
		Location:           toolString(input, "location"),
		LocationSearchName: toolString(input, "locationSearchName"),
	}
	request.Queries = appendStructuredQueries(input["searchQueries"])
	request.Queries = append(request.Queries, appendStructuredQueries(input["queries"])...)
	request.Symbols = appendToolStringSlice(input["symbols"])
	if symbol := toolString(input, "symbol"); symbol != "" {
		request.Symbols = append(request.Symbols, symbol)
	}
	return request
}

func externalSearchToolResult(result ExternalSearchResult) toolpkg.Result {
	references := make([]map[string]any, 0, len(result.References))
	for _, reference := range result.References {
		destination, ok := citationDestinationFromSearch(
			rtsearch.ObjectTypeWebDocument,
			"",
			reference.URL,
		)
		if !ok {
			continue
		}
		entry := map[string]any{
			"title":       reference.Title,
			"source":      reference.Source,
			"snippet":     reference.Snippet,
			"destination": citationDestinationMap(destination),
		}
		if reference.Published != "" {
			entry["pubDate"] = reference.Published
		}
		if reference.Rank > 0 {
			entry["rank"] = reference.Rank
		}
		references = append(references, entry)
	}
	return toolpkg.Result{Output: map[string]any{
		"summary":    result.Summary,
		"references": references,
		"reliable":   true,
	}}
}

func shouldLookupFinance(request ExternalSearchRequest) bool {
	return strings.Contains(strings.ToLower(request.SkillID), "finance") ||
		strings.Contains(strings.ToLower(request.SkillID), "stock") ||
		len(request.Symbols) > 0
}

func shouldLookupWeather(
	request ExternalSearchRequest,
	rawInput map[string]any,
) bool {
	if request.SkillID == "weather" {
		return true
	}
	normalized := strings.ToLower(request.Query)
	for _, marker := range []string{"天气", "气温", "降雨", "weather", "forecast"} {
		if strings.Contains(normalized, marker) {
			return true
		}
	}
	return searchQueriesMentionWeather(rawInput["searchQueries"]) ||
		searchQueriesMentionWeather(rawInput["queries"])
}

func searchQueriesMentionWeather(raw any) bool {
	for _, query := range appendStructuredQueries(raw) {
		normalized := strings.ToLower(query)
		for _, marker := range []string{"天气", "气温", "降雨", "weather", "forecast"} {
			if strings.Contains(normalized, marker) {
				return true
			}
		}
	}
	return false
}

func appendStructuredQueries(raw any) []string {
	switch values := raw.(type) {
	case []any:
		result := make([]string, 0, len(values))
		for _, value := range values {
			switch entry := value.(type) {
			case string:
				if text := strings.TrimSpace(entry); text != "" {
					result = append(result, text)
				}
			case map[string]any:
				if text := toolString(entry, "query"); text != "" {
					result = append(result, text)
				}
			}
		}
		return result
	case []string:
		return append([]string{}, values...)
	default:
		return nil
	}
}

func appendToolStringSlice(raw any) []string {
	switch values := raw.(type) {
	case []string:
		return append([]string{}, values...)
	case []any:
		result := make([]string, 0, len(values))
		for _, value := range values {
			if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
				result = append(result, strings.TrimSpace(text))
			}
		}
		return result
	default:
		return nil
	}
}

func toolString(input map[string]any, key string) string {
	value := strings.TrimSpace(fmt.Sprint(input[key]))
	if value == "<nil>" {
		return ""
	}
	return value
}
