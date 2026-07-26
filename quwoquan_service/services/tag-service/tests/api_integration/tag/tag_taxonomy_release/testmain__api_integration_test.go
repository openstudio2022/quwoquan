package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
)

var (
	mongoDB      *mongo.Database
	tagNodeStore *persistence.MongoTagNodeStore
)

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("tag_taxonomy_release_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("TagTaxonomyRelease api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database
	tagNodeStore = persistence.NewMongoTagNodeStore(mongoDB.Collection("tag_nodes"))
	if err := tagNodeStore.EnsureIndexes(context.Background()); err != nil {
		panic("ensure TagNodeView indexes: " + err.Error())
	}

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}
