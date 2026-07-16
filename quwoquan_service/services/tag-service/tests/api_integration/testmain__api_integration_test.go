package api_integration

import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	httpadapter "quwoquan_service/services/tag-service/internal/adapters/http"
	"quwoquan_service/services/tag-service/internal/application"
	"quwoquan_service/services/tag-service/internal/infrastructure/persistence"
)

var (
	testHandler  http.Handler
	mongoDB      *mongo.Database
	tagNodeStore *persistence.MongoTagNodeStore
	objStore     *persistence.MongoObjectTagIndexStore
)

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("tag_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("tag-service api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database

	tagNodeStore = persistence.NewMongoTagNodeStore(mongoDB.Collection("tag_nodes"))
	objStore = persistence.NewMongoObjectTagIndexStore(mongoDB.Collection("object_tag_index"))
	indexCtx, indexCancel := context.WithTimeout(context.Background(), 30*time.Second)
	if err := tagNodeStore.EnsureIndexes(indexCtx); err != nil {
		indexCancel()
		panic("ensure tag node indexes: " + err.Error())
	}
	if err := objStore.EnsureIndexes(indexCtx); err != nil {
		indexCancel()
		panic("ensure object tag indexes: " + err.Error())
	}
	indexCancel()

	svc := application.NewTagService(tagNodeStore, objStore)
	testHandler = httpadapter.NewTagHandler(svc).Routes()

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func cleanCollections(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	for _, coll := range []string{"tag_nodes", "object_tag_index"} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
}
