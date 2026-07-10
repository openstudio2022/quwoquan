package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rtauth "quwoquan_service/runtime/auth"
	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
)

var (
	testHandler    http.Handler
	pgPool         *pgxpool.Pool
	mongoDB        *mongo.Database
	mr             *miniredis.Miniredis
	redisClient    rtredis.Client
	mongoClient    *mongo.Client
	mongoContainer *mongomod.MongoDBContainer
	mongoRuntimeMu sync.Mutex

	testAccessSecret   = []byte("test-user-service-access-secret")
	testAccessSigner   = rtauth.NewHS256Signer(testAccessSecret, 30*time.Minute)
	testAccessVerifier = rtauth.NewHS256Verifier(testAccessSecret)
)

type acceptedExternalClient struct{}

func (acceptedExternalClient) SubmitSMSOTP(
	ctx context.Context,
	req application.SMSOTPDispatchRequest,
) (application.ExternalInteractionAccepted, error) {
	_ = ctx
	return application.ExternalInteractionAccepted{
		RequestID: req.RequestID,
		Status:    "accepted",
	}, nil
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	// 1. miniredis
	var err error
	mr, err = miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	redisRouter := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "standalone", Addr: mr.Addr()},
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

	// 3. MongoDB best-effort bootstrap. Local runs keep non-Mongo tests runnable,
	// while Mongo-backed tests can explicitly upgrade the runtime on demand.
	if err := bootstrapMongoRuntime(ctx, true); err != nil {
		if configuredMongoURI() != "" || isCIEnvironment() {
			panic("mongo bootstrap: " + err.Error())
		}
		fmt.Fprintf(
			os.Stderr,
			"\n[L2] WARN: Docker unavailable, MongoDB-dependent tests will self-bootstrap or fail when exercised.\n"+
				"  Set QWQ_TEST_MONGO_URI or TEST_MONGO_URI to run them without Docker.\n"+
				"  Error: %v\n\n",
			err,
		)
	}
	if err := rebuildTestHandler(ctx); err != nil {
		panic("build user-service test handler: " + err.Error())
	}

	code := m.Run()

	// Teardown
	pgPool.Close()
	if mongoClient != nil {
		_ = mongoClient.Disconnect(ctx)
	}
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	mr.Close()
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
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
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
		mongoURI = uri
	}

	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
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
	blockStore := persistence.NewPgBlockStore(pgPool)
	greetingStore := persistence.NewPgGreetingStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	var followStore *persistence.MongoFollowStore
	if mongoDB != nil {
		followStore = persistence.NewMongoFollowStore(mongoDB)
		if err := followStore.EnsureIndexes(ctx); err != nil {
			return fmt.Errorf("ensure follow indexes: %w", err)
		}
	}
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	userAuthStore := persistence.NewPgUserAuthStore(pgPool)
	userDeviceStore := persistence.NewPgUserDeviceStore(pgPool)
	consentRecordStore := persistence.NewPgConsentRecordStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
	profileQrTokenStore := persistence.NewPgProfileQrTokenStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)

	profileCache := cache.NewProfileCache(redisClient)
	settingCache := cache.NewSettingCache(redisClient)
	blockCache := cache.NewBlockCache(redisClient)
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
		settingCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenRepository(profileQrTokenStore),
	)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	followService := application.NewFollowService(
		followStore,
		profileStore,
		personaStore,
		profileCache,
		blockStore,
		userEventPublisher,
	)
	conversationGateway := application.NewMemoryConversationGateway()
	greetingService := application.NewGreetingService(
		greetingStore,
		followStore,
		blockStore,
		conversationGateway,
		userEventPublisher,
	)
	blockService := application.NewBlockService(blockStore, followStore, blockCache, userEventPublisher, greetingStore)
	personaService := application.NewPersonaService(personaStore, pgPool, profileCache)
	workService := application.NewWorkService(workStore)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		profileCache,
		shardDirectory,
		application.WithUserAuthRepository(userAuthStore),
		application.WithUserDeviceRepository(userDeviceStore),
		application.WithConsentRepository(consentRecordStore),
		application.WithOtpCodeStore(cache.NewOtpCodeCache(redisClient)),
		application.WithOtpDebugReveal(true),
		application.WithExternalInteractionClient(acceptedExternalClient{}),
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithOneTapPhoneResolver(application.StaticOneTapPhoneResolver{
			"carrier_token_new":      "+8618013813901",
			"carrier_token_existing": "+8618013813902",
		}),
	)
	subAccountService := application.NewSubAccountService(personaStore, profileStore, profileCache)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, personaStore)
	var interestReader application.InterestProfileReader
	if mongoDB != nil {
		interestReader = projection.NewMongoInterestProfileReader(mongoDB)
	}
	interestProfileService := application.NewInterestProfileService(interestReader)

	testHandler = rtauth.Middleware(testAccessVerifier)(httpadapter.NewUserHandler(
		profileService, searchService, followService, blockService, greetingService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
		interestProfileService,
	).Routes())
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
