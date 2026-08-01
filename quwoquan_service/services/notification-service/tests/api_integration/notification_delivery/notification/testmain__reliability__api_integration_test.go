package api_integration

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
	deliverypersistence "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/persistence"
)

var (
	notificationMongoClient     *mongo.Client
	notificationMongoDB         *mongo.Database
	notificationMongoContainer  *mongomod.MongoDBContainer
	notificationReliableStore   *deliverypersistence.MongoNotificationDeliveryJobStore
	notificationAppMessageStore *persistence.MongoAppMessageStore
	notificationAccountClosure  *persistence.MongoUserAccountClosedProjection
	notificationRestriction     *persistence.MongoUserAccountRestrictionProjection
	notificationRedisRuntime    *testinfra.RealRedis
	notificationRedisRouter     *rtredis.Router
	notificationRedisClient     rtredis.Client
)

func TestMain(m *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := runMongoContainer(startupCtx)
		if err != nil {
			panic(
				"notification-service api_integration requires real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + err.Error(),
			)
		}
		notificationMongoContainer = container
		uri, err := container.ConnectionString(startupCtx)
		if err != nil {
			panic("resolve notification-service MongoDB testcontainer URI: " + err.Error())
		}
		mongoURI = uri + "&directConnection=true"
	}

	var err error
	notificationMongoClient, err = mongodb.Connect(
		startupCtx,
		mongodb.ConnectConfig{
			URI:                    mongoURI,
			ConnectTimeoutSeconds:  10,
			ServerSelectionSeconds: 10,
		},
	)
	if err != nil {
		panic("connect notification-service api_integration MongoDB: " + err.Error())
	}
	notificationMongoDB = notificationMongoClient.Database(
		fmt.Sprintf("notification_service_api_integration_%d", time.Now().UnixNano()),
	)
	notificationRestriction, err =
		persistence.NewMongoUserAccountRestrictionProjection(notificationMongoDB)
	if err != nil {
		panic("create notification-service account-restriction projection: " + err.Error())
	}
	if err := notificationRestriction.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service account-restriction indexes: " + err.Error())
	}
	notificationReliableStore = deliverypersistence.NewMongoNotificationDeliveryJobStore(
		notificationMongoDB,
		notificationRestriction,
	)
	if err := notificationReliableStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service reliable-task indexes: " + err.Error())
	}
	notificationAppMessageStore = persistence.NewMongoAppMessageStore(notificationMongoDB)
	if err := notificationAppMessageStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service app-message indexes: " + err.Error())
	}
	notificationAccountClosure, err =
		persistence.NewMongoUserAccountClosedProjection(notificationMongoDB)
	if err != nil {
		panic("create notification-service account-closure projection: " + err.Error())
	}
	if err := notificationAccountClosure.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service account-closure indexes: " + err.Error())
	}
	notificationRedisRuntime, err = testinfra.StartRealRedis(startupCtx)
	if err != nil {
		panic(
			"notification-service api_integration requires real Redis: " +
				err.Error(),
		)
	}
	notificationRedisRouter, err = platformredis.NewRouter(
		rtredis.RouterConfig{
			Scenes: map[string]rtredis.SceneConfig{
				"realtime": {
					Mode:     "standalone",
					Addr:     notificationRedisRuntime.Addr,
					Password: notificationRedisRuntime.Password,
					TLS:      notificationRedisRuntime.TLS,
				},
			},
			DefaultScene: "realtime",
		},
	)
	if err != nil {
		panic("connect notification-service api_integration Redis: " + err.Error())
	}
	notificationRedisClient = notificationRedisRouter.Scene("realtime")
	if err := notificationRedisClient.Ping(startupCtx); err != nil {
		panic("ping notification-service api_integration Redis: " + err.Error())
	}
	cancelStartup()

	code := m.Run()

	cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = notificationMongoDB.Drop(cleanupCtx)
	_ = notificationMongoClient.Disconnect(cleanupCtx)
	if notificationRedisRuntime != nil {
		_ = notificationRedisRuntime.FlushDBs(cleanupCtx, 0)
	}
	if notificationRedisRouter != nil {
		_ = notificationRedisRouter.Close()
	}
	if notificationRedisRuntime != nil {
		_ = notificationRedisRuntime.Close(cleanupCtx)
	}
	if notificationMongoContainer != nil {
		_ = notificationMongoContainer.Terminate(cleanupCtx)
	}
	cancelCleanup()
	os.Exit(code)
}

func runMongoContainer(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func resetNotificationCollections(t *testing.T) {
	t.Helper()
	if notificationMongoDB == nil || notificationReliableStore == nil {
		t.Fatal("real MongoDB notification store was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	for _, collection := range []string{
		"reliable_task_outbox",
		"reliable_async_task",
		"notification_delivery_jobs",
		"notification_delivery_job_recipients",
		"notification_delivery_jobs_command_receipts",
		"notification_delivery_jobs_outbox",
		"notification_external_interaction_result_inbox",
		"app_messages",
		"reliable_task_leases",
		persistence.UserAccountClosedInboxCollection,
		persistence.UserAccountClosedFailureCollection,
		"notification_user_account_restrictions",
		"notification_user_account_restriction_inbox",
		"notification_user_account_restriction_watermarks",
	} {
		if _, err := notificationMongoDB.Collection(collection).DeleteMany(ctx, bson.D{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
	if notificationRedisRuntime != nil {
		if err := notificationRedisRuntime.FlushDBs(ctx, 0); err != nil {
			t.Fatalf("clean Redis: %v", err)
		}
	}
}
