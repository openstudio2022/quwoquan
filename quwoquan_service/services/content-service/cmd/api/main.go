package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	rthttp "quwoquan_service/runtime/http"
	runtimelearning "quwoquan_service/runtime/learning"
	robs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/cache"
	"quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// redisSceneCfg holds configuration for a single Redis deployment (one logical scene).
type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`  // "standalone" (default) | "cluster"
	Addr     string   `yaml:"addr"`  // standalone: host:port
	Addrs    []string `yaml:"addrs"` // cluster: [host:port, ...]
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`  // cluster mode ignores this
	TLS      bool     `yaml:"tls"` // set true for Alibaba Cloud / VeCache public endpoints
	Pool     struct {
		Size           int `yaml:"size"`     // 0 = auto
		MinIdle        int `yaml:"min_idle"` // 0 = auto
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	Mongo struct {
		URI        string `yaml:"uri"`
		Database   string `yaml:"database"`
		Collection string `yaml:"collection"`
	} `yaml:"mongo"`

	Postgres struct {
		ReportDSN string `yaml:"report_dsn"`
	} `yaml:"postgres"`

	// Redis scenes:
	//   rec     — recommendation hot path (session signals, exposed, negative)
	//   general — entity cache, assistant context, rate limiting (reserved)
	Redis struct {
		Rec     redisSceneCfg `yaml:"rec"`
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`

	RecModelService struct {
		URL       string `yaml:"url"`
		TimeoutMs int    `yaml:"timeout_ms"`
		Enabled   bool   `yaml:"enabled"`
	} `yaml:"rec_model_service"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("content-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("content-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("content-service config compatibility failed: %v", err)
	}
	if err := preflightConfig(cfg, appEnv); err != nil {
		log.Fatalf("content-service config preflight failed: %v", err)
	}

	addr := getenvOrDefault("CONTENT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18080"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("content-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("content-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	eventPub := messaging.NewRedisEventPublisher(router.Scene("general"), "content-service", logger)

	// Read path: SessionCache wraps HotPath with L1 cache + singleflight
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 10000)

	// Write path: BufferedHotPath wraps HotPath with async channel
	bufferedWriter := rtrec.NewBufferedHotPath(hotPath, rtrec.WithBufferLogger(logger))
	defer bufferedWriter.Stop()

	// Storage layer: MongoDB when mongo.uri is configured, else InMemory with seeds.
	var store persistence.PostRepository
	var reportStore persistence.ReportRepository
	var postServiceOpts []application.PostServiceOption
	var sharedProjector application.Projector
	recOpts := []rtrec.EngineOption{
		rtrec.WithRecallTimeout(150 * time.Millisecond),
		rtrec.WithLogger(logger),
	}
	learningRecorder := runtimelearning.NewBufferedRecorder(&runtimelearning.LogSink{Logger: logger}, logger, runtimelearning.WithFlushSize(32), runtimelearning.WithFlushInterval(2*time.Second))
	defer learningRecorder.Stop()
	recFeedback := rtrec.NewFeedbackRecorder(learningRecorder)
	recOpts = append(recOpts, rtrec.WithFeedbackRecorder(recFeedback))
	postServiceOpts = append(postServiceOpts, application.WithSignalProcessor(bufferedWriter))
	postServiceOpts = append(postServiceOpts, application.WithLogger(logger))
	postServiceOpts = append(postServiceOpts, application.WithStoryRuntimeConfig(resolveStoryRuntimeConfig()))

	mongoURI := resolveMongoURI(cfg)
	if mongoURI != "" {
		mongoClient, err := mongo.Connect(options.Client().ApplyURI(mongoURI))
		if err != nil {
			log.Fatalf("content-service mongo connect failed: %v", err)
		}
		defer func() {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = mongoClient.Disconnect(ctx)
		}()
		dbName := cfg.Mongo.Database
		if dbName == "" {
			dbName = "quwoquan_content"
		}
		collName := cfg.Mongo.Collection
		if collName == "" {
			collName = "posts"
		}
		db := mongoClient.Database(dbName)
		mongoStore := persistence.NewMongoPostStore(db.Collection(collName))
		store = cache.NewPostCacheRepository(mongoStore, router.Scene("general"), logger)
		log.Printf("content-service storage=mongodb db=%s collection=%s", dbName, collName)

		// Event publisher: Redis Pub/Sub for cross-service consumption
		postServiceOpts = append(postServiceOpts, application.WithEventPublisher(eventPub))

		// In-process projectors: discovery feed + recommendation features.
		discoveryProjector := recinfra.NewDiscoveryFeedProjector(db)
		recommendProjector := recinfra.NewRecommendFeatureProjector(db)
		sharedProjector = &projectorAdapter{discovery: discoveryProjector, recommend: recommendProjector}
		postServiceOpts = append(postServiceOpts, application.WithProjector(sharedProjector))
		recOpts = append(recOpts, rtrec.WithFeatureProvider(recinfra.NewFeatureStore(db)))
	} else {
		store = persistence.NewPostStore(recinfra.DefaultSeedPosts())
		log.Printf("content-service storage=inmemory (no mongo.uri configured)")
	}

	reportDSN := resolveReportDSN(cfg)
	if reportDSN != "" {
		db, err := sql.Open("postgres", reportDSN)
		if err != nil {
			log.Fatalf("content-service report postgres open failed: %v", err)
		}
		defer db.Close()
		pgReportStore, err := persistence.NewPGReportStore(db)
		if err != nil {
			log.Fatalf("content-service report postgres init failed: %v", err)
		}
		reportStore = pgReportStore
		log.Printf("content-service report storage=postgres")
	} else {
		reportStore = persistence.NewInMemoryReportStore()
		log.Printf("content-service report storage=inmemory (no postgres.report_dsn configured)")
	}

	source := recinfra.NewPostRepositorySource(store)

	if cfg.RecModelService.Enabled && cfg.RecModelService.URL != "" {
		timeout := time.Duration(cfg.RecModelService.TimeoutMs) * time.Millisecond
		if timeout <= 0 {
			timeout = 50 * time.Millisecond
		}
		client := recinfra.NewHTTPModelServiceClient(cfg.RecModelService.URL, timeout)
		remoteScorer := rtrec.NewRemoteModelScorer(client, "content_feed")
		ruleScorer := &rtrec.RuleScorer{}
		cascade := rtrec.NewCascadeScorer(remoteScorer, ruleScorer, timeout)
		cascade.Logger = logger
		recOpts = append(recOpts, rtrec.WithScorer(cascade))
		log.Printf("content-service rec-model-service enabled url=%s timeout=%v", cfg.RecModelService.URL, timeout)
	}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source}, recOpts...)
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(store, postServiceOpts...)
	reportService := application.NewReportService(reportStore, eventPub)
	behaviorService := application.NewBehaviorService(
		bufferedWriter,
		store,
		application.WithBehaviorEventPublisher(eventPub),
		application.WithBehaviorProjector(sharedProjector),
		application.WithBehaviorFeedbackRecorder(recFeedback),
	)
	handler := httpadapter.NewContentHandler(feedService, postService, reportService, behaviorService).Routes()

	observedHandler := rthttp.NewHTTPServerMiddleware(handler, rthttp.HTTPServerMiddlewareConfig{
		Service:           "content-service",
		ServiceName:       "content-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "content-service",
		Src:               "content-service",
	}, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr:              addr,
		Handler:           observedHandler,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("content-service listening on %s", addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen and serve: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "content-service")
	appEnv = getenvOrDefault("APP_ENV", "local")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if appEnv != "local" && appEnv != "integration" && appEnv != "prod" {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of local|integration|prod, got %q", appEnv)
	}
	// Enforce explicit config version in prod so rollout always binds image+config.
	if appEnv == "prod" && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=prod")
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func loadConfig(path string) config {
	cfg := config{}
	raw, err := os.ReadFile(path)
	if err != nil {
		return cfg
	}
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		log.Printf("content-service config parse failed: %v", err)
	}
	return cfg
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

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}

	// External mounted config root mode:
	//   <root>/configs/<service>/default/config.yaml
	//   <root>/configs/<service>/<env>/config.yaml
	//   <root>/releases/config/<service>/<version>.yaml
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

	// Repository local mode (service-relative):
	//   configs/default/config.yaml + configs/<env>/config.yaml (+ optional version under releases/)
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

	// Legacy fallback mode.
	return loadConfig(filepath.Join("configs", "config.yaml")), nil
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
		// Allow local dev without image version.
		return nil
	}
	if cfg.Config.MinImageVersion != "" && compareSemver(imageVersion, cfg.Config.MinImageVersion) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s below min_image_version=%s", imageVersion, cfg.Config.MinImageVersion)
	}
	if cfg.Config.MaxImageVersion != "" && compareSemver(imageVersion, cfg.Config.MaxImageVersion) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s above max_image_version=%s", imageVersion, cfg.Config.MaxImageVersion)
	}
	return nil
}

func preflightConfig(cfg config, appEnv string) error {
	mode := strings.ToLower(strings.TrimSpace(cfg.Redis.Rec.Mode))
	if mode == "" {
		mode = "standalone"
	}
	if mode != "standalone" && mode != "cluster" && mode != "memory" {
		return fmt.Errorf("redis.rec.mode must be standalone|cluster|memory, got %q", cfg.Redis.Rec.Mode)
	}
	if mode == "cluster" && len(cfg.Redis.Rec.Addrs) == 0 {
		return fmt.Errorf("redis.rec.mode=cluster requires redis.rec.addrs")
	}
	if appEnv == "prod" {
		if mode == "standalone" && strings.TrimSpace(cfg.Redis.Rec.Addr) == "" {
			return fmt.Errorf("prod requires redis.rec.addr when mode=standalone")
		}
		if mode == "cluster" && len(cfg.Redis.Rec.Addrs) == 0 {
			return fmt.Errorf("prod requires redis.rec.addrs when mode=cluster")
		}
	}
	return nil
}

func compareSemver(a, b string) int {
	parse := func(v string) [3]int {
		var out [3]int
		parts := strings.Split(strings.TrimPrefix(strings.TrimSpace(v), "v"), ".")
		for i := 0; i < len(parts) && i < 3; i++ {
			n, _ := strconv.Atoi(parts[i])
			out[i] = n
		}
		return out
	}
	av := parse(a)
	bv := parse(b)
	for i := 0; i < 3; i++ {
		if av[i] > bv[i] {
			return 1
		}
		if av[i] < bv[i] {
			return -1
		}
	}
	return 0
}

// applyEnvOverrides applies environment variable overrides to all config sections.
// Env vars take precedence over config.yaml values — intended for CI/CD injection.
//
// Rec Redis overrides:
//
//	CONTENT_REDIS_REC_MODE         standalone | cluster
//	CONTENT_REDIS_REC_ADDR         host:port  (standalone)
//	CONTENT_REDIS_REC_ADDRS        host1:port,host2:port,...  (cluster)
//	CONTENT_REDIS_REC_PASSWORD     password
//	CONTENT_REDIS_REC_TLS          true | 1
//
// General Redis overrides:
//
//	CONTENT_REDIS_GENERAL_MODE, _ADDR, _ADDRS, _PASSWORD, _TLS  (same pattern)
//
// Backward-compatible legacy vars (mapped to rec scene):
//
//	CONTENT_REDIS_ADDR, CONTENT_REDIS_PASSWORD, CONTENT_REDIS_DB
//
// RecModelService overrides:
//
//	REC_MODEL_SERVICE_URL, REC_MODEL_SERVICE_ENABLED, REC_MODEL_SERVICE_TIMEOUT_MS
func applyEnvOverrides(cfg *config) {
	applyRedisSceneEnv("CONTENT_REDIS_REC", &cfg.Redis.Rec)
	applyRedisSceneEnv("CONTENT_REDIS_GENERAL", &cfg.Redis.General)

	// Legacy single-Redis env vars → rec scene (backward compat)
	if v := os.Getenv("CONTENT_REDIS_ADDR"); v != "" && cfg.Redis.Rec.Addr == "" {
		cfg.Redis.Rec.Addr = v
	}
	if v := os.Getenv("CONTENT_REDIS_PASSWORD"); v != "" && cfg.Redis.Rec.Password == "" {
		cfg.Redis.Rec.Password = v
	}
	if raw := os.Getenv("CONTENT_REDIS_DB"); raw != "" && cfg.Redis.Rec.DB == 0 {
		if n, err := strconv.Atoi(raw); err == nil {
			cfg.Redis.Rec.DB = n
		}
	}

	// MongoDB
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}

	// RecModelService
	if v := os.Getenv("REC_MODEL_SERVICE_URL"); v != "" {
		cfg.RecModelService.URL = v
	}
	if v := os.Getenv("REC_MODEL_SERVICE_ENABLED"); v == "true" || v == "1" {
		cfg.RecModelService.Enabled = true
	}
	if v := os.Getenv("REC_MODEL_SERVICE_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			cfg.RecModelService.TimeoutMs = ms
		}
	}
}

// applyRedisSceneEnv reads env vars with the given prefix and writes them into cfg.
// prefix example: "CONTENT_REDIS_REC" → reads CONTENT_REDIS_REC_MODE, _ADDR, etc.
func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := os.Getenv(prefix + "_MODE"); v != "" {
		cfg.Mode = v
	}
	if v := os.Getenv(prefix + "_ADDR"); v != "" {
		cfg.Addr = v
	}
	if v := os.Getenv(prefix + "_ADDRS"); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := os.Getenv(prefix + "_PASSWORD"); v != "" {
		cfg.Password = v
	}
	if v := os.Getenv(prefix + "_TLS"); v == "true" || v == "1" {
		cfg.TLS = true
	}
}

func hostname() string {
	h, _ := os.Hostname()
	if h == "" {
		h = "unknown"
	}
	return h
}

// projectorAdapter bridges content read-model projectors to application.Projector.
type projectorAdapter struct {
	discovery *recinfra.DiscoveryFeedProjector
	recommend *recinfra.RecommendFeatureProjector
}

func (a *projectorAdapter) Project(ctx context.Context, event application.ProjectorEvent) error {
	projectorEvent := recinfra.ProjectorEvent{
		Type:          event.Type,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       event.Payload,
		OccurredAt:    event.OccurredAt,
	}
	if a.discovery != nil {
		if err := a.discovery.Project(ctx, projectorEvent); err != nil {
			return err
		}
	}
	if a.recommend != nil {
		if err := a.recommend.Project(ctx, projectorEvent); err != nil {
			return err
		}
	}
	return nil
}

func resolveMongoURI(cfg config) string {
	uri := strings.TrimSpace(cfg.Mongo.URI)
	if uri == "" || uri == "${MONGO_URI}" {
		return ""
	}
	return uri
}

func resolveReportDSN(cfg config) string {
	if v := strings.TrimSpace(os.Getenv("REPORT_DATABASE_URL")); v != "" {
		return v
	}
	dsn := strings.TrimSpace(cfg.Postgres.ReportDSN)
	if dsn == "" || dsn == "${REPORT_DATABASE_URL}" {
		return ""
	}
	return dsn
}

func resolveStoryRuntimeConfig() application.StoryRuntimeConfig {
	return application.StoryRuntimeConfig{
		FeatureFlags: map[string]bool{
			"enable_create_action_entry": parseBoolEnv("CONTENT_FLAG_ENABLE_CREATE_ACTION_ENTRY", true),
			"enable_unified_create_editor": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_UNIFIED_CREATE_EDITOR",
				true,
			),
			"enable_identity_based_surfaces": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_IDENTITY_BASED_SURFACES",
				true,
			),
			"enable_identity_share_template": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_IDENTITY_SHARE_TEMPLATE",
				true,
			),
			"enable_assistant_content_identity_index": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_ASSISTANT_CONTENT_IDENTITY_INDEX",
				true,
			),
		},
		ExperimentBucket: getenvOrDefault(
			"CONTENT_STORY_EXPERIMENT_BUCKET",
			"local_story_enabled",
		),
		CurrentStage: getenvOrDefault("CONTENT_STORY_CURRENT_STAGE", "100%"),
		CanaryMatrix: []application.StoryCanaryStage{
			{Stage: "5%", RolloutPercent: 5},
			{Stage: "20%", RolloutPercent: 20},
			{Stage: "50%", RolloutPercent: 50},
			{Stage: "100%", RolloutPercent: 100},
		},
	}
}

func parseBoolEnv(key string, fallback bool) bool {
	switch strings.TrimSpace(strings.ToLower(os.Getenv(key))) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

// buildRedisRouter creates a redis.Router from the YAML config.
// Falls back to in-memory mode for scenes without addresses (local dev / tests).
func buildRedisRouter(cfg config) *rtredis.Router {
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec":     toSceneConfig(cfg.Redis.Rec),
			"general": toSceneConfig(cfg.Redis.General),
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	}
	return rtredis.MustNewRouter(routerCfg)
}

// toSceneConfig converts the YAML redisSceneCfg to rtredis.SceneConfig.
func toSceneConfig(r redisSceneCfg) rtredis.SceneConfig {
	mode := strings.ToLower(strings.TrimSpace(r.Mode))
	if mode == "" {
		mode = "standalone"
	}
	if mode == "standalone" && r.Addr == "" {
		mode = "memory"
	}
	if mode == "cluster" && len(r.Addrs) == 0 {
		mode = "memory"
	}
	return rtredis.SceneConfig{
		Mode:         mode,
		Addr:         r.Addr,
		Addrs:        r.Addrs,
		Password:     r.Password,
		DB:           r.DB,
		TLS:          r.TLS,
		PoolSize:     r.Pool.Size,
		MinIdleConns: r.Pool.MinIdle,
	}
}
