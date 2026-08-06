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
		testinfra.UniqueDatabaseName("search_index_view_api_integration"),
	)
	mongoStartupCancel()
	if err != nil {
		panic("search index view api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database
	redisStartupCtx, redisStartupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	realRedisRuntime, err = testinfra.StartRealRedis(redisStartupCtx)
	if err != nil {
		redisStartupCancel()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
		_ = mongoRuntime.Close(shutdownCtx)
		shutdownCancel()
		panic("search index view api_integration requires real Redis: " + err.Error())
	}
	if err := realRedisRuntime.FlushDBs(redisStartupCtx, 0); err != nil {
		redisStartupCancel()
		panic("flush search index view Redis: " + err.Error())
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
		t.Fatalf("clean search index view Redis: %v", err)
	}
	for _, collection := range []string{
		"search_user_account_restrictions",
		"search_user_account_restriction_inbox",
		"search_user_account_restriction_watermarks",
		"search_test_documents",
		"search_test_user_account_restrictions",
		"search_test_user_account_restriction_inbox",
		"rm_search_experiment_policy",
	} {
		if _, err := mongoDB.Collection(collection).DeleteMany(
			context.Background(),
			bson.M{},
		); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
