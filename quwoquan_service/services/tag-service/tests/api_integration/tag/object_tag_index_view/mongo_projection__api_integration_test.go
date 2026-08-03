package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	indexports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
)

var (
	indexMongoRuntime *testinfra.RealMongo
	indexMongoDB      *mongo.Database
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("object_tag_index_api_integration"))
	cancel()
	if err != nil {
		panic("ObjectTagIndexView api_integration requires real MongoDB: " + err.Error())
	}
	indexMongoRuntime = runtime
	indexMongoDB = runtime.Database
	code := m.Run()
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = indexMongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func TestObjectTagIndexProjectionConvergesOnHighestSourceVersion(t *testing.T) {
	collection := indexMongoDB.Collection("object_tag_index")
	if _, err := collection.DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}
	store := indexpersistence.NewMongoObjectTagIndexStore(collection)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	newer := indexports.UserProfileTagProjection{
		EventID: "profile-tags-newer", UserID: "user-001",
		TagRefs:           []string{"Audience/用户/兴趣偏好/科技/AI"},
		TaxonomyReleaseID: "taxonomy-release-2", ProfileVersion: 2, OccurredAt: now,
	}
	applied, err := store.ApplyUserProfileTagProjection(context.Background(), newer)
	if err != nil || !applied {
		t.Fatalf("apply newer projection: applied=%v err=%v", applied, err)
	}
	stale := newer
	stale.EventID = "profile-tags-stale"
	stale.TagRefs = []string{"Audience/用户/兴趣偏好/生活/咖啡"}
	stale.TaxonomyReleaseID = "taxonomy-release-1"
	stale.ProfileVersion = 1
	stale.OccurredAt = now.Add(-time.Minute)
	applied, err = store.ApplyUserProfileTagProjection(context.Background(), stale)
	if err != nil || applied {
		t.Fatalf("stale projection applied=%v err=%v", applied, err)
	}
	index, err := store.FindByObject(context.Background(), "user-001", "user")
	if err != nil || index == nil || len(index.TagRefs) != 1 || index.TagRefs[0] != newer.TagRefs[0] {
		t.Fatalf("canonical index=%+v err=%v", index, err)
	}
}
