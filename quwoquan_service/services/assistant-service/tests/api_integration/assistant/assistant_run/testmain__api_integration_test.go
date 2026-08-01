package assistant_run_integration

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
)

var (
	publicWebMongoDB        *mongo.Database
	publicWebMongoClient    *mongo.Client
	publicWebMongoContainer *mongomod.MongoDBContainer
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	testinfra.ConfigureLocalContainerRuntime()
	startPublicWebMongo(ctx)
	cancel()

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 45*time.Second)
	if publicWebMongoDB != nil {
		_ = publicWebMongoDB.Drop(shutdownCtx)
	}
	if publicWebMongoClient != nil {
		_ = publicWebMongoClient.Disconnect(shutdownCtx)
	}
	if publicWebMongoContainer != nil {
		_ = publicWebMongoContainer.Terminate(shutdownCtx)
	}
	shutdownCancel()
	os.Exit(code)
}

func startPublicWebMongo(ctx context.Context) {
	mongoURI := strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
	if mongoURI == "" {
		mongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	}
	if mongoURI == "" {
		container, err := mongomod.Run(
			ctx,
			"mongo:7-jammy",
			mongomod.WithReplicaSet("rs0"),
		)
		if err != nil {
			panic("public web api_integration requires real MongoDB: " + err.Error())
		}
		publicWebMongoContainer = container
		mongoURI, err = container.ConnectionString(ctx)
		if err != nil {
			panic("public web api_integration MongoDB connection string: " + err.Error())
		}
	}
	clientOptions := options.Client().
		ApplyURI(mongoURI).
		SetServerSelectionTimeout(15 * time.Second)
	if publicWebMongoContainer != nil {
		clientOptions.SetDirect(true)
	}
	var err error
	publicWebMongoClient, err = mongo.Connect(clientOptions)
	if err != nil {
		panic("public web api_integration connect MongoDB: " + err.Error())
	}
	if err := publicWebMongoClient.Ping(ctx, nil); err != nil {
		panic("public web api_integration ping MongoDB: " + err.Error())
	}
	publicWebMongoDB = publicWebMongoClient.Database(
		"assistant_public_web_api_integration_" + strconv.Itoa(os.Getpid()),
	)
}

func resetPublicWebMongo(t *testing.T) {
	t.Helper()
	if _, err := publicWebMongoDB.Collection("assistant_run_web_evidence").
		DeleteMany(t.Context(), map[string]any{}); err != nil {
		t.Fatalf("reset public web evidence: %v", err)
	}
	if _, err := publicWebMongoDB.Collection("assistant_run_web_budgets").
		DeleteMany(t.Context(), map[string]any{}); err != nil {
		t.Fatalf("reset public web budgets: %v", err)
	}
}

func requirePublicWebMongo(t *testing.T) *mongo.Database {
	t.Helper()
	if publicWebMongoDB == nil {
		t.Fatal(fmt.Errorf("public web MongoDB was not initialized"))
	}
	return publicWebMongoDB
}
