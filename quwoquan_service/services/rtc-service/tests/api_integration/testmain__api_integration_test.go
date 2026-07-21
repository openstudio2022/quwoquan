package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"sync"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	rtchttp "quwoquan_service/services/rtc-service/internal/adapters/http"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

var (
	testHandler      http.Handler
	testOrchestrator *application.CallOrchestrator
	mongoDB          *mongo.Database
	mongoClient      *mongo.Client
	integrationRedis *testinfra.RealRedis
	redisRouter      *rtredis.Router
)

var collections = []string{
	"call_sessions",
	"call_session_command_receipts",
	"call_session_outbox",
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
	if err := callStore.EnsureIndexes(ctx); err != nil {
		panic("ensure rtc call session indexes: " + err.Error())
	}
	callCache := rtccache.NewCallStateCache(redisRouter.Scene("general"))
	realtimeTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"rtc-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
	)
	if err != nil {
		panic("construct rtc message transport: " + err.Error())
	}
	realtimePublisher := mq.NewRealtimePublisher(realtimeTransport)
	domainSvc := callsession.NewCallSessionService()
	orchestrator := application.NewCallOrchestrator(
		callStore,
		callCache,
		domainSvc,
		newTestMediaRoomProvider(),
		application.AllowRelationshipGateForTest(),
	)
	testOrchestrator = orchestrator
	outboxRelay := application.NewCallOutboxRelay(callStore, realtimePublisher)
	workerCtx, cancelWorker := context.WithCancel(ctx)
	var workerWG sync.WaitGroup
	workerWG.Add(1)
	go func() {
		defer workerWG.Done()
		_ = outboxRelay.Run(workerCtx, 10*time.Millisecond)
	}()

	// 真实链路：auth middleware 从可信 Principal 派生 actor（不信任客户端 header），
	// 命令级 Idempotency-Key 经 handler 注入 context。operation guard 的
	// commercial 闸门属 Phase 7（commercial 翻 ready）后由生产 main.go 覆盖，
	// 其鉴权行为由 runtime/auth 合同测试保证。
	testHandler = withTrustedPrincipal(rtchttp.NewCallHandler(orchestrator).Routes())

	code := m.Run()

	cancelWorker()
	workerWG.Wait()
	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	_ = integrationRedis.Close(ctx)
	os.Exit(code)
}

type testMediaRoomProvider struct{}

func newTestMediaRoomProvider() *testMediaRoomProvider {
	return &testMediaRoomProvider{}
}

func (*testMediaRoomProvider) CreateRoom(context.Context, string, int) error {
	return nil
}

func (*testMediaRoomProvider) DeleteRoom(context.Context, string) error {
	return nil
}

func (*testMediaRoomProvider) ListParticipants(
	context.Context,
	string,
) ([]application.RoomParticipant, error) {
	return nil, nil
}

func (*testMediaRoomProvider) RemoveParticipant(
	context.Context,
	string,
	string,
) error {
	return nil
}

func (*testMediaRoomProvider) IssueParticipantAccess(
	_ context.Context,
	roomName string,
	participantIdentity string,
) (application.MediaSessionAccess, error) {
	return application.MediaSessionAccess{
		AccessToken: "test-access:" + roomName + ":" + participantIdentity,
	}, nil
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
