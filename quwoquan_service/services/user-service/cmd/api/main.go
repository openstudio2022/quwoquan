package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

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
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("user-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("user-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("user-service config compatibility failed: %v", err)
	}

	ctx := context.Background()
	addr := getenvOrDefault("USER_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	// 1. PostgreSQL
	pgPool, err := pgxpool.New(ctx, cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("postgres connect: %v", err)
	}
	defer pgPool.Close()
	if err := pgPool.Ping(ctx); err != nil {
		log.Fatalf("postgres ping: %v", err)
	}

	// 2. Run migrations
	if err := persistence.RunMigrations(ctx, pgPool); err != nil {
		log.Fatalf("migration: %v", err)
	}

	// 3. MongoDB
	var mongoDB *mongo.Database
	if cfg.MongoDB.URI != "" {
		mongoClient, err := mongo.Connect(mongoopts.Client().ApplyURI(cfg.MongoDB.URI))
		if err != nil {
			log.Fatalf("mongodb connect: %v", err)
		}
		defer func() { _ = mongoClient.Disconnect(ctx) }()
		dbName := cfg.MongoDB.Database
		if dbName == "" {
			dbName = "quwoquan"
		}
		mongoDB = mongoClient.Database(dbName)
	}

	// 4. Redis
	redisRouter := buildRedisRouter(cfg)
	defer redisRouter.Close()
	redisClient := redisRouter.Scene("general")

	// 5. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB)
	settingStore := persistence.NewPgSettingStore(pgPool)
	blockStore := persistence.NewPgBlockStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)

	var followStore *persistence.MongoFollowStore
	if mongoDB != nil {
		followStore = persistence.NewMongoFollowStore(mongoDB)
		if err := followStore.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: follow_edges index creation: %v", err)
		}
	}

	// 6. Caches
	profileCache := cache.NewProfileCache(redisClient)
	settingCache := cache.NewSettingCache(redisClient)
	blockCache := cache.NewBlockCache(redisClient)
	userEventPublisher := mq.NewEventPublisher(redisClient)
	userSyncService := runtimesync.NewService(redisClient, redisRouter.Scene("realtime"))

	// 7. Services
	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		settingStore,
		profileCache,
		settingCache,
		userEventPublisher,
		userSyncService,
	)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	followService := application.NewFollowService(
		followStore,
		profileStore,
		personaStore,
		profileCache,
		blockStore,
		userEventPublisher,
	)
	blockService := application.NewBlockService(blockStore, blockCache)
	personaService := application.NewPersonaService(personaStore, pgPool, profileCache)
	workService := application.NewWorkService(workStore)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	authService := application.NewAuthService(profileStore, personaStore, credentialStore, profileCache)
	subAccountService := application.NewSubAccountService(personaStore, profileStore, profileCache)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, personaStore)

	// 8. Handler
	handler := httpadapter.NewUserHandler(
		profileService, searchService, followService, blockService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
	).Routes()

	// 9. Start
	server := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("user-service listening on %s (env=%s)", addr, appEnv)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen and serve: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "user-service")
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

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		_ = mergeConfigFile(&cfg, defaultFile)
		_ = mergeConfigFile(&cfg, envFile)
		if configVersion != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			_ = mergeConfigFile(&cfg, versionFile)
		}
		return cfg, nil
	}
	_ = mergeConfigFile(&cfg, "configs/default/config.yaml")
	_ = mergeConfigFile(&cfg, "configs/"+appEnv+"/config.yaml")
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
	if v := os.Getenv("POSTGRES_DSN"); v != "" {
		cfg.Postgres.DSN = v
	}
	if v := os.Getenv("MONGODB_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("REDIS_ADDR"); v != "" {
		cfg.Redis.General.Addr = v
	}
}

func validateRuntimeCompatibility(cfg config, _, _ string) error {
	if cfg.Postgres.DSN == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
	return nil
}

func buildRedisRouter(cfg config) *rtredis.Router {
	rc := cfg.Redis.General
	mode := rc.Mode
	if mode == "" {
		mode = "memory"
	}
	return rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     mode,
				Addr:     rc.Addr,
				Addrs:    rc.Addrs,
				Password: rc.Password,
				DB:       rc.DB,
				TLS:      rc.TLS,
			},
		},
		DefaultScene: "general",
	})
}
