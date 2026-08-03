package api_integration

import (
	"context"
	"encoding/base64"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
	operationsecurity "quwoquan_service/generated/operationsecurity"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/otpseal"
	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	accountsessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	accountsessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	credentialhttp "quwoquan_service/services/user-service/internal/account/credential_binding/adapters/inbound/http"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
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
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
	useraccountcache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/projection"
	useraccountprojection "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/projection"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/searchindex"
	usercache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/cache"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	usersettingshttp "quwoquan_service/services/user-service/internal/account/user_settings/adapters/inbound/http"
	usersettingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	usersettingspersistence "quwoquan_service/services/user-service/internal/account/user_settings/infrastructure/persistence"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalhttp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/adapters/inbound/http"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmessaging "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/messaging"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
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
	greetingpersistence "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/persistence"
	relationshipadapter "quwoquan_service/services/user-service/internal/relationship/persona_relationship/adapters/inbound/application"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	relationshipprojection "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/projection"
	subjectfollowhttp "quwoquan_service/services/user-service/internal/relationship/subject_follow/adapters/inbound/http"
	subjectfollowapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
	subjectfollowpersistence "quwoquan_service/services/user-service/internal/relationship/subject_follow/infrastructure/persistence"
)

var (
	testHandler                   http.Handler
	testAccountEnforcementHandler http.Handler
	pgPool                        *pgxpool.Pool
	mongoDB                       *mongo.Database
	integrationRedis              *testinfra.RealRedis
	redisRouter                   *rtredis.Router
	redisClient                   rtredis.Client
	mongoClient                   *mongo.Client
	mongoContainer                *mongomod.MongoDBContainer
	mongoRuntimeMu                sync.Mutex
	externalProviderRuntime       *externalProviderContractRuntime
	externalInteractionRuntime    *externalInteractionContractRuntime
	chatContractRuntime           *chatServiceContractRuntime
	conversationGateway           *integration.ChatServiceClient
	relationshipCounterProjector  *relationshipprojection.CounterProjector
	relationshipCounterReconciler *relationshipprojection.CounterReconciler
	relationshipRelayCancel       context.CancelFunc
	accountCloseRelayCancel       context.CancelFunc
	integrationRelayRunners       sync.WaitGroup

	testAccessConfig = rtauth.TokenConfig{
		Secret:       []byte("test-user-service-access-secret-v1"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
	testAccessSigner   = mustAccessSigner(testAccessConfig)
	testAccessVerifier = mustAccessVerifier(testAccessConfig)
	testOTPCodeSealer  = mustOTPCodeSealer()
)

type staticCarrierPhoneResolver map[string]string

func (resolver staticCarrierPhoneResolver) ResolvePhone(
	_ context.Context,
	carrierToken string,
) (application.VerifiedCarrierPhone, error) {
	phone := strings.TrimSpace(resolver[strings.TrimSpace(carrierToken)])
	if phone == "" {
		return application.VerifiedCarrierPhone{}, fmt.Errorf("test carrier token is unknown")
	}
	return application.VerifiedCarrierPhone{
		Phone:        phone,
		DisplayLabel: "180****3901",
	}, nil
}

func mustOTPCodeSealer() *otpseal.Sealer {
	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef")),
	})
	if err != nil {
		panic(err)
	}
	return sealer
}

func mustAccessSigner(config rtauth.TokenConfig) *rtauth.Signer {
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		panic(err)
	}
	return signer
}

func mustAccessVerifier(config rtauth.TokenConfig) *rtauth.Verifier {
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		panic(err)
	}
	return verifier
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	// 1. 真实 Redis 协议实现。
	var err error
	integrationRedis, err = testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("user-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedis.FlushDBs(ctx, 0); err != nil {
		panic("flush user-service integration Redis: " + err.Error())
	}

	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 0, TLS: integrationRedis.TLS},
		},
		DefaultScene: "general",
	})
	redisClient = redisRouter.Scene("general")

	// 2. embedded-postgres
	pgDSN := os.Getenv("TEST_PG_DSN")
	if pgDSN == "" {
		pgDSN = startEmbeddedPostgres()
	}
	pgPool, err = pgxpool.New(ctx, pgDSN)
	if err != nil {
		panic("postgres connect: " + err.Error())
	}

	// Run migrations
	runTestMigrations(ctx, pgPool)

	externalProviderRuntime, err = startExternalProviderContractRuntime()
	if err != nil {
		panic("external provider contract runtime: " + err.Error())
	}
	externalInteractionRuntime, err = startExternalInteractionContractRuntime()
	if err != nil {
		panic("external interaction contract runtime: " + err.Error())
	}
	chatContractRuntime, conversationGateway = startChatServiceContractRuntime()

	// 3. MongoDB 是 api_integration 必需依赖，不得部分启动或动态降级。
	if err := bootstrapMongoRuntime(ctx, false); err != nil {
		panic("mongo bootstrap: " + err.Error())
	}
	if err := rebuildTestHandler(ctx); err != nil {
		panic("build user-service test handler: " + err.Error())
	}

	code := m.Run()

	// Teardown
	stopIntegrationRelayRunners()
	pgPool.Close()
	if mongoClient != nil {
		_ = mongoClient.Disconnect(ctx)
	}
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	chatContractRuntime.Close()
	externalInteractionRuntime.Close()
	externalProviderRuntime.Close()
	_ = redisRouter.Close()
	_ = integrationRedis.Close(ctx)
	if embeddedPG != nil {
		_ = embeddedPG.Stop()
	}
	if embeddedPGRuntimePath != "" {
		_ = os.RemoveAll(embeddedPGRuntimePath)
	}
	os.Exit(code)
}

func stopIntegrationRelayRunners() {
	if relationshipRelayCancel != nil {
		relationshipRelayCancel()
		relationshipRelayCancel = nil
	}
	if accountCloseRelayCancel != nil {
		accountCloseRelayCancel()
		accountCloseRelayCancel = nil
	}
	integrationRelayRunners.Wait()
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic: %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}

func configuredMongoURI() string {
	mongoURI := strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
	if mongoURI == "" {
		mongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	}
	return mongoURI
}

func isCIEnvironment() bool {
	return os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true"
}

func bootstrapMongoRuntime(ctx context.Context, allowLocalUnavailable bool) error {
	if mongoDB != nil {
		return nil
	}

	mongoURI := configuredMongoURI()
	if mongoURI == "" {
		if mongoContainer == nil {
			container, runErr := tryRunMongoContainer(ctx)
			if runErr != nil {
				if allowLocalUnavailable && !isCIEnvironment() {
					return runErr
				}
				return fmt.Errorf("failed to start mongo testcontainer: %w", runErr)
			}
			mongoContainer = container
		}
		uri, err := mongoContainer.ConnectionString(ctx)
		if err != nil {
			return fmt.Errorf("mongo connection string: %w", err)
		}
		mongoURI = uri + "&directConnection=true"
	}

	clientOptions := mongoopts.Client().ApplyURI(mongoURI)
	if mongoContainer != nil {
		clientOptions.SetDirect(true)
	}
	client, err := mongo.Connect(clientOptions)
	if err != nil {
		return fmt.Errorf("mongo connect: %w", err)
	}
	mongoClient = client
	mongoDB = client.Database("user_test")
	return nil
}

func rebuildTestHandler(ctx context.Context) error {
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := userpersistence.NewPgPersonaStore(pgPool)
	invitationStore, err := invitationpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}
	invitationFacade, err := invitationapp.NewFacade(invitationStore, personaStore)
	if err != nil {
		return err
	}
	invitationHandler, err := invitationhttp.NewHandler(invitationFacade)
	if err != nil {
		return err
	}
	userSettingsStore, err := usersettingspersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}
	userSettingsCommands := usersettingsapp.NewUserSettingsCommandFacade(
		userSettingsStore,
	)
	userSettingsQueries := usersettingsapp.NewUserSettingsQueryFacade(
		userSettingsStore,
	)
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := greetingpersistence.NewPgGreetingStore(pgPool)
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	credentialQueries := credentialapp.NewCredentialQueryFacade(
		credentialStore,
	)
	accountSessionStore, err := accountsessionpersistence.NewAccountSessionPostgresStore(pgPool)
	if err != nil {
		return err
	}
	accountSessionCommands :=
		accountsessionapp.NewAccountSessionCommandFacade(accountSessionStore)
	deviceRegistrationStore, err := registrationpersistence.NewPostgresStore(
		pgPool,
	)
	if err != nil {
		return err
	}
	pushTokenCipher, err := registrationpersistence.NewAESGCMTokenCipher(
		make([]byte, 32),
	)
	if err != nil {
		return err
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
	authenticationChallengeStore, err :=
		challengepersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}
	authenticationChallenges :=
		challengeapp.NewAuthenticationChallengeCommandFacade(
			authenticationChallengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
	anonymousDeviceBindingStore := userpersistence.NewPgAnonymousDeviceBindingStore(pgPool)
	profileQrTokenStore := userpersistence.NewPgProfileQrTokenStore(pgPool)
	contactDiscoveryStore := contactpersistence.NewPgContactDiscoveryStore(pgPool)
	personaProfileProposalStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		return err
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}

	profileCache := usercache.NewProfileCache(redisClient)
	relationshipCounterProjector = relationshipprojection.NewCounterProjector(
		pgPool,
		profileCache,
	)
	relationshipCounterReconciler = relationshipprojection.NewCounterReconciler(
		pgPool,
		profileCache,
	)
	messageTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"user-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redisClient,
		redisClient,
	)
	if err != nil {
		return err
	}
	userEventPublisher := mq.NewEventPublisher(messageTransport)
	userSyncService := runtimesync.NewService(redisClient, redisClient)
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		return err
	}

	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		return err
	}
	personaProfileProjector, err := useraccountpersistence.NewPersonaProfileProjector(pgPool)
	if err != nil {
		return err
	}
	profileService, err := application.NewProfileService(
		profileStore,
		personaStore,
		personaCommandStore,
		personaProfileProjector,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
		application.WithProfileTagValidator(
			application.PathProfileTagValidator{},
		),
		application.WithProfilePublicBaseURL("https://quwoquan.com"),
	)
	if err != nil {
		return err
	}
	searchService := application.NewSearchService(profileStore, personaStore)
	relationshipService := relationshipapp.NewPersonaRelationshipService(
		relationshipStore,
		personaStore,
		profileCache,
		greetingStore,
	)
	// SubjectFollow / FollowingSubject / FollowedSubjectVisitState packet
	subjectFollowStore := subjectfollowpersistence.NewPgSubjectFollowStore(pgPool)
	subjectFollowService := subjectfollowapp.NewSubjectFollowService(subjectFollowStore)
	followingSubjectStore := followingpersistence.NewMongoFollowingSubjectStore(mongoDB)
	followedSubjectVisitStore := visitpersistence.NewMongoFollowedSubjectVisitStore(mongoDB)
	var followingProjector *followingevent.Handler
	if mongoDB != nil {
		if err := followingSubjectStore.EnsureIndexes(ctx); err != nil {
			return err
		}
		if err := followedSubjectVisitStore.EnsureIndexes(ctx); err != nil {
			return err
		}
		followingProjector = followingevent.NewHandler(followingapp.NewProjector(followingSubjectStore))
	}
	followedSubjectVisitService := visitapp.NewVisitService(followedSubjectVisitStore, followingSubjectStore)
	followingSubjectQueryService := followingapp.NewQueryService(followingSubjectStore, personaStore, nil)
	stopIntegrationRelayRunners()
	relationshipRelayContext, cancelRelationshipRelay := context.WithCancel(context.Background())
	relationshipRelayCancel = cancelRelationshipRelay
	relationshipRelay := relationshipapp.NewOutboxRelay(
		relationshipStore,
		&testPersonaRelationshipFanout{
			events:    userEventPublisher,
			projector: followingProjector,
			counters:  relationshipCounterProjector,
		},
	)
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		_ = relationshipRelay.Run(relationshipRelayContext, 10*time.Millisecond)
	}()
	subjectFollowRelay := subjectfollowapp.NewOutboxRelay(
		subjectFollowStore,
		&testSubjectFollowFanout{events: userEventPublisher, projector: followingProjector},
	)
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		_ = subjectFollowRelay.Run(relationshipRelayContext, 10*time.Millisecond)
	}()
	greetingService := greetingapp.NewGreetingService(
		greetingStore,
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
		userEventPublisher,
		greetingapp.NewSettingsGreetingNotifyPolicy(
			userSettingsStore,
			personaStore,
		),
	)
	greetingRelay := greetingapp.NewGreetingOutboxRelay(
		greetingStore,
		userEventPublisher,
		userEventPublisher,
	)
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		_ = greetingRelay.Run(relationshipRelayContext, 10*time.Millisecond)
	}()
	profileProposalRelay, err := proposalapp.NewOutboxRelay(
		profileProposalStore,
		proposalmessaging.NewEventPublisher(messageTransport),
	)
	if err != nil {
		return err
	}
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		_ = profileProposalRelay.Run(relationshipRelayContext, 10*time.Millisecond)
	}()
	accountEnforcementStore, err := useraccountpersistence.NewEnforcementStore(pgPool)
	if err != nil {
		return err
	}
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithAccountSessionCommands(accountSessionCommands),
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
		application.WithOtpCodeStore(cache.NewOtpCodeCache(redisClient)),
		application.WithAuthenticationChallenges(authenticationChallenges),
		application.WithOTPCodeSealer(testOTPCodeSealer),
		application.WithExternalInteractionClient(externalInteractionRuntime.client),
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithAccountSecurityReader(accountEnforcementStore),
		application.WithCarrierPhoneResolver(staticCarrierPhoneResolver{
			"carrier_token_new":      "+8618013813901",
			"carrier_token_existing": "+8618013813902",
		}),
	)
	personaService := application.NewPersonaService(
		personaStore,
		personaCommandStore,
		personaProfileProjector,
		profileStore,
		profileCache,
		application.WithCreatorRuntimeProfiles(
			newCreatorRuntimeProfileTestAdapter(
				creatorpersistence.NewCreatorRuntimeProfileReader(mongoDB),
			),
		),
	)
	contactDiscoveryService := contactapp.NewContactDiscoveryService(contactDiscoveryStore, userEventPublisher)
	var interestReader application.InterestProfileReader
	if mongoDB != nil {
		interestReader = projection.NewMongoInterestProfileReader(mongoDB)
	}
	interestProfileService := application.NewInterestProfileService(interestReader)
	personaProfileProposalFacade, err := personaapp.NewProfileProposalFacade(personaProfileProposalStore)
	if err != nil {
		return err
	}
	profileProposalFacade, err := proposalapp.NewFacade(
		profileProposalStore,
		profileProposalStore,
		personaProfileProposalFacade,
		personaProfileProposalStore,
	)
	if err != nil {
		return err
	}

	accountCloseStore, err := useraccountpersistence.NewCloseStore(pgPool)
	if err != nil {
		return err
	}
	accountOutboxStore, err :=
		useraccountpersistence.NewUserAccountOutboxStore(pgPool)
	if err != nil {
		return err
	}
	accountCloseProjections := searchindex.ComposePublisher()
	if mongoDB != nil {
		accountCloseProjections = searchindex.ComposePublisher(
			accountCloseProjections,
			useraccountprojection.NewMongoCleanupProjector(mongoDB),
			newAccountClosureTestPublisher(
				followingSubjectStore,
				followedSubjectVisitStore,
				creatorpersistence.NewCreatorRuntimeProfileReader(mongoDB),
			),
		)
	}
	accountEventFanout, err := mq.NewUserAccountEventFanout(
		userEventPublisher,
		accountCloseProjections,
	)
	if err != nil {
		return err
	}
	accountOutboxRelay, err := useraccountapp.NewUserAccountOutboxRelay(
		accountOutboxStore,
		accountEventFanout,
		"user-service-api-integration",
	)
	if err != nil {
		return err
	}
	accountCloseRelayContext, cancelAccountCloseRelay :=
		context.WithCancel(context.Background())
	accountCloseRelayCancel = cancelAccountCloseRelay
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		accountOutboxRelay.Run(accountCloseRelayContext)
	}()
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
		return err
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
		return err
	}
	greetingHandler, err := greetinghttp.NewHandler(greetingService)
	if err != nil {
		return err
	}
	contactDiscoveryHandler, err := contacthttp.NewHandler(
		contactDiscoveryService,
		relationshipService,
		greetingService,
	)
	if err != nil {
		return err
	}
	userHandler.WithAccountLifecycle(closeAccountFacade)
	userHandler.WithAccountEnforcement(accountEnforcementFacade)
	userHandler.WithAccountSecurityReader(accountEnforcementStore)
	userHandler.WithFederatedLogins(
		application.NewFederatedLoginFacade(
			authService,
			externalProviderRuntime.wechat,
			nil,
		),
		application.NewFederatedLoginFacade(
			authService,
			externalProviderRuntime.alipay,
			externalProviderRuntime.alipayIssue,
		),
		application.NewFederatedLoginFacade(
			authService,
			externalProviderRuntime.qq,
			nil,
		),
	)
	federatedPhoneBindingHandler, err :=
		credentialhttp.NewFederatedPhoneBindingHandler(authService)
	if err != nil {
		return err
	}
	serviceMux := http.NewServeMux()
	userHandler.RegisterRoutes(serviceMux)
	federatedPhoneBindingHandler.RegisterRoutes(serviceMux)
	profileProposalHandler.RegisterRoutes(serviceMux)
	invitationHandler.RegisterRoutes(serviceMux)
	greetingHandler.RegisterRoutes(serviceMux)
	contactDiscoveryHandler.RegisterRoutes(serviceMux)
	authorized := rtauth.EnforceGeneratedOperationAuthorization(
		operationsecurity.ForDomain("user"),
	)(userHandler.WrapAccountSecurity(serviceMux))
	testHandler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: testAccessVerifier,
	})(authorized)
	// SuspendAccount/RestoreAccount remain commercially blocked until the
	// Product Ops approval producer and cross-domain closure are complete. This
	// API-integration-only composition changes only those two descriptor copies
	// to exercise the already-implemented User transport trust boundary. It is
	// never reachable from an environment service composition.
	enforcementDescriptors := operationsecurity.ForDomain("user")
	for index := range enforcementDescriptors {
		switch enforcementDescriptors[index].CanonicalOperationID {
		case "user.user_account.SuspendAccount",
			"user.user_account.RestoreAccount":
			enforcementDescriptors[index].CommercialStatus = "ready"
		}
	}
	enforcementAuthorized := rtauth.EnforceGeneratedOperationAuthorization(
		enforcementDescriptors,
	)(userHandler.WrapAccountSecurity(serviceMux))
	testAccountEnforcementHandler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: testAccessVerifier,
	})(enforcementAuthorized)
	return nil
}

// testPersonaRelationshipFanout / testSubjectFollowFanout 与生产 composition
// 的 fanout 同构：Redis 发布 + following_subjects 投影都成功才推进 checkpoint。
type testPersonaRelationshipFanout struct {
	events    *mq.EventPublisher
	projector *followingevent.Handler
	counters  *relationshipprojection.CounterProjector
}

func (f *testPersonaRelationshipFanout) PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error {
	if err := f.events.PublishPersonaRelationship(ctx, event); err != nil {
		return err
	}
	if err := f.counters.Apply(ctx, event); err != nil {
		return err
	}
	if f.projector == nil {
		return nil
	}
	payload := event.Payload
	return f.projector.Apply(ctx, followingapp.FollowChangedEvent{
		EventID: event.EventID, ViewerPersonaID: payload.SourcePersonaID,
		SubjectType: "persona", SubjectID: payload.TargetPersonaID,
		Following: payload.Following, OccurredAt: payload.OccurredAt,
		SourceVersion: payload.Version,
	})
}

type testSubjectFollowFanout struct {
	events    *mq.EventPublisher
	projector *followingevent.Handler
}

func (f *testSubjectFollowFanout) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if err := f.events.PublishSubjectFollow(ctx, event); err != nil {
		return err
	}
	if f.projector == nil {
		return nil
	}
	payload := event.Payload
	return f.projector.Apply(ctx, followingapp.FollowChangedEvent{
		EventID: event.EventID, ViewerPersonaID: payload.PersonaID,
		SubjectType: payload.SubjectType, SubjectID: payload.SubjectID,
		Following:  payload.State == sfmodel.StateFollowing,
		OccurredAt: payload.OccurredAt, SourceVersion: payload.Version,
	})
}

func requireMongoBackedRuntime(tb testing.TB) {
	tb.Helper()
	mongoRuntimeMu.Lock()
	defer mongoRuntimeMu.Unlock()

	if mongoDB != nil {
		return
	}

	ctx := context.Background()
	if err := bootstrapMongoRuntime(ctx, false); err != nil {
		tb.Fatalf("mongo-backed user-service tests require QWQ_TEST_MONGO_URI/TEST_MONGO_URI or Docker-backed testcontainers: %v", err)
	}
	if err := rebuildTestHandler(ctx); err != nil {
		tb.Fatalf("rebuild user-service test handler with mongo runtime: %v", err)
	}
}
