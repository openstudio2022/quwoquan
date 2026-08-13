package bootstrap

import (
	"context"
	"fmt"
	"log"
	"net"
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
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/servicehost"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle/adapters/inbound/http"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/cache"
	circlepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/circle/persistence"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence"
	circleconfig "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/runtimeconfig"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	behaviorfactmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/messaging"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/persistence"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	fileexternal "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/external"
	filemessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/messaging"
	filepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/persistence"
	groupievents "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/events"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/messaging"
	groupersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	groupmembershipmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/messaging"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	membershipmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/infrastructure/messaging"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/infrastructure/persistence"
	placementevents "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/events"
	placementapp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	placementmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/messaging"
	placementpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
	searchviewevents "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/adapters/inbound/events"
	searchviewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
	searchviewes "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/infrastructure/elasticsearch"
	searchviewpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/infrastructure/persistence"
	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringexternal "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
	gatheringmessaging "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/messaging"
	gatheringpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
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
		Version string `yaml:"version"`
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

	ES searchviewes.Config `yaml:"es"`
}

// NewModule assembles circle-service without binding a listener, starting
// workers, admitting traffic, or owning process signals.
func NewModule() (_ *Module, resultErr error) {
	cleanups := &cleanupStack{}
	initialized := false
	defer func() {
		if initialized {
			return
		}
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = cleanups.Close(cleanupCtx)
	}()

	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return nil, fmt.Errorf("circle-service runtime identity invalid: %w", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return nil, fmt.Errorf("circle-service config load failed: %w", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion, imageVersion); err != nil {
		return nil, fmt.Errorf("circle-service config identity failed: %w", err)
	}

	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("circle-service access token config invalid: %w", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service account security authority credential init failed: %w", err)
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
		return nil, fmt.Errorf("circle-service account security authority config invalid: %w", err)
	}

	addr := getenvOrDefault("CIRCLE_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18082"
	}

	ctx := context.Background()
	workers := &workerRegistry{}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "circle-service", SamplingRatio: 0.1})
	cleanups.Add(func(context.Context) error {
		otelShutdown()
		return nil
	})

	// MongoDB
	mongoURI := getenvOrDefault("CIRCLE_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}
	mongoDBName := getenvOrDefault("CIRCLE_MONGO_DATABASE", cfg.Mongo.Database)
	if mongoDBName == "" {
		mongoDBName = "quwoquan_circle"
	}

	mongoClient, err := rtmongo.Connect(ctx, rtmongo.ConnectConfig{URI: mongoURI})
	if err != nil {
		return nil, fmt.Errorf("circle-service MongoDB connect failed: %w", err)
	}
	cleanups.Add(mongoClient.Disconnect)

	db := mongoClient.Database(mongoDBName)
	circleStore := persistence.NewMongoCircleStore(db.Collection("circles"))
	circleAggregateStore := circlepersistence.NewMongoAggregateStore(db)
	if err := circleAggregateStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle aggregate indexes failed: %w", err)
	}
	gatheringStore := gatheringpersistence.NewMongoAggregateStore(db)
	if err := gatheringStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service Gathering aggregate indexes failed: %w", err)
	}
	fileStore := filepersistence.NewMongoAggregateStore(db)
	if err := fileStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle file indexes failed: %w", err)
	}
	fileReaders := filepersistence.NewMongoReaders(db)
	groupStore := groupersistence.NewMongoAggregateStore(db)
	if err := groupStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle group indexes failed: %w", err)
	}
	groupReaders := groupersistence.NewMongoReaders(db)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(db)
	if err := groupMembershipStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle group membership indexes failed: %w", err)
	}
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(db)

	// Redis (via runtime Router)
	router, messageTransportSceneModes := buildRedisRouter(cfg)
	cleanups.Add(func(context.Context) error { return router.Close() })
	messageTransport, err := requireCircleAPIMessageTransport(
		ctx,
		appEnv,
		router,
		messageTransportSceneModes,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service message transport preflight failed: %w", err)
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
		return nil, fmt.Errorf("circle-service circle discovery feed indexes failed: %w", err)
	}
	cachedDiscoveryFeedReader := cache.NewCachedCircleDiscoveryFeedReader(
		discoveryFeedReader,
		redisClient,
	)
	placementStore := placementpersistence.NewMongoAggregateStore(db)
	if err := placementStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle post placement indexes failed: %w", err)
	}
	placementReaders := placementpersistence.NewMongoPolicyReaders(db)
	if err := placementReaders.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle post placement policy indexes failed: %w", err)
	}
	membershipStore := membershippersistence.NewMongoAggregateStore(db)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle membership indexes failed: %w", err)
	}
	membershipReaders := membershippersistence.NewMongoReaders(db)
	behaviorFactStore := behaviorfactpersistence.NewMongoAppendSink(db)
	if err := behaviorFactStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service circle behavior fact indexes failed: %w", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the circle service runs without a
	// search publisher, so the primary write path is unaffected. The projector
	// reads circles back through the same (cached) store the service writes
	// through, so reconciles see the just-written state.
	searchviewes.ApplyEnvOverrides(&cfg.ES)
	searchBuilt, err := searchviewes.Build(cfg.ES)
	if err != nil {
		return nil, fmt.Errorf("circle-service search index build failed: %w", err)
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
		return nil, fmt.Errorf("circle-service content-service credential init failed: %w", err)
	}
	gatheringSafetyCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"content.gathering.safety.authorize"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Gathering safety authority credential init failed: %w", err)
	}
	gatheringSafetyAuthority, err := gatheringexternal.NewHTTPSafetyTerminationAuthorizer(
		os.Getenv("CONTENT_SERVICE_BASE_URL"),
		gatheringSafetyCredentials,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Gathering safety authority invalid: %w", err)
	}
	gatheringChatCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig, "circle-service", []string{"chat.gathering.write"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Chat Gathering projection credential init failed: %w", err)
	}
	gatheringConversationPort, err := gatheringexternal.NewChatConversationPort(
		os.Getenv("CHAT_SERVICE_BASE_URL"), gatheringChatCredentials, nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Chat Gathering projection port invalid: %w", err)
	}
	gatheringTargetReader, err := gatheringexternal.NewTargetReader(gatheringexternal.TargetReaderConfig{
		ContentBaseURL: os.Getenv("CONTENT_SERVICE_BASE_URL"),
		EntityBaseURL:  os.Getenv("ENTITY_SERVICE_BASE_URL"),
		UserBaseURL:    os.Getenv("USER_SERVICE_BASE_URL"),
		Circles:        gatheringCircleReader{circles: circleAggregateStore},
	})
	if err != nil {
		return nil, fmt.Errorf("circle-service Gathering target reader invalid: %w", err)
	}
	gatheringCommands := gatheringapp.NewCommandFacade(gatheringStore)
	gatheringQueryReader := gatheringpersistence.NewMongoGatheringQueryReader(db)
	gatheringQueries := gatheringapp.NewGatheringQueryFacade(
		gatheringQueryReader,
		time.Now,
	)
	circleHostAuthorityEvaluator, err := application.NewHostAuthorityEvaluator(
		circleAggregateStore,
		membershipStore,
		time.Now,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Circle Host authority evaluator invalid: %w", err)
	}
	personaHostAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"user.persona.gathering_host_authority.evaluate"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Persona Host authority credential init failed: %w", err)
	}
	personaHostAuthorityClient, err := gatheringexternal.NewPersonaHostAuthorityHTTPClient(
		os.Getenv("USER_SERVICE_BASE_URL"),
		personaHostAuthorityCredentials,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Persona Host authority client invalid: %w", err)
	}
	entityHostAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"entity.homepage.gathering_host_authority.evaluate"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service EntityHomepage Host authority credential init failed: %w", err)
	}
	entityHostAuthorityClient, err := gatheringexternal.NewEntityHomepageHostAuthorityHTTPClient(
		os.Getenv("ENTITY_SERVICE_BASE_URL"),
		entityHostAuthorityCredentials,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service EntityHomepage Host authority client invalid: %w", err)
	}
	gatheringHostAuthority := gatheringexternal.NewHostAuthorityReader(
		personaHostAuthorityClient,
		entityHostAuthorityClient,
		gatheringexternal.NewLocalCircleHostAuthorityClient(circleHostAuthorityEvaluator),
	)
	gatheringHostOutcome := gatheringapp.NewHostOutcomeFacade(
		gatheringStore,
		gatheringHostAuthority,
	)
	gatheringLifecycle := gatheringapp.NewLifecycleFacade(
		gatheringStore,
		gatheringTargetReader,
		gatheringHostOutcome,
		gatheringHostOutcome,
		gatheringHostOutcome,
		gatheringSafetyAuthority,
	)
	gatheringReconciler := gatheringapp.NewReconciler(
		gatheringStore, gatheringStore, gatheringConversationPort,
	)
	mediaAssetReader, err := fileexternal.NewMediaAssetOwnerReader(
		os.Getenv("CONTENT_SERVICE_BASE_URL"), contentCredentials, nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service content-service MediaAsset reader invalid: %w", err)
	}
	fileCommands := fileapp.NewCommandFacade(fileStore, fileReaders, mediaAssetReader)
	fileQueries := fileapp.NewQueryFacade(fileReaders, fileReaders)
	groupCommands := groupapp.NewCommandFacade(groupStore, groupReaders)
	groupQueries := groupapp.NewQueryFacade(groupReaders, groupReaders)
	groupConversationBindingProjector := groupapp.NewConversationBindingProjector(groupStore)
	groupConversationBindingFailures := groupersistence.NewMongoConversationBindingFailureStore(db)
	if err := groupConversationBindingFailures.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service group conversation binding failure indexes failed: %w", err)
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
		return nil, fmt.Errorf("circle-service Post lifecycle projection indexes failed: %w", err)
	}
	instanceID, _ := os.Hostname()
	if strings.TrimSpace(instanceID) == "" {
		instanceID = "circle-service"
	}
	contentPostConsumer := placementevents.NewContentPostConsumer(
		messageTransport, postLifecycleProjection, postLifecycleProjection, instanceID, nil,
	).WithDiscoveryFeedCacheInvalidator(func(ctx context.Context) error {
		return cache.InvalidateCircleDiscoveryFeed(ctx, redisClient)
	})
	accountClosedProjection := persistence.NewMongoUserAccountClosedProjection(
		db,
		redisClient,
	)
	if err := accountClosedProjection.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service UserAccountClosed projection indexes failed: %w", err)
	}
	accountRestrictionProjection, err :=
		persistence.NewMongoUserAccountRestrictionProjection(db)
	if err != nil {
		return nil, fmt.Errorf("circle-service account restriction projection invalid: %w", err)
	}
	if err := accountRestrictionProjection.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("circle-service account restriction projection indexes failed: %w", err)
	}
	accountClosedConsumer, err := messaging.NewUserAccountClosedConsumer(
		messageTransport,
		accountClosedProjection,
		accountClosedProjection,
		instanceID,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service UserAccountClosed consumer init failed: %w", err)
	}
	accountClosedConsumer.WithUserAccountRestrictionProjection(
		accountRestrictionProjection,
	)
	if err := accountClosedConsumer.EnsureGroup(ctx); err != nil {
		return nil, fmt.Errorf("circle-service UserAccountClosed consumer group failed: %w", err)
	}
	groupConversationBindingConsumer, err := groupmessaging.NewCircleGroupConversationBindingConsumer(
		messageTransport,
		groupConversationBindingProjector,
		groupConversationBindingFailures,
		"circle-group-conversation-binding-projector:"+instanceID,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service group conversation binding consumer init failed: %w", err)
	}
	if err := groupConversationBindingConsumer.EnsureGroup(ctx); err != nil {
		return nil, fmt.Errorf("circle-service group conversation binding consumer group failed: %w", err)
	}
	placementCountRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		circlePostCountConsumer{handler: application.NewCirclePostCountProjectionHandler(
			persistence.NewMongoPostCountProjector(db, cachedCircleStore),
		)},
		"circle-post-count",
	)
	placementStreamRelay := placementapp.NewOutboxRelay(
		placementStore, placementStore,
		placementmessaging.NewCirclePostPlacementStreamPublisher(messageTransport),
		"circle-post-placement-stream",
	)
	membershipCountRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		circleMembershipCountConsumer{handler: application.NewCircleMemberCountProjectionHandler(
			persistence.NewMongoMemberCountProjector(db, cachedCircleStore),
		)},
		"circle-member-count",
	)
	membershipStreamRelay := membershipapp.NewOutboxRelay(
		membershipStore, membershipStore,
		membershipmessaging.NewCircleMembershipStreamPublisher(messageTransport),
		"circle-membership-stream",
	)
	behaviorWeeklyActiveRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		circleWeeklyActiveConsumer{handler: application.NewCircleWeeklyActiveProjectionHandler(
			persistence.NewMongoWeeklyActiveProjector(db, cachedCircleStore),
		)},
		"circle-weekly-active",
	)
	behaviorStreamRelay := behaviorfactapp.NewOutboxRelay(
		behaviorFactStore, behaviorFactStore,
		behaviorfactmessaging.NewCircleBehaviorFactStreamPublisher(messageTransport),
		"circle-behavior-fact-stream",
	)
	groupStreamRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		groupmessaging.NewCircleGroupStreamPublisher(messageTransport),
		"circle-group-stream",
	)
	gatheringEventPublisher, err := gatheringmessaging.NewEventPublisher(messageTransport)
	if err != nil {
		return nil, fmt.Errorf("circle-service Gathering event publisher init failed: %w", err)
	}
	gatheringOutboxRelay, err := gatheringapp.NewOutboxRelay(
		gatheringStore,
		gatheringEventPublisher,
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service Gathering outbox relay init failed: %w", err)
	}
	if err := messageTransport.SetDurableRetention(
		ctx,
		gatheringmessaging.GatheringEventStream,
		gatheringmessaging.GatheringEventRetention,
	); err != nil {
		return nil, fmt.Errorf("circle-service Gathering event stream retention preflight failed: %w", err)
	}
	groupOwnerMembershipRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore,
		groupmembershipapp.NewCircleGroupOwnerProjector(groupMembershipCommands),
		"circle-group-owner-membership",
	)
	var groupSearchRelay *groupapp.OutboxRelay
	if searchBuilt.Indexer != nil {
		groupSearchRelay = groupapp.NewOutboxRelay(
			groupStore,
			groupStore,
			groupievents.NewCircleGroupSearchIndexHandler(searchBuilt.Indexer, groupStore),
			"circle-group-search-index",
		)
	}
	groupMembershipStreamRelay := groupmembershipapp.NewOutboxRelay(
		groupMembershipStore, groupMembershipStore,
		groupmembershipmessaging.NewCircleGroupMembershipStreamPublisher(messageTransport),
		"circle-group-membership-stream",
	)
	fileStreamRelay := fileapp.NewOutboxRelay(
		fileStore, fileStore,
		filemessaging.NewCircleFileStreamPublisher(messageTransport),
		"circle-file-stream",
	)
	circleEventPublisher, err := messaging.NewCircleEventStreamPublisher(messageTransport)
	if err != nil {
		return nil, fmt.Errorf("circle-service Circle event publisher init failed: %w", err)
	}
	circleOutboxRelay := application.NewCircleOutboxRelay(
		circleAggregateStore,
		circleAggregateStore,
		circleEventPublisher,
		"circle-event-stream",
	)
	if err := messageTransport.SetDurableRetention(
		ctx,
		messaging.CircleEventStream,
		messaging.CircleEventStreamRetention,
	); err != nil {
		return nil, fmt.Errorf("circle-service Circle event stream retention preflight failed: %w", err)
	}
	var circleSearchRelay *searchviewapp.Relay
	if searchBuilt.Index != nil {
		searchProjector := searchviewapp.NewProjector(searchBuilt.Index)
		searchSink := searchviewevents.NewSink(
			searchProjector,
			circleSearchItemSnapshotReader{store: circleAggregateStore},
		)
		circleSearchRelay = searchviewapp.NewRelay(
			circleSearchItemEventSource{reader: circleAggregateStore},
			searchviewpersistence.NewMongoCheckpointStore(db),
			searchSink,
			"circle-search-index",
		)
	}

	circleHandler := newCircleObjectRoutes(
		httpadapter.NewCircleHandler(circleService, circleCommands).
			WithHostAuthorityEvaluator(circleHostAuthorityEvaluator).
			Routes(),
		fileCommands, fileQueries, behaviorFactWriter, groupCommands, groupQueries,
		groupMembershipCommands, groupMembershipQueries,
		membershipCommands, membershipQueries, placementCommands,
	)
	objectRoutes := http.NewServeMux()
	gatheringhttp.NewHandler(
		gatheringLifecycle,
		gatheringCommands,
		gatheringHostOutcome,
		gatheringQueries,
	).Register(objectRoutes)
	if err := registerGatheringPlanRuntime(ctx, objectRoutes, db, gatheringStore); err != nil {
		return nil, fmt.Errorf("circle-service GatheringPlan runtime composition failed: %w", err)
	}
	objectRoutes.Handle("/", circleHandler)
	var handler http.Handler = objectRoutes
	handler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		handler,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/circle/account-closure/dead-letters:recover",
			Module:   rterr.ModuleCircle,
			Releaser: accountClosedConsumer,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("circle-service account-closure recovery route failed: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("circle-service access token verifier invalid: %w", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("circle-service device ticket config invalid: %w", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return nil, fmt.Errorf("circle-service device ticket verifier invalid: %w", err)
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
	healthChecker.Register("gathering-chat-reconciliation", func(_ context.Context) error {
		return gatheringReconciler.Healthy(10 * time.Second)
	})
	healthChecker.Register("gathering-outbox-relay", func(hctx context.Context) error {
		return gatheringOutboxRelay.Healthy(hctx, 5*time.Second)
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
	if groupSearchRelay != nil {
		healthChecker.Register("circle-group-search-index-relay", func(_ context.Context) error {
			return groupSearchRelay.Healthy(5 * time.Second)
		})
	}
	healthChecker.Register("circle-group-membership-stream", func(_ context.Context) error {
		return groupMembershipStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-file-stream", func(_ context.Context) error {
		return fileStreamRelay.Healthy(5 * time.Second)
	})
	healthChecker.Register("circle-event-stream", func(_ context.Context) error {
		return circleOutboxRelay.Healthy(5 * time.Second)
	})
	if circleSearchRelay != nil {
		healthChecker.Register("circle-search-index-relay", func(_ context.Context) error {
			return circleSearchRelay.Healthy(5 * time.Second)
		})
	}
	workers.Add(func(workerCtx context.Context) {
		contentPostConsumer.Run(workerCtx, 250*time.Millisecond)
	})
	workers.Add(accountClosedConsumer.Run)
	workers.Add(groupConversationBindingConsumer.Run)
	workers.Add(func(workerCtx context.Context) {
		if err := gatheringReconciler.Run(workerCtx, 500*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("Gathering Chat reconciliation stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		gatheringOutboxRelay.Run(workerCtx, time.Second)
	})
	workers.Add(func(workerCtx context.Context) {
		if err := placementCountRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle post-count projection stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := placementStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle post-placement stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := membershipCountRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle member-count projection stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := membershipStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle membership stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := behaviorWeeklyActiveRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle weekly-active projection stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := behaviorStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle behavior-fact stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := groupStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := groupOwnerMembershipRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group owner-membership relay stopped: %v", err)
		}
	})
	if groupSearchRelay != nil {
		workers.Add(func(workerCtx context.Context) {
			if err := groupSearchRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
				log.Printf("circle group search-index relay stopped: %v", err)
			}
		})
	}
	workers.Add(func(workerCtx context.Context) {
		if err := groupMembershipStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group membership stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := fileStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle file stream relay stopped: %v", err)
		}
	})
	workers.Add(func(workerCtx context.Context) {
		if err := circleOutboxRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle event stream relay stopped: %v", err)
		}
	})
	if circleSearchRelay != nil {
		workers.Add(func(workerCtx context.Context) {
			if err := circleSearchRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
				log.Printf("circle search-index relay stopped: %v", err)
			}
		})
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
		return nil, fmt.Errorf("circle-service runtime log exporter init failed: %w", err)
	}
	cleanups.Add(func(context.Context) error {
		runtimeLogExporter.Close()
		return nil
	})
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	cleanups.Add(func(context.Context) error {
		errorLogWriter.Close()
		standardLogWriter.Close()
		return nil
	})
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		return nil, fmt.Errorf("circle-service process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return nil, fmt.Errorf("circle-service exception logger init failed: %w", err)
	}
	observed := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "circle-service",
		ServiceName:       "circle-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)

	if err := registerConfigSyncWorker(
		workers,
		serviceName,
		appEnv,
		configRoot,
		configVersion,
		imageVersion,
		instanceID,
	); err != nil {
		return nil, err
	}
	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("circle"),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(observed),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module := &Module{
		appEnv:       appEnv,
		configDigest: strings.TrimSpace(configVersion),
		server:       server,
		health:       healthChecker,
		serveError:   make(chan error, 1),
		workerStarts: workers.starts,
		cleanup:      cleanups.Close,
	}
	if module.configDigest == "" {
		module.configDigest = strings.TrimSpace(cfg.Config.Version)
	}
	if module.configDigest == "" {
		module.configDigest = operationsecurity.ContractGraphSHA256
	}
	server.Handler = module.admissionHandler(server.Handler)
	server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	initialized = true
	return module, nil
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
	serviceName = strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("circle-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "circle-service"
	}
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = servicehost.ModuleEnvironmentValue(
		"circle-service",
		"CONFIG_VERSION",
	)
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

func validateRuntimeConfigurationIdentity(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return controlplane.ValidateImageIdentity(imageVersion)
}
