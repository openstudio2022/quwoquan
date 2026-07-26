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

// mongoDB 供真实存储 api_integration（recent_search_state / feedbackstore）使用；
// 既有 httptest 级检索合同测试不依赖它。
var mongoDB *mongo.Database

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("search_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("search-service api_integration requires real MongoDB: " + err.Error())
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
	for _, coll := range []string{
		"search_queries", "search_feedback_events",
		"search_feedback_command_receipts",
		"recent_search_states", "recent_search_receipts",
		"rm_search_term_heat",
		"search_user_account_closed_inbox",
		"search_user_account_closed_failures",
	} {
		if _, err := mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{}); err != nil {
			t.Fatalf("clean %s: %v", coll, err)
		}
	}
}
