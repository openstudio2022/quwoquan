package api_integration // TagNodeView real-store test runtime

import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	httpadapter "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	nodepersistence "quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

var (
	testHandler  http.Handler
	mongoDB      *mongo.Database
	tagNodeStore *nodepersistence.MongoTagNodeStore
	objStore     *indexpersistence.MongoObjectTagIndexStore
	releaseStore *taxonomyreleasestore.Store
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

	tagNodeStore = nodepersistence.NewMongoTagNodeStore(mongoDB.Collection("tag_nodes"))
	objStore = indexpersistence.NewMongoObjectTagIndexStore(mongoDB.Collection("object_tag_index"))
	releaseStore = taxonomyreleasestore.NewStore(mongoDB)
	indexCtx, indexCancel := context.WithTimeout(context.Background(), 30*time.Second)
	if err := tagNodeStore.EnsureIndexes(indexCtx); err != nil {
		indexCancel()
		panic("ensure tag node indexes: " + err.Error())
	}
	if err := objStore.EnsureIndexes(indexCtx); err != nil {
		indexCancel()
		panic("ensure object tag indexes: " + err.Error())
	}
	if err := releaseStore.EnsureIndexes(indexCtx); err != nil {
		indexCancel()
		panic("ensure taxonomy release indexes: " + err.Error())
	}
	indexCancel()

	svc := application.NewTagService(tagNodeStore, objStore, releaseStore)
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
	for _, coll := range []string{"tag_nodes", "object_tag_index", "tag_taxonomy_releases"} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
}

func activateReleaseForSeed(t *testing.T, releaseID string, nodeCount int) {
	t.Helper()
	facade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		t.Fatalf("new release facade: %v", err)
	}
	if _, err := facade.Stage(context.Background(), taxonomyrelease.StageCommand{
		ReleaseID:       releaseID,
		SourceOwner:     "test",
		CanonicalDigest: "seed-" + releaseID,
		ReleaseKind:     releasemodel.ReleaseKindContent,
		NodeCount:       nodeCount,
	}); err != nil {
		t.Fatalf("stage seed release %s: %v", releaseID, err)
	}
	if _, err := facade.Activate(context.Background(), releaseID); err != nil {
		t.Fatalf("activate seed release %s: %v", releaseID, err)
	}
}
