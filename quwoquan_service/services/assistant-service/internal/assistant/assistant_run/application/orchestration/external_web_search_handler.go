package orchestration

import (
	"context"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// NewPublicWebSearchHandler projects only the public-web capability. Weather
// and finance are separate typed tools; provider selection is never inferred
// from Skill identity or user text.
func NewPublicWebSearchHandler(provider ports.PublicSearchProvider) toolpkg.Handler {
	return newExternalSearchHandler(
		"public_search",
		publicSearchInputFromTool,
		func(ctx context.Context, request ports.ExternalSearchRequest) (
			ports.ExternalSearchResult,
			error,
		) {
			if provider == nil {
				return ports.ExternalSearchResult{}, ports.ProviderFailure{
					Capability: "public_search",
					Reason:     ports.ProviderFailureUnavailable,
				}
			}
			return provider.Search(ctx, request)
		},
	)
}

func NewWeatherLookupHandler(provider ports.WeatherProvider) toolpkg.Handler {
	return newExternalSearchHandler(
		"weather",
		weatherLookupInputFromTool,
		func(ctx context.Context, request ports.ExternalSearchRequest) (
			ports.ExternalSearchResult,
			error,
		) {
			if provider == nil {
				return ports.ExternalSearchResult{}, ports.ProviderFailure{
					Capability: "weather",
					Reason:     ports.ProviderFailureUnavailable,
				}
			}
			return provider.Lookup(ctx, request)
		},
	)
}

func NewFinanceQuoteHandler(provider ports.FinanceProvider) toolpkg.Handler {
	return newExternalSearchHandler(
		"finance",
		financeQuoteInputFromTool,
		func(ctx context.Context, request ports.ExternalSearchRequest) (
			ports.ExternalSearchResult,
			error,
		) {
			if provider == nil {
				return ports.ExternalSearchResult{}, ports.ProviderFailure{
					Capability: "finance",
					Reason:     ports.ProviderFailureUnavailable,
				}
			}
			return provider.Lookup(ctx, request)
		},
	)
}

type externalSearchInvoke func(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error)

type externalSearchInputDecoder func(map[string]any) ports.ExternalSearchRequest

func newExternalSearchHandler(
	capability string,
	decode externalSearchInputDecoder,
	invoke externalSearchInvoke,
) toolpkg.Handler {
	return func(ctx context.Context, request toolpkg.Request) (toolpkg.Result, error) {
		input := decode(request.Input)
		if input.Query == "" {
			return toolpkg.Result{}, ports.ProviderFailure{
				Capability: capability,
				Reason:     ports.ProviderFailureInvalidResponse,
			}
		}
		result, err := invoke(ctx, input)
		if err != nil {
			return toolpkg.Result{}, err
		}
		return externalSearchToolResult(result), nil
	}
}

func publicSearchInputFromTool(
	input map[string]any,
) ports.ExternalSearchRequest {
	request := ports.ExternalSearchRequest{
		Query:   toolString(input, "query"),
		SkillID: toolString(input, "skillId"),
	}
	request.Queries = appendStructuredQueries(input["searchQueries"])
	return request
}

func weatherLookupInputFromTool(
	input map[string]any,
) ports.ExternalSearchRequest {
	return ports.ExternalSearchRequest{
		Query:              toolString(input, "query"),
		SkillID:            toolString(input, "skillId"),
		Location:           toolString(input, "location"),
		LocationSearchName: toolString(input, "locationSearchName"),
	}
}

func financeQuoteInputFromTool(
	input map[string]any,
) ports.ExternalSearchRequest {
	request := ports.ExternalSearchRequest{
		Query:   toolString(input, "query"),
		SkillID: toolString(input, "skillId"),
	}
	request.Symbols = appendToolStringSlice(input["symbols"])
	if symbol := toolString(input, "symbol"); symbol != "" {
		request.Symbols = append(request.Symbols, symbol)
	}
	return request
}

func externalSearchToolResult(result ports.ExternalSearchResult) toolpkg.Result {
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
