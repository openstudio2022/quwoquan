package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
)

var mongoDB *mongo.Database

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("search_index_view_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("search index view api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func cleanSearchCollections(t *testing.T) {
	t.Helper()
	for _, collection := range []string{
		"search_user_account_restrictions",
		"search_user_account_restriction_inbox",
		"search_user_account_restriction_watermarks",
		"search_test_documents",
		"search_test_user_account_restrictions",
		"search_test_user_account_restriction_inbox",
	} {
		if _, err := mongoDB.Collection(collection).DeleteMany(
			context.Background(),
			bson.M{},
		); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
