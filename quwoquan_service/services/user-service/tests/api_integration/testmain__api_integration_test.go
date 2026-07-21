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
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	sfmodel "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/model"
	accountsessionpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/account_session/persistence"
	challengepersistence "quwoquan_service/services/user-service/internal/infrastructure/account/authentication_challenge/persistence"
	credentialpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/credential_binding/persistence"
	registrationpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/device_registration/persistence"
	useraccountcache "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/cache"
	useraccountpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/persistence"
	useraccountprojection "quwoquan_service/services/user-service/internal/infrastructure/account/user_account/projection"
	usersettingspersistence "quwoquan_service/services/user-service/internal/infrastructure/account/user_settings/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/persona/persistence"
	proposalpersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/profile_update_proposal/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
	relationshippersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/persistence"
	relationshipprojection "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/projection"
	subjectfollowpersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/subject_follow/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/searchindex"
	"quwoquan_service/services/user-service/internal/infrastructure/tagindex"
	usercache "quwoquan_service/services/user-service/internal/infrastructure/user/cache"
	userpersistence "quwoquan_service/services/user-service/internal/infrastructure/user/persistence"
)

var (
	testHandler                   http.Handler
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
	conversationGateway           application.ConversationGateway
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
	greetingStore := userpersistence.NewPgGreetingStore(pgPool)
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
	contactDiscoveryStore := userpersistence.NewPgContactDiscoveryStore(pgPool)
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

	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
	)
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
	followingSubjectStore := persistence.NewMongoFollowingSubjectStore(mongoDB)
	followedSubjectVisitStore := persistence.NewMongoFollowedSubjectVisitStore(mongoDB)
	var followingProjector *followingapp.Projector
	if mongoDB != nil {
		if err := followingSubjectStore.EnsureIndexes(ctx); err != nil {
			return err
		}
		if err := followedSubjectVisitStore.EnsureIndexes(ctx); err != nil {
			return err
		}
		followingProjector = followingapp.NewProjector(followingSubjectStore)
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
	greetingService := application.NewGreetingService(
		greetingStore,
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
		userEventPublisher,
		application.NewSettingsGreetingNotifyPolicy(
			userSettingsStore,
			personaStore,
		),
	)
	greetingRelay := application.NewGreetingOutboxRelay(
		greetingStore,
		userEventPublisher,
		userEventPublisher,
	)
	integrationRelayRunners.Add(1)
	go func() {
		defer integrationRelayRunners.Done()
		_ = greetingRelay.Run(relationshipRelayContext, 10*time.Millisecond)
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
		application.WithDeviceRegistration(deviceRegistrationCommands),
		application.WithConsentRecordStore(consentRecordStore),
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
	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		return err
	}
	subAccountService := application.NewSubAccountService(
		personaStore,
		personaCommandStore,
		profileStore,
		profileCache,
	)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore, userEventPublisher)
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
			tagindex.NewProjector(
				mongoDB.Collection("object_tag_index"),
				profileStore,
			),
			useraccountprojection.NewMongoCleanupProjector(mongoDB),
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
	authorized := rtauth.EnforceGeneratedOperationAuthorization(
		operationsecurity.ForDomain("user"),
	)(userHandler.Routes())
	testHandler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: testAccessVerifier,
	})(authorized)
	return nil
}

// testPersonaRelationshipFanout / testSubjectFollowFanout 与生产 composition
// 的 fanout 同构：Redis 发布 + following_subjects 投影都成功才推进 checkpoint。
type testPersonaRelationshipFanout struct {
	events    *mq.EventPublisher
	projector *followingapp.Projector
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
	return f.projector.ApplyPersonaRelationship(ctx, event)
}

type testSubjectFollowFanout struct {
	events    *mq.EventPublisher
	projector *followingapp.Projector
}

func (f *testSubjectFollowFanout) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if err := f.events.PublishSubjectFollow(ctx, event); err != nil {
		return err
	}
	if f.projector == nil {
		return nil
	}
	return f.projector.ApplySubjectFollow(ctx, event)
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
