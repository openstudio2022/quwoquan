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
	"quwoquan_service/internal/platform/reliabletaskmongo"
	"quwoquan_service/internal/platform/testinfra"
)

var (
	integrationMongoClient    *mongo.Client
	integrationMongoDB        *mongo.Database
	integrationMongoContainer *mongomod.MongoDBContainer
	integrationReliableStore  *reliabletaskmongo.Store
)

func TestMain(m *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := runMongoContainer(startupCtx)
		if err != nil {
			panic(
				"integration-service api_integration requires real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + err.Error(),
			)
		}
		integrationMongoContainer = container
		uri, err := container.ConnectionString(startupCtx)
		if err != nil {
			panic("resolve integration-service MongoDB testcontainer URI: " + err.Error())
		}
		mongoURI = uri + "&directConnection=true"
	}

	var err error
	integrationMongoClient, err = mongodb.Connect(
		startupCtx,
		mongodb.ConnectConfig{
			URI:                    mongoURI,
			ConnectTimeoutSeconds:  10,
			ServerSelectionSeconds: 10,
		},
	)
	if err != nil {
		panic("connect integration-service api_integration MongoDB: " + err.Error())
	}
	integrationMongoDB = integrationMongoClient.Database(
		fmt.Sprintf("integration_service_api_integration_%d", time.Now().UnixNano()),
	)
	integrationReliableStore = reliabletaskmongo.New(integrationMongoDB)
	if err := integrationReliableStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure integration-service reliable-task indexes: " + err.Error())
	}
	cancelStartup()

	code := m.Run()

	cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = integrationMongoDB.Drop(cleanupCtx)
	_ = integrationMongoClient.Disconnect(cleanupCtx)
	if integrationMongoContainer != nil {
		_ = integrationMongoContainer.Terminate(cleanupCtx)
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

func resetReliableTaskCollections(t *testing.T) {
	t.Helper()
	if integrationMongoDB == nil || integrationReliableStore == nil {
		t.Fatal("real MongoDB reliable-task store was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	for _, collection := range []string{
		"reliable_task_outbox",
		"reliable_async_task",
		"notification_outbox",
		"notification_delivery_ledger",
		"external_provider_attempt_ledger",
		"external_interaction_result_outbox",
		"reliable_task_recovery_receipts",
		"otp_code_reference_vault",
		"reliable_task_leases",
	} {
		if _, err := integrationMongoDB.Collection(collection).DeleteMany(ctx, bson.D{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
