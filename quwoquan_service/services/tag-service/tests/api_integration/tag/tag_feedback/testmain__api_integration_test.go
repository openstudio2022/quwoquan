package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

var (
	mongoDB      *mongo.Database
	tagNodeStore *persistence.MongoTagNodeStore
	releaseStore *taxonomyreleasestore.Store
	tagService   *application.TagService
)

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("tag_feedback_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("TagFeedback api_integration requires real MongoDB: " + err.Error())
	}
	mongoDB = mongoRuntime.Database
	tagNodeStore = persistence.NewMongoTagNodeStore(mongoDB.Collection("tag_nodes"))
	releaseStore = taxonomyreleasestore.NewStore(mongoDB)
	if err := tagNodeStore.EnsureIndexes(context.Background()); err != nil {
		panic("ensure TagNodeView indexes: " + err.Error())
	}
	if err := releaseStore.EnsureIndexes(context.Background()); err != nil {
		panic("ensure TagTaxonomyRelease indexes: " + err.Error())
	}
	tagService = application.NewTagService(tagNodeStore, nil, releaseStore)

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func cleanCollections(t *testing.T) {
	t.Helper()
	for _, collection := range []string{"tag_nodes", "tag_feedback", "tag_taxonomy_releases"} {
		if _, err := mongoDB.Collection(collection).DeleteMany(context.Background(), bson.M{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}

func seedLaunchSubset(t *testing.T) {
	t.Helper()
	cleanCollections(t)
	_, err := tagNodeStore.Create(context.Background(), &model.TagNode{
		TagRef:          "Topic/旅行",
		Group:           "Topic",
		Label:           "旅行",
		DisplayLabel:    "旅行",
		LabelEn:         "Travel",
		Depth:           1,
		ReleaseID:       "feedback-test-release",
		LifecycleStatus: "active",
	})
	if err != nil {
		t.Fatalf("seed TagFeedback tag node: %v", err)
	}
	facade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		t.Fatalf("new release facade: %v", err)
	}
	if _, err := facade.Stage(context.Background(), taxonomyrelease.StageCommand{
		ReleaseID:       "feedback-test-release",
		SourceOwner:     "test",
		CanonicalDigest: "feedback-test-digest",
		NodeCount:       1,
	}); err != nil {
		t.Fatalf("stage feedback release: %v", err)
	}
	if _, err := facade.Activate(context.Background(), "feedback-test-release"); err != nil {
		t.Fatalf("activate feedback release: %v", err)
	}
}
