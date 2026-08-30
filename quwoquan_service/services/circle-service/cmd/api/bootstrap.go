package bootstrap

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/servicekit"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle/adapters/inbound/http"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/cache"
	circlepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/circle/persistence"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence"
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

// config 是 circle-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// Mongo 按「声明即装配」自动发现（DEC-028），env 覆盖键由服务名派生前缀
// CIRCLE 拼出。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Mongo servicekit.MongoConfig `yaml:"mongo"`

	// scene 专属键带 scene 段（CIRCLE_REDIS_GENERAL_ADDR）。不带 scene 段的
	// CIRCLE_REDIS_ADDR 已退役：`<PREFIX>_REDIS_ADDR` 这个形状在本仓库被
	// rtc-service 用作跨 scene 共享地址位，同一形状承载两种语义时读者无法
	// 从键名判断它给哪个 scene 供值。
	Redis struct {
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`

	ES searchviewes.Config `yaml:"es"`

	// 服务出口地址由部署面按无前缀共享键注入（同一个被调服务对多个调用方
	// 是同一地址），因此用 envAbsolute 而非服务前缀派生。声明在此是为了让
	// 键集进入 DeclaredEnvKeys，被注入键对账测试看见；下游构造器仍各自
	// fail-closed 校验空值。
	Egress struct {
		ContentBaseURL string `yaml:"-" envAbsolute:"CONTENT_SERVICE_BASE_URL"`
		ChatBaseURL    string `yaml:"-" envAbsolute:"CHAT_SERVICE_BASE_URL"`
		EntityBaseURL  string `yaml:"-" envAbsolute:"ENTITY_SERVICE_BASE_URL"`
		UserBaseURL    string `yaml:"-" envAbsolute:"USER_SERVICE_BASE_URL"`
	} `yaml:"-"`
}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix("circle-service"), &config{})
}

// retiredEnvKeys 列出被 scene 专属键取代的注入键。继续注入它们不会有任何读取点，
// general scene 就会缺地址而在装配期判否；拒收给出的是「这个键名已经没有读取点」
// 这条准确信息，比让部署面注入一个无人读的键更接近修复位置。
func retiredEnvKeys() []string {
	return []string{
		"CIRCLE_REDIS_MODE",
		"CIRCLE_REDIS_ADDR",
		"CIRCLE_REDIS_ADDRS",
		"CIRCLE_REDIS_PASSWORD",
		"CIRCLE_REDIS_DB",
		"CIRCLE_REDIS_TLS",
	}
}

// NewModule assembles circle-service without binding a listener, starting
// workers, admitting traffic, or owning process signals.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap("circle-service", servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("circle"),
		AuthorityScopes:      []string{"user.account.security.read"},
		// general 场景配置同时覆盖 rec/realtime 两个 codegen scene。
		RedisScenes: func(cfg *config) map[string]servicekit.RedisSceneConfig {
			return map[string]servicekit.RedisSceneConfig{
				"general":  cfg.Redis.General,
				"rec":      cfg.Redis.General,
				"realtime": cfg.Redis.General,
			}
		},
		RetiredEnvKeys: retiredEnvKeys(),
		Assemble:       assembleCircleDomain,
	})
}

func assembleCircleDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	db := asm.MongoDB
	accessTokenConfig := asm.Auth.AccessTokenConfig

	circleStore := persistence.NewMongoCircleStore(db.Collection("circles"))
	circleAggregateStore := circlepersistence.NewMongoAggregateStore(db)
	if err := circleAggregateStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle aggregate indexes failed: %w", err)
	}
	gatheringStore := gatheringpersistence.NewMongoAggregateStore(db)
	if err := gatheringStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("Gathering aggregate indexes failed: %w", err)
	}
	fileStore := filepersistence.NewMongoAggregateStore(db)
	if err := fileStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle file indexes failed: %w", err)
	}
	fileReaders := filepersistence.NewMongoReaders(db)
	groupStore := groupersistence.NewMongoAggregateStore(db)
	if err := groupStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle group indexes failed: %w", err)
	}
	groupReaders := groupersistence.NewMongoReaders(db)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(db)
	if err := groupMembershipStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle group membership indexes failed: %w", err)
	}
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(db)

	messageTransport, err := requireCircleAPIMessageTransport(
		ctx,
		asm.Identity.AppEnv,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport preflight failed: %w", err)
	}
	if err := asm.RedisRouter.PingAll(ctx); err != nil {
		log.Printf("WARN: circle-service redis ping: %v", err)
	}
	redisClient := asm.RedisRouter.Scene("general")
	cachedCircleStore := cache.NewCachedCircleStore(circleStore, redisClient)
	circleStorage := application.CircleStoragePorts{Records: cachedCircleStore}
	log.Printf("circle-service redis cache enabled via runtime router")

	feedStore := persistence.NewMongoFeedStore(db)
	discoveryFeedReader := persistence.NewMongoCircleDiscoveryFeedReader(db)
	if err := discoveryFeedReader.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle discovery feed indexes failed: %w", err)
	}
	cachedDiscoveryFeedReader := cache.NewCachedCircleDiscoveryFeedReader(
		discoveryFeedReader,
		redisClient,
	)
	placementStore := placementpersistence.NewMongoAggregateStore(db)
	if err := placementStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle post placement indexes failed: %w", err)
	}
	placementReaders := placementpersistence.NewMongoPolicyReaders(db)
	if err := placementReaders.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle post placement policy indexes failed: %w", err)
	}
	membershipStore := membershippersistence.NewMongoAggregateStore(db)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle membership indexes failed: %w", err)
	}
	membershipReaders := membershippersistence.NewMongoReaders(db)
	behaviorFactStore := behaviorfactpersistence.NewMongoAppendSink(db)
	if err := behaviorFactStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("circle behavior fact indexes failed: %w", err)
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
		return fmt.Errorf("search index build failed: %w", err)
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
		return fmt.Errorf("content-service credential init failed: %w", err)
	}
	gatheringSafetyCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"content.gathering.safety.authorize"},
	)
	if err != nil {
		return fmt.Errorf("Gathering safety authority credential init failed: %w", err)
	}
	gatheringSafetyAuthority, err := gatheringexternal.NewHTTPSafetyTerminationAuthorizer(
		cfg.Egress.ContentBaseURL,
		gatheringSafetyCredentials,
		nil,
	)
	if err != nil {
		return fmt.Errorf("Gathering safety authority invalid: %w", err)
	}
	gatheringChatCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig, "circle-service", []string{"chat.gathering.write"},
	)
	if err != nil {
		return fmt.Errorf("Chat Gathering projection credential init failed: %w", err)
	}
	gatheringConversationPort, err := gatheringexternal.NewChatConversationPort(
		cfg.Egress.ChatBaseURL, gatheringChatCredentials, nil,
	)
	if err != nil {
		return fmt.Errorf("Chat Gathering projection port invalid: %w", err)
	}
	gatheringTargetReader, err := gatheringexternal.NewTargetReader(gatheringexternal.TargetReaderConfig{
		ContentBaseURL: cfg.Egress.ContentBaseURL,
		EntityBaseURL:  cfg.Egress.EntityBaseURL,
		UserBaseURL:    cfg.Egress.UserBaseURL,
		Circles:        gatheringCircleReader{circles: circleAggregateStore},
	})
	if err != nil {
		return fmt.Errorf("Gathering target reader invalid: %w", err)
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
		return fmt.Errorf("Circle Host authority evaluator invalid: %w", err)
	}
	personaHostAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"user.persona.gathering_host_authority.evaluate"},
	)
	if err != nil {
		return fmt.Errorf("Persona Host authority credential init failed: %w", err)
	}
	personaHostAuthorityClient, err := gatheringexternal.NewPersonaHostAuthorityHTTPClient(
		cfg.Egress.UserBaseURL,
		personaHostAuthorityCredentials,
		nil,
	)
	if err != nil {
		return fmt.Errorf("Persona Host authority client invalid: %w", err)
	}
	entityHostAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"circle-service",
		[]string{"entity.homepage.gathering_host_authority.evaluate"},
	)
	if err != nil {
		return fmt.Errorf("EntityHomepage Host authority credential init failed: %w", err)
	}
	entityHostAuthorityClient, err := gatheringexternal.NewEntityHomepageHostAuthorityHTTPClient(
		cfg.Egress.EntityBaseURL,
		entityHostAuthorityCredentials,
		nil,
	)
	if err != nil {
		return fmt.Errorf("EntityHomepage Host authority client invalid: %w", err)
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
		cfg.Egress.ContentBaseURL, contentCredentials, nil,
	)
	if err != nil {
		return fmt.Errorf("content-service MediaAsset reader invalid: %w", err)
	}
	fileCommands := fileapp.NewCommandFacade(fileStore, fileReaders, mediaAssetReader)
	fileQueries := fileapp.NewQueryFacade(fileReaders, fileReaders)
	groupCommands := groupapp.NewCommandFacade(groupStore, groupReaders)
	groupQueries := groupapp.NewQueryFacade(groupReaders, groupReaders)
	groupConversationBindingProjector := groupapp.NewConversationBindingProjector(groupStore)
	groupConversationBindingFailures := groupersistence.NewMongoConversationBindingFailureStore(db)
	if err := groupConversationBindingFailures.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("group conversation binding failure indexes failed: %w", err)
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
		return fmt.Errorf("Post lifecycle projection indexes failed: %w", err)
	}
	instanceID := asm.Identity.InstanceID
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
		return fmt.Errorf("UserAccountClosed projection indexes failed: %w", err)
	}
	accountRestrictionProjection, err :=
		persistence.NewMongoUserAccountRestrictionProjection(db)
	if err != nil {
		return fmt.Errorf("account restriction projection invalid: %w", err)
	}
	if err := accountRestrictionProjection.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("account restriction projection indexes failed: %w", err)
	}
	accountClosedConsumer, err := messaging.NewUserAccountClosedConsumer(
		messageTransport,
		accountClosedProjection,
		accountClosedProjection,
		instanceID,
		nil,
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed consumer init failed: %w", err)
	}
	accountClosedConsumer.WithUserAccountRestrictionProjection(
		accountRestrictionProjection,
	)
	if err := accountClosedConsumer.EnsureGroup(ctx); err != nil {
		return fmt.Errorf("UserAccountClosed consumer group failed: %w", err)
	}
	groupConversationBindingConsumer, err := groupmessaging.NewCircleGroupConversationBindingConsumer(
		messageTransport,
		groupConversationBindingProjector,
		groupConversationBindingFailures,
		"circle-group-conversation-binding-projector:"+instanceID,
		nil,
	)
	if err != nil {
		return fmt.Errorf("group conversation binding consumer init failed: %w", err)
	}
	if err := groupConversationBindingConsumer.EnsureGroup(ctx); err != nil {
		return fmt.Errorf("group conversation binding consumer group failed: %w", err)
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
		return fmt.Errorf("Gathering event publisher init failed: %w", err)
	}
	gatheringOutboxRelay, err := gatheringapp.NewOutboxRelay(
		gatheringStore,
		gatheringEventPublisher,
	)
	if err != nil {
		return fmt.Errorf("Gathering outbox relay init failed: %w", err)
	}
	if err := messageTransport.SetDurableRetention(
		ctx,
		gatheringmessaging.GatheringEventStream,
		gatheringmessaging.GatheringEventRetention,
	); err != nil {
		return fmt.Errorf("Gathering event stream retention preflight failed: %w", err)
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
		return fmt.Errorf("Circle event publisher init failed: %w", err)
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
		return fmt.Errorf("Circle event stream retention preflight failed: %w", err)
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
		return fmt.Errorf("GatheringPlan runtime composition failed: %w", err)
	}
	objectRoutes.Handle("/", circleHandler)
	domainHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		objectRoutes,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/circle/account-closure/dead-letters:recover",
			Module:   rterr.ModuleCircle,
			Releaser: accountClosedConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route failed: %w", err)
	}
	asm.Mux.Handle("/", domainHandler)

	if ping := searchBuilt.HealthPing(); ping != nil {
		asm.Health.Register("elasticsearch", ping)
	}
	asm.Health.Register("content-post-owner-projection", func(_ context.Context) error {
		return contentPostConsumer.Healthy(5 * time.Second)
	})
	asm.Health.Register("user-account-closed-consumer", func(_ context.Context) error {
		return accountClosedConsumer.Healthy(10 * time.Second)
	})
	asm.Health.Register("gathering-chat-reconciliation", func(_ context.Context) error {
		return gatheringReconciler.Healthy(10 * time.Second)
	})
	asm.Health.Register("gathering-outbox-relay", func(hctx context.Context) error {
		return gatheringOutboxRelay.Healthy(hctx, 5*time.Second)
	})
	asm.Health.Register("circle-group-conversation-binding-projector", func(_ context.Context) error {
		return groupConversationBindingConsumer.Healthy(30 * time.Second)
	})
	asm.Health.Register("circle-post-count-projection", func(_ context.Context) error {
		return placementCountRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-post-placement-stream", func(_ context.Context) error {
		return placementStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-member-count-projection", func(_ context.Context) error {
		return membershipCountRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-membership-stream", func(_ context.Context) error {
		return membershipStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-weekly-active-projection", func(_ context.Context) error {
		return behaviorWeeklyActiveRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-behavior-fact-stream", func(_ context.Context) error {
		return behaviorStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-group-stream", func(_ context.Context) error {
		return groupStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-group-owner-membership", func(_ context.Context) error {
		return groupOwnerMembershipRelay.Healthy(5 * time.Second)
	})
	if groupSearchRelay != nil {
		asm.Health.Register("circle-group-search-index-relay", func(_ context.Context) error {
			return groupSearchRelay.Healthy(5 * time.Second)
		})
	}
	asm.Health.Register("circle-group-membership-stream", func(_ context.Context) error {
		return groupMembershipStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-file-stream", func(_ context.Context) error {
		return fileStreamRelay.Healthy(5 * time.Second)
	})
	asm.Health.Register("circle-event-stream", func(_ context.Context) error {
		return circleOutboxRelay.Healthy(5 * time.Second)
	})
	if circleSearchRelay != nil {
		asm.Health.Register("circle-search-index-relay", func(_ context.Context) error {
			return circleSearchRelay.Healthy(5 * time.Second)
		})
	}

	asm.Workers.Add(func(workerCtx context.Context) {
		contentPostConsumer.Run(workerCtx, 250*time.Millisecond)
	})
	asm.Workers.Add(accountClosedConsumer.Run)
	asm.Workers.Add(groupConversationBindingConsumer.Run)
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := gatheringReconciler.Run(workerCtx, 500*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("Gathering Chat reconciliation stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		gatheringOutboxRelay.Run(workerCtx, time.Second)
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := placementCountRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle post-count projection stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := placementStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle post-placement stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := membershipCountRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle member-count projection stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := membershipStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle membership stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := behaviorWeeklyActiveRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle weekly-active projection stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := behaviorStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle behavior-fact stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := groupStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := groupOwnerMembershipRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group owner-membership relay stopped: %v", err)
		}
	})
	if groupSearchRelay != nil {
		asm.Workers.Add(func(workerCtx context.Context) {
			if err := groupSearchRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
				log.Printf("circle group search-index relay stopped: %v", err)
			}
		})
	}
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := groupMembershipStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle group membership stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := fileStreamRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle file stream relay stopped: %v", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := circleOutboxRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
			log.Printf("circle event stream relay stopped: %v", err)
		}
	})
	if circleSearchRelay != nil {
		asm.Workers.Add(func(workerCtx context.Context) {
			if err := circleSearchRelay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil {
				log.Printf("circle search-index relay stopped: %v", err)
			}
		})
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
