package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	rtchttp "quwoquan_service/services/rtc-service/internal/adapters/http"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

var (
	testHandler      http.Handler
	mongoDB          *mongo.Database
	mongoClient      *mongo.Client
	integrationRedis *testinfra.RealRedis
	redisRouter      *rtredis.Router
)

var collections = []string{
	"call_sessions",
}

func requireMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	if mongoDB == nil {
		tb.Fatal("rtc-service tests require TestMain to provision mongoDB or exit before execution")
	}
	return mongoDB
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	var err error
	integrationRedis, err = testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("rtc-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2); err != nil {
		panic("flush rtc-service integration Redis: " + err.Error())
	}

	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 0, TLS: integrationRedis.TLS},
			"realtime": {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 1, TLS: integrationRedis.TLS},
			"rec":      {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 2, TLS: integrationRedis.TLS},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	})

	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			panic(
				"rtc-service api_integration requires a real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + runErr.Error(),
			)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		mongoURI = uri
	}

	mongoClientOptions := mongoopts.Client().ApplyURI(mongoURI)
	if mongoContainer != nil {
		mongoClientOptions.SetDirect(true)
	}
	mongoClient, err = mongo.Connect(mongoClientOptions)
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("rtc_test")

	callStore := persistence.NewMongoCallStore(mongoDB)
	callCache := rtccache.NewCallStateCache(redisRouter.Scene("general"))
	eventPublisher := mq.NewEventPublisher(redisRouter.Scene("realtime"))
	domainSvc := callsession.NewCallSessionService()
	tokenIssuer := livekit.NewParticipantTokenIssuer("testkey", "testsecret")
	orchestrator := application.NewCallOrchestrator(
		callStore,
		callCache,
		domainSvc,
		nil,
		tokenIssuer,
		eventPublisher,
		application.AllowRelationshipGateForTest(),
		nil,
	)

	testHandler = rtchttp.NewCallHandler(orchestrator, nil).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	_ = integrationRedis.Close(ctx)
	os.Exit(code)
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}

func cleanAll(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	ctx := context.Background()
	for _, name := range collections {
		_, _ = mongoDB.Collection(name).DeleteMany(ctx, bson.M{})
	}
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2); err != nil {
		t.Fatalf("flush rtc integration Redis: %v", err)
	}
}
