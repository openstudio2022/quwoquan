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

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/otpseal"
	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	personaapp "quwoquan_service/services/user-service/internal/application/persona/persona"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	relationshipapp "quwoquan_service/services/user-service/internal/application/relationship/persona_relationship"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/persona/persistence"
	proposalpersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/profile_update_proposal/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
	relationshippersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/persistence"
)

var (
	testHandler                http.Handler
	pgPool                     *pgxpool.Pool
	mongoDB                    *mongo.Database
	integrationRedis           *testinfra.RealRedis
	redisRouter                *rtredis.Router
	redisClient                rtredis.Client
	mongoClient                *mongo.Client
	mongoContainer             *mongomod.MongoDBContainer
	mongoRuntimeMu             sync.Mutex
	externalProviderRuntime    *externalProviderContractRuntime
	externalInteractionRuntime *externalInteractionContractRuntime
	chatContractRuntime        *chatServiceContractRuntime
	conversationGateway        application.ConversationGateway
	relationshipRelayCancel    context.CancelFunc

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
	if relationshipRelayCancel != nil {
		relationshipRelayCancel()
	}
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
	os.Exit(code)
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
	personaStore := persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB)
	settingStore := persistence.NewPgSettingStore(pgPool)
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := persistence.NewPgGreetingStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	userAuthStore := persistence.NewPgUserAuthStore(pgPool)
	userDeviceStore := persistence.NewPgUserDeviceStore(pgPool)
	consentRecordStore := persistence.NewPgConsentRecordStore(pgPool)
	otpChallengeStore := persistence.NewPgOtpChallengeStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
	profileQrTokenStore := persistence.NewPgProfileQrTokenStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)
	personaProfileProposalStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		return err
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		return err
	}

	profileCache := cache.NewProfileCache(redisClient)
	settingCache := cache.NewSettingCache(redisClient)
	userEventPublisher := mq.NewEventPublisher(redisClient)
	userSyncService := runtimesync.NewService(redisClient, redisClient)
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		return err
	}

	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		settingStore,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
	)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	relationshipService := relationshipapp.NewPersonaRelationshipService(
		relationshipStore,
		profileStore,
		personaStore,
		profileCache,
		greetingStore,
	)
	if relationshipRelayCancel != nil {
		relationshipRelayCancel()
	}
	relationshipRelayContext, cancelRelationshipRelay := context.WithCancel(context.Background())
	relationshipRelayCancel = cancelRelationshipRelay
	relationshipRelay := relationshipapp.NewOutboxRelay(relationshipStore, userEventPublisher)
	go func() { _ = relationshipRelay.Run(relationshipRelayContext, 10*time.Millisecond) }()
	greetingService := application.NewGreetingService(
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
	)
	personaService := application.NewPersonaService(personaStore, personaStore, profileCache)
	workService := application.NewWorkService(workStore)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithAccountSessionStore(userAuthStore),
		application.WithDeviceRegistrationStore(userDeviceStore),
		application.WithConsentRecordStore(consentRecordStore),
		application.WithOtpCodeStore(cache.NewOtpCodeCache(redisClient)),
		application.WithOtpChallengeStore(otpChallengeStore),
		application.WithOTPCodeSealer(testOTPCodeSealer),
		application.WithExternalInteractionClient(externalInteractionRuntime.client),
		application.WithExternalAuthProviderClient(externalProviderRuntime.client),
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithOneTapPhoneResolver(application.StaticOneTapPhoneResolver{
			"carrier_token_new":      "+8618013813901",
			"carrier_token_existing": "+8618013813902",
		}),
	)
	subAccountService := application.NewSubAccountService(
		personaStore,
		personaStore,
		personaStore,
		profileStore,
		profileCache,
	)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, inviteStore)
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

	userHandler, err := httpadapter.NewUserHandler(
		profileService, searchService, relationshipService, greetingService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
		interestProfileService,
		profileProposalFacade,
	)
	if err != nil {
		return err
	}
	testHandler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: testAccessVerifier,
	})(userHandler.Routes())
	return nil
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
