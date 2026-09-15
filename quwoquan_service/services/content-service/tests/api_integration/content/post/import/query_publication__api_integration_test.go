package api_integration

import (
	"context"
	"go.mongodb.org/mongo-driver/v2/bson"
	"quwoquan_service/internal/platform/testinfra"
	rt "quwoquan_service/runtime/search"
	importer "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestQueryPublicationAtomicBindingAndReplay(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("query_publication"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		_ = runtime.Close(c)
	}()
	d := "sha256:" + strings.Repeat("a", 64)
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate", d}
	binding := rt.ReleaseQueryPreparationBinding{Release: release, Slice: "recommendation", SchemaGeneration: d, ProviderBindingGeneration: d}
	snapshot := rt.ReleasePostCandidateSnapshot{Release: release, SourceClosureDigest: d, MediaClosureDigest: d, Posts: []rt.ReleasePostPublicSnapshot{}}
	_ = snapshot.Seal()
	// 通过正式owner stage构造真实非空Post候选，source query不依赖active。
	now := time.Now().UTC().Truncate(time.Millisecond)
	post := importer.PostDoc{PostRef: "posts/article/source/1", ContentID: "source-post", ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", PoolStatus: "active", ContentType: "article", ContentIdentity: "work", Title: "真实候选文章", Body: "候选正文", AuthorID: "source-author", AuthorDisplayName: "候选作者", ArticleMarkdown: "# 候选正文", Admission: importer.ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "production", EvidenceRef: "audit/source", EvidenceDigest: d}, CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now}
	opts := importer.ImportOptions{ReleaseID: release.ReleaseID, ManifestDigest: release.ManifestDigest, ReleaseKind: "content", ActivationMode: "stage-only", Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data", ProjectionVersion: 1}
	if _, err = importer.StageImportedPostRelease(ctx, runtime.Database, "gamma", []importer.PostDoc{post}, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	snapshot, err = importer.NewPostCandidateReader(runtime.Database, nil).ReadPostCandidate(ctx, release)
	if err != nil || len(snapshot.Posts) != 1 {
		t.Fatal("verified candidate source", err)
	}
	publisher := importer.NewQueryPublisher(runtime.Database)
	id, err := publisher.Publish(ctx, binding, snapshot)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := publisher.Publish(ctx, binding, snapshot)
	if err != nil || replay != id {
		t.Fatal(replay, err)
	}
	for _, collection := range []string{"data_release_query_publications", "content_outbox"} {
		n, err := runtime.Database.Collection(collection).CountDocuments(ctx, bson.M{})
		if err != nil || n != 1 {
			t.Fatal(collection, n, err)
		}
	}
	snapshot.SourceClosureDigest = "sha256:" + strings.Repeat("b", 64)
	_ = snapshot.Seal()
	if _, err = publisher.Publish(ctx, binding, snapshot); err == nil {
		t.Fatal("same binding drift accepted")
	}
	count, err := runtime.Database.Collection("data_release_state").CountDocuments(ctx, bson.M{"kind": "active_pointer"})
	if err != nil || count != 0 {
		t.Fatal("publication created active", count, err)
	}
}
