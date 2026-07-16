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

	"gopkg.in/yaml.v3"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	httpadapter "quwoquan_service/services/circle-service/internal/adapters/http"
	"quwoquan_service/services/circle-service/internal/application"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/application/circle/circle_behavior_fact"
	fileapp "quwoquan_service/services/circle-service/internal/application/circle/circle_file"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group_membership"
	membershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_membership"
	placementapp "quwoquan_service/services/circle-service/internal/application/circle/circle_post_placement"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
	"quwoquan_service/services/circle-service/internal/infrastructure/cache"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_behavior_fact/persistence"
	fileexternal "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_file/external"
	filepersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_file/persistence"
	groupersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group/persistence"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group_membership/persistence"
	membershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_membership/persistence"
	placementpersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_post_placement/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/searchindex"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size    int `yaml:"size"`
		MinIdle int `yaml:"min_idle"`
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
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`

	ES searchindex.ESConfig `yaml:"es"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("circle-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("circle-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("circle-service config compatibility failed: %v", err)
	}

	addr := getenvOrDefault("CIRCLE_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18082"
	}

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "circle-service", SamplingRatio: 0.1})
	defer otelShutdown()

	// MongoDB
	mongoURI := getenvOrDefault("CIRCLE_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}
	mongoDBName := getenvOrDefault("CIRCLE_MONGO_DATABASE", cfg.Mongo.Database)
	if mongoDBName == "" {
		mongoDBName = "quwoquan_circle"
	}

	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "circle-service")
	defer mongoClient.Disconnect(ctx)

	db := mongoClient.Database(mongoDBName)
	circleStore := persistence.NewMongoCircleStore(db.Collection("circles"))
	fileStore := filepersistence.NewMongoAggregateStore(db)
	if err := fileStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle file indexes failed: %v", err)
	}
	fileReaders := filepersistence.NewMongoReaders(db)
	groupStore := groupersistence.NewMongoAggregateStore(db)
	if err := groupStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle group indexes failed: %v", err)
	}
	groupReaders := groupersistence.NewMongoReaders(db)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(db)
	if err := groupMembershipStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle group membership indexes failed: %v", err)
	}
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(db)

	// Redis (via runtime Router)
	router := buildRedisRouter(cfg)
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: circle-service redis ping: %v", err)
	}
	redisClient := router.Scene("general")
	cachedCircleStore := cache.NewCachedCircleStore(
		circleStore,
		circleStore,
		circleStore,
		redisClient,
	)
	circleStorage := application.CircleStoragePorts{
		Records: cachedCircleStore, Metrics: cachedCircleStore, Sections: cachedCircleStore,
		IDs: persistence.ObjectIDGenerator{},
	}
	log.Printf("circle-service redis cache enabled via runtime router")

	feedStore := persistence.NewMongoFeedStore(db.Collection("posts"))
	placementStore := placementpersistence.NewMongoAggregateStore(db)
	if err := placementStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle post placement indexes failed: %v", err)
	}
	placementReaders := placementpersistence.NewMongoPolicyReaders(db)
	if err := placementReaders.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle post placement policy indexes failed: %v", err)
	}
	membershipStore := membershippersistence.NewMongoAggregateStore(db)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle membership indexes failed: %v", err)
	}
	membershipReaders := membershippersistence.NewMongoReaders(db)
	behaviorFactStore := behaviorfactpersistence.NewMongoAppendSink(db)
	if err := behaviorFactStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle behavior fact indexes failed: %v", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the circle service runs without a
	// search publisher, so the primary write path is unaffected. The projector
	// reads circles back through the same (cached) store the service writes
	// through, so reconciles see the just-written state.
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchindex.Build(cfg.ES, circleStorage.Records)
	if err != nil {
		log.Fatalf("circle-service search index build failed: %v", err)
	}
	if err := searchBuilt.EnsureIndex(ctx); err != nil {
		log.Fatalf("circle-service search index ensure failed: %v", err)
	}

	// Application services
	circleOpts := []application.CircleServiceOption{
		application.WithFeedStore(feedStore),
	}
	if searchBuilt.Projector != nil {
		circleOpts = append(circleOpts, application.WithEventPublisher(searchBuilt.Projector))
	}
	circleService := application.NewCircleService(circleStorage, circleOpts...)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	contentCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig, "circle-service", []string{"content.media.reference.read"},
	)
	if err != nil {
		log.Fatalf("content-service credential init failed: %v", err)
	}
	mediaAssetReader, err := fileexternal.NewMediaAssetOwnerReader(
		os.Getenv("CONTENT_SERVICE_BASE_URL"), contentCredentials, nil,
	)
	if err != nil {
		log.Fatalf("content-service MediaAsset reader invalid: %v", err)
	}
	fileCommands := fileapp.NewCommandFacade(fileStore, fileReaders, mediaAssetReader)
	fileQueries := fileapp.NewQueryFacade(fileReaders, fileReaders)
	groupCommands := groupapp.NewCommandFacade(groupStore, groupReaders)
	groupQueries := groupapp.NewQueryFacade(groupReaders, groupReaders)
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	groupMembershipQueries := groupmembershipapp.NewQueryFacade(groupMembershipReaders, groupMembershipReaders)
	placementCommands := placementapp.NewCommandFacade(placementStore, placementPortsFrom(placementReaders))
	membershipCommands := membershipapp.NewCommandFacade(membershipStore, membershipReaders, membershipReaders)
	membershipQueries := membershipapp.NewQueryFacade(membershipReaders, membershipReaders)
	behaviorFactWriter := behaviorfactapp.NewWriter(behaviorFactStore, behaviorFactStore)
	postLifecycleProjection := placementpersistence.NewMongoPostLifecycleProjection(db)
	if err := postLifecycleProjection.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle Post lifecycle projection indexes failed: %v", err)
	}
	instanceID, _ := os.Hostname()
	contentPostConsumer := messaging.NewContentPostConsumer(
		redisClient, postLifecycleProjection, postLifecycleProjection, instanceID, nil,
	)
	placementCountRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		placementpersistence.NewMongoPostCountProjector(db, redisClient),
		"circle-post-count",
	)
	placementStreamRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		messaging.NewCirclePostPlacementStreamPublisher(redisClient),
		"circle-post-placement-stream",
	)
	membershipCountRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		membershippersistence.NewMongoMemberCountProjector(db, redisClient),
		"circle-member-count",
	)
	membershipStreamRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		messaging.NewCircleMembershipStreamPublisher(redisClient),
		"circle-membership-stream",
	)
	behaviorWeeklyActiveRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		behaviorfactpersistence.NewMongoWeeklyActiveProjector(db, redisClient),
		"circle-weekly-active",
	)
	behaviorStreamRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		messaging.NewCircleBehaviorFactStreamPublisher(redisClient),
		"circle-behavior-fact-stream",
	)
	groupStreamRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		messaging.NewCircleGroupStreamPublisher(redisClient),
		"circle-group-stream",
	)
	groupOwnerMembershipRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		groupmembershipapp.NewCircleGroupOwnerProjector(groupMembershipCommands),
		"circle-group-owner-membership",
	)
	groupMembershipStreamRelay := groupmembershipapp.NewOutboxRelay(
		groupMembershipStore, groupMembershipStore,
		messaging.NewCircleGroupMembershipStreamPublisher(redisClient),
		"circle-group-membership-stream",
	)
	fileStreamRelay := fileapp.NewOutboxRelay(
		fileStore, fileStore,
		messaging.NewCircleFileStreamPublisher(redisClient),
		"circle-file-stream",
	)

	handler := httpadapter.NewCircleHandler(
		circleService, fileCommands, fileQueries, behaviorFactWriter, groupCommands, groupQueries,
		groupMembershipCommands, groupMembershipQueries,
		membershipCommands, membershipQueries, placementCommands,
	).Routes()
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("device ticket verifier invalid: %v", err)
	}
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("circle"),
	)(handler)

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("search-es", ping)
	}
	healthChecker.Register("content-post-owner-projection", func(_ context.Context) error {
		return contentPostConsumer.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-post-count-projection", func(_ context.Context) error {
		return placementCountRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-post-placement-stream", func(_ context.Context) error {
		return placementStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-member-count-projection", func(_ context.Context) error {
		return membershipCountRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-membership-stream", func(_ context.Context) error {
		return membershipStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-weekly-active-projection", func(_ context.Context) error {
		return behaviorWeeklyActiveRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-behavior-fact-stream", func(_ context.Context) error {
		return behaviorStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-group-stream", func(_ context.Context) error {
		return groupStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-group-owner-membership", func(_ context.Context) error {
		return groupOwnerMembershipRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-group-membership-stream", func(_ context.Context) error {
		return groupMembershipStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-file-stream", func(_ context.Context) error {
		return fileStreamRelay.Healthy(5 * time.Second)
	})
	go contentPostConsumer.Run(ctx, 250*time.Millisecond)
	go func() {
		if err := placementCountRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle post-count projection stopped: %v", err)
		}
	}()
	go func() {
		if err := placementStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle post-placement stream relay stopped: %v", err)
		}
	}()
	go func() {
		if err := membershipCountRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle member-count projection stopped: %v", err)
		}
	}()
	go func() {
		if err := membershipStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle membership stream relay stopped: %v", err)
		}
	}()
	go func() {
		if err := behaviorWeeklyActiveRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle weekly-active projection stopped: %v", err)
		}
	}()
	go func() {
		if err := behaviorStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle behavior-fact stream relay stopped: %v", err)
		}
	}()
	go func() {
		if err := groupStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle group stream relay stopped: %v", err)
		}
	}()
	go func() {
		if err := groupOwnerMembershipRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle group owner-membership relay stopped: %v", err)
		}
	}()
	go func() {
		if err := groupMembershipStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle group membership stream relay stopped: %v", err)
		}
	}()
	go func() {
		if err := fileStreamRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			log.Printf("circle file stream relay stopped: %v", err)
		}
	}()
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("circle-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("circle-service exception logger init failed: %v", err)
	}
	observed := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "circle-service",
		ServiceName:       "circle-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)

	hotConfigStore := controlplane.NewHotConfigStore()
	rateLimiter := rtgov.NewRateLimiter(1000)
	go startConfigSyncLoop(serviceName, appEnv, configRoot, configVersion, imageVersion, instanceID, hotConfigStore, rateLimiter)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(observed)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier, DeviceTicketVerifier: deviceTicketVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("circle-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("circle-service: %v", err)
	}
}

func placementPortsFrom(readers *placementpersistence.MongoPolicyReaders) placementports.PolicyReaders {
	return placementports.PolicyReaders{
		Circles: readers, Groups: readers, Posts: readers, Memberships: readers,
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "circle-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
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
		mergeConfigFile(&cfg, defaultFile)
		mergeConfigFile(&cfg, envFile)
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", serviceName, "configs", "releases", configVersion+".yaml")
			mergeConfigFile(&cfg, versionFile)
		}
		return cfg, nil
	}
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		mergeConfigFile(&cfg, localDefault)
		mergeConfigFile(&cfg, localEnv)
		return cfg, nil
	}
	return loadConfig(filepath.Join("configs", "config.yaml")), nil
}

func loadConfig(path string) config {
	cfg := config{}
	raw, err := os.ReadFile(path)
	if err != nil {
		return cfg
	}
	yaml.Unmarshal(raw, &cfg)
	return cfg
}

func mergeConfigFile(cfg *config, path string) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return
	}
	yaml.Unmarshal(raw, cfg)
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("CIRCLE_MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}
	if v := os.Getenv("CIRCLE_MONGO_DATABASE"); v != "" {
		cfg.Mongo.Database = v
	}
	if v := os.Getenv("CIRCLE_REDIS_ADDR"); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := os.Getenv("CIRCLE_REDIS_PASSWORD"); v != "" {
		cfg.Redis.General.Password = v
	}
	if v := os.Getenv("CIRCLE_REDIS_DB"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cfg.Redis.General.DB = n
		}
	}
}

func buildRedisRouter(cfg config) *rtredis.Router {
	generalScene := toSceneConfig(cfg.Redis.General)
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"rec":      generalScene,
			"realtime": generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	}
	return platformredis.MustNewRouter(routerCfg)
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

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return nil
}
