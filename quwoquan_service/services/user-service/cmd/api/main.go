package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	rterr "quwoquan_service/runtime/errors"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/servicehost"

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

// Module is user-service's service-owned servicehost adapter.
type Module struct {
	configDigest string
	server       *http.Server
	health       *rthealth.Checker
	listener     net.Listener
	admission    atomic.Bool
	serveError   chan error

	workerCancel context.CancelFunc
	workerGroup  sync.WaitGroup
	workerStart  []func(context.Context)
	cleanup      func()
}

var _ servicehost.Module = (*Module)(nil)

// NewModule assembles user-service's private dependencies and HTTP contract.
// The process host owns listener binding, worker lifetime, readiness admission
// and shutdown.
func NewModule() (_ *Module, resultErr error) {
	cleanup := func() {}
	initialized := false
	defer func() {
		if !initialized {
			cleanup()
		}
	}()

	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return nil, fmt.Errorf("user-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return nil, fmt.Errorf("user-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return nil, fmt.Errorf("user-service config identity failed: %v", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)

	ctx := context.Background()
	workerStarts := []func(context.Context){}

	startWorker := func(start func(context.Context)) {
		workerStarts = append(workerStarts, start)
	}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "user-service", SamplingRatio: 0.1})
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		otelShutdown()
	})

	addr := getenvOrDefault("USER_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	// 1. PostgreSQL
	poolCfg, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		return nil, fmt.Errorf("postgres parse config: %v", err)
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
		return nil, fmt.Errorf("postgres connect: %v", err)
	}
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		pgPool.Close()
	})
	if err := pgPool.Ping(ctx); err != nil {
		return nil, fmt.Errorf("postgres ping: %v", err)
	}

	// 2. Run startup migrations with a persisted ledger so restart/rollout can
	// safely keep the existing Postgres volume.
	if err := persistence.RunManagedMigrations(ctx, pgPool); err != nil {
		return nil, fmt.Errorf("migration: %v", err)
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
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		if mongoClient != nil {
			_ = mongoClient.Disconnect(context.Background())
		}
	})

	// 4. Redis
	redisRouter := buildRedisRouter(cfg)
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		_ = redisRouter.Close()
	})
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
		return nil, fmt.Errorf("user-service message transport preflight failed: %v", err)
	}
	researchAuditTransport, _ := messageTransport.(runtimemessaging.DurableRecordAppender)
	researchSessionHandler, err := buildResearchSessionHandler(
		appEnv,
		cfg,
		researchAuditTransport,
	)
	if err != nil {
		return nil, fmt.Errorf("research identity composition failed: %v", err)
	}
	researchSessionAttestationHandler, err := buildResearchSessionAttestationHandler(
		appEnv,
		cfg,
	)
	if err != nil {
		return nil, fmt.Errorf("research identity readback composition failed: %v", err)
	}
	managedAcceptanceIdentity, err := loadManagedAcceptanceIdentity()
	if err != nil && cfg.ResearchIdentity.Enabled {
		return nil, fmt.Errorf("managed acceptance identity composition failed: %v", err)
	}
	redisClient := redisRouter.Scene("general")

	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		return nil, fmt.Errorf("load shard directory: %v", err)
	}

	// 5. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := userpersistence.NewPgPersonaStore(pgPool)
	invitationStore, err := invitationpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("Invitation store init failed: %v", err)
	}
	invitationFacade, err := invitationapp.NewFacade(
		invitationStore,
		personapersistence.NewOwnerReader(pgPool),
	)
	if err != nil {
		return nil, fmt.Errorf("Invitation facade init failed: %v", err)
	}
	invitationHandler, err := invitationhttp.NewHandler(invitationFacade)
	if err != nil {
		return nil, fmt.Errorf("Invitation HTTP composition failed: %v", err)
	}
	userSettingsStore, err := usersettingspersistence.NewPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("user-service UserSettings store init failed: %v", err)
	}
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := greetingpersistence.NewPgGreetingStore(pgPool)
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("CredentialBinding store init failed: %v", err)
	}
	credentialAuditTransport, ok := messageTransport.(runtimemessaging.DurableRecordAppender)
	if !ok {
		return nil, errors.New("CredentialBinding audit requires durable retention transport")
	}
	credentialAuditPublisher, err := credentialmessaging.NewSecurityAuditPublisher(
		credentialAuditTransport,
	)
	if err != nil {
		return nil, fmt.Errorf("CredentialBinding audit publisher init failed: %v", err)
	}
	credentialAuditRelay, err := credentialapp.NewSecurityAuditRelay(
		credentialStore,
		credentialAuditPublisher,
	)
	if err != nil {
		return nil, fmt.Errorf("CredentialBinding audit relay init failed: %v", err)
	}
	if _, err := credentialAuditRelay.Drain(ctx, 1); err != nil {
		return nil, fmt.Errorf("CredentialBinding audit relay preflight failed: %v", err)
	}
	startWorker(func(workerCtx context.Context) {
		if err := credentialAuditRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: CredentialBinding audit relay stopped: %v", err)
		}
	})
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	credentialQueries := credentialapp.NewCredentialQueryFacade(
		credentialStore,
	)
	accountSessionStore, err := accountsessionpersistence.NewAccountSessionPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("AccountSession store init failed: %v", err)
	}
	accountSessionCommands :=
		accountsessionapp.NewAccountSessionCommandFacade(accountSessionStore)
	deviceRegistrationStore, err := registrationpersistence.NewPostgresStore(
		pgPool,
	)
	if err != nil {
		return nil, fmt.Errorf("DeviceRegistration store init failed: %v", err)
	}
	pushTokenCipher, err := registrationpersistence.LoadAESGCMTokenCipher(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, fmt.Errorf("DeviceRegistration token cipher init failed: %v", err)
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
		return nil, fmt.Errorf("Persona profile proposal Store init failed: %v", err)
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("ProfileUpdateProposal Store init failed: %v", err)
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
		return nil, errors.New("PUBLIC_WEB_BASE_URL must be injected from environment topology")
	}
	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("Persona command store init failed: %v", err)
	}
	personaDurableTransport, ok := messageTransport.(runtimemessaging.DurableRecordAppender)
	if !ok {
		return nil, errors.New("Persona publication requires durable retention transport")
	}
	if err := personaDurableTransport.SetDurableRetention(
		ctx,
		personamessaging.PersonaEventStream,
		personamessaging.PersonaEventStreamRetention,
	); err != nil {
		return nil, fmt.Errorf("Persona event stream retention setup failed: %v", err)
	}
	personaEventPublisher, err := personamessaging.NewEventPublisher(personaDurableTransport)
	if err != nil {
		return nil, fmt.Errorf("Persona event publisher init failed: %v", err)
	}
	personaOutboxRelay, err := personaapp.NewOutboxRelay(
		personaCommandStore,
		personaEventPublisher,
	)
	if err != nil {
		return nil, fmt.Errorf("Persona outbox relay init failed: %v", err)
	}
	if _, err := personaOutboxRelay.Drain(ctx, 1); err != nil {
		return nil, fmt.Errorf("Persona outbox relay preflight failed: %v", err)
	}
	startWorker(func(workerCtx context.Context) {
		if err := personaOutboxRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: Persona outbox relay stopped: %v", err)
		}
	})
	personaProfileProjectionStore, err := useraccountpersistence.NewPersonaProfileProjector(pgPool)
	if err != nil {
		return nil, fmt.Errorf("Persona profile projector init failed: %v", err)
	}
	personaProfileProjector, err := application.NewPersonaProfileProjector(
		personaProfileProjectionStore,
	)
	if err != nil {
		return nil, fmt.Errorf("Persona profile application facet init failed: %v", err)
	}
	startWorker(func(workerCtx context.Context) {
		if err := personaProfileProjector.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: Persona profile projector stopped: %v", err)
		}
	})
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
		return nil, fmt.Errorf("Profile service init failed: %v", err)
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
	startWorker(func(workerCtx context.Context) {
		if err := relationshipCounterReconciler.Run(
			workerCtx,
			time.Minute,
			500,
		); err != nil && workerCtx.Err() == nil {
			log.Printf(
				"ERROR: persona relationship counter reconciler stopped: %v",
				err,
			)
		}
	})
	relationshipService := relationshipapp.NewPersonaRelationshipService(
		relationshipStore,
		personaStore,
		profileCache,
		greetingStore,
	)
	chatServiceBaseURL := strings.TrimSpace(getenvOrDefault("CHAT_SERVICE_BASE_URL", ""))
	if chatServiceBaseURL == "" {
		return nil, errors.New("user-service startup failed: CHAT_SERVICE_BASE_URL is required")
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, fmt.Errorf("access token config invalid: %v", err)
	}
	accessSigner, err := rtauth.NewHS256Signer(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("access token signer invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("access token verifier invalid: %v", err)
	}
	chatCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"user-service",
		[]string{"chat.conversation.internal_direct"},
	)
	if err != nil {
		return nil, fmt.Errorf("user-service chat credential init failed: %v", err)
	}
	conversationGateway, err := userintegration.NewAuthorizedChatServiceClient(
		chatServiceBaseURL,
		nil,
		chatCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("user-service chat client init failed: %v", err)
	}
	contentServiceBaseURL := strings.TrimSpace(getenvOrDefault("CONTENT_SERVICE_BASE_URL", ""))
	if contentServiceBaseURL == "" {
		return nil, errors.New("user-service startup failed: CONTENT_SERVICE_BASE_URL is required")
	}
	intersectionCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"user-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("user-service content credential init failed: %v", err)
	}
	intersectionResolver, err := greetingintegration.NewIntersectionResolver(
		contentServiceBaseURL,
		nil,
		intersectionCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("user-service greeting intersection resolver init failed: %v", err)
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
	startWorker(func(workerCtx context.Context) {
		if err := greetingOutboxRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: greeting outbox relay stopped: %v", err)
		}
	})
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
			return nil, fmt.Errorf("following subject index ensure failed: %v", err)
		}
		followedSubjectVisitStore = visitpersistence.NewMongoFollowedSubjectVisitStore(mongoDB)
		if err := followedSubjectVisitStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("followed subject visit index ensure failed: %v", err)
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
	startWorker(func(workerCtx context.Context) {
		if err := subjectFollowRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: subject follow outbox relay stopped: %v", err)
		}
	})
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
	startWorker(func(workerCtx context.Context) {
		if err := relationshipOutboxRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			log.Printf("ERROR: persona relationship outbox relay stopped: %v", err)
		}
	})
	// FollowedSubjectVisitState packet：Mongo 水位 + FollowedSubjectVisited
	// outbox 同事务提交；relay 是投影的唯一投递主线，命令路径不再在提交后
	// 尽力 apply 投影。
	followedSubjectVisitService := visitapp.NewVisitService(followedSubjectVisitStore)
	if followedSubjectVisitStore != nil && followingSubjectStore != nil {
		followedSubjectVisitRelay := visitapp.NewOutboxRelay(
			followedSubjectVisitStore,
			&followedSubjectVisitFanout{projection: followingSubjectStore},
		)
		startWorker(func(workerCtx context.Context) {
			if err := followedSubjectVisitRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
				log.Printf("ERROR: followed subject visit outbox relay stopped: %v", err)
			}
		})
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
		return nil, fmt.Errorf("AuthenticationChallenge store init failed: %v", err)
	}
	authenticationChallenges :=
		challengeapp.NewAuthenticationChallengeCommandFacade(
			authenticationChallengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
	challengeDeliveryTransport, ok := messageTransport.(challengestream.DurableMessageTransport)
	if !ok {
		return nil, errors.New("AuthenticationChallenge delivery results require durable message transport")
	}
	challengeDeliveryConsumer, err :=
		challengestream.NewAuthenticationChallengeDeliveryResultConsumer(
			challengeDeliveryTransport,
			authenticationChallenges,
			fmt.Sprintf("user-authentication-challenge-%d", os.Getpid()),
			nil,
		)
	if err != nil {
		return nil, fmt.Errorf("AuthenticationChallenge delivery consumer init failed: %v", err)
	}
	if err := challengeDeliveryConsumer.EnsureGroup(ctx); err != nil {
		return nil, fmt.Errorf("AuthenticationChallenge delivery consumer preflight failed: %v", err)
	}
	startWorker(func(workerCtx context.Context) { challengeDeliveryConsumer.Run(workerCtx) })
	accountAppealStore, err := appealpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("AccountAppealIntake store init failed: %v", err)
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
		return nil, fmt.Errorf("AccountAppealIntake HTTP composition failed: %v", err)
	}
	startWorker(func(workerCtx context.Context) {
		if purgeErr := accountAppealFacade.RunRetentionPurge(
			workerCtx,
			time.Hour,
		); purgeErr != nil && !errors.Is(purgeErr, context.Canceled) {
			log.Printf("ERROR: AccountAppealIntake retention purge stopped: %v", purgeErr)
		}
	})
	carrierPhoneResolver, err := newCarrierPhoneResolver()
	if err != nil &&
		!errors.Is(err, ErrAuthRuntimeCapabilityBlocked) &&
		!errors.Is(err, ErrAuthRuntimeCapabilityUnavailable) {
		return nil, fmt.Errorf("carrier identity adapter init failed: %v", err)
	}
	otpCodeSealer, err := otpseal.LoadFromEnvironment()
	if err != nil {
		return nil, fmt.Errorf("otp code reference sealer invalid: %v", err)
	}
	otpCodeGenerator := application.GenerateSecureOTPCode
	var externalInteractionClient *userintegration.ExternalInteractionClient
	if !contentSliceExternalAuthDisabled() {
		externalInteractionBaseURL := getenvOrDefault("INTEGRATION_EXTERNAL_INTERACTION_BASE_URL", cfg.Integration.ExternalInteractionBaseURL)
		externalInteractionClient, err = newRemoteOTPExternalInteractionClient(
			externalInteractionBaseURL,
			appEnv,
			accessSigner,
		)
		if err != nil {
			return nil, fmt.Errorf("external interaction client init failed: %v", err)
		}
	}
	accountEnforcementStore, err := useraccountpersistence.NewEnforcementStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("UserAccount enforcement store init failed: %v", err)
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
		application.WithSMSOTPDeliveryReadinessQuery(externalInteractionClient),
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
		return nil, fmt.Errorf("federated identity adapter init failed: %v", err)
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
	startWorker(func(workerCtx context.Context) { contactDiscoveryService.RunExpiredCleanup(workerCtx, time.Hour) })
	personaProfileProposalFacade, err := personaapp.NewProfileProposalFacade(personaProfileProposalStore)
	if err != nil {
		return nil, fmt.Errorf("Persona profile proposal Facade init failed: %v", err)
	}
	profileProposalFacade, err := proposalapp.NewFacade(
		profileProposalStore,
		profileProposalStore,
		personaadapter.NewProfileProposalHandler(personaProfileProposalFacade),
		personaProfileProposalStore,
	)
	if err != nil {
		return nil, fmt.Errorf("ProfileUpdateProposal Facade init failed: %v", err)
	}
	profileProposalOutboxRelay, err := proposalapp.NewOutboxRelay(
		profileProposalStore,
		proposalmessaging.NewEventPublisher(messageTransport),
	)
	if err != nil {
		return nil, fmt.Errorf("ProfileUpdateProposal outbox relay init failed: %v", err)
	}

	healthChecker := rthealth.NewChecker()
	profileSearchOutboxStore, err :=
		useraccountpersistence.NewUserProfileSearchOutboxStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("UserProfile search outbox store init failed: %v", err)
	}
	profileSearchPublisher, err := profileprojection.NewStreamPublisher(messageTransport)
	if err != nil {
		return nil, fmt.Errorf("UserProfile search stream publisher init failed: %v", err)
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
		return nil, fmt.Errorf("UserProfile search outbox relay init failed: %v", err)
	}
	healthChecker.Register(
		"user_profile_search_outbox_relay",
		func(hctx context.Context) error {
			return profileSearchOutboxRelay.Healthy(hctx, 15*time.Second)
		},
	)
	startWorker(func(workerCtx context.Context) { profileSearchOutboxRelay.Run(workerCtx) })
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
		healthChecker.RegisterWithTimeout(
			"mongodb",
			rtmongo.DefaultReadinessTimeout,
			func(hctx context.Context) error {
				return mongoClient.Ping(hctx, nil)
			},
		)
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
	startWorker(func(workerCtx context.Context) {
		if err := profileProposalOutboxRelay.Run(workerCtx, time.Second); err != nil &&
			workerCtx.Err() == nil {
			log.Printf(
				"ERROR: ProfileUpdateProposal outbox relay stopped: %v",
				err,
			)
		}
	})
	// 8. Handler
	var interestReader application.InterestProfileReader
	if mongoDB != nil {
		interestReader = projection.NewMongoInterestProfileReader(mongoDB)
	}
	interestProfileService := application.NewInterestProfileService(interestReader)
	accountCloseStore, err := useraccountpersistence.NewCloseStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("UserAccount close store init failed: %v", err)
	}
	accountOutboxStore, err :=
		useraccountpersistence.NewUserAccountOutboxStore(pgPool)
	if err != nil {
		return nil, fmt.Errorf("UserAccount outbox store init failed: %v", err)
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
		return nil, fmt.Errorf("UserAccount event fanout init failed: %v", err)
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
		return nil, fmt.Errorf("UserAccount outbox relay init failed: %v", err)
	}
	healthChecker.Register("user_account_outbox_relay", func(hctx context.Context) error {
		return accountOutboxRelay.Healthy(hctx, 15*time.Second)
	})
	startWorker(func(workerCtx context.Context) { accountOutboxRelay.Run(workerCtx) })
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
		return nil, fmt.Errorf("user-service HTTP composition failed: %v", err)
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
		return nil, fmt.Errorf("ProfileUpdateProposal HTTP composition failed: %v", err)
	}
	greetingHandler, err := greetinghttp.NewHandler(greetingService)
	if err != nil {
		return nil, fmt.Errorf("GreetingRequest HTTP composition failed: %v", err)
	}
	contactDiscoveryHandler, err := contacthttp.NewHandler(
		contactDiscoveryService,
		relationshipService,
		greetingService,
	)
	if err != nil {
		return nil, fmt.Errorf("ContactDiscoveryRecord HTTP composition failed: %v", err)
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
		return nil, fmt.Errorf("FederatedPhoneBinding HTTP composition failed: %v", err)
	}
	personaHostAuthorityEvaluator, err := personaapp.NewHostAuthorityEvaluator(
		personapersistence.NewHostAuthorityReader(pgPool),
		time.Now,
	)
	if err != nil {
		return nil, fmt.Errorf("Persona Host authority composition failed: %v", err)
	}
	personaHostAuthorityHandler := personahttp.NewHostAuthorityHandler(
		personaHostAuthorityEvaluator,
	)
	serviceMux := http.NewServeMux()
	userHandler.RegisterRoutes(serviceMux)
	accountsessionhttp.RegisterResearchSessionRoutes(serviceMux, researchSessionHandler)
	accountsessionhttp.RegisterResearchSessionAttestationRoutes(
		serviceMux,
		researchSessionAttestationHandler,
	)
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
		return nil, fmt.Errorf("user-service observability middleware init failed: %v", err)
	}
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		closeObservedHandler()
	})

	// 8.2 Interest profile projector: consume content's UserInterestRecomputed
	// and maintain the user-domain rm_user_profile_view interest read model.
	if mongoDB != nil {
		interestProjector := projection.NewInterestProfileProjector(mongoDB, nil)
		startWorker(func(workerCtx context.Context) {
			if err := interestProjector.Run(workerCtx, redisClient); err != nil && workerCtx.Err() == nil {
				log.Printf("WARN: interest profile projector stopped: %v", err)
			}
		})
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
	module := &Module{
		configDigest: configVersion,
		server:       server,
		health:       healthChecker,
		serveError:   make(chan error, 1),
		workerStart:  workerStarts,
		cleanup:      cleanup,
	}
	if module.configDigest == "" {
		module.configDigest = cfg.Config.Version
	}
	if module.configDigest == "" {
		module.configDigest = "user-service-runtime"
	}
	server.Handler = module.admissionHandler(server.Handler)
	initialized = true
	return module, nil
}

func (module *Module) Name() string { return "user-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil {
		return errors.New("user-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("user-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(context.Context) error {
	if module.listener == nil {
		return errors.New("user-service listener is not bound")
	}
	workerContext, workerCancel := context.WithCancel(context.Background())
	module.workerCancel = workerCancel
	for _, start := range module.workerStart {
		module.workerGroup.Add(1)
		module.startWorker(workerContext, start)
	}
	go func() {
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			module.serveError <- err
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.health.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("user-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("user-service listener failed: %w", err)
	default:
		return nil
	}
}

func (module *Module) OpenAdmission(context.Context) error {
	module.admission.Store(true)
	return nil
}

func (module *Module) Shutdown(ctx context.Context) error {
	module.admission.Store(false)
	var result error
	if module.server != nil {
		result = errors.Join(result, module.server.Shutdown(ctx))
	}
	if module.workerCancel != nil {
		module.workerCancel()
		module.workerGroup.Wait()
		module.workerCancel = nil
	}
	if module.cleanup != nil {
		module.cleanup()
		module.cleanup = nil
	}
	return result
}

func (module *Module) startWorker(ctx context.Context, start func(context.Context)) {
	go func() {
		defer module.workerGroup.Done()
		start(ctx)
	}()
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz",
			"/readyz",
			"/metrics",
			"/internal/user/account-security/health":
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admission.Load() {
			rterr.WriteHTTPError(
				writer,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindMiddleware, "upstream_unavailable"),
					"服务暂不可用，请稍后重试",
					"service admission is not ready",
				).WithMetadata("upstream_unavailable", http.StatusServiceUnavailable).
					WithRecoveryDirective("retry", "snackbar", 1),
				rterr.HTTPWriteOptionsFromRequest(request),
			)
			return
		}
		next.ServeHTTP(writer, request)
	})
}
