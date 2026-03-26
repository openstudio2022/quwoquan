package tests

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

var (
	testHandler http.Handler
	pgPool      *pgxpool.Pool
	mongoDB     *mongo.Database
	mr          *miniredis.Miniredis
	redisClient rtredis.Client
)

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

	// 3. MongoDB testcontainer
	mongoURI := os.Getenv("TEST_MONGO_URI")
	var mongoContainer *mongomod.MongoDBContainer
	var mongoClient *mongo.Client
	mongoSkipped := false
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr, "\n[L2] WARN: Docker unavailable, MongoDB-dependent tests will be skipped.\n")
			mongoSkipped = true
		} else {
			mongoContainer = container
			mongoURI, err = container.ConnectionString(ctx)
			if err != nil {
				panic("mongo connection string: " + err.Error())
			}
		}
	}

	if !mongoSkipped {
		mongoClient, err = mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
		if err != nil {
			panic("mongo connect: " + err.Error())
		}
		mongoDB = mongoClient.Database("user_test")
	}

	// 4. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := persistence.NewPgPersonaStore(pgPool)
	settingStore := persistence.NewPgSettingStore(pgPool)
	blockStore := persistence.NewPgBlockStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	var followStore *persistence.MongoFollowStore
	if mongoDB != nil {
		followStore = persistence.NewMongoFollowStore(mongoDB)
		_ = followStore.EnsureIndexes(ctx)
	}
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)

	// 5. Caches
	profileCache := cache.NewProfileCache(redisClient)
	settingCache := cache.NewSettingCache(redisClient)
	blockCache := cache.NewBlockCache(redisClient)

	// 6. Services
	profileService := application.NewProfileService(profileStore, personaStore, settingStore, profileCache, settingCache)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	followService := application.NewFollowService(followStore, profileStore, profileCache)
	blockService := application.NewBlockService(blockStore, blockCache)
	personaService := application.NewPersonaService(personaStore, pgPool, profileCache)
	workService := application.NewWorkService(workStore)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	authService := application.NewAuthService(profileStore, personaStore, credentialStore, profileCache)
	subAccountService := application.NewSubAccountService(personaStore, profileStore, profileCache)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, personaStore)

	// 7. Handler
	testHandler = httpadapter.NewUserHandler(
		profileService, searchService, followService, blockService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
	).Routes()

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
