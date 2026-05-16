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
	"gopkg.in/yaml.v3"

	rthealth "quwoquan_service/runtime/health"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	rtmongo "quwoquan_service/runtime/mongodb"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"

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
		General  redisSceneCfg `yaml:"general"`
		Realtime redisSceneCfg `yaml:"realtime"`
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

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "user-service", SamplingRatio: 0.1})
	defer otelShutdown()

	addr := getenvOrDefault("USER_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	// 1. PostgreSQL
	poolCfg, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("postgres parse config: %v", err)
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
	var mongoClient *mongo.Client
	var mongoDB *mongo.Database
	if cfg.MongoDB.URI != "" {
		mongoClient = rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "user-service")
		dbName := cfg.MongoDB.Database
		if dbName == "" {
			dbName = "quwoquan"
		}
		mongoDB = mongoClient.Database(dbName)
	}
	defer func() {
		if mongoClient != nil {
			_ = mongoClient.Disconnect(ctx)
		}
	}()

	// 4. Redis
	redisRouter := buildRedisRouter(cfg)
	defer redisRouter.Close()
	if err := redisRouter.PingAll(ctx); err != nil {
		log.Printf("WARN: user-service redis ping: %v", err)
	}
	redisClient := redisRouter.Scene("general")

	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		log.Fatalf("load shard directory: %v", err)
	}

	// 5. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB)
	settingStore := persistence.NewPgSettingStore(pgPool)
	blockStore := persistence.NewPgBlockStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
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
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		profileCache,
		shardDirectory,
	)
	subAccountService := application.NewSubAccountService(personaStore, profileStore, profileCache)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, personaStore)

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("postgres", func(hctx context.Context) error {
		return pgPool.Ping(hctx)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return redisRouter.PingAll(hctx)
	})
	if mongoDB != nil {
		healthChecker.Register("mongodb", func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		})
	}

	// 8. Handler
	handler := httpadapter.NewUserHandler(
		profileService, searchService, followService, blockService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
	).Routes()

	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", handler)

	// 8.1 Observability middleware
	instanceID, _ := os.Hostname()
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("user-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("user-service exception logger init failed: %v", err)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "user-service",
		ServiceName:       "user-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)

	// 9. Start
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(observedHandler)
	server := &http.Server{
		Addr:              addr,
		Handler:           rateLimited,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("user-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("user-service: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "user-service")
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
	if v := os.Getenv("REDIS_REALTIME_ADDR"); v != "" {
		cfg.Redis.Realtime.Addr = v
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
	rt := cfg.Redis.Realtime
	if strings.TrimSpace(rt.Mode) == "" {
		rt.Mode = rc.Mode
	}
	if strings.TrimSpace(rt.Addr) == "" && len(rt.Addrs) == 0 {
		rt.Addr = rc.Addr
		rt.Addrs = append([]string(nil), rc.Addrs...)
	}
	if strings.TrimSpace(rt.Password) == "" {
		rt.Password = rc.Password
	}
	if rt.DB == 0 {
		rt.DB = rc.DB
	}
	if !rt.TLS {
		rt.TLS = rc.TLS
	}
	if rt.Pool.Size == 0 {
		rt.Pool.Size = rc.Pool.Size
	}
	if rt.Pool.MinIdle == 0 {
		rt.Pool.MinIdle = rc.Pool.MinIdle
	}
	if rt.Pool.ReadTimeoutMs == 0 {
		rt.Pool.ReadTimeoutMs = rc.Pool.ReadTimeoutMs
	}
	if rt.Pool.WriteTimeoutMs == 0 {
		rt.Pool.WriteTimeoutMs = rc.Pool.WriteTimeoutMs
	}
	if rt.Pool.DialTimeoutMs == 0 {
		rt.Pool.DialTimeoutMs = rc.Pool.DialTimeoutMs
	}
	mode := rc.Mode
	if mode == "" {
		mode = "memory"
	}
	rtMode := rt.Mode
	if rtMode == "" {
		rtMode = mode
	}
	generalScene := rtredis.SceneConfig{
		Mode:         mode,
		Addr:         rc.Addr,
		Addrs:        rc.Addrs,
		Password:     rc.Password,
		DB:           rc.DB,
		TLS:          rc.TLS,
		PoolSize:     rc.Pool.Size,
		MinIdleConns: rc.Pool.MinIdle,
	}
	realtimeScene := rtredis.SceneConfig{
		Mode:         rtMode,
		Addr:         rt.Addr,
		Addrs:        rt.Addrs,
		Password:     rt.Password,
		DB:           rt.DB,
		TLS:          rt.TLS,
		PoolSize:     rt.Pool.Size,
		MinIdleConns: rt.Pool.MinIdle,
	}
	return rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"realtime": realtimeScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}
