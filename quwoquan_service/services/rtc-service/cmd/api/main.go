package main

import (
	"context"
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
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/rtc-service/internal/adapters/http"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	wsadapter "quwoquan_service/services/rtc-service/internal/adapters/ws"
	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
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

	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`

	Redis struct {
		Realtime redisSceneCfg `yaml:"realtime"`
		General  redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`

	LiveKit struct {
		URL       string `yaml:"url"`
		APIKey    string `yaml:"api_key"`
		APISecret string `yaml:"api_secret"`
	} `yaml:"livekit"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("rtc-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("rtc-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("rtc-service config compatibility failed: %v", err)
	}

	addr := getenvOrDefault("RTC_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18083"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("rtc-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("rtc-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx := context.Background()
	mongoClient, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoDB.URI))
	if err != nil {
		log.Fatalf("rtc-service mongo connect failed: %v", err)
	}
	defer func() { _ = mongoClient.Disconnect(ctx) }()

	mongoDB := mongoClient.Database(cfg.MongoDB.Database)
	callStore := persistence.NewMongoCallStore(mongoDB)
	callCache := rtccache.NewCallStateCache(router.Scene("general"))
	eventPublisher := mq.NewEventPublisher(router.Scene("realtime"))

	roomAdapter := livekit.NewLiveKitRoomAdapter(cfg.LiveKit.URL, cfg.LiveKit.APIKey, cfg.LiveKit.APISecret)
	domainSvc := callsession.NewCallSessionService()
	roomSvc := application.NewRoomService(roomAdapter)
	tokenSvc := application.NewTokenService(cfg.LiveKit.APIKey, cfg.LiveKit.APISecret)

	signalHandler := wsadapter.NewSignalHandler(callCache, logger)
	orchestrator := application.NewCallOrchestrator(callStore, callCache, domainSvc, roomSvc, tokenSvc, eventPublisher, signalHandler)
	handler := httpadapter.NewCallHandler(orchestrator, signalHandler).Routes()

	observedHandler := rthttp.NewHTTPServerMiddleware(handler, rthttp.HTTPServerMiddlewareConfig{
		Service:           "rtc-service",
		ServiceName:       "rtc-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "rtc-service",
		Src:               "rtc-service",
	}, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr:              addr,
		Handler:           observedHandler,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	logger.Info("rtc-service starting", "addr", addr, "env", appEnv)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("rtc-service listen failed: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "rtc-service")
	appEnv = getenvOrDefault("APP_ENV", "local")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if appEnv != "local" && appEnv != "integration" && appEnv != "prod" {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of local|integration|prod, got %q", appEnv)
	}
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

func hostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return h
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

	legacyPath := filepath.Join("configs", "config.yaml")
	if _, err := os.Stat(legacyPath); err == nil {
		if err := mergeConfigFile(&cfg, legacyPath); err != nil {
			return config{}, fmt.Errorf("read legacy config: %w", err)
		}
	}
	return cfg, nil
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
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

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("MONGO_DATABASE"); v != "" {
		cfg.MongoDB.Database = v
	}

	if v := os.Getenv("LIVEKIT_URL"); v != "" {
		cfg.LiveKit.URL = v
	}
	if v := os.Getenv("LIVEKIT_API_KEY"); v != "" {
		cfg.LiveKit.APIKey = v
	}
	if v := os.Getenv("LIVEKIT_API_SECRET"); v != "" {
		cfg.LiveKit.APISecret = v
	}

	applyRedisSceneEnv("RTC_REDIS_REALTIME", &cfg.Redis.Realtime)
	applyRedisSceneEnv("RTC_REDIS_GENERAL", &cfg.Redis.General)

	if v := os.Getenv("REDIS_ADDR"); v != "" {
		if cfg.Redis.General.Addr == "" {
			cfg.Redis.General.Addr = v
		}
		if cfg.Redis.Realtime.Addr == "" {
			cfg.Redis.Realtime.Addr = v
		}
	}
}

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

func buildRedisRouter(cfg config) *rtredis.Router {
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": toSceneConfig(cfg.Redis.Realtime),
			"general":  toSceneConfig(cfg.Redis.General),
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	}
	return rtredis.MustNewRouter(routerCfg)
}

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
		Mode:     mode,
		Addr:     r.Addr,
		Addrs:    r.Addrs,
		Password: r.Password,
		DB:       r.DB,
		TLS:      r.TLS,
	}
}
