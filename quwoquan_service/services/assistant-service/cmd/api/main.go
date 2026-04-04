package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
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
		log.Printf("assistant-service events storage=mongodb db=%s", dbName)
		log.Printf("assistant-service learning profile storage=mongodb db=%s", dbName)
	} else {
		eventStore = persistence.NewMemoryEventStore()
		profileStore = projection.NewMemoryLearningProfileStore()
		log.Printf("assistant-service events storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service learning profile storage=inmemory (no mongodb.uri configured)")
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
	)
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
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("assistant-service listen failed: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "assistant-service")
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
	legacy := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, legacy); err != nil {
		return config{}, fmt.Errorf("read legacy config: %w", err)
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

func getenvOrDefault(key, fallback string) string {
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
