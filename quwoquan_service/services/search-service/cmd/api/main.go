package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	rtmongodb "quwoquan_service/runtime/mongodb"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/search-service/internal/adapters/http"
	"quwoquan_service/services/search-service/internal/application"
	"quwoquan_service/services/search-service/internal/application/queryheat"
	"quwoquan_service/services/search-service/internal/infrastructure/feedbackstore"
	"quwoquan_service/services/search-service/internal/infrastructure/queryheatstore"
	"quwoquan_service/services/search-service/internal/infrastructure/searchbackend"
	"quwoquan_service/services/search-service/internal/infrastructure/searchsignals"
)

const serviceName = "search-service"

// heatRebuildInterval is how often the search-term heat read model is rebuilt
// from the query/feedback logs. The read-model TTL is wider than this so a brief
// rebuild stall never empties the served heat.
const heatRebuildInterval = 10 * time.Minute

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	ES searchbackend.ESConfig `yaml:"es"`

	// Mongo persists query logs + feedback + the heat read model. When unset
	// (alpha without Mongo), the service still serves searches with base ranking.
	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		General redisSceneCfg `yaml:"general"`
		Rec     redisSceneCfg `yaml:"rec"`
	} `yaml:"redis"`

	// Ranking carries the search-term heat boost weight and the AB rollout.
	Ranking struct {
		TermHeatBoost float64 `yaml:"termHeatBoost"`
		Experiment    struct {
			Enabled       bool   `yaml:"enabled"`
			PolicyVersion string `yaml:"policyVersion"`
			Buckets       []struct {
				Name      string `yaml:"name"`
				WeightPct int    `yaml:"weightPct"`
			} `yaml:"buckets"`
		} `yaml:"experiment"`
	} `yaml:"ranking"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("%s config load failed: %v", serviceName, err)
	}
	normalizeDefaults(&cfg)
	applyESEnvOverrides(&cfg.ES)
	applyMongoEnvOverrides(&cfg)
	applyRedisEnvOverrides(&cfg)

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: serviceName, SamplingRatio: 0.1})
	defer otelShutdown()

	built, err := searchbackend.Build(cfg.ES, nil)
	if err != nil {
		log.Fatalf("%s backend assembly failed: %v", serviceName, err)
	}
	if err := built.EnsureIndex(ctx); err != nil {
		// Non-fatal: the service still boots; queries degrade via Retrieve until
		// ES recovers. The failure is surfaced through /healthz.
		log.Printf("%s WARN: ensure ES index failed: %v", serviceName, err)
	}

	logger := slog.Default()
	redisRouter := buildRedisRouter(cfg)
	defer redisRouter.Close()
	if err := redisRouter.PingAll(ctx); err != nil {
		log.Printf("%s WARN: redis ping: %v", serviceName, err)
	}
	searchSignalPublisher := searchsignals.NewStreamPublisher(redisRouter.Scene("general"), logger)

	// Persistence + heat read model are optional: without Mongo the service still
	// serves searches (base ranking, no query log, no related terms). With Mongo
	// it closes the feedback loop (query log -> heat -> ranking + relatedTerms).
	var feedbackSink application.FeedbackSink
	var termHeat application.TermHeatProvider
	var queryLogSink application.QueryLogSink
	if strings.TrimSpace(cfg.Mongo.URI) != "" {
		client := rtmongodb.MustConnect(ctx, rtmongodb.ConnectConfig{
			URI: cfg.Mongo.URI, Database: cfg.Mongo.Database,
		}, serviceName)
		db := client.Database(cfg.Mongo.Database)
		store := feedbackstore.NewStore(db, logger)
		feedbackSink = store
		queryLogSink = store
		heatStore := queryheatstore.NewStore(db, queryheat.Config{}, logger)
		// Hot-query related-terms cache: collapses the per-search Mongo read for
		// repeated hot queries into one read per key per TTL window (backpressure
		// on the Mongo side under concurrency). Best-effort, read-through.
		termHeat = application.NewCachedTermHeat(heatStore,
			time.Duration(getenvInt("SEARCH_RELATED_TERMS_CACHE_TTL_MS", 2000))*time.Millisecond,
			getenvInt("SEARCH_RELATED_TERMS_CACHE_MAX", 1024))
		startHeatRebuildLoop(ctx, heatStore, logger)
		log.Printf("%s feedback/query-log + term-heat read model enabled (db=%s)", serviceName, cfg.Mongo.Database)
	} else {
		log.Printf("%s WARN: mongo.uri unset; query logging + term-heat disabled (base ranking only)", serviceName)
	}

	searchSvc := application.NewSearchService(built.Backend, feedbackSink,
		application.WithQueryLogSink(queryLogSink),
		application.WithSearchSignalPublisher(searchSignalPublisher),
		application.WithLogger(logger))
	decorator := application.NewRankingDecorator(termHeat, application.NewExperiments(experimentConfig(cfg)), cfg.Ranking.TermHeatBoost, logger)

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("%s process logger init failed: %v", serviceName, err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("%s exception logger init failed: %v", serviceName, err)
	}

	handler := httpadapter.NewHandler(searchSvc, decorator).Routes()
	// Backpressure: cap concurrent in-flight searches so a slow ES sheds load
	// (typed 503) instead of piling up and collapsing the instance. Aligned with
	// search_slo.yaml#load_model.max_concurrency_per_instance; applied only to the
	// search routes so /healthz and /metrics stay reachable while shedding.
	inflightLimiter := rtgov.NewInflightLimiter(getenvInt("SEARCH_MAX_INFLIGHT", 256))
	searchHandler := httpadapter.MaxInflightMiddleware(inflightLimiter)(handler)
	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	if ping := built.HealthPing(); ping != nil {
		healthChecker.Register("elasticsearch", ping)
	}
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle("/", searchHandler)

	serverCfg := rthttp.HTTPServerMiddlewareConfig{
		Service:           serviceName,
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          serviceName + ".http",
		Src:               "gateway",
		ServiceName:       serviceName,
		ServiceInstanceID: hostname(),
	}
	withObs := rthttp.NewHTTPServerMiddleware(rootMux, serverCfg, ioLogger, processLogger, exceptionLogger)
	rateLimited := rtgov.RateLimitMiddleware(rtgov.NewRateLimiter(1000))(withObs)

	server := &http.Server{
		Addr:              cfg.Service.HTTP.Addr,
		Handler:           rateLimited,
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("%s listening on %s (es.enabled=%t)", serviceName, cfg.Service.HTTP.Addr, cfg.ES.Enabled)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("%s: %v", serviceName, err)
	}
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	name := getenvOrDefault("SERVICE_NAME", serviceName)
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(os.Getenv("CONFIG_VERSION"))
	if !isValidAppEnv(appEnv) {
		return config{}, fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && configVersion == "" {
		return config{}, fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}

	if configRoot != "" {
		defaultFile := filepath.Join(configRoot, "configs", name, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", name, appEnv, "config.yaml")
		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, err
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, err
		}
		if configVersion != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", name, "configs", "releases", configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, err
			}
		}
		return cfg, nil
	}

	if err := mergeConfigFile(&cfg, filepath.Join("configs", "default", "config.yaml")); err == nil {
		_ = mergeConfigFile(&cfg, filepath.Join("configs", appEnv, "config.yaml"))
		if configVersion != "" {
			_ = mergeConfigFile(&cfg, filepath.Join("configs", "releases", configVersion+".yaml"))
		}
		return cfg, nil
	}

	current := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, current); err != nil {
		return config{}, fmt.Errorf("read config failed: %w", err)
	}
	return cfg, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func normalizeDefaults(cfg *config) {
	if strings.TrimSpace(cfg.Service.Name) == "" {
		cfg.Service.Name = serviceName
	}
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18095"
	}
	if strings.TrimSpace(cfg.ES.Index) == "" {
		cfg.ES.Index = "quwoquan_objects"
	}
}

// applyESEnvOverrides lets the deploy layer inject ES endpoints/credentials as
// environment secrets (consistent with how other services inject *_URI), without
// hardcoding them in committed config.
func applyESEnvOverrides(es *searchbackend.ESConfig) {
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); v != "" {
		parts := strings.Split(v, ",")
		eps := make([]string, 0, len(parts))
		for _, p := range parts {
			if p = strings.TrimSpace(p); p != "" {
				eps = append(eps, p)
			}
		}
		es.Endpoints = eps
		es.Enabled = true
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_USERNAME")); v != "" {
		es.Username = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_PASSWORD")); v != "" {
		es.Password = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_API_KEY")); v != "" {
		es.APIKey = v
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_ES_ENABLED"))) {
	case "true", "1":
		es.Enabled = true
	case "false", "0":
		es.Enabled = false
	}
}

// applyMongoEnvOverrides lets the deploy layer inject the Mongo endpoint as an
// environment secret (consistent with how *_URI are injected elsewhere).
func applyMongoEnvOverrides(cfg *config) {
	if v := strings.TrimSpace(os.Getenv("SEARCH_MONGO_URI")); v != "" {
		cfg.Mongo.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_MONGO_DATABASE")); v != "" {
		cfg.Mongo.Database = v
	}
	if strings.TrimSpace(cfg.Mongo.URI) != "" && strings.TrimSpace(cfg.Mongo.Database) == "" {
		cfg.Mongo.Database = "quwoquan"
	}
}

func applyRedisEnvOverrides(cfg *config) {
	applyRedisSceneEnv("SEARCH_REDIS_GENERAL", &cfg.Redis.General)
	applyRedisSceneEnv("SEARCH_REDIS_REC", &cfg.Redis.Rec)
}

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := strings.TrimSpace(os.Getenv(prefix + "_MODE")); v != "" {
		cfg.Mode = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDR")); v != "" {
		cfg.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDRS")); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_PASSWORD")); v != "" {
		cfg.Password = v
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv(prefix + "_TLS"))) {
	case "true", "1", "yes", "on":
		cfg.TLS = true
	}
}

func buildRedisRouter(cfg config) *rtredis.Router {
	base := rtredis.DefaultRouterConfig()
	base.Scenes["general"] = toSceneConfig(cfg.Redis.General)
	base.Scenes["rec"] = toSceneConfig(cfg.Redis.Rec)
	return rtredis.MustNewRouter(base)
}

func toSceneConfig(cfg redisSceneCfg) rtredis.SceneConfig {
	return rtredis.SceneConfig{
		Mode:           cfg.Mode,
		Addr:           cfg.Addr,
		Addrs:          cfg.Addrs,
		Password:       cfg.Password,
		DB:             cfg.DB,
		TLS:            cfg.TLS,
		PoolSize:       cfg.Pool.Size,
		MinIdleConns:   cfg.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Pool.DialTimeoutMs,
	}
}

// experimentConfig maps the service config AB block into the application config.
func experimentConfig(cfg config) application.ExperimentConfig {
	out := application.ExperimentConfig{
		Enabled:       cfg.Ranking.Experiment.Enabled,
		PolicyVersion: cfg.Ranking.Experiment.PolicyVersion,
	}
	for _, b := range cfg.Ranking.Experiment.Buckets {
		out.Buckets = append(out.Buckets, application.ExperimentBucket{Name: b.Name, WeightPct: b.WeightPct})
	}
	return out
}

// startHeatRebuildLoop rebuilds the search-term heat read model on a ticker and
// once at startup, both best-effort. It stops when ctx is canceled (graceful
// shutdown), so it never leaks past the server lifetime.
func startHeatRebuildLoop(ctx context.Context, store *queryheatstore.Store, logger *slog.Logger) {
	rebuild := func() {
		runCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
		defer cancel()
		written, err := store.Rebuild(runCtx)
		if err != nil {
			logger.WarnContext(runCtx, "search term-heat rebuild failed (best-effort)", slog.String("err", err.Error()))
			return
		}
		logger.InfoContext(runCtx, "search term-heat rebuilt", slog.Int("terms", written))
	}
	go func() {
		rebuild()
		ticker := time.NewTicker(heatRebuildInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				rebuild()
			}
		}
	}()
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

// getenvInt reads a positive integer env override, falling back to def when the
// var is unset or not a positive integer (so a bad value never disables the cap).
func getenvInt(key string, def int) int {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
