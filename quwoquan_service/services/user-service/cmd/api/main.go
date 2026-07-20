package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"

	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	accountsessionapp "quwoquan_service/services/user-service/internal/application/account/account_session"
	challengeapp "quwoquan_service/services/user-service/internal/application/account/authentication_challenge"
	credentialapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	registrationapp "quwoquan_service/services/user-service/internal/application/account/device_registration"
	useraccountapp "quwoquan_service/services/user-service/internal/application/account/user_account"
	usersettingsapp "quwoquan_service/services/user-service/internal/application/account/user_settings"
	personaapp "quwoquan_service/services/user-service/internal/application/persona/persona"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	visitapp "quwoquan_service/services/user-service/internal/application/relationship/followed_subject_visit_state"
	followingapp "quwoquan_service/services/user-service/internal/application/relationship/following_subject"
	relationshipapp "quwoquan_service/services/user-service/internal/application/relationship/persona_relationship"
	subjectfollowapp "quwoquan_service/services/user-service/internal/application/relationship/subject_follow"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	accountsessionpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/account_session/persistence"
	challengepersistence "quwoquan_service/services/user-service/internal/infrastructure/account/authentication_challenge/persistence"
	credentialpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/credential_binding/persistence"
	registrationpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/device_registration/persistence"
	useraccountcache "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/cache"
	useraccountobservability "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/observability"
	useraccountpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/persistence"
	useraccountprojection "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/projection"
	usersettingspersistence "quwoquan_service/services/user-service/internal/infrastructure/account/user_settings/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	userintegration "quwoquan_service/services/user-service/internal/infrastructure/integration"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/persona/persistence"
	proposalpersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/profile_update_proposal/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
	relobservability "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/observability"
	relationshippersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/persistence"
	relationshipprojection "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/projection"
	subjectfollowpersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/subject_follow/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/searchindex"
	"quwoquan_service/services/user-service/internal/infrastructure/tagindex"
	usercache "quwoquan_service/services/user-service/internal/infrastructure/user/cache"
	userobservability "quwoquan_service/services/user-service/internal/infrastructure/user/observability"
	userpersistence "quwoquan_service/services/user-service/internal/infrastructure/user/persistence"
)

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

	// 2. Run startup migrations with a persisted ledger so restart/rollout can
	// safely keep the existing Postgres volume.
	if err := persistence.RunManagedMigrations(ctx, pgPool); err != nil {
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
	personaStore := userpersistence.NewPgPersonaStore(pgPool)
	userSettingsStore, err := usersettingspersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("user-service UserSettings store init failed: %v", err)
	}
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := userpersistence.NewPgGreetingStore(pgPool)
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("CredentialBinding store init failed: %v", err)
	}
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	credentialQueries := credentialapp.NewCredentialQueryFacade(
		credentialStore,
	)
	accountSessionStore, err := accountsessionpersistence.NewAccountSessionPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("AccountSession store init failed: %v", err)
	}
	accountSessionCommands :=
		accountsessionapp.NewAccountSessionCommandFacade(accountSessionStore)
	deviceRegistrationStore, err := registrationpersistence.NewPostgresStore(
		pgPool,
	)
	if err != nil {
		log.Fatalf("DeviceRegistration store init failed: %v", err)
	}
	pushTokenCipher, err := registrationpersistence.LoadAESGCMTokenCipher(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("DeviceRegistration token cipher init failed: %v", err)
	}
	deviceRegistrationCommands := registrationapp.NewCommandFacade(
		deviceRegistrationStore,
		pushTokenCipher,
	)
	deviceRegistrationQueries := registrationapp.NewQueryFacade(
		deviceRegistrationStore,
		deviceRegistrationStore,
		personaStore,
		pushTokenCipher,
	)
	consentRecordStore := persistence.NewPgConsentRecordStore(pgPool)
	anonymousDeviceBindingStore := userpersistence.NewPgAnonymousDeviceBindingStore(pgPool)
	profileQrTokenStore := userpersistence.NewPgProfileQrTokenStore(pgPool)
	contactDiscoveryStore := userpersistence.NewPgContactDiscoveryStore(pgPool)
	personaProfileProposalStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Persona profile proposal Store init failed: %v", err)
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Store init failed: %v", err)
	}

	// 5b. Search index (ES) — write side of user.search_index_worker. Disabled
	// (no-op) unless es.enabled / SEARCH_ES_* are set, so the primary write path
	// is unaffected in alpha and any env without the shared cluster.
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchindex.Build(cfg.ES, profileStore)
	if err != nil {
		log.Fatalf("user-service search index build failed: %v", err)
	}
	if searchBuilt.Client != nil {
		if err := searchBuilt.EnsureIndex(ctx); err != nil {
			// UserProfile remains authoritative in Postgres. SearchIndexView is a
			// best-effort derived projection, so transient ES failure degrades
			// health without taking profile commands offline.
			log.Printf("WARN: user-service search index ensure failed: %v", err)
		}
		log.Printf("user-service search index enabled: %s", searchBuilt.Client.IndexName())
	}

	// 6. Caches
	profileCache := usercache.NewProfileCache(redisClient)
	// The domain MQ publisher stays the primary; when ES is enabled the search
	// projector is composed onto the fan-out tail (best-effort, never blocks).
	relationshipEventPublisher := mq.NewEventPublisher(redisClient)
	var userEventPublisher application.UserEventPublisher = relationshipEventPublisher
	accountCloseProjections := searchindex.ComposePublisher()
	if searchBuilt.Projector != nil {
		userEventPublisher = searchindex.ComposePublisher(userEventPublisher, searchBuilt.Projector)
		accountCloseProjections = searchindex.ComposePublisher(
			accountCloseProjections,
			searchBuilt.Projector,
		)
	}
	// object_tag_index 是 tag 域跨服务共享派生读模型（tag/storage.yaml），
	// writer 必须与 tag-service 读同一 Mongo database：优先 TAG_MONGO_URI/
	// TAG_MONGO_DATABASE（与 tag-service 同名 env，环境注入同值即对齐）。
	if objectTagColl := resolveObjectTagIndexCollection(ctx, mongoDB); objectTagColl != nil {
		objectTagProjector := tagindex.NewProjector(objectTagColl, profileStore)
		userEventPublisher = searchindex.ComposePublisher(
			userEventPublisher,
			objectTagProjector,
		)
		accountCloseProjections = searchindex.ComposePublisher(
			accountCloseProjections,
			objectTagProjector,
		)
	}
	if mongoDB != nil {
		mongoCleanupProjector :=
			useraccountprojection.NewMongoCleanupProjector(mongoDB)
		userEventPublisher = searchindex.ComposePublisher(
			userEventPublisher,
			mongoCleanupProjector,
		)
		accountCloseProjections = searchindex.ComposePublisher(
			accountCloseProjections,
			mongoCleanupProjector,
		)
	}
	userSyncService := runtimesync.NewService(redisClient, redisRouter.Scene("realtime"))

	// 7. Services
	var regionTagResolver application.RegionTagResolver = application.PathRegionTagResolver{}
	var profileTagValidator application.ProfileTagValidator = application.PathProfileTagValidator{}
	if tagServiceBaseURL := getenvOrDefault("TAG_SERVICE_BASE_URL", ""); tagServiceBaseURL != "" {
		regionTagResolver = userintegration.NewTagServiceRegionResolver(tagServiceBaseURL, nil)
		profileTagValidator = userintegration.NewTagServiceProfileTagValidator(tagServiceBaseURL, nil)
	}
	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
		application.WithRegionTagResolver(regionTagResolver),
		application.WithProfileTagValidator(profileTagValidator),
	)
	searchService := application.NewSearchService(profileStore, personaStore)
	// R-OBJ-001：对象级关系指标经 Prometheus sink 导出到 /metrics。
	reltelemetry.Collector().SetSink(relobservability.PrometheusSink{})
	userMetricsSink := userobservability.PrometheusSink{}
	usertelemetry.Collector().SetSink(userMetricsSink)
	usertelemetry.RolloutCollector().SetSink(userMetricsSink)
	relationshipCounterProjector := relationshipprojection.NewCounterProjector(
		pgPool,
		profileCache,
	)
	relationshipCounterReconciler := relationshipprojection.NewCounterReconciler(
		pgPool,
		profileCache,
	)
	go func() {
		if err := relationshipCounterReconciler.Run(
			ctx,
			time.Minute,
			500,
		); err != nil && ctx.Err() == nil {
			log.Printf(
				"ERROR: persona relationship counter reconciler stopped: %v",
				err,
			)
		}
	}()
	relationshipService := relationshipapp.NewPersonaRelationshipService(
		relationshipStore,
		personaStore,
		profileCache,
		greetingStore,
	)
	chatServiceBaseURL := strings.TrimSpace(getenvOrDefault("CHAT_SERVICE_BASE_URL", ""))
	if chatServiceBaseURL == "" {
		log.Fatal("user-service startup failed: CHAT_SERVICE_BASE_URL is required")
	}
	conversationGateway := userintegration.NewChatServiceClient(chatServiceBaseURL, nil)
	greetingService := application.NewGreetingService(
		greetingStore,
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
		relationshipEventPublisher,
		application.NewSettingsGreetingNotifyPolicy(
			userSettingsStore,
			personaStore,
		),
	)
	greetingOutboxRelay := application.NewGreetingOutboxRelay(
		greetingStore,
		userEventPublisher,
		relationshipEventPublisher,
	)
	go func() {
		if err := greetingOutboxRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: greeting outbox relay stopped: %v", err)
		}
	}()
	var creatorRuntimeStore *persistence.CreatorRuntimeProfileReader
	if mongoDB != nil {
		creatorRuntimeStore = persistence.NewCreatorRuntimeProfileReader(mongoDB)
	}
	subAccountOptions := make([]application.SubAccountServiceOption, 0, 1)
	if creatorRuntimeStore != nil {
		subAccountOptions = append(
			subAccountOptions,
			application.WithCreatorRuntimeProfiles(creatorRuntimeStore),
		)
	}
	// UserSettings 对象 packet：PG 聚合 store（state+outbox 同事务、内部 CAS）
	// + 对象专属 command/query facade；旧 SettingService 已退役。
	userSettingsCommands := usersettingsapp.NewUserSettingsCommandFacade(userSettingsStore)
	userSettingsQueries := usersettingsapp.NewUserSettingsQueryFacade(userSettingsStore)

	// SubjectFollow packet：PG 聚合 + receipt + outbox；relay 组合 Redis Stream
	// 发布与 following_subjects 投影 upsert（两者都成功才推进 checkpoint）。
	subjectFollowStore := subjectfollowpersistence.NewPgSubjectFollowStore(pgPool)
	subjectFollowService := subjectfollowapp.NewSubjectFollowService(subjectFollowStore)
	var followingSubjectStore *persistence.MongoFollowingSubjectStore
	var followedSubjectVisitStore *persistence.MongoFollowedSubjectVisitStore
	var followingProjector *followingapp.Projector
	if mongoDB != nil {
		followingSubjectStore = persistence.NewMongoFollowingSubjectStore(mongoDB)
		if err := followingSubjectStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("following subject index ensure failed: %v", err)
		}
		followedSubjectVisitStore = persistence.NewMongoFollowedSubjectVisitStore(mongoDB)
		if err := followedSubjectVisitStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("followed subject visit index ensure failed: %v", err)
		}
		followingProjector = followingapp.NewProjector(followingSubjectStore)
	}
	subjectFollowPublisher := &subjectFollowFanout{
		events:    relationshipEventPublisher,
		projector: followingProjector,
	}
	subjectFollowRelay := subjectfollowapp.NewOutboxRelay(subjectFollowStore, subjectFollowPublisher)
	go func() {
		if err := subjectFollowRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: subject follow outbox relay stopped: %v", err)
		}
	}()
	// PersonaFollowStateChanged 同样驱动 following_subjects 投影：relay 的
	// publisher 组合 Redis 发布与投影 upsert，两者都成功才推进 checkpoint。
	relationshipOutboxRelay := relationshipapp.NewOutboxRelay(
		relationshipStore,
		&personaRelationshipFanout{
			events:    relationshipEventPublisher,
			projector: followingProjector,
			counters:  relationshipCounterProjector,
		},
	)
	go func() {
		if err := relationshipOutboxRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: persona relationship outbox relay stopped: %v", err)
		}
	}()
	followedSubjectVisitService := visitapp.NewVisitService(
		followedSubjectVisitStore,
		followingSubjectStore,
	)
	var homepageDisplayResolver followingapp.SubjectDisplayResolver
	if entityServiceBaseURL := strings.TrimSpace(
		getenvOrDefault("ENTITY_SERVICE_BASE_URL", ""),
	); entityServiceBaseURL != "" {
		homepageDisplayResolver = userintegration.NewEntityHomepageDisplayClient(entityServiceBaseURL, nil)
	}
	followingSubjectQueryService := followingapp.NewQueryService(
		followingSubjectStore,
		personaStore,
		homepageDisplayResolver,
	)
	otpCodeCache := cache.NewOtpCodeCache(redisClient)
	authenticationChallengeStore, err :=
		challengepersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("AuthenticationChallenge store init failed: %v", err)
	}
	authenticationChallenges :=
		challengeapp.NewAuthenticationChallengeCommandFacade(
			authenticationChallengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
	socialProviderClient, err := socialAuthProviderClient(cfg)
	if err != nil {
		log.Fatalf("social auth provider client init failed: %v", err)
	}
	oneTapResolverImpl, err := oneTapResolver(cfg)
	if err != nil {
		log.Fatalf("one tap resolver init failed: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	accessSigner, err := rtauth.NewHS256Signer(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token signer invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token verifier invalid: %v", err)
	}
	otpCodeSealer, err := otpseal.LoadFromEnvironment()
	if err != nil {
		log.Fatalf("otp code reference sealer invalid: %v", err)
	}
	otpMode := configuredOTPMode(appEnv, cfg.Integration.OTP.Mode)
	otpCodeGenerator, err := otpCodeGeneratorForMode(appEnv, otpMode)
	if err != nil {
		log.Fatalf("otp mode invalid: %v", err)
	}
	externalInteractionBaseURL := getenvOrDefault("INTEGRATION_EXTERNAL_INTERACTION_BASE_URL", cfg.Integration.ExternalInteractionBaseURL)
	externalInteractionClient, err := otpExternalInteractionClientForEnvironment(
		appEnv,
		otpMode,
		externalInteractionBaseURL,
		accessSigner,
	)
	if err != nil {
		log.Fatalf("external interaction client init failed: %v", err)
	}
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithAccountSessionCommands(accountSessionCommands),
		application.WithCredentialCommands(credentialCommands),
		application.WithDeviceRegistration(deviceRegistrationCommands),
		application.WithConsentRecordStore(consentRecordStore),
		application.WithOtpCodeStore(otpCodeCache),
		application.WithAuthenticationChallenges(authenticationChallenges),
		application.WithOTPCodeSealer(otpCodeSealer),
		application.WithOTPCodeGenerator(otpCodeGenerator),
		application.WithExternalInteractionClient(externalInteractionClient),
		application.WithExternalAuthProviderClient(socialProviderClient),
		application.WithOneTapPhoneResolver(oneTapResolverImpl),
		application.WithAccessTokenSigner(accessSigner),
		application.WithDefaultNicknamePrefix(getenvOrDefault("USER_DEFAULT_NICKNAME_PREFIX", "新同学")),
	)
	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Persona command store init failed: %v", err)
	}
	subAccountService := application.NewSubAccountService(
		personaStore,
		personaCommandStore,
		profileStore,
		profileCache,
		subAccountOptions...,
	)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore, userEventPublisher)
	go contactDiscoveryService.RunExpiredCleanup(ctx, time.Hour)
	personaProfileProposalFacade, err := personaapp.NewProfileProposalFacade(personaProfileProposalStore)
	if err != nil {
		log.Fatalf("Persona profile proposal Facade init failed: %v", err)
	}
	profileProposalFacade, err := proposalapp.NewFacade(
		profileProposalStore,
		profileProposalStore,
		personaProfileProposalFacade,
		personaProfileProposalStore,
	)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Facade init failed: %v", err)
	}

	healthChecker := rthealth.NewChecker()
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("elasticsearch", ping)
	}
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
	var interestReader application.InterestProfileReader
	if mongoDB != nil {
		interestReader = projection.NewMongoInterestProfileReader(mongoDB)
	}
	interestProfileService := application.NewInterestProfileService(interestReader)
	accountCloseStore, err := useraccountpersistence.NewCloseStore(pgPool)
	if err != nil {
		log.Fatalf("UserAccount close store init failed: %v", err)
	}
	accountCloseOutboxStore, err :=
		useraccountpersistence.NewCloseOutboxStore(pgPool)
	if err != nil {
		log.Fatalf("UserAccount close outbox store init failed: %v", err)
	}
	accountCloseFanout, err := mq.NewUserAccountClosedFanout(
		relationshipEventPublisher,
		accountCloseProjections,
	)
	if err != nil {
		log.Fatalf("UserAccount close event fanout init failed: %v", err)
	}
	accountCloseOutboxRelay, err := useraccountapp.NewCloseOutboxRelay(
		accountCloseOutboxStore,
		accountCloseFanout,
		fmt.Sprintf("user-service-%d", os.Getpid()),
		useraccountapp.WithCloseOutboxObserver(
			useraccountobservability.CloseOutboxObserver{},
		),
	)
	if err != nil {
		log.Fatalf("UserAccount close outbox relay init failed: %v", err)
	}
	go accountCloseOutboxRelay.Run(ctx)
	closeAccountFacade := useraccountapp.NewCloseAccountFacade(
		accountCloseStore,
		useraccountcache.NewClosedAccountCache(redisClient),
	)
	userHandler, err := httpadapter.NewUserHandler(
		profileService, searchService, relationshipService, greetingService,
		userSettingsCommands, userSettingsQueries,
		authService, credentialQueries,
		deviceRegistrationCommands, deviceRegistrationQueries,
		subAccountService, contactDiscoveryService,
		interestProfileService,
		profileProposalFacade,
		subjectFollowService,
		followedSubjectVisitService,
		followingSubjectQueryService,
	)
	if err != nil {
		log.Fatalf("user-service HTTP composition failed: %v", err)
	}
	userHandler.WithAccountLifecycle(closeAccountFacade)
	handler := userHandler.Routes()

	outerMux := buildUserHTTPMux(handler, healthChecker)

	// 8.1 Observability middleware
	instanceID, _ := os.Hostname()
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("user-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("user-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("user-service exception logger init failed: %v", err)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "user-service",
		ServiceName:       "user-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())

	// 8.2 Interest profile projector: consume content's UserInterestRecomputed
	// and maintain the user-domain rm_user_profile_view interest read model.
	if mongoDB != nil {
		interestProjector := projection.NewInterestProfileProjector(mongoDB, nil)
		projCtx, projCancel := context.WithCancel(ctx)
		defer projCancel()
		go func() {
			if err := interestProjector.Run(projCtx, redisClient); err != nil && projCtx.Err() == nil {
				log.Printf("WARN: interest profile projector stopped: %v", err)
			}
		}()
	}

	// 9. Start
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{
		Addr: addr,
		// Authentication must run before observability builds ActorContext.
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("user-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("user-service: %v", err)
	}
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
	return platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"realtime": realtimeScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}
