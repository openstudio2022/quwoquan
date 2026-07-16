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
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/notification-service/internal/infrastructure/persistence"
)

var (
	notificationMongoClient     *mongo.Client
	notificationMongoDB         *mongo.Database
	notificationMongoContainer  *mongomod.MongoDBContainer
	notificationReliableStore   *persistence.MongoNotificationDeliveryJobStore
	notificationAppMessageStore *persistence.MongoAppMessageStore
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
	notificationReliableStore = persistence.NewMongoNotificationDeliveryJobStore(notificationMongoDB)
	if err := notificationReliableStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service reliable-task indexes: " + err.Error())
	}
	notificationAppMessageStore = persistence.NewMongoAppMessageStore(notificationMongoDB)
	if err := notificationAppMessageStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure notification-service app-message indexes: " + err.Error())
	}
	cancelStartup()

	code := m.Run()

	cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = notificationMongoDB.Drop(cleanupCtx)
	_ = notificationMongoClient.Disconnect(cleanupCtx)
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
		"app_messages",
		"external_provider_attempt_ledger",
		"reliable_task_leases",
	} {
		if _, err := notificationMongoDB.Collection(collection).DeleteMany(ctx, bson.D{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
