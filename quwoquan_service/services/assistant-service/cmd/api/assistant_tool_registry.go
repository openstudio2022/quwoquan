package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"strings"
	"time"

	rtgov "quwoquan_service/runtime/governance"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/infrastructure/searchclient"
)

func buildAgentLoop(
	cfg config,
	appEnv string,
	internalSearch *searchclient.Client,
) (*application.AgentLoop, error) {
	model, err := buildModelProvider(cfg.ModelProvider, appEnv)
	if err != nil {
		return nil, fmt.Errorf("model provider config invalid: %w", err)
	}
	registry, err := buildSearchRegistry(cfg.SearchProvider, internalSearch, appEnv)
	if err != nil {
		return nil, fmt.Errorf("search provider config invalid: %w", err)
	}
	log.Printf("assistant-service provider config modelProvider=%s model=%s searchProvider=%s", cfg.ModelProvider.Provider, cfg.ModelProvider.Model, cfg.SearchProvider.Provider)
	return application.NewAgentLoop(application.ModelDrivenSkillRuntime{
		Model: model,
	}, application.ReactRuntime{
		Model: model,
		Tools: application.DefaultToolCoordinator{
			Registry: registry,
		},
	}, nil), nil
}

func buildModelProvider(cfg providerCfg, appEnv string) (application.ModelProvider, error) {
	provider := strings.TrimSpace(cfg.Provider)
	if provider == "" {
		provider = "deterministic"
	}
	switch provider {
	case "deterministic":
		if requiresRealProvider(appEnv) {
			return nil, fmt.Errorf("APP_ENV=%s requires real model_provider", appEnv)
		}
		return application.DeterministicModelProvider{}, nil
	case "openai_compatible":
		apiKey, err := providerAPIKey(cfg)
		if err != nil {
			return nil, err
		}
		if strings.TrimSpace(cfg.BaseURL) == "" {
			return nil, fmt.Errorf("model_provider.base_url is required")
		}
		if strings.TrimSpace(cfg.Model) == "" {
			return nil, fmt.Errorf("model_provider.model is required")
		}
		return openAICompatibleModelProvider{
			baseURL: strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/"),
			model:   strings.TrimSpace(cfg.Model),
			apiKey:  apiKey,
			client: rtgov.WrapClientWithCB(
				&http.Client{Timeout: providerTimeout(cfg.TimeoutMs)},
				rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
			),
		}, nil
	default:
		return nil, fmt.Errorf("unsupported model_provider.provider %q", provider)
	}
}

func buildSearchRegistry(
	cfg providerCfg,
	internalSearch *searchclient.Client,
	appEnv string,
) (tool.Registry, error) {
	provider := strings.TrimSpace(cfg.Provider)
	if provider == "" {
		provider = "disabled"
	}
	registry := tool.BaseRegistry()
	if internalSearch == nil {
		return tool.Registry{}, fmt.Errorf("canonical search client is required")
	}
	registry.Register(tool.AppSearchMetadata(), internalSearch.Handler())

	switch provider {
	case "disabled":
		if requiresRealProvider(appEnv) {
			return tool.Registry{}, fmt.Errorf("APP_ENV=%s requires real search_provider", appEnv)
		}
	case "duckduckgo_html":
		registry.Register(tool.WebSearchMetadata(), realSearchHandler(cfg))
	default:
		return tool.Registry{}, fmt.Errorf("unsupported search_provider.provider %q", provider)
	}
	return registry, nil
}

func realSearchHandler(cfg providerCfg) tool.Handler {
	provider := strings.TrimSpace(cfg.Provider)
	client := searchHTTPClient(cfg.TimeoutMs)
	return func(ctx context.Context, req tool.Request) (tool.Result, error) {
		startedAt := time.Now()
		query := inputString(req.Input, "query")
		location := inputString(req.Input, "location")
		locationSearchName := inputString(req.Input, "locationSearchName")
		skillID := inputString(req.Input, "skillId")
		queries := preferredSearchQueries(req.Input, query)
		log.Printf("assistant search requested provider=%s tool=%s query=%q", provider, req.ToolName, query)
		switch provider {
		case "duckduckgo_html":
			if shouldTryWeatherLookup(skillID, query, location, locationSearchName, req.Input) {
				if summary, refs, weatherProvider, ok := openMeteoWeatherSearch(ctx, client, query, location, locationSearchName); ok {
					log.Printf("assistant weather search completed provider=%s tool=%s query=%q refs=%d summaryLen=%d durationMs=%d", weatherProvider, req.ToolName, query, len(refs), len([]rune(summary)), time.Since(startedAt).Milliseconds())
					return searchToolResult(req.ToolName, weatherProvider, summary, refs, true), nil
				}
				summary, refs := deterministicSearchFallbackResult(query, "weather lookup failed")
				log.Printf("assistant weather search unavailable provider=open_meteo tool=%s query=%q", req.ToolName, query)
				return searchToolResult(req.ToolName, "open_meteo", summary, refs, false), nil
			}
			if shouldTryFinanceLookup(skillID, req.Input) {
				if summary, refs, ok := yahooFinanceSearch(ctx, client, req.Input); ok {
					log.Printf("assistant finance search completed provider=yahoo_finance tool=%s query=%q refs=%d summaryLen=%d durationMs=%d", req.ToolName, query, len(refs), len([]rune(summary)), time.Since(startedAt).Milliseconds())
					return searchToolResult(req.ToolName, "yahoo_finance", summary, refs, true), nil
				}
			}
			summary, refs, reliable, err := executeDuckDuckGoQueries(ctx, client, queries)
			if err != nil {
				log.Printf("assistant search failed provider=%s tool=%s query=%q err=%v", provider, req.ToolName, query, err)
				if bingSummary, bingRefs, ok := bingRSSSearch(ctx, client, query); ok {
					summary, refs, reliable = rebuildSearchOutcomeFromRefs(bingSummary, bingRefs), bingRefs, true
				} else {
					summary, refs = deterministicSearchFallbackResult(query, err.Error())
					reliable = false
				}
			}
			log.Printf("assistant search completed provider=%s tool=%s query=%q refs=%d summaryLen=%d durationMs=%d", provider, req.ToolName, query, len(refs), len([]rune(summary)), time.Since(startedAt).Milliseconds())
			return searchToolResult(req.ToolName, provider, summary, refs, reliable), nil
		default:
			return tool.Result{}, fmt.Errorf("unsupported search_provider.provider %q", provider)
		}
	}
}

func preferredSearchQueries(input map[string]any, fallbackQuery string) []string {
	queries := []string{}
	seen := map[string]bool{}
	appendOne := func(query string) {
		if query == "" || seen[query] {
			return
		}
		seen[query] = true
		queries = append(queries, query)
	}
	appendQueryCandidates := func(raw string) {
		base := strings.TrimSpace(raw)
		if base == "" {
			return
		}
		appendOne(base)
	}
	appendStructuredSearchQueries(input["searchQueries"], appendQueryCandidates)
	appendStructuredSearchQueries(input["queries"], appendQueryCandidates)
	appendQueryCandidates(fallbackQuery)
	return queries
}

func appendStructuredSearchQueries(raw any, appendOne func(string)) {
	switch items := raw.(type) {
	case []any:
		for _, item := range items {
			appendOne(searchQueryText(item))
		}
	case []map[string]any:
		for _, item := range items {
			appendOne(searchQueryText(item))
		}
	case []string:
		for _, item := range items {
			appendOne(searchQueryText(item))
		}
	}
}

func searchQueryText(raw any) string {
	switch item := raw.(type) {
	case map[string]any:
		if value := strings.TrimSpace(fmt.Sprint(item["query"])); value != "" && value != "<nil>" {
			return value
		}
		return ""
	case string:
		return strings.TrimSpace(item)
	default:
		value := strings.TrimSpace(fmt.Sprint(raw))
		if value == "<nil>" {
			return ""
		}
		return value
	}
}
