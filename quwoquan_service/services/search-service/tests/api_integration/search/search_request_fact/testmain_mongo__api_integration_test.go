package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
)

// mongoDB 供真实存储 api_integration（recent_search_state / feedbackstore）使用；
// 既有 httptest 级检索合同测试不依赖它。
var (
	mongoDB          *mongo.Database
	realRedisRuntime *testinfra.RealRedis
	realRedisClient  rtredis.Client
	redisRouter      *rtredis.Router
)

func TestMain(m *testing.M) {
	mongoStartupCtx, mongoStartupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		mongoStartupCtx,
		testinfra.UniqueDatabaseName("search_api_integration"),
	)
	mongoStartupCancel()
	if err != nil {
		panic("search-service api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database
	redisStartupCtx, redisStartupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	realRedisRuntime, err = testinfra.StartRealRedis(redisStartupCtx)
	if err != nil {
		redisStartupCancel()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
		_ = mongoRuntime.Close(shutdownCtx)
		shutdownCancel()
		panic("search request fact api_integration requires real Redis: " + err.Error())
	}
	if err := realRedisRuntime.FlushDBs(redisStartupCtx, 0); err != nil {
		redisStartupCancel()
		panic("flush search request fact Redis: " + err.Error())
	}
	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     realRedisRuntime.Addr,
				Password: realRedisRuntime.Password,
				DB:       0,
				TLS:      realRedisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	realRedisClient = redisRouter.Scene("general")
	redisStartupCancel()

	code := m.Run()

	_ = redisRouter.Close()
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = realRedisRuntime.Close(shutdownCtx)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func cleanSearchCollections(t *testing.T) {
	t.Helper()
	if err := realRedisRuntime.FlushDBs(t.Context(), 0); err != nil {
		t.Fatalf("clean search request fact Redis: %v", err)
	}
	for _, coll := range []string{
		"search_queries", "search_feedback_events",
		"search_feedback_command_receipts",
		"recent_search_states", "recent_search_receipts",
		"rm_search_term_heat",
		"search_user_account_closed_inbox",
		"search_user_account_closed_failures",
		"search_user_account_restrictions",
		"search_user_account_restriction_inbox",
		"search_user_account_restriction_watermarks",
		"search_test_documents",
		"search_test_user_account_restrictions",
		"search_test_user_account_restriction_inbox",
	} {
		if _, err := mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{}); err != nil {
			t.Fatalf("clean %s: %v", coll, err)
		}
	}
}
