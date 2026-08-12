package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"

	runtimesync "quwoquan_service/runtime/sync"
	usercomposition "quwoquan_service/services/user-service/cmd/internal/composition"
	appealhttp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/adapters/inbound/http"
	appealapp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	appealidentity "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/identity"
	appealobservability "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/observability"
	appealpersistence "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/persistence"
	accountsessionadapter "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/application"
	accountsessionhttp "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/http"
	accountsessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	accountsessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	challengeadapter "quwoquan_service/services/user-service/internal/account/authentication_challenge/adapters/inbound/application"
	challengestream "quwoquan_service/services/user-service/internal/account/authentication_challenge/adapters/inbound/stream"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	credentialhttp "quwoquan_service/services/user-service/internal/account/credential_binding/adapters/inbound/http"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmessaging "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/messaging"
	credentialpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	registrationhttp "quwoquan_service/services/user-service/internal/account/device_registration/adapters/inbound/http"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	invitationhttp "quwoquan_service/services/user-service/internal/account/invitation/adapters/inbound/http"
	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationpersistence "quwoquan_service/services/user-service/internal/account/invitation/infrastructure/persistence"
	httpadapter "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	"quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
	useraccountcache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	useraccountobservability "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/observability"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	profileprojection "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/profileprojection"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/projection"
	useraccountprojection "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/projection"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/searchindex"
	usersyncstream "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/syncstream"
	usercache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/cache"
	userobservability "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/observability"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	usersettingshttp "quwoquan_service/services/user-service/internal/account/user_settings/adapters/inbound/http"
	usersettingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	usersettingspersistence "quwoquan_service/services/user-service/internal/account/user_settings/infrastructure/persistence"
	personaadapter "quwoquan_service/services/user-service/internal/persona_management/persona/adapters/inbound/application"
	personahttp "quwoquan_service/services/user-service/internal/persona_management/persona/adapters/inbound/http"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamessaging "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/messaging"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalhttp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/adapters/inbound/http"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmessaging "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/messaging"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
	creatorpersistence "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
	followingevent "quwoquan_service/services/user-service/internal/profile_projection/following_subject/adapters/inbound/event"
	followinghttp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/adapters/inbound/http"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	followingpersistence "quwoquan_service/services/user-service/internal/profile_projection/following_subject/infrastructure/persistence"
	contacthttp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/adapters/inbound/http"
	contactapp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/application"
	contactpersistence "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/infrastructure/persistence"
	visithttp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/adapters/inbound/http"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	visitpersistence "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/infrastructure/persistence"
	greetinghttp "quwoquan_service/services/user-service/internal/relationship/greeting_request/adapters/inbound/http"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingintegration "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/integration"
	greetingpersistence "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/persistence"
	relationshipadapter "quwoquan_service/services/user-service/internal/relationship/persona_relationship/adapters/inbound/application"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
	relobservability "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/observability"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	relationshipprojection "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/projection"
	subjectfollowhttp "quwoquan_service/services/user-service/internal/relationship/subject_follow/adapters/inbound/http"
	subjectfollowapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
	subjectfollowpersistence "quwoquan_service/services/user-service/internal/relationship/subject_follow/infrastructure/persistence"
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
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		log.Fatalf("user-service config identity failed: %v", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)

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
	messageTransport, err := newUserMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		cfg,
	)
	if err != nil {
		log.Fatalf("user-service message transport preflight failed: %v", err)
	}
	researchAuditTransport, _ := messageTransport.(runtimemessaging.DurableRecordAppender)
	researchSessionHandler, err := buildResearchSessionHandler(
		appEnv,
		cfg,
		researchAuditTransport,
	)
	if err != nil {
		log.Fatalf("research identity composition failed: %v", err)
	}
	managedAcceptanceIdentity, err := loadManagedAcceptanceIdentity()
	if err != nil && cfg.ResearchIdentity.Enabled {
		log.Fatalf("managed acceptance identity composition failed: %v", err)
	}
	redisClient := redisRouter.Scene("general")

	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		log.Fatalf("load shard directory: %v", err)
	}

	// 5. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := userpersistence.NewPgPersonaStore(pgPool)
	invitationStore, err := invitationpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Invitation store init failed: %v", err)
	}
	invitationFacade, err := invitationapp.NewFacade(
		invitationStore,
		personapersistence.NewOwnerReader(pgPool),
	)
	if err != nil {
		log.Fatalf("Invitation facade init failed: %v", err)
	}
	invitationHandler, err := invitationhttp.NewHandler(invitationFacade)
	if err != nil {
		log.Fatalf("Invitation HTTP composition failed: %v", err)
	}
	userSettingsStore, err := usersettingspersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("user-service UserSettings store init failed: %v", err)
	}
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := greetingpersistence.NewPgGreetingStore(pgPool)
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("CredentialBinding store init failed: %v", err)
	}
	credentialAuditTransport, ok := messageTransport.(runtimemessaging.DurableRecordAppender)
	if !ok {
		log.Fatal("CredentialBinding audit requires durable retention transport")
	}
	credentialAuditPublisher, err := credentialmessaging.NewSecurityAuditPublisher(
		credentialAuditTransport,
	)
	if err != nil {
		log.Fatalf("CredentialBinding audit publisher init failed: %v", err)
	}
	credentialAuditRelay, err := credentialapp.NewSecurityAuditRelay(
		credentialStore,
		credentialAuditPublisher,
	)
	if err != nil {
		log.Fatalf("CredentialBinding audit relay init failed: %v", err)
	}
	if _, err := credentialAuditRelay.Drain(ctx, 1); err != nil {
		log.Fatalf("CredentialBinding audit relay preflight failed: %v", err)
	}
	go func() {
		if err := credentialAuditRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: CredentialBinding audit relay stopped: %v", err)
		}
	}()
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
	contactDiscoveryStore := contactpersistence.NewPgContactDiscoveryStore(pgPool)
	personaProfileProposalStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Persona profile proposal Store init failed: %v", err)
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Store init failed: %v", err)
	}

	// 6. Caches
	profileCache := usercache.NewProfileCache(redisClient)
	// The domain MQ publisher remains the immediate profile-event path. Ordinary
	// profile search projection is relayed from its own durable PostgreSQL
	// checkpoint below; it must never run in this write-path fan-out.
	relationshipEventPublisher := mq.NewEventPublisher(messageTransport)
	var userEventPublisher application.UserEventPublisher = relationshipEventPublisher
	accountCloseProjections := searchindex.ComposePublisher()
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
	userSyncService := usersyncstream.NewRuntimeUserSyncStream(
		runtimesync.NewService(redisClient, redisRouter.Scene("realtime")),
	)

	// 7. Services
	var regionTagResolver application.RegionTagResolver = application.PathRegionTagResolver{}
	var profileTagValidator application.ProfileTagValidator = application.PathProfileTagValidator{}
	if tagServiceBaseURL := getenvOrDefault("TAG_SERVICE_BASE_URL", ""); tagServiceBaseURL != "" {
		regionTagResolver = userintegration.NewTagServiceRegionResolver(tagServiceBaseURL, nil)
		profileTagValidator = userintegration.NewTagServiceProfileTagValidator(tagServiceBaseURL, nil)
	}
	publicWebBaseURL := strings.TrimSpace(getenvOrDefault("PUBLIC_WEB_BASE_URL", ""))
	if publicWebBaseURL == "" {
		log.Fatal("PUBLIC_WEB_BASE_URL must be injected from environment topology")
	}
	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Persona command store init failed: %v", err)
	}
	personaDurableTransport, ok := messageTransport.(runtimemessaging.DurableRecordAppender)
	if !ok {
		log.Fatal("Persona publication requires durable retention transport")
	}
	if err := personaDurableTransport.SetDurableRetention(
		ctx,
		personamessaging.PersonaEventStream,
		personamessaging.PersonaEventStreamRetention,
	); err != nil {
		log.Fatalf("Persona event stream retention setup failed: %v", err)
	}
	personaEventPublisher, err := personamessaging.NewEventPublisher(personaDurableTransport)
	if err != nil {
		log.Fatalf("Persona event publisher init failed: %v", err)
	}
	personaOutboxRelay, err := personaapp.NewOutboxRelay(
		personaCommandStore,
		personaEventPublisher,
	)
	if err != nil {
		log.Fatalf("Persona outbox relay init failed: %v", err)
	}
	if _, err := personaOutboxRelay.Drain(ctx, 1); err != nil {
		log.Fatalf("Persona outbox relay preflight failed: %v", err)
	}
	go func() {
		if err := personaOutboxRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: Persona outbox relay stopped: %v", err)
		}
	}()
	personaProfileProjectionStore, err := useraccountpersistence.NewPersonaProfileProjector(pgPool)
	if err != nil {
		log.Fatalf("Persona profile projector init failed: %v", err)
	}
	personaProfileProjector, err := application.NewPersonaProfileProjector(
		personaProfileProjectionStore,
	)
	if err != nil {
		log.Fatalf("Persona profile application facet init failed: %v", err)
	}
	go func() {
		if err := personaProfileProjector.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: Persona profile projector stopped: %v", err)
		}
	}()
	profileService, err := application.NewProfileService(
		profileStore,
		personaStore,
		personaCommandStore,
		personaProfileProjector,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
		application.WithRegionTagResolver(regionTagResolver),
		application.WithProfileTagValidator(profileTagValidator),
		application.WithProfilePublicBaseURL(publicWebBaseURL),
	)
	if err != nil {
		log.Fatalf("Profile service init failed: %v", err)
	}
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
	chatCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"user-service",
		[]string{"chat.conversation.internal_direct"},
	)
	if err != nil {
		log.Fatalf("user-service chat credential init failed: %v", err)
	}
	conversationGateway, err := userintegration.NewAuthorizedChatServiceClient(
		chatServiceBaseURL,
		nil,
		chatCredentials,
	)
	if err != nil {
		log.Fatalf("user-service chat client init failed: %v", err)
	}
	contentServiceBaseURL := strings.TrimSpace(getenvOrDefault("CONTENT_SERVICE_BASE_URL", ""))
	if contentServiceBaseURL == "" {
		log.Fatal("user-service startup failed: CONTENT_SERVICE_BASE_URL is required")
	}
	intersectionCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"user-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		log.Fatalf("user-service content credential init failed: %v", err)
	}
	intersectionResolver, err := greetingintegration.NewIntersectionResolver(
		contentServiceBaseURL,
		nil,
		intersectionCredentials,
	)
	if err != nil {
		log.Fatalf("user-service greeting intersection resolver init failed: %v", err)
	}
	greetingService := greetingapp.NewGreetingService(
		greetingStore,
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
		relationshipEventPublisher,
		personapersistence.NewOwnerReader(pgPool),
		greetingapp.NewSettingsGreetingNotifyPolicy(
			userSettingsStore,
		),
		intersectionResolver,
	)
	greetingOutboxRelay := greetingapp.NewGreetingOutboxRelay(
		greetingStore,
		userEventPublisher,
		relationshipEventPublisher,
	)
	go func() {
		if err := greetingOutboxRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: greeting outbox relay stopped: %v", err)
		}
	}()
	var creatorRuntimeStore *creatorpersistence.CreatorRuntimeProfileReader
	if mongoDB != nil {
		creatorRuntimeStore = creatorpersistence.NewCreatorRuntimeProfileReader(mongoDB)
	}
	personaOptions := make([]application.PersonaServiceOption, 0, 1)
	if creatorRuntimeStore != nil {
		personaOptions = append(
			personaOptions,
			application.WithCreatorRuntimeProfiles(
				usercomposition.NewCreatorRuntimeProfileAdapter(creatorRuntimeStore),
			),
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
	var followingSubjectStore *followingpersistence.MongoFollowingSubjectStore
	var followedSubjectVisitStore *visitpersistence.MongoFollowedSubjectVisitStore
	var followingProjector *followingevent.Handler
	if mongoDB != nil {
		followingSubjectStore = followingpersistence.NewMongoFollowingSubjectStore(mongoDB)
		if err := followingSubjectStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("following subject index ensure failed: %v", err)
		}
		followedSubjectVisitStore = visitpersistence.NewMongoFollowedSubjectVisitStore(mongoDB)
		if err := followedSubjectVisitStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("followed subject visit index ensure failed: %v", err)
		}
		followingProjector = followingevent.NewHandler(
			followingapp.NewFollowingSubjectProjector(followingSubjectStore),
		)
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
	// FollowedSubjectVisitState packet：Mongo 水位 + FollowedSubjectVisited
	// outbox 同事务提交；relay 是投影的唯一投递主线，命令路径不再在提交后
	// 尽力 apply 投影。
	followedSubjectVisitService := visitapp.NewVisitService(followedSubjectVisitStore)
	if followedSubjectVisitStore != nil && followingSubjectStore != nil {
		followedSubjectVisitRelay := visitapp.NewOutboxRelay(
			followedSubjectVisitStore,
			&followedSubjectVisitFanout{projection: followingSubjectStore},
		)
		go func() {
			if err := followedSubjectVisitRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
				log.Printf("ERROR: followed subject visit outbox relay stopped: %v", err)
			}
		}()
	}
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
	challengeDeliveryTransport, ok := messageTransport.(challengestream.DurableMessageTransport)
	if !ok {
		log.Fatal("AuthenticationChallenge delivery results require durable message transport")
	}
	challengeDeliveryConsumer, err :=
		challengestream.NewAuthenticationChallengeDeliveryResultConsumer(
			challengeDeliveryTransport,
			authenticationChallenges,
			fmt.Sprintf("user-authentication-challenge-%d", os.Getpid()),
			nil,
		)
	if err != nil {
		log.Fatalf("AuthenticationChallenge delivery consumer init failed: %v", err)
	}
	if err := challengeDeliveryConsumer.EnsureGroup(ctx); err != nil {
		log.Fatalf("AuthenticationChallenge delivery consumer preflight failed: %v", err)
	}
	go challengeDeliveryConsumer.Run(ctx)
	accountAppealStore, err := appealpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("AccountAppealIntake store init failed: %v", err)
	}
	accountAppealFacade := appealapp.NewCommandFacade(
		accountAppealStore,
		appealidentity.NewChallengeVerifier(
			authenticationChallenges,
			credentialStore,
		),
		appealobservability.Recorder{},
	)
	accountAppealHandler, err := appealhttp.NewHandler(accountAppealFacade)
	if err != nil {
		log.Fatalf("AccountAppealIntake HTTP composition failed: %v", err)
	}
	go func() {
		if purgeErr := accountAppealFacade.RunRetentionPurge(
			ctx,
			time.Hour,
		); purgeErr != nil && !errors.Is(purgeErr, context.Canceled) {
			log.Printf("ERROR: AccountAppealIntake retention purge stopped: %v", purgeErr)
		}
	}()
	carrierPhoneResolver, err := newCarrierPhoneResolver()
	if err != nil &&
		!errors.Is(err, ErrAuthRuntimeCapabilityBlocked) &&
		!errors.Is(err, ErrAuthRuntimeCapabilityUnavailable) {
		log.Fatalf("carrier identity adapter init failed: %v", err)
	}
	otpCodeSealer, err := otpseal.LoadFromEnvironment()
	if err != nil {
		log.Fatalf("otp code reference sealer invalid: %v", err)
	}
	otpCodeGenerator := application.GenerateSecureOTPCode
	var externalInteractionClient application.ExternalInteractionClient
	if !contentSliceExternalAuthDisabled() {
		externalInteractionBaseURL := getenvOrDefault("INTEGRATION_EXTERNAL_INTERACTION_BASE_URL", cfg.Integration.ExternalInteractionBaseURL)
		externalInteractionClient, err = newRemoteOTPExternalInteractionClient(
			externalInteractionBaseURL,
			appEnv,
			accessSigner,
		)
		if err != nil {
			log.Fatalf("external interaction client init failed: %v", err)
		}
	}
	accountEnforcementStore, err := useraccountpersistence.NewEnforcementStore(pgPool)
	if err != nil {
		log.Fatalf("UserAccount enforcement store init failed: %v", err)
	}
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithAccountSessionCommands(accountsessionadapter.NewHandler(accountSessionCommands)),
		application.WithCredentialCommands(credentialCommands),
		application.WithPersonaCommandPipeline(
			personaCommandStore,
			personaProfileProjector,
		),
		application.WithDeviceRegistration(deviceRegistrationCommands),
		application.WithConsentRecordStore(consentRecordStore),
		application.WithFederatedPhoneBindingTickets(
			credentialStore,
		),
		application.WithOtpCodeStore(otpCodeCache),
		application.WithAuthenticationChallenges(challengeadapter.NewHandler(authenticationChallenges)),
		application.WithOTPCodeSealer(otpCodeSealer),
		application.WithOTPCodeGenerator(otpCodeGenerator),
		application.WithExternalInteractionClient(externalInteractionClient),
		application.WithCarrierPhoneResolver(carrierPhoneResolver),
		application.WithAccessTokenSigner(accessSigner),
		application.WithAccountSecurityReader(accountEnforcementStore),
		application.WithDefaultNicknamePrefix(getenvOrDefault("USER_DEFAULT_NICKNAME_PREFIX", "新同学")),
		application.WithManagedAcceptanceIdentity(
			managedAcceptanceIdentity.Phone,
			managedAcceptanceIdentity.AccountID,
		),
	)
	federatedLogins, err := newFederatedLoginBindings(authService)
	if err != nil &&
		!errors.Is(err, ErrAuthRuntimeCapabilityBlocked) &&
		!errors.Is(err, ErrAuthRuntimeCapabilityUnavailable) {
		log.Fatalf("federated identity adapter init failed: %v", err)
	}
	personaService := application.NewPersonaService(
		personaStore,
		personaCommandStore,
		personaProfileProjector,
		profileStore,
		profileCache,
		personaOptions...,
	)
	contactDiscoveryService := contactapp.NewContactDiscoveryService(contactDiscoveryStore, userEventPublisher)
	go contactDiscoveryService.RunExpiredCleanup(ctx, time.Hour)
	personaProfileProposalFacade, err := personaapp.NewProfileProposalFacade(personaProfileProposalStore)
	if err != nil {
		log.Fatalf("Persona profile proposal Facade init failed: %v", err)
	}
	profileProposalFacade, err := proposalapp.NewFacade(
		profileProposalStore,
		profileProposalStore,
		personaadapter.NewProfileProposalHandler(personaProfileProposalFacade),
		personaProfileProposalStore,
	)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Facade init failed: %v", err)
	}
	profileProposalOutboxRelay, err := proposalapp.NewOutboxRelay(
		profileProposalStore,
		proposalmessaging.NewEventPublisher(messageTransport),
	)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal outbox relay init failed: %v", err)
	}

	healthChecker := rthealth.NewChecker()
	profileSearchOutboxStore, err :=
		useraccountpersistence.NewUserProfileSearchOutboxStore(pgPool)
	if err != nil {
		log.Fatalf("UserProfile search outbox store init failed: %v", err)
	}
	profileSearchPublisher, err := profileprojection.NewStreamPublisher(messageTransport)
	if err != nil {
		log.Fatalf("UserProfile search stream publisher init failed: %v", err)
	}
	profileSearchOutboxRelay, err :=
		useraccountapp.NewUserProfileSearchOutboxRelay(
			profileSearchOutboxStore,
			profileSearchPublisher,
			fmt.Sprintf("user-service-profile-search-%d", os.Getpid()),
			useraccountapp.WithUserProfileSearchOutboxObserver(
				useraccountobservability.ProfileSearchOutboxObserver{},
			),
		)
	if err != nil {
		log.Fatalf("UserProfile search outbox relay init failed: %v", err)
	}
	healthChecker.Register(
		"user_profile_search_outbox_relay",
		func(hctx context.Context) error {
			return profileSearchOutboxRelay.Healthy(hctx, 15*time.Second)
		},
	)
	go profileSearchOutboxRelay.Run(ctx)
	healthChecker.Register("postgres", func(hctx context.Context) error {
		return pgPool.Ping(hctx)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return redisRouter.PingAll(hctx)
	})
	healthChecker.Register(
		"authentication_challenge_delivery_consumer",
		func(context.Context) error {
			return challengeDeliveryConsumer.Healthy(15 * time.Second)
		},
	)
	if mongoDB != nil {
		healthChecker.Register("mongodb", func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		})
	}
	healthChecker.Register("profile_update_proposal_outbox_relay", func(hctx context.Context) error {
		return profileProposalOutboxRelay.Healthy(hctx, 15*time.Second)
	})
	healthChecker.Register("persona_outbox_relay", func(context.Context) error {
		return personaOutboxRelay.Healthy(15 * time.Second)
	})
	healthChecker.Register("credential_binding_audit_relay", func(context.Context) error {
		return credentialAuditRelay.Healthy(15 * time.Second)
	})
	go func() {
		if err := profileProposalOutboxRelay.Run(ctx, time.Second); err != nil &&
			ctx.Err() == nil {
			log.Printf(
				"ERROR: ProfileUpdateProposal outbox relay stopped: %v",
				err,
			)
		}
	}()
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
	accountOutboxStore, err :=
		useraccountpersistence.NewUserAccountOutboxStore(pgPool)
	if err != nil {
		log.Fatalf("UserAccount outbox store init failed: %v", err)
	}
	if mongoDB != nil {
		accountCloseProjections = searchindex.ComposePublisher(
			accountCloseProjections,
			usercomposition.NewUserAccountClosurePublisher(
				followingapp.NewAccountClosureProjector(followingSubjectStore),
				visitapp.NewAccountClosureProjector(followedSubjectVisitStore),
				creatorapp.NewAccountClosureProjector(creatorRuntimeStore),
			),
		)
	}
	accountEventFanout, err := mq.NewUserAccountEventFanout(
		relationshipEventPublisher,
		accountCloseProjections,
	)
	if err != nil {
		log.Fatalf("UserAccount event fanout init failed: %v", err)
	}
	accountOutboxRelay, err := useraccountapp.NewUserAccountOutboxRelay(
		accountOutboxStore,
		accountEventFanout,
		fmt.Sprintf("user-service-%d", os.Getpid()),
		useraccountapp.WithUserAccountOutboxObserver(
			useraccountobservability.CloseOutboxObserver{},
		),
	)
	if err != nil {
		log.Fatalf("UserAccount outbox relay init failed: %v", err)
	}
	healthChecker.Register("user_account_outbox_relay", func(hctx context.Context) error {
		return accountOutboxRelay.Healthy(hctx, 15*time.Second)
	})
	go accountOutboxRelay.Run(ctx)
	closeAccountFacade := useraccountapp.NewCloseAccountFacade(
		accountCloseStore,
		useraccountcache.NewClosedAccountCache(redisClient),
	)
	accountEnforcementFacade :=
		useraccountapp.NewAccountEnforcementCommandFacade(accountEnforcementStore)
	userHandler, err := httpadapter.NewUserHandler(
		profileService, searchService, relationshipadapter.NewHandler(relationshipService), greetingService,
		authService, credentialQueries,
		personaService,
		interestProfileService,
	)
	if err != nil {
		log.Fatalf("user-service HTTP composition failed: %v", err)
	}
	userHandler.WithUserSettingsRoutes(
		usersettingshttp.NewHandler(userSettingsCommands, userSettingsQueries),
	)
	userHandler.WithDeviceRegistrationRoutes(
		registrationhttp.NewHandler(deviceRegistrationCommands, deviceRegistrationQueries),
	)
	userHandler.WithSubjectObjectRoutes(
		subjectfollowhttp.NewHandler(subjectFollowService, userHandler),
		visithttp.NewHandler(followedSubjectVisitService, userHandler),
		followinghttp.NewHandler(followingSubjectQueryService, userHandler),
	)
	profileProposalHandler, err := proposalhttp.NewHandler(profileProposalFacade)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal HTTP composition failed: %v", err)
	}
	greetingHandler, err := greetinghttp.NewHandler(greetingService)
	if err != nil {
		log.Fatalf("GreetingRequest HTTP composition failed: %v", err)
	}
	contactDiscoveryHandler, err := contacthttp.NewHandler(
		contactDiscoveryService,
		relationshipService,
		greetingService,
	)
	if err != nil {
		log.Fatalf("ContactDiscoveryRecord HTTP composition failed: %v", err)
	}
	userHandler.WithAccountLifecycle(closeAccountFacade)
	userHandler.WithAccountEnforcement(accountEnforcementFacade)
	userHandler.WithAccountSecurityReader(accountEnforcementStore)
	userHandler.WithFederatedLogins(
		federatedLogins.wechat,
		federatedLogins.alipay,
		federatedLogins.qq,
	)
	federatedPhoneBindingHandler, err :=
		credentialhttp.NewFederatedPhoneBindingHandler(authService)
	if err != nil {
		log.Fatalf("FederatedPhoneBinding HTTP composition failed: %v", err)
	}
	personaHostAuthorityEvaluator, err := personaapp.NewHostAuthorityEvaluator(
		personapersistence.NewHostAuthorityReader(pgPool),
		time.Now,
	)
	if err != nil {
		log.Fatalf("Persona Host authority composition failed: %v", err)
	}
	personaHostAuthorityHandler := personahttp.NewHostAuthorityHandler(
		personaHostAuthorityEvaluator,
	)
	serviceMux := http.NewServeMux()
	userHandler.RegisterRoutes(serviceMux)
	accountsessionhttp.RegisterResearchSessionRoutes(serviceMux, researchSessionHandler)
	personaHostAuthorityHandler.RegisterRoutes(serviceMux)
	accountAppealHandler.RegisterRoutes(serviceMux)
	federatedPhoneBindingHandler.RegisterRoutes(serviceMux)
	profileProposalHandler.RegisterRoutes(serviceMux)
	invitationHandler.RegisterRoutes(serviceMux)
	greetingHandler.RegisterRoutes(serviceMux)
	contactDiscoveryHandler.RegisterRoutes(serviceMux)
	handler := userHandler.WrapAccountSecurity(serviceMux)

	outerMux := buildUserHTTPMux(handler, healthChecker)

	// 8.1 Observability middleware
	corsHandler, closeObservedHandler, err := buildObservedUserHandler(outerMux)
	if err != nil {
		log.Fatalf("user-service observability middleware init failed: %v", err)
	}
	defer closeObservedHandler()

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
	timeouts := rtauth.ContractHTTPServerTimeouts(userOperationDescriptors())
	server := &http.Server{
		Addr: addr,
		// Authentication must run before observability builds ActorContext.
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	log.Printf("user-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("user-service: %v", err)
	}
}
