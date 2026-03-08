package tests

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"testing"

	"github.com/alicebob/miniredis/v2"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	rtchttp "quwoquan_service/services/rtc-service/internal/adapters/http"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

var (
	testHandler http.Handler
	mongoDB     *mongo.Database
	mongoClient *mongo.Client
	mr          *miniredis.Miniredis
	redisRouter *rtredis.Router
)

var collections = []string{
	"call_sessions",
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	var err error
	mr, err = miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	redisRouter = rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "standalone", Addr: mr.Addr()},
			"realtime": {Mode: "standalone", Addr: mr.Addr()},
			"rec":      {Mode: "standalone", Addr: mr.Addr()},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	})

	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping rtc-service L2 tests.\n"+
					"  Set TEST_MONGO_URI=mongodb://localhost:27017 to run without Docker.\n"+
					"  Error: %v\n\n", runErr)
			os.Exit(0)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		mongoURI = uri
	}

	mongoClient, err = mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("rtc_test")

	callStore := persistence.NewMongoCallStore(mongoDB)
	callCache := rtccache.NewCallStateCache(redisRouter.Scene("general"))
	eventPublisher := mq.NewEventPublisher(redisRouter.Scene("realtime"))
	domainSvc := callsession.NewCallSessionService()
	tokenSvc := application.NewTokenService("testkey", "testsecret")
	orchestrator := application.NewCallOrchestrator(callStore, callCache, domainSvc, nil, tokenSvc, eventPublisher)

	testHandler = rtchttp.NewCallHandler(orchestrator, nil).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	mr.Close()
	os.Exit(code)
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
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
	mr.FlushAll()
}
