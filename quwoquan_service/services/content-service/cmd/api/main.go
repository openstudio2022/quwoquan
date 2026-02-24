package main

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"

	"gopkg.in/yaml.v3"
	rtrec "quwoquan_service/runtime/recommendation"
	httpadapter "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

type config struct {
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Redis struct {
		Addr     string `yaml:"addr"`
		Password string `yaml:"password"`
		DB       int    `yaml:"db"`
	} `yaml:"redis"`
	RecModelService struct {
		URL       string `yaml:"url"`
		TimeoutMs int    `yaml:"timeout_ms"`
		Enabled   bool   `yaml:"enabled"`
	} `yaml:"rec_model_service"`
}

func main() {
	cfg := loadConfig("configs/config.yaml")
	applyRecModelServiceEnv(&cfg)
	addr := getenvOrDefault("CONTENT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18080"
	}

	logger := slog.Default()

	redisClient := buildRedisClient(cfg)
	hotPath := rtrec.NewHotPath(redisClient)

	// Read path: SessionCache wraps HotPath with L1 cache + singleflight
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 10000)

	// Write path: BufferedHotPath wraps HotPath with async channel
	bufferedWriter := rtrec.NewBufferedHotPath(hotPath, rtrec.WithBufferLogger(logger))
	defer bufferedWriter.Stop()

	store := persistence.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostRepositorySource(store)

	opts := []rtrec.EngineOption{
		rtrec.WithRecallTimeout(150 * time.Millisecond),
		rtrec.WithLogger(logger),
	}
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
		opts = append(opts, rtrec.WithScorer(cascade))
		log.Printf("content-service rec-model-service enabled url=%s timeout=%v", cfg.RecModelService.URL, timeout)
	}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source}, opts...)
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(store,
		application.WithSignalProcessor(bufferedWriter),
	)
	behaviorService := application.NewBehaviorService(bufferedWriter, store)
	handler := httpadapter.NewContentHandler(feedService, postService, behaviorService).Routes()

	server := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("content-service listening on %s", addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen and serve: %v", err)
	}
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

// applyRecModelServiceEnv overrides rec_model_service from env (e.g. Docker: REC_MODEL_SERVICE_URL=http://rec-model-service:8000).
func applyRecModelServiceEnv(cfg *config) {
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

func buildRedisClient(cfg config) rtrec.RedisClient {
	addr := getenvOrDefault("CONTENT_REDIS_ADDR", cfg.Redis.Addr)
	if addr == "" {
		log.Printf("content-service using in-memory redis client")
		return recinfra.NewMemoryRedis()
	}
	password := getenvOrDefault("CONTENT_REDIS_PASSWORD", cfg.Redis.Password)
	db := cfg.Redis.DB
	if raw := os.Getenv("CONTENT_REDIS_DB"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil {
			db = parsed
		}
	}
	client := recinfra.NewRedisClientAdapter(addr, password, db)
	if _, err := client.Get(context.Background(), "__content_service_ping__"); err != nil {
		_ = client.Set(context.Background(), "__content_service_ping__", "1", time.Second)
	}
	log.Printf("content-service using redis addr=%s db=%d", addr, db)
	return client
}
