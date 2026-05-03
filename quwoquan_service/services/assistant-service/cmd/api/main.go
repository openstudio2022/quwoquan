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
	server := &http.Server{Addr: addr, Handler: observedHandler, ReadHeaderTimeout: 5 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second}
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
	return appEnv == "beta" && strings.TrimSpace(os.Getenv("ALLOW_DETERMINISTIC_BETA")) == "1"
}

func realSearchHandler(cfg providerCfg) tool.Handler {
	provider := strings.TrimSpace(cfg.Provider)
	client := &http.Client{Timeout: providerTimeout(cfg.TimeoutMs)}
	return func(ctx context.Context, req tool.Request) (tool.Result, error) {
		query := inputString(req.Input, "query")
		location := inputString(req.Input, "location")
		locationSearchName := inputString(req.Input, "locationSearchName")
		skillID := inputString(req.Input, "skillId")
		log.Printf("assistant search requested provider=%s tool=%s query=%q", provider, req.ToolName, query)
		switch provider {
		case "duckduckgo_html":
			if shouldTryWeatherLookup(skillID, query, location) {
				if summary, refs, ok := openMeteoWeatherSearch(ctx, client, query, location, locationSearchName); ok {
					log.Printf("assistant weather search completed provider=open_meteo tool=%s query=%q refs=%d summaryLen=%d", req.ToolName, query, len(refs), len([]rune(summary)))
					return searchToolResult(req.ToolName, "open_meteo", summary, refs, true), nil
				}
			}
			if shouldTryFinanceLookup(skillID, req.Input) {
				if summary, refs, ok := yahooFinanceSearch(ctx, client, req.Input); ok {
					log.Printf("assistant finance search completed provider=yahoo_finance tool=%s query=%q refs=%d summaryLen=%d", req.ToolName, query, len(refs), len([]rune(summary)))
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
			log.Printf("assistant search completed provider=%s tool=%s query=%q refs=%d summaryLen=%d", provider, req.ToolName, query, len(refs), len([]rune(summary)))
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

func shouldTryWeatherLookup(skillID, query, location string) bool {
	if strings.TrimSpace(location) != "" {
		return true
	}
	normalized := strings.ToLower(strings.TrimSpace(query))
	if skillID == "weather" {
		return true
	}
	return strings.Contains(normalized, "天气") ||
		strings.Contains(normalized, "气温") ||
		strings.Contains(normalized, "降雨") ||
		strings.Contains(normalized, "weather") ||
		strings.Contains(normalized, "forecast")
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

func openMeteoWeatherSearch(ctx context.Context, client *http.Client, query, location, locationSearchName string) (string, []map[string]any, bool) {
	candidates := []string{}
	if strings.TrimSpace(locationSearchName) != "" {
		candidates = append(candidates, strings.TrimSpace(locationSearchName))
	}
	candidate := weatherLocationCandidate(query, location)
	if candidate == "" {
		return "", nil, false
	}
	candidates = append(candidates, candidate)
	seenCandidates := map[string]bool{}
	for _, item := range candidates {
		if seenCandidates[item] {
			continue
		}
		seenCandidates[item] = true
		if summary, refs, ok := openMeteoWeatherSearchCandidate(ctx, client, item); ok {
			return summary, refs, true
		}
	}
	return "", nil, false
}

func openMeteoWeatherSearchCandidate(ctx context.Context, client *http.Client, candidate string) (string, []map[string]any, bool) {
	geoURL := "https://geocoding-api.open-meteo.com/v1/search?count=5&language=zh&format=json&name=" + url.QueryEscape(candidate)
	geoReq, err := http.NewRequestWithContext(ctx, http.MethodGet, geoURL, nil)
	if err != nil {
		return "", nil, false
	}
	geoReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	geoResp, err := client.Do(geoReq)
	if err != nil {
		log.Printf("assistant open_meteo geocode failed location=%q err=%v", candidate, err)
		return "", nil, false
	}
	defer geoResp.Body.Close()
	if geoResp.StatusCode < 200 || geoResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo geocode status location=%q status=%d", candidate, geoResp.StatusCode)
		return "", nil, false
	}
	var geo openMeteoGeocodeResponse
	if err := json.NewDecoder(io.LimitReader(geoResp.Body, 128*1024)).Decode(&geo); err != nil {
		log.Printf("assistant open_meteo geocode decode failed location=%q err=%v", candidate, err)
		return "", nil, false
	}
	if len(geo.Results) == 0 {
		log.Printf("assistant open_meteo geocode empty location=%q", candidate)
		return "", nil, false
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
		return "", nil, false
	}
	forecastReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	forecastResp, err := client.Do(forecastReq)
	if err != nil {
		log.Printf("assistant open_meteo forecast failed location=%q err=%v", candidate, err)
		return "", nil, false
	}
	defer forecastResp.Body.Close()
	if forecastResp.StatusCode < 200 || forecastResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo forecast status location=%q status=%d", candidate, forecastResp.StatusCode)
		return "", nil, false
	}
	var forecast openMeteoForecastResponse
	if err := json.NewDecoder(io.LimitReader(forecastResp.Body, 128*1024)).Decode(&forecast); err != nil {
		log.Printf("assistant open_meteo forecast decode failed location=%q err=%v", candidate, err)
		return "", nil, false
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
	return summary, refs, true
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
			{"role": "system", "content": "输出唯一 JSON：nextAction（call_tool）、toolName（web_search 或 app_search）、toolInput（含 query，可含 location、locationSearchName、symbol 或 symbols）、stageNarrative（唯一面向用户叙事字段，120-220字，合并说明你如何理解问题、为何这样设计检索词、会优先核验哪些实时事实）。不要再输出其他面向用户叙事字段。toolInput.query 由你生成检索短词；如问题涉及天气、出行地点或本地实时信息，toolInput.location 填你识别出的地点，toolInput.locationSearchName 填适合地理检索的英文/拉丁写法（例如杭州用 Hangzhou、深圳用 Shenzhen），用于避免同名地误匹配；如问题涉及证券/股票，toolInput.symbol 或 symbols 填你能识别的交易代码（例如 A 股带 .SZ/.SS，港股带 .HK，美股保留 ticker）。拼音/缩写须自行理解为可用检索词。禁止输出 JSON 外文字。"},
			{"role": "user", "content": prompt},
		}
	}
	if req.Stage == "evidence_processing" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：{\"retrievalProcessing\":{\"processingSummary\":\"...\",\"selectedKeyPoints\":[\"...\"],\"acceptedReferences\":[{\"title\":\"\",\"url\":\"\",\"source\":\"\",\"snippet\":\"\"}]},\"evidenceSufficient\":true}。processingSummary 为面向用户的证据处理叙事；references 仅保留高置信条目，可留空。若工具结果 reliable=false 或 references 为空，不得声称已接纳可靠资料，acceptedReferences 必须为空；面向用户文字不要出现 reliable=true/false 这类协议字段。"},
			{"role": "user", "content": prompt},
		}
	}
	if req.Stage == "final" {
		body["response_format"] = map[string]string{"type": "json_object"}
		body["messages"] = []map[string]string{
			{"role": "system", "content": "输出唯一 JSON：{\"userMarkdown\":\"...\"}。userMarkdown 为面向用户的完整回答，可用 Markdown。若工具观察标记为可靠，请直接使用工具摘要中的事实给出可执行建议，不要再说没有可靠信息；若工具观察标记为不可靠，才说明实时证据不足并给下一步核验办法。面向用户正文不要出现 reliable=true/false、JSON 字段名、协议调试词，也不要写“工具观察标记为可靠/不可靠”这类内部状态表述。遵守法律法规；勿编造实时事实；不确定处提示用户自行核实；仅当用户问题确实涉及金融、股票、证券、基金、买卖或投资决策时才加注非投资建议声明；天气、出行、行程规划等非金融问题禁止出现投资建议声明。禁止输出 JSON 外文字。"},
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
		return application.ModelResponse{}, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		emitAssistantModelErrorLog(req, p.model, resp.StatusCode, string(respBody))
		return application.ModelResponse{}, fmt.Errorf("model provider status=%d body=%s", resp.StatusCode, string(respBody))
	}
	log.Printf("assistant model response provider=openai_compatible stage=%s turnId=%s status=%d bodyLen=%d", req.Stage, req.TurnID, resp.StatusCode, len(respBody))
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

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
