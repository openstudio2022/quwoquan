package assistant_run_integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
)

var (
	publicWebMongoDB     *mongo.Database
	publicWebMongoClient *mongo.Client
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		ctx,
		testinfra.UniqueDatabaseName("assistant_public_web_api_integration"),
	)
	cancel()
	if err != nil {
		panic("public web api_integration requires real MongoDB: " + err.Error())
	}
	publicWebMongoDB = mongoRuntime.Database
	publicWebMongoClient = mongoRuntime.Client

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 45*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
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
