package main

import (
	"bytes"
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	htmlpkg "html"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/projection"
)

type redisPoolCfg struct {
	Size           int `yaml:"size"`
	MinIdle        int `yaml:"min_idle"`
	ReadTimeoutMs  int `yaml:"read_timeout_ms"`
	WriteTimeoutMs int `yaml:"write_timeout_ms"`
	DialTimeoutMs  int `yaml:"dial_timeout_ms"`
}

type redisSceneCfg struct {
	Mode     string       `yaml:"mode"`
	Addr     string       `yaml:"addr"`
	Addrs    []string     `yaml:"addrs"`
	Password string       `yaml:"password"`
	DB       int          `yaml:"db"`
	TLS      bool         `yaml:"tls"`
	Pool     redisPoolCfg `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Postgres struct {
		DSN                    string `yaml:"dsn"`
		MaxOpenConns           int    `yaml:"max_open_conns"`
		MaxIdleConns           int    `yaml:"max_idle_conns"`
		ConnMaxLifetimeMinutes int    `yaml:"conn_max_lifetime_minutes"`
	} `yaml:"postgres"`
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Redis struct {
		Rec     redisSceneCfg `yaml:"rec"`
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
	ModelProvider  providerCfg `yaml:"model_provider"`
	SearchProvider providerCfg `yaml:"search_provider"`
}

type providerCfg struct {
	Provider  string `yaml:"provider"`
	BaseURL   string `yaml:"base_url"`
	Model     string `yaml:"model"`
	APIKeyEnv string `yaml:"api_key_env"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("assistant-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("assistant-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("assistant-service config compatibility failed: %v", err)
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("assistant-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("assistant-service exception logger init failed: %v", err)
	}
	router := buildRedisRouter(cfg)
	defer router.Close()
	ctx := context.Background()

	var eventStore application.EventStore
	var profileStore application.LearningProfileStore
	var subscriptionStore application.SkillSubscriptionStore
	if strings.TrimSpace(cfg.MongoDB.URI) != "" {
		mongoClient, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoDB.URI))
		if err != nil {
			log.Fatalf("assistant-service mongo connect failed: %v", err)
		}
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = mongoClient.Disconnect(shutdownCtx)
		}()
		dbName := cfg.MongoDB.Database
		if strings.TrimSpace(dbName) == "" {
			dbName = "quwoquan_assistant"
		}
		db := mongoClient.Database(dbName)
		mongoStore := persistence.NewMongoEventStore(db)
		if err := mongoStore.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure mongo indexes: %v", err)
		}
		eventStore = mongoStore
		mongoProfiles := projection.NewLearningProfileStore(db)
		if err := mongoProfiles.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure learning profile indexes: %v", err)
		}
		profileStore = mongoProfiles
		mongoSubscriptions := persistence.NewMongoSkillSubscriptionStore(db)
		if err := mongoSubscriptions.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure skill subscription indexes: %v", err)
		}
		subscriptionStore = mongoSubscriptions
		log.Printf("assistant-service events storage=mongodb db=%s", dbName)
		log.Printf("assistant-service learning profile storage=mongodb db=%s", dbName)
		log.Printf("assistant-service skill subscription storage=mongodb db=%s", dbName)
	} else {
		eventStore = persistence.NewMemoryEventStore()
		profileStore = projection.NewMemoryLearningProfileStore()
		subscriptionStore = persistence.NewMemorySkillSubscriptionStore()
		log.Printf("assistant-service events storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service learning profile storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service skill subscription storage=inmemory (no mongodb.uri configured)")
	}

	var consentStore application.ConsentStore
	if strings.TrimSpace(cfg.Postgres.DSN) != "" {
		poolCfg, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
		if err != nil {
			log.Fatalf("assistant-service postgres parse failed: %v", err)
		}
		if cfg.Postgres.MaxOpenConns > 0 {
			poolCfg.MaxConns = int32(cfg.Postgres.MaxOpenConns)
		}
		if cfg.Postgres.MaxIdleConns > 0 {
			poolCfg.MinConns = int32(cfg.Postgres.MaxIdleConns)
		}
		if cfg.Postgres.ConnMaxLifetimeMinutes > 0 {
			poolCfg.MaxConnLifetime = time.Duration(cfg.Postgres.ConnMaxLifetimeMinutes) * time.Minute
		}
		pgPool, err := pgxpool.NewWithConfig(ctx, poolCfg)
		if err != nil {
			log.Fatalf("assistant-service postgres connect failed: %v", err)
		}
		defer pgPool.Close()
		pgStore := persistence.NewPgConsentStore(pgPool)
		if err := pgStore.EnsureSchema(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure pg schema: %v", err)
		}
		consentStore = pgStore
		log.Printf("assistant-service consent storage=postgres")
	} else {
		consentStore = persistence.NewMemoryConsentStore()
		log.Printf("assistant-service consent storage=inmemory (no postgres.dsn configured)")
	}

	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	service := application.NewAssistantService(
		eventStore,
		consentStore,
		router.Scene("general"),
		application.WithLearningProfileStore(profileStore),
		application.WithEventPublisher(publisher),
		application.WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
		application.WithSkillSubscriptionStore(subscriptionStore),
		application.WithAgentLoop(buildAgentLoop(cfg, appEnv)),
	)
	if seedRefs := scenarioSeedRefsFromEnv(); len(seedRefs) > 0 {
		pack, err := application.LoadAssistantScenarioPack()
		if err != nil {
			log.Fatalf("assistant-service scenario seed load failed: %v", err)
		}
		if err := application.SeedAssistantServiceFromScenarioPack(ctx, service, "user_m11_scenario", pack, seedRefs); err != nil {
			log.Fatalf("assistant-service scenario seed failed: %v", err)
		}
		log.Printf("assistant-service scenario seed loaded refs=%s", strings.Join(seedRefs, ","))
	}
	handler := httpadapter.NewHandler(service).Routes()
	observedHandler := rthttp.NewHTTPServerMiddleware(handler, rthttp.HTTPServerMiddlewareConfig{
		Service:           "assistant-service",
		ServiceName:       "assistant-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "assistant-service",
		Src:               "assistant-service",
	}, ioLogger, processLogger, exceptionLogger)
	server := &http.Server{Addr: addr, Handler: observedHandler, ReadHeaderTimeout: 5 * time.Second, WriteTimeout: assistantHTTPWriteTimeout(), IdleTimeout: 60 * time.Second}
	log.Printf("assistant-service listening on %s env=%s", addr, appEnv)
	if err := runHTTPServerWithGracefulShutdown(server, assistantShutdownTimeout()); err != nil {
		log.Fatalf("assistant-service listen failed: %v", err)
	}
}

func runHTTPServerWithGracefulShutdown(server *http.Server, shutdownTimeout time.Duration) error {
	signalCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	select {
	case err := <-errCh:
		return err
	case <-signalCtx.Done():
		stop()
	}

	log.Printf("assistant-service shutdown signal received; draining for %s", shutdownTimeout)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("WARN: assistant-service graceful shutdown failed: %v", err)
		_ = server.Close()
		return err
	}
	if err := <-errCh; err != nil {
		return err
	}
	log.Printf("assistant-service shutdown complete")
	return nil
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "assistant-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")
	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod-gray|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, fmt.Errorf("read default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		if err := mergeConfigFile(&cfg, localDefault); err != nil {
			return config{}, fmt.Errorf("read local default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, localEnv); err != nil {
			return config{}, fmt.Errorf("read local env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join("..", "..", "..", "releases", "config", serviceName, configVersion+".yaml")
			if _, err := os.Stat(versionFile); err == nil {
				if err := mergeConfigFile(&cfg, versionFile); err != nil {
					return config{}, fmt.Errorf("read local version config: %w", err)
				}
			}
		}
		return cfg, nil
	}
	current := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, current); err != nil {
		return config{}, fmt.Errorf("read current config: %w", err)
	}
	return cfg, nil
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, cfg)
}

func applyEnvOverrides(cfg *config) {
	if v := strings.TrimSpace(os.Getenv("MONGODB_URI")); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("MONGODB_DATABASE")); v != "" {
		cfg.MongoDB.Database = v
	}
	if v := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); v != "" {
		cfg.Postgres.DSN = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_GENERAL_ADDR")); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv("REDIS_REC_ADDR")); v != "" {
		cfg.Redis.Rec.Addr = v
	}
	applyProviderEnvOverrides(&cfg.ModelProvider, "ASSISTANT_MODEL")
	applyProviderEnvOverrides(&cfg.SearchProvider, "ASSISTANT_SEARCH")
}

func applyProviderEnvOverrides(cfg *providerCfg, prefix string) {
	if v := strings.TrimSpace(os.Getenv(prefix + "_PROVIDER")); v != "" {
		cfg.Provider = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_BASE_URL")); v != "" {
		cfg.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_MODEL")); v != "" {
		cfg.Model = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_API_KEY_ENV")); v != "" {
		cfg.APIKeyEnv = v
	}
}

func buildAgentLoop(cfg config, appEnv string) *application.AgentLoop {
	model, err := buildModelProvider(cfg.ModelProvider, appEnv)
	if err != nil {
		log.Fatalf("assistant-service model provider config invalid: %v", err)
	}
	registry, err := buildSearchRegistry(cfg.SearchProvider, appEnv)
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
			client:  &http.Client{Timeout: providerTimeout(cfg.TimeoutMs)},
		}, nil
	default:
		return nil, fmt.Errorf("unsupported model_provider.provider %q", provider)
	}
}

func buildSearchRegistry(cfg providerCfg, appEnv string) (tool.Registry, error) {
	provider := strings.TrimSpace(cfg.Provider)
	if provider == "" {
		provider = "fake"
	}
	if provider == "fake" {
		if requiresRealProvider(appEnv) && !allowDeterministicProvider(appEnv) {
			return tool.Registry{}, fmt.Errorf("APP_ENV=%s requires real search_provider", appEnv)
		}
		return tool.DefaultRegistry(), nil
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
	registry.Register(tool.Metadata{
		ToolName:           "app_search",
		DisplayName:        "应用信息检索",
		Description:        "检索趣我圈站内内容、聊天、圈子和用户对象的云端工具。",
		Placement:          tool.PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "results"},
		Resilience:         tool.DefaultMetadata("app_search").Resilience,
		Recovery:           tool.DefaultMetadata("app_search").Recovery,
	}, realSearchHandler(cfg))
	return registry, nil
}

func allowDeterministicProvider(appEnv string) bool {
	if strings.TrimSpace(os.Getenv("ALLOW_DETERMINISTIC_BETA")) != "1" {
		return false
	}
	return appEnv == "beta" || appEnv == "gamma"
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
			summary, refs, err := duckDuckGoHTMLSearch(ctx, client, query)
			reliable := true
			if err != nil {
				log.Printf("assistant search failed provider=%s tool=%s query=%q err=%v", provider, req.ToolName, query, err)
				if bingSummary, bingRefs, ok := bingRSSSearch(ctx, client, query); ok {
					summary, refs = bingSummary, bingRefs
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

func searchToolResult(toolName string, provider string, summary string, refs []map[string]any, reliable bool) tool.Result {
	if toolName == "app_search" {
		return tool.Result{Output: map[string]any{
			"provider": provider,
			"summary":  summary,
			"results":  refs,
			"reliable": reliable,
		}}
	}
	return tool.Result{Output: map[string]any{
		"provider":   provider,
		"summary":    summary,
		"references": refs,
		"reliable":   reliable,
	}}
}

func duckDuckGoHTMLSearch(ctx context.Context, client *http.Client, query string) (string, []map[string]any, error) {
	if query == "" {
		return "", nil, fmt.Errorf("search query is required")
	}
	endpoint := "https://duckduckgo.com/html/?q=" + url.QueryEscape(query)
	log.Printf("assistant duckduckgo request query=%q", query)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()
	log.Printf("assistant duckduckgo response query=%q status=%d", query, resp.StatusCode)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", nil, fmt.Errorf("duckduckgo status=%d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return "", nil, err
	}
	summary, refs := extractDuckDuckGoResults(string(body))
	if summary == "" {
		log.Printf("assistant duckduckgo fallback query=%q reason=empty_summary", query)
		return "", nil, fmt.Errorf("empty_summary")
	}
	log.Printf("assistant duckduckgo parsed query=%q refs=%d summaryLen=%d", query, len(refs), len([]rune(summary)))
	return summary, refs, nil
}

func stripHTML(raw string) string {
	var out strings.Builder
	inTag := false
	for _, r := range raw {
		switch r {
		case '<':
			inTag = true
		case '>':
			inTag = false
			out.WriteRune(' ')
		default:
			if !inTag {
				out.WriteRune(r)
			}
		}
	}
	return out.String()
}

var (
	duckDuckGoTitlePattern   = regexp.MustCompile(`(?is)<a[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>`)
	duckDuckGoSnippetPattern = regexp.MustCompile(`(?is)<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>`)
)

func extractDuckDuckGoResults(raw string) (string, []map[string]any) {
	titles := duckDuckGoTitlePattern.FindAllStringSubmatch(raw, 3)
	snippets := duckDuckGoSnippetPattern.FindAllStringSubmatch(raw, 3)
	refs := []map[string]any{}
	parts := []string{}
	for i, titleMatch := range titles {
		title := cleanSearchText(titleMatch[1])
		snippet := ""
		if i < len(snippets) {
			for _, candidate := range snippets[i][1:] {
				if strings.TrimSpace(candidate) != "" {
					snippet = cleanSearchText(candidate)
					break
				}
			}
		}
		if title == "" && snippet == "" {
			continue
		}
		if snippet == "" {
			snippet = title
		}
		parts = append(parts, snippet)
		refs = append(refs, map[string]any{
			"title":   title,
			"source":  "duckduckgo_html",
			"snippet": snippet,
		})
	}
	summary := strings.Join(parts, "；")
	summary = truncateRunes(summary, 500)
	return summary, refs
}

func truncateRunes(s string, maxRunes int) string {
	runes := []rune(s)
	if len(runes) <= maxRunes {
		return s
	}
	return string(runes[:maxRunes])
}

func cleanSearchText(raw string) string {
	text := htmlpkg.UnescapeString(stripHTML(raw))
	text = strings.Join(strings.Fields(text), " ")
	return strings.TrimSpace(text)
}

func deterministicSearchFallback(query string) string {
	return fmt.Sprintf("已围绕“%s”尝试检索，但外部搜索未返回可靠结构化摘要；请基于用户问题与已有上下文回答，明确不确定性，不虚构实时事实。", query)
}

func deterministicSearchFallbackResult(query string, reason string) (string, []map[string]any) {
	summary := deterministicSearchFallback(query)
	_ = reason
	return summary, []map[string]any{}
}

func inputString(input map[string]any, key string) string {
	value := strings.TrimSpace(fmt.Sprint(input[key]))
	if value == "<nil>" {
		return ""
	}
	return value
}

func yahooFinanceSymbols(input map[string]any) []string {
	symbols := []string{}
	add := func(raw any) {
		symbol := strings.ToUpper(strings.TrimSpace(fmt.Sprint(raw)))
		if symbol == "" || symbol == "<NIL>" {
			return
		}
		matched, _ := regexp.MatchString(`^[0-9]{6}\.(SZ|SS|SH)$|^[A-Z]{1,6}(\.[A-Z]{1,3})?$`, symbol)
		if matched {
			symbols = append(symbols, symbol)
		}
	}
	add(input["symbol"])
	switch items := input["symbols"].(type) {
	case []any:
		for _, item := range items {
			add(item)
		}
	case []string:
		for _, item := range items {
			add(item)
		}
	}
	query := inputString(input, "query")
	for _, match := range regexp.MustCompile(`[0-9]{6}\.(?:SZ|SS|SH)|[A-Z]{1,6}(?:\.[A-Z]{1,3})?`).FindAllString(strings.ToUpper(query), 4) {
		add(match)
	}
	if len(symbols) == 0 {
		return nil
	}
	seen := map[string]bool{}
	unique := []string{}
	for _, symbol := range symbols {
		if seen[symbol] {
			continue
		}
		seen[symbol] = true
		unique = append(unique, symbol)
	}
	return unique
}

func shouldTryFinanceLookup(skillID string, input map[string]any) bool {
	if strings.Contains(skillID, "finance") || strings.Contains(skillID, "stock") {
		return true
	}
	return inputString(input, "symbol") != "" || len(symbolList(input["symbols"])) > 0
}

func symbolList(raw any) []string {
	switch items := raw.(type) {
	case []any:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" && text != "<nil>" {
				out = append(out, text)
			}
		}
		return out
	case []string:
		return items
	default:
		return nil
	}
}

type yahooFinanceChartResponse struct {
	Chart struct {
		Result []struct {
			Meta struct {
				Symbol               string  `json:"symbol"`
				Currency             string  `json:"currency"`
				LongName             string  `json:"longName"`
				ShortName            string  `json:"shortName"`
				RegularMarketTime    int64   `json:"regularMarketTime"`
				RegularMarketPrice   float64 `json:"regularMarketPrice"`
				RegularMarketDayHigh float64 `json:"regularMarketDayHigh"`
				RegularMarketDayLow  float64 `json:"regularMarketDayLow"`
				RegularMarketVolume  int64   `json:"regularMarketVolume"`
				ChartPreviousClose   float64 `json:"chartPreviousClose"`
				Timezone             string  `json:"timezone"`
				ExchangeName         string  `json:"exchangeName"`
			} `json:"meta"`
			Timestamp  []int64 `json:"timestamp"`
			Indicators struct {
				Quote []struct {
					Close []float64 `json:"close"`
				} `json:"quote"`
			} `json:"indicators"`
		} `json:"result"`
		Error any `json:"error"`
	} `json:"chart"`
}

func yahooFinanceSearch(ctx context.Context, client *http.Client, input map[string]any) (string, []map[string]any, bool) {
	symbols := yahooFinanceSymbols(input)
	if len(symbols) == 0 {
		return "", nil, false
	}
	parts := []string{}
	refs := []map[string]any{}
	for _, symbol := range symbols {
		endpoint := "https://query1.finance.yahoo.com/v8/finance/chart/" + url.PathEscape(symbol) + "?range=5d&interval=1d"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			continue
		}
		req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
		resp, err := client.Do(req)
		if err != nil {
			log.Printf("assistant yahoo_finance failed symbol=%s err=%v", symbol, err)
			continue
		}
		func() {
			defer resp.Body.Close()
			if resp.StatusCode < 200 || resp.StatusCode >= 300 {
				log.Printf("assistant yahoo_finance status symbol=%s status=%d", symbol, resp.StatusCode)
				return
			}
			var decoded yahooFinanceChartResponse
			if err := json.NewDecoder(io.LimitReader(resp.Body, 128*1024)).Decode(&decoded); err != nil {
				log.Printf("assistant yahoo_finance decode failed symbol=%s err=%v", symbol, err)
				return
			}
			if len(decoded.Chart.Result) == 0 {
				return
			}
			meta := decoded.Chart.Result[0].Meta
			name := strings.TrimSpace(meta.LongName)
			if name == "" {
				name = strings.TrimSpace(meta.ShortName)
			}
			if name == "" {
				name = symbol
			}
			change := meta.RegularMarketPrice - meta.ChartPreviousClose
			changePct := 0.0
			if meta.ChartPreviousClose != 0 {
				changePct = change / meta.ChartPreviousClose * 100
			}
			marketTime := time.Unix(meta.RegularMarketTime, 0).UTC().Format(time.RFC3339)
			snippet := fmt.Sprintf(
				"Yahoo Finance 行情：%s（%s，%s）最新价 %.2f %s，较前收 %.2f 变化 %.2f（%.2f%%），日内 %.2f-%.2f，成交量 %d，市场时间 %s。",
				name,
				meta.Symbol,
				meta.ExchangeName,
				meta.RegularMarketPrice,
				meta.Currency,
				meta.ChartPreviousClose,
				change,
				changePct,
				meta.RegularMarketDayLow,
				meta.RegularMarketDayHigh,
				meta.RegularMarketVolume,
				marketTime,
			)
			parts = append(parts, snippet)
			refs = append(refs, map[string]any{
				"title":   "Yahoo Finance - " + name + " (" + meta.Symbol + ")",
				"url":     endpoint,
				"source":  "yahoo_finance",
				"snippet": snippet,
			})
		}()
	}
	if len(parts) == 0 {
		return "", nil, false
	}
	return strings.Join(parts, "；"), refs, true
}

type bingRSS struct {
	Channel struct {
		Items []struct {
			Title       string `xml:"title"`
			Link        string `xml:"link"`
			Description string `xml:"description"`
			PubDate     string `xml:"pubDate"`
		} `xml:"item"`
	} `xml:"channel"`
}

func bingRSSSearch(ctx context.Context, client *http.Client, query string) (string, []map[string]any, bool) {
	query = strings.TrimSpace(query)
	if query == "" {
		return "", nil, false
	}
	endpoint := "https://www.bing.com/search?format=rss&q=" + url.QueryEscape(query)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, false
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 quwoquan-assistant-beta/1.0")
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("assistant bing_rss failed query=%q err=%v", query, err)
		return "", nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("assistant bing_rss status query=%q status=%d", query, resp.StatusCode)
		return "", nil, false
	}
	var decoded bingRSS
	if err := xml.NewDecoder(io.LimitReader(resp.Body, 128*1024)).Decode(&decoded); err != nil {
		log.Printf("assistant bing_rss decode failed query=%q err=%v", query, err)
		return "", nil, false
	}
	refs := []map[string]any{}
	parts := []string{}
	required := firstSearchToken(query)
	for _, item := range decoded.Channel.Items {
		title := cleanSearchText(item.Title)
		snippet := cleanSearchText(item.Description)
		if title == "" && snippet == "" {
			continue
		}
		if required != "" && !strings.Contains(title+snippet, required) {
			continue
		}
		if snippet == "" {
			snippet = title
		}
		parts = append(parts, snippet)
		refs = append(refs, map[string]any{
			"title":   title,
			"url":     strings.TrimSpace(item.Link),
			"source":  "bing_rss",
			"snippet": snippet,
			"pubDate": item.PubDate,
		})
		if len(refs) >= 5 {
			break
		}
	}
	if len(parts) == 0 {
		return "", nil, false
	}
	return truncateRunes(strings.Join(parts, "；"), 500), refs, true
}

func firstSearchToken(query string) string {
	for _, token := range strings.Fields(query) {
		token = strings.TrimSpace(token)
		if len([]rune(token)) >= 2 {
			return token
		}
	}
	return ""
}

func shouldTryWeatherLookup(skillID, query, location, locationSearchName string, input map[string]any) bool {
	if strings.TrimSpace(location) != "" {
		return true
	}
	if strings.TrimSpace(locationSearchName) != "" {
		return true
	}
	normalized := strings.ToLower(strings.TrimSpace(query))
	if skillID == "weather" {
		return true
	}
	if searchQueriesMentionWeather(input["searchQueries"]) || searchQueriesMentionWeather(input["queries"]) {
		return true
	}
	return strings.Contains(normalized, "天气") ||
		strings.Contains(normalized, "气温") ||
		strings.Contains(normalized, "降雨") ||
		strings.Contains(normalized, "weather") ||
		strings.Contains(normalized, "forecast")
}

func searchQueriesMentionWeather(raw any) bool {
	switch items := raw.(type) {
	case []any:
		for _, item := range items {
			if searchQueryMentionsWeather(item) {
				return true
			}
		}
	case []map[string]any:
		for _, item := range items {
			if searchQueryMentionsWeather(item) {
				return true
			}
		}
	}
	return false
}

func searchQueryMentionsWeather(raw any) bool {
	text := strings.ToLower(strings.TrimSpace(fmt.Sprint(raw)))
	if text == "" || text == "<nil>" {
		return false
	}
	return strings.Contains(text, "天气") ||
		strings.Contains(text, "气温") ||
		strings.Contains(text, "降雨") ||
		strings.Contains(text, "weather") ||
		strings.Contains(text, "forecast")
}

func weatherLocationCandidate(query, location string) string {
	candidate := strings.TrimSpace(location)
	if candidate == "" {
		candidate = strings.TrimSpace(query)
	}
	replacements := []string{
		"天气预报", "", "天气", "", "气温", "", "温度", "", "预报", "",
		"weather", "", "forecast", "",
		"今天", "", "明天", "", "当前", "", "现在", "",
		"怎么样", "", "如何", "", "查询", "", "搜索", "",
		"？", "", "?", "", "。", "", "，", "", ",", "", "“", "", "”", "", "\"", "",
	}
	replacer := strings.NewReplacer(replacements...)
	candidate = strings.TrimSpace(replacer.Replace(candidate))
	if len([]rune(candidate)) > 24 {
		return ""
	}
	return candidate
}

type openMeteoGeocodeResponse struct {
	Results []struct {
		Name      string  `json:"name"`
		Latitude  float64 `json:"latitude"`
		Longitude float64 `json:"longitude"`
		Country   string  `json:"country"`
		Admin1    string  `json:"admin1"`
		Timezone  string  `json:"timezone"`
	} `json:"results"`
}

type openMeteoForecastResponse struct {
	Timezone string `json:"timezone"`
	Current  struct {
		Time             string  `json:"time"`
		Temperature2m    float64 `json:"temperature_2m"`
		ApparentTemp     float64 `json:"apparent_temperature"`
		RelativeHumidity int     `json:"relative_humidity_2m"`
		Precipitation    float64 `json:"precipitation"`
		WeatherCode      int     `json:"weather_code"`
		WindSpeed10m     float64 `json:"wind_speed_10m"`
	} `json:"current"`
	Daily struct {
		Time                     []string  `json:"time"`
		WeatherCode              []int     `json:"weather_code"`
		Temperature2mMax         []float64 `json:"temperature_2m_max"`
		Temperature2mMin         []float64 `json:"temperature_2m_min"`
		PrecipitationProbability []int     `json:"precipitation_probability_max"`
	} `json:"daily"`
}

type metNoForecastResponse struct {
	Properties struct {
		Timeseries []struct {
			Time string `json:"time"`
			Data struct {
				Instant struct {
					Details struct {
						AirTemperature   float64 `json:"air_temperature"`
						RelativeHumidity float64 `json:"relative_humidity"`
						WindSpeed        float64 `json:"wind_speed"`
					} `json:"details"`
				} `json:"instant"`
				Next1Hours struct {
					Summary struct {
						SymbolCode string `json:"symbol_code"`
					} `json:"summary"`
					Details struct {
						PrecipitationAmount float64 `json:"precipitation_amount"`
					} `json:"details"`
				} `json:"next_1_hours"`
				Next6Hours struct {
					Summary struct {
						SymbolCode string `json:"symbol_code"`
					} `json:"summary"`
					Details struct {
						PrecipitationAmount float64 `json:"precipitation_amount"`
					} `json:"details"`
				} `json:"next_6_hours"`
			} `json:"data"`
		} `json:"timeseries"`
	} `json:"properties"`
}

func openMeteoWeatherSearch(ctx context.Context, client *http.Client, query, location, locationSearchName string) (string, []map[string]any, string, bool) {
	candidates := []string{}
	if strings.TrimSpace(locationSearchName) != "" {
		candidates = append(candidates, strings.TrimSpace(locationSearchName))
	}
	candidate := weatherLocationCandidate(query, location)
	if candidate == "" {
		return "", nil, "", false
	}
	candidates = append(candidates, candidate)
	seenCandidates := map[string]bool{}
	for _, item := range candidates {
		if seenCandidates[item] {
			continue
		}
		seenCandidates[item] = true
		if summary, refs, provider, ok := openMeteoWeatherSearchCandidate(ctx, client, item); ok {
			return summary, refs, provider, true
		}
	}
	return "", nil, "", false
}

func openMeteoWeatherSearchCandidate(ctx context.Context, client *http.Client, candidate string) (string, []map[string]any, string, bool) {
	geoURL := "https://geocoding-api.open-meteo.com/v1/search?count=5&language=zh&format=json&name=" + url.QueryEscape(candidate)
	geoReq, err := http.NewRequestWithContext(ctx, http.MethodGet, geoURL, nil)
	if err != nil {
		return "", nil, "", false
	}
	geoReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	geoResp, err := client.Do(geoReq)
	if err != nil {
		log.Printf("assistant open_meteo geocode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	defer geoResp.Body.Close()
	if geoResp.StatusCode < 200 || geoResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo geocode status location=%q status=%d", candidate, geoResp.StatusCode)
		return "", nil, "", false
	}
	var geo openMeteoGeocodeResponse
	if err := json.NewDecoder(io.LimitReader(geoResp.Body, 128*1024)).Decode(&geo); err != nil {
		log.Printf("assistant open_meteo geocode decode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	if len(geo.Results) == 0 {
		log.Printf("assistant open_meteo geocode empty location=%q", candidate)
		return "", nil, "", false
	}
	place := geo.Results[0]
	tz := strings.TrimSpace(place.Timezone)
	if tz == "" {
		tz = "auto"
	}
	forecastURL := fmt.Sprintf(
		"https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=%s&forecast_days=3",
		strconv.FormatFloat(place.Latitude, 'f', -1, 64),
		strconv.FormatFloat(place.Longitude, 'f', -1, 64),
		url.QueryEscape(tz),
	)
	forecastReq, err := http.NewRequestWithContext(ctx, http.MethodGet, forecastURL, nil)
	if err != nil {
		return "", nil, "", false
	}
	forecastReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	forecastResp, err := client.Do(forecastReq)
	if err != nil {
		log.Printf("assistant open_meteo forecast failed location=%q err=%v", candidate, err)
		return metNoWeatherSearch(ctx, client, place.Name, place.Admin1, place.Latitude, place.Longitude)
	}
	defer forecastResp.Body.Close()
	if forecastResp.StatusCode < 200 || forecastResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo forecast status location=%q status=%d", candidate, forecastResp.StatusCode)
		return metNoWeatherSearch(ctx, client, place.Name, place.Admin1, place.Latitude, place.Longitude)
	}
	var forecast openMeteoForecastResponse
	if err := json.NewDecoder(io.LimitReader(forecastResp.Body, 128*1024)).Decode(&forecast); err != nil {
		log.Printf("assistant open_meteo forecast decode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	placeName := place.Name
	if place.Admin1 != "" {
		placeName = placeName + "，" + place.Admin1
	}
	current := forecast.Current
	dailyParts := []string{}
	for i := range forecast.Daily.Time {
		if i >= 3 || i >= len(forecast.Daily.Temperature2mMax) || i >= len(forecast.Daily.Temperature2mMin) {
			break
		}
		weather := ""
		if i < len(forecast.Daily.WeatherCode) {
			weather = weatherCodeText(forecast.Daily.WeatherCode[i])
		}
		precip := ""
		if i < len(forecast.Daily.PrecipitationProbability) {
			precip = fmt.Sprintf("，降水概率%d%%", forecast.Daily.PrecipitationProbability[i])
		}
		dailyParts = append(dailyParts, fmt.Sprintf("%s：%s，%.0f-%.0f°C%s", forecast.Daily.Time[i], weather, forecast.Daily.Temperature2mMin[i], forecast.Daily.Temperature2mMax[i], precip))
	}
	summary := fmt.Sprintf(
		"Open-Meteo 实时天气：%s 当前%s，气温%.1f°C，体感%.1f°C，湿度%d%%，降水%.1fmm，风速%.1fkm/h。未来三天：%s。数据时间：%s（%s）。",
		placeName,
		weatherCodeText(current.WeatherCode),
		current.Temperature2m,
		current.ApparentTemp,
		current.RelativeHumidity,
		current.Precipitation,
		current.WindSpeed10m,
		strings.Join(dailyParts, "；"),
		current.Time,
		tz,
	)
	summary = withLocalWeatherAuthoritySummary(candidate, placeName, "Open-Meteo", summary)
	refs := []map[string]any{
		{
			"title":   "Open-Meteo Forecast API - " + placeName,
			"url":     "https://open-meteo.com/en/docs",
			"source":  "open_meteo_forecast",
			"snippet": summary + " 原始 forecast endpoint: " + forecastURL,
		},
		{
			"title":   "Open-Meteo Geocoding API - " + placeName,
			"url":     "https://open-meteo.com/en/docs/geocoding-api",
			"source":  "open_meteo_geocoding",
			"snippet": fmt.Sprintf("地理解析命中：%s，经纬度 %.5f, %.5f，时区 %s。原始 geocoding endpoint: %s", placeName, place.Latitude, place.Longitude, tz, geoURL),
		},
		{
			"title":   "Open-Meteo Weather Forecast API 文档",
			"url":     "https://open-meteo.com/en/docs",
			"source":  "open_meteo_docs",
			"snippet": "Open-Meteo 天气预报接口说明，包含 current 与 daily 预报字段定义。",
		},
	}
	refs = withLocalWeatherAuthorityReferences(candidate, placeName, refs)
	return summary, refs, "open_meteo", true
}

func metNoWeatherSearch(ctx context.Context, client *http.Client, name, admin string, lat, lon float64) (string, []map[string]any, string, bool) {
	endpoint := fmt.Sprintf(
		"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%s&lon=%s",
		strconv.FormatFloat(lat, 'f', -1, 64),
		strconv.FormatFloat(lon, 'f', -1, 64),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, "", false
	}
	req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0 contact=dev@quwoquan.local")
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("assistant met_no forecast failed location=%q err=%v", name, err)
		return "", nil, "", false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("assistant met_no forecast status location=%q status=%d", name, resp.StatusCode)
		return "", nil, "", false
	}
	var forecast metNoForecastResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, 256*1024)).Decode(&forecast); err != nil {
		log.Printf("assistant met_no forecast decode failed location=%q err=%v", name, err)
		return "", nil, "", false
	}
	if len(forecast.Properties.Timeseries) == 0 {
		log.Printf("assistant met_no forecast empty location=%q", name)
		return "", nil, "", false
	}
	placeName := strings.TrimSpace(name)
	if strings.TrimSpace(admin) != "" {
		placeName = placeName + "，" + strings.TrimSpace(admin)
	}
	current := forecast.Properties.Timeseries[0]
	details := current.Data.Instant.Details
	symbol := strings.ReplaceAll(current.Data.Next1Hours.Summary.SymbolCode, "_", " ")
	if symbol == "" {
		symbol = strings.ReplaceAll(current.Data.Next6Hours.Summary.SymbolCode, "_", " ")
	}
	precip := current.Data.Next1Hours.Details.PrecipitationAmount
	if precip == 0 {
		precip = current.Data.Next6Hours.Details.PrecipitationAmount
	}
	summary := fmt.Sprintf(
		"MET Norway Locationforecast 实时天气：%s 当前气温%.1f°C，湿度%.0f%%，风速%.1fm/s，近期天气符号%s，未来降水量%.1fmm。数据时间：%s。",
		placeName,
		details.AirTemperature,
		details.RelativeHumidity,
		details.WindSpeed,
		symbol,
		precip,
		current.Time,
	)
	summary = withLocalWeatherAuthoritySummary(name+" "+admin, placeName, "MET Norway", summary)
	refs := []map[string]any{
		{
			"title":   "MET Norway Locationforecast - " + placeName,
			"url":     "https://api.met.no/weatherapi/locationforecast/2.0/documentation",
			"source":  "met_no_locationforecast",
			"snippet": summary + " 原始 endpoint: " + endpoint,
		},
		{
			"title":   "MET Norway Locationforecast 数据模型说明",
			"url":     "https://api.met.no/weatherapi/locationforecast/2.0/documentation",
			"source":  "met_no_locationforecast_docs",
			"snippet": "Locationforecast 接口说明，包含 instant、next_1_hours、next_6_hours 等字段定义。",
		},
		{
			"title":   "Norwegian Meteorological Institute API Terms",
			"url":     "https://developer.yr.no/doc/TermsOfService/",
			"source":  "met_no_terms",
			"snippet": "MET Norway / Yr 开放天气 API 使用条款与数据来源说明。",
		},
	}
	refs = withLocalWeatherAuthorityReferences(name+" "+admin, placeName, refs)
	return summary, refs, "met_no", true
}

func withLocalWeatherAuthoritySummary(query, placeName, structuredProvider, summary string) string {
	if len(weatherAuthorityReferences(query, placeName)) == 0 {
		return summary
	}
	provider := strings.TrimSpace(structuredProvider)
	if provider == "" {
		provider = "结构化天气 API"
	}
	return "天气证据优先按国家级气象服务入口与可解析的省/自治区/直辖市气象局排序；" +
		provider + " 仅作为实时温度、湿度、风力、降水等结构化数据补充。 " + summary
}

func withLocalWeatherAuthorityReferences(query, placeName string, refs []map[string]any) []map[string]any {
	authorityRefs := weatherAuthorityReferences(query, placeName)
	if len(authorityRefs) == 0 {
		return refs
	}
	merged := make([]map[string]any, 0, len(authorityRefs)+len(refs))
	seen := map[string]bool{}
	appendRef := func(ref map[string]any) {
		rawURL, _ := ref["url"].(string)
		key := strings.TrimSpace(rawURL)
		if key != "" {
			if seen[key] {
				return
			}
			seen[key] = true
		}
		merged = append(merged, ref)
	}
	for _, ref := range authorityRefs {
		appendRef(ref)
	}
	for _, ref := range refs {
		appendRef(ref)
	}
	for i := range merged {
		merged[i]["rank"] = i + 1
	}
	return merged
}

func weatherAuthorityReferences(query, placeName string) []map[string]any {
	refs := []map[string]any{
		{
			"title":   "中国天气网",
			"url":     "https://www.weather.com.cn/",
			"source":  "weather_com_cn",
			"snippet": "中国天气网为国家级天气服务入口，可按城市查询实况、预报、生活指数等信息。",
		},
		{
			"title":   "中央气象台",
			"url":     "https://www.nmc.cn/",
			"source":  "national_meteorological_center",
			"snippet": "中央气象台提供全国天气预报、气象预警、降水、台风和雷达等国家级气象服务。",
		},
		{
			"title":   "中国气象局",
			"url":     "https://www.cma.gov.cn/",
			"source":  "china_meteorological_administration",
			"snippet": "中国气象局为国家气象主管机构入口，可用于核验权威气象服务和区域气象机构信息。",
		},
	}
	if ref, ok := regionalWeatherAuthorityReference(query + " " + placeName); ok {
		refs = append(refs, ref)
	}
	return refs
}

func regionalWeatherAuthorityReference(raw string) (map[string]any, bool) {
	normalized := strings.ToLower(raw)
	regionRefs := []struct {
		keywords []string
		title    string
		url      string
		source   string
	}{
		{[]string{"北京", "beijing"}, "北京市气象局", "http://bj.cma.gov.cn/", "beijing_meteorological_bureau"},
		{[]string{"上海", "shanghai"}, "上海市气象局", "http://sh.cma.gov.cn/", "shanghai_meteorological_bureau"},
		{[]string{"天津", "tianjin"}, "天津市气象局", "http://tj.cma.gov.cn/", "tianjin_meteorological_bureau"},
		{[]string{"重庆", "chongqing"}, "重庆市气象局", "http://cq.cma.gov.cn/", "chongqing_meteorological_bureau"},
		{[]string{"河北", "hebei"}, "河北省气象局", "http://he.cma.gov.cn/", "hebei_meteorological_bureau"},
		{[]string{"山西", "shanxi"}, "山西省气象局", "http://sx.cma.gov.cn/", "shanxi_meteorological_bureau"},
		{[]string{"内蒙古", "inner mongolia"}, "内蒙古自治区气象局", "http://nm.cma.gov.cn/", "inner_mongolia_meteorological_bureau"},
		{[]string{"辽宁", "liaoning"}, "辽宁省气象局", "http://ln.cma.gov.cn/", "liaoning_meteorological_bureau"},
		{[]string{"吉林", "jilin"}, "吉林省气象局", "http://jl.cma.gov.cn/", "jilin_meteorological_bureau"},
		{[]string{"黑龙江", "heilongjiang"}, "黑龙江省气象局", "http://hl.cma.gov.cn/", "heilongjiang_meteorological_bureau"},
		{[]string{"江苏", "jiangsu"}, "江苏省气象局", "http://js.cma.gov.cn/", "jiangsu_meteorological_bureau"},
		{[]string{"浙江", "zhejiang"}, "浙江省气象局", "http://zj.cma.gov.cn/", "zhejiang_meteorological_bureau"},
		{[]string{"安徽", "anhui"}, "安徽省气象局", "http://ah.cma.gov.cn/", "anhui_meteorological_bureau"},
		{[]string{"福建", "fujian"}, "福建省气象局", "http://fj.cma.gov.cn/", "fujian_meteorological_bureau"},
		{[]string{"江西", "jiangxi"}, "江西省气象局", "http://jx.cma.gov.cn/", "jiangxi_meteorological_bureau"},
		{[]string{"山东", "shandong"}, "山东省气象局", "http://sd.cma.gov.cn/", "shandong_meteorological_bureau"},
		{[]string{"河南", "henan"}, "河南省气象局", "http://ha.cma.gov.cn/", "henan_meteorological_bureau"},
		{[]string{"湖北", "hubei"}, "湖北省气象局", "http://hb.cma.gov.cn/", "hubei_meteorological_bureau"},
		{[]string{"湖南", "hunan"}, "湖南省气象局", "http://hn.cma.gov.cn/", "hunan_meteorological_bureau"},
		{[]string{"广东", "guangdong"}, "广东省气象局", "http://gd.cma.gov.cn/", "guangdong_meteorological_bureau"},
		{[]string{"广西", "guangxi"}, "广西壮族自治区气象局", "http://gx.cma.gov.cn/", "guangxi_meteorological_bureau"},
		{[]string{"海南", "hainan"}, "海南省气象局", "http://hi.cma.gov.cn/", "hainan_meteorological_bureau"},
		{[]string{"四川", "sichuan"}, "四川省气象局", "http://sc.cma.gov.cn/", "sichuan_meteorological_bureau"},
		{[]string{"贵州", "guizhou"}, "贵州省气象局", "http://gz.cma.gov.cn/", "guizhou_meteorological_bureau"},
		{[]string{"云南", "yunnan"}, "云南省气象局", "http://yn.cma.gov.cn/", "yunnan_meteorological_bureau"},
		{[]string{"西藏", "tibet", "xizang"}, "西藏自治区气象局", "http://xz.cma.gov.cn/", "xizang_meteorological_bureau"},
		{[]string{"陕西", "shaanxi"}, "陕西省气象局", "http://sn.cma.gov.cn/", "shaanxi_meteorological_bureau"},
		{[]string{"甘肃", "gansu"}, "甘肃省气象局", "http://gs.cma.gov.cn/", "gansu_meteorological_bureau"},
		{[]string{"青海", "qinghai"}, "青海省气象局", "http://qh.cma.gov.cn/", "qinghai_meteorological_bureau"},
		{[]string{"宁夏", "ningxia"}, "宁夏回族自治区气象局", "http://nx.cma.gov.cn/", "ningxia_meteorological_bureau"},
		{[]string{"新疆", "xinjiang"}, "新疆维吾尔自治区气象局", "http://xj.cma.gov.cn/", "xinjiang_meteorological_bureau"},
	}
	for _, ref := range regionRefs {
		for _, keyword := range ref.keywords {
			if strings.Contains(normalized, strings.ToLower(keyword)) {
				return map[string]any{
					"title":   ref.title,
					"url":     ref.url,
					"source":  ref.source,
					"snippet": ref.title + "为区域气象服务入口，可用于核验该省/自治区/直辖市范围内的天气预报、预警和实况信息。",
				}, true
			}
		}
	}
	return nil, false
}

func weatherCodeText(code int) string {
	switch code {
	case 0:
		return "晴"
	case 1, 2, 3:
		return "多云"
	case 45, 48:
		return "雾"
	case 51, 53, 55, 56, 57:
		return "毛毛雨"
	case 61, 63, 65, 66, 67, 80, 81, 82:
		return "降雨"
	case 71, 73, 75, 77, 85, 86:
		return "降雪"
	case 95, 96, 99:
		return "雷暴"
	default:
		return fmt.Sprintf("天气代码%d", code)
	}
}

type openAICompatibleModelProvider struct {
	baseURL string
	model   string
	apiKey  string
	client  *http.Client
}

func assistantClientModelTrace(req application.ModelRequest, userPrompt, responseText string, delta map[string]any, finishReason string, usage map[string]any) map[string]any {
	return map[string]any{
		"stage":             req.Stage,
		"skillId":           req.SkillID,
		"turnId":            req.TurnID,
		"traceId":           req.TraceID,
		"requestUserPrompt": userPrompt,
		"responseText":      responseText,
		"structuredDelta":   delta,
		"usage":             usage,
		"finishReason":      finishReason,
	}
}

func (p openAICompatibleModelProvider) Complete(ctx context.Context, req application.ModelRequest) (application.ModelResponse, error) {
	startedAt := time.Now()
	prompt := req.Prompt
	contextPrompt := application.FormatModelContextForPrompt(req.ContextTurns)
	switch req.Stage {
	case "final":
		raw, _ := json.Marshal(req.Observation)
		prompt = fmt.Sprintf("%s%s\n用户问题：%s\n工具观察：%s", req.Prompt, contextPrompt, req.UserQuestion, string(raw))
	case "evidence_processing":
		raw, _ := json.Marshal(req.Observation)
		prompt = fmt.Sprintf("%s%s\n用户问题：%s\n工具观察JSON：%s", req.Prompt, contextPrompt, req.UserQuestion, string(raw))
	default:
		prompt = fmt.Sprintf("%s%s\n用户问题：%s", req.Prompt, contextPrompt, req.UserQuestion)
	}
	body := map[string]any{
		"model": p.model,
		"messages": []map[string]string{
			{"role": "system", "content": "你是趣我圈小趣私人助理云侧引擎。严格遵守输出格式约定。"},
			{"role": "user", "content": prompt},
		},
		"temperature": 0.2,
	}
	if req.Stage == "skill_selection" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "你是趣我圈小趣私人助理的技能选择器。只能从用户提供的 manifest 中选择一个 skillId，输出 JSON：{\"skillId\":\"...\",\"reason\":\"...\"}。reason 仅供调试追溯，不要使用固定模板套话。"},
			{"role": "user", "content": prompt},
		}
	}
	if req.Stage == "reasoning" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：nextAction（call_tool）、toolName（web_search 或 app_search）、toolInput（含 query；可含 searchQueries:[{dimension,query}]、location、locationSearchName、symbol 或 symbols）、stageNarrative（唯一面向用户叙事字段，180-320字）。stageNarrative 必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先用 2-4 句深入说明你真正要解决的问题，覆盖地点、时间、人数/对象、出行或决策约束、已知上下文和缺失信息；检索设计只占最后 1 句，简要说明会核验哪些事实，不要让检索词占据主体。toolInput.query 是主检索短词；如有天气、交通、景点、人流、股票、新闻等多个维度，在 toolInput.searchQueries 中每个维度一行列出结构化检索词。如问题涉及天气、出行地点或本地实时信息，toolInput.location 填你识别出的地点，toolInput.locationSearchName 填适合地理检索的英文/拉丁写法（例如杭州用 Hangzhou、深圳用 Shenzhen）；如问题涉及证券/股票，toolInput.symbol 或 symbols 填你能识别的交易代码。拼音/缩写须自行理解为可用检索词。禁止输出 JSON 外文字。"},
			{"role": "user", "content": prompt},
		}
	}
	if req.Stage == "evidence_processing" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：{\"retrievalProcessing\":{\"processingSummary\":\"...\",\"selectedKeyPoints\":[\"...\"],\"acceptedReferences\":[{\"title\":\"\",\"url\":\"\",\"source\":\"\",\"snippet\":\"\"}]},\"evidenceSufficient\":true}。processingSummary 为面向用户的证据处理叙事，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”；先说明证据覆盖了你问题里的哪些维度，再说明未覆盖或需要自行复核的部分。acceptedReferences 只能从输入 references 中挑选；若输入有 2-4 条相关高置信引用，应保留 2-4 条不同来源或不同用途的引用，不要无故压缩成 1 条；若工具结果 reliable=false 或 references 为空，不得声称已接纳可靠资料，acceptedReferences 必须为空。面向用户文字不要出现 reliable=true/false、JSON 字段名、工具调用、工具结果、工具观察等协议或调试表述。"},
			{"role": "user", "content": prompt},
		}
	}
	if req.Stage == "final" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：{\"userMarkdown\":\"...\"}。userMarkdown 为面向用户的完整回答，可用 Markdown，必须非空，必须使用第二人称“你/你的”，禁止写“用户/该用户/客户/提问者”。开头直接给结论或建议，不要用内部证据来源作为开场，不要出现“工具、观察、检索、证据标记、协议、JSON、reliable”等内部过程或调试表述；也不要复述同一会话前文里的生硬模板口吻。若输入证据可靠，请把事实自然融入回答并给可执行建议；若输入证据不足，才说明不确定性与下一步核验办法。Markdown 结构必须清晰：优先使用 2-4 个短小段落、项目符号或小标题；每个要点单独成行，避免把天气、原因、行动建议挤成一个长段。遵守法律法规；勿编造实时事实；不确定处提示用户自行核实；仅当用户问题确实涉及金融、股票、证券、基金、买卖或投资决策时才加注非投资建议声明；天气、出行、行程规划等非金融问题禁止出现投资建议声明。禁止输出 JSON 外文字。"},
			{"role": "user", "content": prompt},
		}
	}
	payload, _ := json.Marshal(body)
	log.Printf("assistant model request provider=openai_compatible stage=%s skillId=%s turnId=%s promptLen=%d", req.Stage, req.SkillID, req.TurnID, len([]rune(prompt)))
	emitAssistantModelRequestLog(req, p.model, body)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return application.ModelResponse{}, err
	}
	httpReq.Header.Set("Authorization", "Bearer "+p.apiKey)
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := p.client.Do(httpReq)
	if err != nil {
		log.Printf("assistant model failed provider=openai_compatible stage=%s turnId=%s durationMs=%d err=%v", req.Stage, req.TurnID, time.Since(startedAt).Milliseconds(), err)
		return application.ModelResponse{}, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		emitAssistantModelErrorLog(req, p.model, resp.StatusCode, string(respBody))
		log.Printf("assistant model completed provider=openai_compatible stage=%s turnId=%s status=%d durationMs=%d", req.Stage, req.TurnID, resp.StatusCode, time.Since(startedAt).Milliseconds())
		return application.ModelResponse{}, fmt.Errorf("model provider status=%d body=%s", resp.StatusCode, string(respBody))
	}
	modelDurationMs := time.Since(startedAt).Milliseconds()
	log.Printf("assistant model response provider=openai_compatible stage=%s turnId=%s status=%d bodyLen=%d durationMs=%d", req.Stage, req.TurnID, resp.StatusCode, len(respBody), modelDurationMs)
	var decoded struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Usage map[string]any `json:"usage"`
	}
	if err := json.Unmarshal(respBody, &decoded); err != nil {
		return application.ModelResponse{}, err
	}
	if len(decoded.Choices) == 0 {
		return application.ModelResponse{}, fmt.Errorf("model provider returned no choices")
	}
	rawText := strings.TrimSpace(decoded.Choices[0].Message.Content)
	outText := rawText
	delta := map[string]any(nil)
	switch req.Stage {
	case "skill_selection", "reasoning", "evidence_processing":
		delta = map[string]any{}
		var parsed map[string]any
		if err := json.Unmarshal([]byte(rawText), &parsed); err == nil {
			delta = parsed
		}
		if req.Stage == "reasoning" {
			delta["toolName"] = normalizeModelToolName(fmt.Sprint(delta["toolName"]))
		}
	case "final":
		delta = map[string]any{}
		var parsed map[string]any
		if err := json.Unmarshal([]byte(rawText), &parsed); err == nil {
			delta = parsed
			if md, ok := parsed["userMarkdown"].(string); ok {
				outText = strings.TrimSpace(md)
			}
		}
		if strings.TrimSpace(outText) == "" {
			outText = rawText
		}
	}
	if decoded.Usage == nil {
		decoded.Usage = map[string]any{}
	}
	decoded.Usage["provider"] = "openai_compatible"
	decoded.Usage["model"] = p.model
	decoded.Usage["latencyMs"] = modelDurationMs
	emitAssistantModelResponseLog(req, p.model, resp.StatusCode, rawText, decoded.Choices[0].FinishReason, decoded.Usage, delta)
	trace := assistantClientModelTrace(req, prompt, outText, delta, decoded.Choices[0].FinishReason, decoded.Usage)
	return application.ModelResponse{
		Text:                   outText,
		StructuredDelta:        delta,
		Usage:                  decoded.Usage,
		FinishReason:           decoded.Choices[0].FinishReason,
		ClientModelInteraction: trace,
	}, nil
}

func emitAssistantModelRequestLog(req application.ModelRequest, model string, body map[string]any) {
	header := fmt.Sprintf("[AssistantModel][cloud] REQUEST stage=%s skillId=%s turnId=%s model=%s", req.Stage, req.SkillID, req.TurnID, model)
	log.Print(header)
	emitAssistantModelSection("request", body)
}

func emitAssistantModelResponseLog(req application.ModelRequest, model string, statusCode int, text string, finishReason string, usage map[string]any, delta map[string]any) {
	header := fmt.Sprintf("[AssistantModel][cloud] RESPONSE stage=%s skillId=%s turnId=%s model=%s status=%d finishReason=%s", req.Stage, req.SkillID, req.TurnID, model, statusCode, finishReason)
	log.Print(header)
	emitAssistantModelSection("response", map[string]any{
		"content":         text,
		"structuredDelta": delta,
		"usage":           usage,
	})
}

func emitAssistantModelErrorLog(req application.ModelRequest, model string, statusCode int, body string) {
	header := fmt.Sprintf("[AssistantModel][cloud] ERROR stage=%s skillId=%s turnId=%s model=%s status=%d", req.Stage, req.SkillID, req.TurnID, model, statusCode)
	log.Print(header)
	emitAssistantModelSection("error", body)
}

func emitAssistantModelSection(title string, value any) {
	log.Printf("[AssistantModel] %s:", title)
	switch typed := value.(type) {
	case map[string]any:
		emitAssistantModelMap("[AssistantModel]   ", typed)
	case string:
		emitAssistantModelMultiline("[AssistantModel]   ", typed)
	default:
		encoded, err := json.MarshalIndent(typed, "", "  ")
		if err != nil {
			log.Printf("[AssistantModel]   %v", typed)
			return
		}
		emitAssistantModelMultiline("[AssistantModel]   ", string(encoded))
	}
}

func emitAssistantModelMap(prefix string, values map[string]any) {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		value := values[key]
		switch typed := value.(type) {
		case string:
			log.Printf("%s%s:", prefix, key)
			emitAssistantModelMultiline(prefix+"  ", typed)
		case []map[string]string:
			log.Printf("%s%s:", prefix, key)
			for index, message := range typed {
				log.Printf("%s  [%d].role: %s", prefix, index, message["role"])
				log.Printf("%s  [%d].content:", prefix, index)
				emitAssistantModelMultiline(prefix+"    ", message["content"])
			}
		default:
			encoded, err := json.MarshalIndent(typed, "", "  ")
			if err != nil {
				log.Printf("%s%s: %v", prefix, key, typed)
				continue
			}
			log.Printf("%s%s:", prefix, key)
			emitAssistantModelMultiline(prefix+"  ", string(encoded))
		}
	}
}

func emitAssistantModelMultiline(prefix string, text string) {
	if strings.TrimSpace(text) == "" {
		log.Printf("%s<empty>", prefix)
		return
	}
	for _, line := range strings.Split(text, "\n") {
		log.Printf("%s%s", prefix, line)
	}
}

func normalizeModelToolName(raw string) string {
	toolName := strings.TrimSpace(raw)
	switch toolName {
	case "web_search", "search", "web_fetch", "app_search", "memory_search", "app_action":
		return toolName
	case "":
		return "web_search"
	default:
		log.Printf("assistant model normalized unsupported toolName=%s to web_search", toolName)
		return "web_search"
	}
}

func providerAPIKey(cfg providerCfg) (string, error) {
	envKey := strings.TrimSpace(cfg.APIKeyEnv)
	if envKey == "" {
		return "", fmt.Errorf("provider api_key_env is required")
	}
	key := strings.TrimSpace(os.Getenv(envKey))
	if key == "" {
		return "", fmt.Errorf("provider api key env %s is empty", envKey)
	}
	return key, nil
}

func providerTimeout(ms int) time.Duration {
	if ms <= 0 {
		return 30 * time.Second
	}
	return time.Duration(ms) * time.Millisecond
}

func searchProviderTimeout(ms int) time.Duration {
	if ms <= 0 {
		return 8 * time.Second
	}
	timeout := time.Duration(ms) * time.Millisecond
	if timeout > 10*time.Second {
		return 10 * time.Second
	}
	return timeout
}

func searchHTTPClient(ms int) *http.Client {
	timeout := searchProviderTimeout(ms)
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSHandshakeTimeout = timeout
	transport.ResponseHeaderTimeout = timeout
	return &http.Client{Timeout: timeout, Transport: transport}
}

func requiresRealProvider(appEnv string) bool {
	return appEnv == "beta" || appEnv == "gamma" || appEnv == "prod-gray" || appEnv == "prod"
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	_ = configVersion
	if strings.TrimSpace(imageVersion) == "" {
		return nil
	}
	min := strings.TrimSpace(cfg.Config.MinImageVersion)
	max := strings.TrimSpace(cfg.Config.MaxImageVersion)
	if min != "" && compareSemver(imageVersion, min) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s < min_image_version=%s", imageVersion, min)
	}
	if max != "" && compareSemver(imageVersion, max) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s > max_image_version=%s", imageVersion, max)
	}
	return nil
}

func compareSemver(a, b string) int {
	ap := parseSemver(a)
	bp := parseSemver(b)
	for i := 0; i < 3; i++ {
		if ap[i] < bp[i] {
			return -1
		}
		if ap[i] > bp[i] {
			return 1
		}
	}
	return 0
}

func parseSemver(raw string) [3]int {
	trimmed := strings.TrimPrefix(strings.TrimSpace(raw), "v")
	parts := strings.Split(trimmed, ".")
	out := [3]int{}
	for i := 0; i < len(parts) && i < 3; i++ {
		out[i], _ = strconv.Atoi(parts[i])
	}
	return out
}

func buildRedisRouter(cfg config) *rtredis.Router {
	return rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec": {
				Mode:         fallbackMode(cfg.Redis.Rec.Mode, cfg.Redis.Rec.Addr, cfg.Redis.Rec.Addrs),
				Addr:         cfg.Redis.Rec.Addr,
				Addrs:        cfg.Redis.Rec.Addrs,
				Password:     cfg.Redis.Rec.Password,
				DB:           cfg.Redis.Rec.DB,
				TLS:          cfg.Redis.Rec.TLS,
				PoolSize:     cfg.Redis.Rec.Pool.Size,
				MinIdleConns: cfg.Redis.Rec.Pool.MinIdle,
			},
			"general": {
				Mode:         fallbackMode(cfg.Redis.General.Mode, cfg.Redis.General.Addr, cfg.Redis.General.Addrs),
				Addr:         cfg.Redis.General.Addr,
				Addrs:        cfg.Redis.General.Addrs,
				Password:     cfg.Redis.General.Password,
				DB:           cfg.Redis.General.DB,
				TLS:          cfg.Redis.General.TLS,
				PoolSize:     cfg.Redis.General.Pool.Size,
				MinIdleConns: cfg.Redis.General.Pool.MinIdle,
			},
		},
		PrefixRoutes: []rtredis.PrefixRoute{{Prefix: "rec:", Scene: "rec"}, {Prefix: "cache:", Scene: "general"}, {Prefix: "page_ctx:", Scene: "general"}, {Prefix: "suggested_actions:", Scene: "general"}},
		DefaultScene: "general",
	})
}

func fallbackMode(mode string, addr string, addrs []string) string {
	if strings.TrimSpace(mode) != "" && (strings.TrimSpace(addr) != "" || len(addrs) > 0) {
		return mode
	}
	return "memory"
}

func scenarioSeedRefsFromEnv() []string {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_SCENARIO_SEED_REFS"))
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod-gray", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod-gray", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func assistantShutdownTimeout() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_SHUTDOWN_TIMEOUT_SECONDS"))
	if raw == "" {
		return 10 * time.Second
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds <= 0 {
		log.Printf("WARN: invalid ASSISTANT_SHUTDOWN_TIMEOUT_SECONDS=%q; using 10s", raw)
		return 10 * time.Second
	}
	return time.Duration(seconds) * time.Second
}

func assistantHTTPWriteTimeout() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS"))
	if raw == "" {
		return 180 * time.Second
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds <= 0 {
		log.Printf("WARN: invalid ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS=%q; using 180s", raw)
		return 180 * time.Second
	}
	return time.Duration(seconds) * time.Second
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
