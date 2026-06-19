package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	rtmongo "quwoquan_service/runtime/mongodb"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
	"quwoquan_service/services/entity-service/internal/infrastructure/persistence"
	"quwoquan_service/services/entity-service/internal/infrastructure/searchindex"
)

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	ES searchindex.ESConfig `yaml:"es"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("entity-service config load failed: %v", err)
	}
	normalizeDefaults(&cfg)

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "entity-service", SamplingRatio: 0.1})
	defer otelShutdown()

	var stateStore application.HomepageStateStore
	var mongoPing func(context.Context) error
	mongoURI := getenvOrDefault("ENTITY_MONGO_URI", cfg.Mongo.URI)
	if mongoURI != "" {
		mongoDBName := getenvOrDefault("ENTITY_MONGO_DATABASE", cfg.Mongo.Database)
		if mongoDBName == "" {
			mongoDBName = "quwoquan_entity"
		}
		mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "entity-service")
		stateStore = persistence.NewMongoHomepageStateStore(
			mongoClient.Database(mongoDBName).Collection("homepage_state"),
		)
		mongoPing = func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		}
		defer mongoClient.Disconnect(ctx)
	}

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("entity-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("entity-service exception logger init failed: %v", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the homepage service runs without a
	// projector, so the primary write path is unaffected.
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchindex.Build(cfg.ES)
	if err != nil {
		log.Fatalf("entity-service search index build failed: %v", err)
	}
	if err := searchBuilt.EnsureIndex(ctx); err != nil {
		log.Fatalf("entity-service search index ensure failed: %v", err)
	}

	var serviceOpts []application.HomepageServiceOption
	if searchBuilt.Projector != nil {
		serviceOpts = append(serviceOpts, application.WithProjector(searchBuilt.Projector))
	}
	homepageService := application.NewHomepageServiceWithStore(ctx, stateStore, serviceOpts...)
	handler := httpadapter.NewHandler(homepageService).Routes()
	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	if mongoPing != nil {
		healthChecker.Register("mongodb", mongoPing)
	}
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("search-es", ping)
	}
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle("/", handler)
	serverCfg := rthttp.HTTPServerMiddlewareConfig{
		Service:           "entity-service",
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          "entity-service.http",
		Src:               "gateway",
		ServiceName:       "entity-service",
		ServiceInstanceID: hostname(),
	}
	withObs := rthttp.NewHTTPServerMiddleware(rootMux, serverCfg, ioLogger, processLogger, exceptionLogger)

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(withObs)

	server := &http.Server{
		Addr:              cfg.Service.HTTP.Addr,
		Handler:           rateLimited,
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("entity-service listening on %s", cfg.Service.HTTP.Addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("entity-service: %v", err)
	}
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "entity-service")
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
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, err
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, err
		}
		if configVersion != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, err
			}
		}
		return cfg, nil
	}

	if err := mergeConfigFile(&cfg, filepath.Join("configs", "default", "config.yaml")); err == nil {
		_ = mergeConfigFile(&cfg, filepath.Join("configs", appEnv, "config.yaml"))
		if configVersion != "" {
			_ = mergeConfigFile(&cfg, filepath.Join("..", "..", "..", "releases", "config", serviceName, configVersion+".yaml"))
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
		cfg.Service.Name = "entity-service"
	}
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18084"
	}
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
