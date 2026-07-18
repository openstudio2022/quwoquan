package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	rtgov "quwoquan_service/runtime/governance"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/application/tool"
)

func buildAgentLoop(cfg config, appEnv string) *application.AgentLoop {
	model, err := buildModelProvider(cfg.ModelProvider, appEnv)
	if err != nil {
		log.Fatalf("assistant-service model provider config invalid: %v", err)
	}
	registry, err := buildSearchRegistry(cfg.SearchProvider, cfg.ContentSearch, appEnv)
	if err != nil {
		log.Fatalf("assistant-service search provider config invalid: %v", err)
	}
	log.Printf("assistant-service provider config modelProvider=%s model=%s searchProvider=%s", cfg.ModelProvider.Provider, cfg.ModelProvider.Model, cfg.SearchProvider.Provider)
	return application.NewAgentLoop(application.ModelDrivenSkillRuntime{
		Model: model,
	}, application.ReactRuntime{
		Model: model,
		Tools: application.DefaultToolCoordinator{
			Registry: registry,
		},
	}, nil)
}

func buildModelProvider(cfg providerCfg, appEnv string) (application.ModelProvider, error) {
	provider := strings.TrimSpace(cfg.Provider)
	if provider == "" {
		provider = "deterministic"
	}
	switch provider {
	case "deterministic":
		if requiresRealProvider(appEnv) && !allowDeterministicProvider(appEnv) {
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

func buildSearchRegistry(cfg providerCfg, contentCfg contentSearchCfg, appEnv string) (tool.Registry, error) {
	provider := strings.TrimSpace(cfg.Provider)
	if provider == "" {
		provider = "fake"
	}
	contentBase := strings.TrimSpace(contentCfg.BaseURL)
	if provider == "fake" {
		if requiresRealProvider(appEnv) && !allowDeterministicProvider(appEnv) {
			return tool.Registry{}, fmt.Errorf("APP_ENV=%s requires real search_provider", appEnv)
		}
		registry := tool.DefaultRegistry()
		// 即便其余工具仍为 fake adapter，app_search 也优先直连 content-service 站内检索，
		// 让小艺在 alpha 等环境消费真实灌库内容（content base url 未配置时回退 fake）。
		if contentBase != "" {
			registry.Register(appSearchMetadata(), contentAppSearchHandler(contentBase, contentCfg.TimeoutMs))
		}
		return registry, nil
	}
	registry := tool.NewRegistry()
	registry.Register(tool.DefaultMetadata("mock_search"), func(context.Context, tool.Request) (tool.Result, error) {
		return tool.Result{}, fmt.Errorf("mock_search is disabled for configured assistant provider")
	})
	registry.Register(tool.Metadata{
		ToolName:           "web_search",
		DisplayName:        "网络搜索",
		Description:        "检索公开网络信息的云端工具。",
		Placement:          tool.PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "references"},
		Resilience:         tool.DefaultMetadata("web_search").Resilience,
		Recovery:           tool.DefaultMetadata("web_search").Recovery,
	}, realSearchHandler(cfg))
	// app_search 优先站内真实检索；未配置 content base url 时回退到外部搜索 adapter。
	if contentBase != "" {
		registry.Register(appSearchMetadata(), contentAppSearchHandler(contentBase, contentCfg.TimeoutMs))
	} else {
		registry.Register(appSearchMetadata(), realSearchHandler(cfg))
	}
	return registry, nil
}

// appSearchMetadata 是 app_search 工具的统一元数据（站内 / 外部两种 handler 共用）。
func appSearchMetadata() tool.Metadata {
	return tool.Metadata{
		ToolName:           "app_search",
		DisplayName:        "应用信息检索",
		Description:        "检索趣我圈站内内容（content posts）的云端工具。",
		Placement:          tool.PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "results"},
		Resilience:         tool.DefaultMetadata("app_search").Resilience,
		Recovery:           tool.DefaultMetadata("app_search").Recovery,
	}
}

// contentAppSearchHandler 让 app_search 直连 content-service 站内检索接口
// （GET /content/posts/search），返回真实 posts 供小艺 ReAct 消费与引用。
// 复用 searchHTTPClient（含 rtgov 熔断）的 egress 客户端。
func contentAppSearchHandler(baseURL string, timeoutMs int) tool.Handler {
	base := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	client := searchHTTPClient(timeoutMs)
	return func(ctx context.Context, req tool.Request) (tool.Result, error) {
		startedAt := time.Now()
		query := inputString(req.Input, "query")
		var payload struct {
			Items []struct {
				PostId        string `json:"postId"`
				ContentType   string `json:"contentType"`
				Title         string `json:"title"`
				Summary       string `json:"summary"`
				CategoryId    string `json:"categoryId"`
				SubCategory   string `json:"subCategory"`
				HighlightText string `json:"highlightText"`
			} `json:"items"`
		}
		usedQuery := strings.TrimSpace(query)
		for _, candidate := range contentSearchQueryCandidates(query) {
			endpoint := base + "/content/posts/search?limit=10&query=" + url.QueryEscape(candidate)
			httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
			if err != nil {
				return tool.Result{}, fmt.Errorf("app_search build request: %w", err)
			}
			resp, err := client.Do(httpReq)
			if err != nil {
				return tool.Result{}, fmt.Errorf("app_search content-service request: %w", err)
			}
			if resp.StatusCode != http.StatusOK {
				resp.Body.Close()
				return tool.Result{}, fmt.Errorf("app_search content-service status %d", resp.StatusCode)
			}
			payload.Items = nil
			if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
				resp.Body.Close()
				return tool.Result{}, fmt.Errorf("app_search decode response: %w", err)
			}
			resp.Body.Close()
			usedQuery = candidate
			if len(payload.Items) > 0 {
				break
			}
		}
		results := make([]map[string]any, 0, len(payload.Items))
		for _, it := range payload.Items {
			results = append(results, map[string]any{
				"objectType":    "content.post",
				"postId":        it.PostId,
				"title":         it.Title,
				"summary":       it.Summary,
				"contentType":   it.ContentType,
				"categoryId":    it.CategoryId,
				"subCategory":   it.SubCategory,
				"highlightText": it.HighlightText,
			})
		}
		log.Printf("assistant app_search content-backed query=%q usedQuery=%q results=%d durationMs=%d", query, usedQuery, len(results), time.Since(startedAt).Milliseconds())
		return tool.Result{Output: map[string]any{
			"provider": "content_internal",
			"summary":  fmt.Sprintf("app_search 命中 %d 条站内内容（query=%q）", len(results), usedQuery),
			"results":  results,
		}}, nil
	}
}

func contentSearchQueryCandidates(query string) []string {
	raw := strings.TrimSpace(query)
	if raw == "" {
		return []string{""}
	}
	candidates := []string{raw}
	normalized := raw
	for _, prefix := range []string{
		"站内查找一下", "站内搜索一下", "站内查找", "站内搜索",
		"帮我查找一下", "帮我搜索一下", "帮我查找", "帮我搜索",
		"请查找一下", "请搜索一下", "查找一下", "搜索一下",
		"请查找", "请搜索", "查找", "搜索",
	} {
		if strings.HasPrefix(normalized, prefix) {
			normalized = strings.TrimSpace(strings.TrimPrefix(normalized, prefix))
			break
		}
	}
	normalized = strings.Trim(normalized, " ：:，,。.!！?？")
	if normalized != "" && normalized != raw {
		candidates = append(candidates, normalized)
	}
	return candidates
}

func allowDeterministicProvider(appEnv string) bool {
	if strings.TrimSpace(os.Getenv("ALLOW_DETERMINISTIC_BETA")) != "1" {
		return false
	}
	switch appEnv {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
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
