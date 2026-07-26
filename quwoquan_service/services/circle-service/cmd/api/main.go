package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle/adapters/inbound/http"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/cache"
	circlepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/circle/persistence"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence"
	circleconfig "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/runtimeconfig"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/searchindex"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/persistence"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	fileexternal "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/external"
	filepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/persistence"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/infrastructure/persistence"
	placementapp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	placementpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
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

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMs int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`

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
	if err := run(); err != nil {
		log.Fatalf("circle-service: %v", err)
	}
}

func run() error {
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

	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		log.Fatalf("account security authority credential init failed: %v", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(cfg.UserAccountSecurityAuthority.TimeoutMs) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     cfg.UserAccountSecurityAuthority.BaseURL,
			HTTPClient:  &http.Client{Timeout: accountSecurityAuthorityTimeout},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		log.Fatalf("account security authority config invalid: %v", err)
	}

	addr := getenvOrDefault("CIRCLE_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18082"
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

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
	circleAggregateStore := circlepersistence.NewMongoAggregateStore(db)
	if err := circleAggregateStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle aggregate indexes failed: %v", err)
	}
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
	router, messageTransportSceneModes := buildRedisRouter(cfg)
	defer router.Close()
	messageTransport, err := requireCircleAPIMessageTransport(
		ctx,
		appEnv,
		router,
		messageTransportSceneModes,
	)
	if err != nil {
		return fmt.Errorf("circle-service message transport preflight failed: %w", err)
	}
	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: circle-service redis ping: %v", err)
	}
	redisClient := router.Scene("general")
	cachedCircleStore := cache.NewCachedCircleStore(circleStore, redisClient)
	circleStorage := application.CircleStoragePorts{Records: cachedCircleStore}
	log.Printf("circle-service redis cache enabled via runtime router")

	feedStore := persistence.NewMongoFeedStore(db)
	discoveryFeedReader := persistence.NewMongoCircleDiscoveryFeedReader(db)
	if err := discoveryFeedReader.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle discovery feed indexes failed: %v", err)
	}
	cachedDiscoveryFeedReader := cache.NewCachedCircleDiscoveryFeedReader(
		discoveryFeedReader,
		redisClient,
	)
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
		// SearchIndexView is a derived read model. A transient ES outage must not
		// make Circle writes unavailable; the projector retries on subsequent
		// domain events/backfill, while healthz exposes the dependency failure.
		log.Printf("WARN: circle-service search index ensure failed: %v", err)
	}

	// Application services
	circleService := application.NewCircleService(
		circleStorage,
		application.WithFeedStore(feedStore),
		application.WithDiscoveryFeedReader(cachedDiscoveryFeedReader),
	)
	circleCommands := application.NewCircleCommandFacade(
		circleAggregateStore,
		membershipRoleReaderFrom(db),
		cachedCircleStore,
		nil,
	)
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
	groupConversationBindingProjector := groupapp.NewConversationBindingProjector(groupStore)
	groupConversationBindingFailures := groupersistence.NewMongoConversationBindingFailureStore(db)
	if err := groupConversationBindingFailures.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle group conversation binding failure indexes failed: %v", err)
	}
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	groupMembershipQueries := groupmembershipapp.NewQueryFacade(groupMembershipReaders, groupMembershipReaders)
	placementCommands := placementapp.NewCommandFacade(placementStore, placementPortsFrom(placementReaders))
	membershipCommands := membershipapp.NewCommandFacade(membershipStore, membershipReaders, membershipReaders)
	membershipQueries := membershipapp.NewQueryFacade(membershipReaders, membershipReaders, membershipReaders)
	behaviorFactWriter := behaviorfactapp.NewWriter(behaviorFactStore, behaviorFactStore)
	postLifecycleProjection := placementpersistence.NewMongoPostLifecycleProjection(db)
	if err := postLifecycleProjection.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle Post lifecycle projection indexes failed: %v", err)
	}
	instanceID, _ := os.Hostname()
	if strings.TrimSpace(instanceID) == "" {
		instanceID = "circle-service"
	}
	contentPostConsumer := messaging.NewContentPostConsumer(
		messageTransport, postLifecycleProjection, postLifecycleProjection, instanceID, nil,
	).WithDiscoveryFeedCache(redisClient)
	accountClosedProjection := persistence.NewMongoUserAccountClosedProjection(
		db,
		redisClient,
	)
	if err := accountClosedProjection.EnsureIndexes(ctx); err != nil {
		log.Fatalf("circle UserAccountClosed projection indexes failed: %v", err)
	}
	accountClosedConsumer, err := messaging.NewUserAccountClosedConsumer(
		messageTransport,
		accountClosedProjection,
		accountClosedProjection,
		instanceID,
		nil,
	)
	if err != nil {
		log.Fatalf("circle UserAccountClosed consumer init failed: %v", err)
	}
	if err := accountClosedConsumer.EnsureGroup(ctx); err != nil {
		log.Fatalf("circle UserAccountClosed consumer group failed: %v", err)
	}
	groupConversationBindingConsumer, err := messaging.NewCircleGroupConversationBindingConsumer(
		messageTransport,
		groupConversationBindingProjector,
		groupConversationBindingFailures,
		"circle-group-conversation-binding-projector:"+instanceID,
		nil,
	)
	if err != nil {
		log.Fatalf("circle group conversation binding consumer init failed: %v", err)
	}
	if err := groupConversationBindingConsumer.EnsureGroup(ctx); err != nil {
		log.Fatalf("circle group conversation binding consumer group failed: %v", err)
	}
	placementCountRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		placementpersistence.NewMongoPostCountProjector(db, cachedCircleStore),
		"circle-post-count",
	)
	placementStreamRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		messaging.NewCirclePostPlacementStreamPublisher(messageTransport),
		"circle-post-placement-stream",
	)
	membershipCountRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		membershippersistence.NewMongoMemberCountProjector(db, cachedCircleStore),
		"circle-member-count",
	)
	membershipStreamRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		messaging.NewCircleMembershipStreamPublisher(messageTransport),
		"circle-membership-stream",
	)
	behaviorWeeklyActiveRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		behaviorfactpersistence.NewMongoWeeklyActiveProjector(db, cachedCircleStore),
		"circle-weekly-active",
	)
	behaviorStreamRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		messaging.NewCircleBehaviorFactStreamPublisher(messageTransport),
		"circle-behavior-fact-stream",
	)
	groupStreamRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		messaging.NewCircleGroupStreamPublisher(messageTransport),
		"circle-group-stream",
	)
	groupOwnerMembershipRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		groupmembershipapp.NewCircleGroupOwnerProjector(groupMembershipCommands),
		"circle-group-owner-membership",
	)
	groupMembershipStreamRelay := groupmembershipapp.NewOutboxRelay(
		groupMembershipStore, groupMembershipStore,
		messaging.NewCircleGroupMembershipStreamPublisher(messageTransport),
		"circle-group-membership-stream",
	)
	fileStreamRelay := fileapp.NewOutboxRelay(
		fileStore, fileStore,
		messaging.NewCircleFileStreamPublisher(messageTransport),
		"circle-file-stream",
	)
	var circleSearchRelay *application.CircleOutboxRelay
	if searchBuilt.Projector != nil {
		circleSearchRelay = application.NewCircleOutboxRelay(
			circleAggregateStore, circleAggregateStore,
			application.NewCircleDomainEventSink(searchBuilt.Projector),
			"circle-search-index",
		)
	}

	handler := httpadapter.NewCircleHandler(
		circleService, circleCommands, fileCommands, fileQueries, behaviorFactWriter, groupCommands, groupQueries,
		groupMembershipCommands, groupMembershipQueries,
		membershipCommands, membershipQueries, placementCommands,
	).Routes()
	handler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		handler,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/circle/account-closure/dead-letters:recover",
			Module:   rterr.ModuleCircle,
			Releaser: accountClosedConsumer,
		},
	)
	if err != nil {
		log.Fatalf("circle account-closure recovery route failed: %v", err)
	}
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
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("elasticsearch", ping)
	}
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})
	healthChecker.Register("content-post-owner-projection", func(_ context.Context) error {
		return contentPostConsumer.Healthy(5 * time.Second)
	})
	healthChecker.Register("user-account-closed-consumer", func(_ context.Context) error {
		return accountClosedConsumer.Healthy(10 * time.Second)
	})
	healthChecker.Register("circle-group-conversation-binding-projector", func(_ context.Context) error {
		return groupConversationBindingConsumer.Healthy(30 * time.Second)
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
	if circleSearchRelay != nil {
		healthChecker.Register("circle-search-index-relay", func(_ context.Context) error {
			return circleSearchRelay.Healthy(5 * time.Second)
		})
	}
	go contentPostConsumer.Run(ctx, 250*time.Millisecond)
	accountClosedConsumerDone := make(chan struct{})
	go func() {
		defer close(accountClosedConsumerDone)
		accountClosedConsumer.Run(ctx)
	}()
	groupConversationBindingDone := make(chan struct{})
	go func() {
		defer close(groupConversationBindingDone)
		groupConversationBindingConsumer.Run(ctx)
	}()
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
	if circleSearchRelay != nil {
		go func() {
			if err := circleSearchRelay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
				log.Printf("circle search-index relay stopped: %v", err)
			}
		}()
	}
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("circle-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("circle-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
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
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("circle-service listening on %s (env=%s)", addr, appEnv)
	serverErr := rthttp.ListenAndServeGraceful(server, 15*time.Second)
	cancel()
	select {
	case <-accountClosedConsumerDone:
	case <-time.After(5 * time.Second):
		log.Printf("WARN: circle UserAccountClosed consumer shutdown timed out")
	}
	select {
	case <-groupConversationBindingDone:
	case <-time.After(5 * time.Second):
		log.Printf("WARN: circle group conversation binding consumer shutdown timed out")
	}
	if serverErr != nil {
		return serverErr
	}
	return nil
}

func placementPortsFrom(readers *placementpersistence.MongoPolicyReaders) placementports.PolicyReaders {
	return placementports.PolicyReaders{
		Circles: readers, Groups: readers, Posts: readers, Memberships: readers,
	}
}

// membershipRoleReader 复用 placement policy readers 的成员角色读，
// 适配 Circle 本体命令的权限校验端口。
type membershipRoleReader struct {
	readers *placementpersistence.MongoPolicyReaders
}

func membershipRoleReaderFrom(db *mongo.Database) circleports.MembershipRoleReader {
	return membershipRoleReader{readers: placementpersistence.NewMongoPolicyReaders(db)}
}

func (reader membershipRoleReader) ReadMembershipRole(ctx context.Context, circleID, personaID string) (string, string, bool, error) {
	slice, found, err := reader.readers.ReadMembershipRole(ctx, circleID, personaID)
	if err != nil || !found {
		return "", "", found, err
	}
	return slice.Role, slice.State, true, nil
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
	if err := circleconfig.LoadCanonicalSnapshot(serviceName, appEnv, configRoot, &cfg); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
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

func buildRedisRouter(cfg config) (*rtredis.Router, map[string]string) {
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
	return platformredis.MustNewRouter(routerCfg), map[string]string{
		"general": generalScene.Mode,
	}
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
