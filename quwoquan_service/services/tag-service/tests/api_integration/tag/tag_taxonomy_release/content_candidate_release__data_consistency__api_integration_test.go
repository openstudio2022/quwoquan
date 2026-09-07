package api_integration

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	nodemodel "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/tagreleasecontrol"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

func TestTagReleaseControlCLIWritesExactFoundReceipt(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	candidates := taxonomyreleasestore.NewContentCandidateStore(mongoDB)
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := mongoDB.Collection(taxonomyreleasestore.ContentCandidateCollection).DeleteMany(ctx, bson.M{}); err != nil {
		t.Fatal(err)
	}
	seedCandidateNode(t, "candidate-cli", "Topic/文化")
	manifest := "sha256:" + strings.Repeat("7", 64)
	candidate, err := candidates.BuildContentCandidate(ctx, "alpha", "qwq_data", "candidate-cli", manifest, "content", 1, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := candidates.StageVerified(ctx, candidate); err != nil {
		t.Fatal(err)
	}
	report := filepath.Join(t.TempDir(), "candidate.json")
	if err := tagreleasecontrol.Run(ctx, []string{
		"--operation", "query-candidate", "--mongo-uri", testMongoURI,
		"--db", mongoDB.Name(), "--env", "alpha", "--release-id", "candidate-cli",
		"--manifest-digest", manifest, "--report", report,
	}); err != nil {
		t.Fatalf("run release-control: %v", err)
	}
	var receipt tagreleasecontrol.CandidateReceipt
	raw, err := os.ReadFile(report)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &receipt); err != nil {
		t.Fatal(err)
	}
	if receipt.Status != "found" || receipt.ReleaseID != "candidate-cli" || receipt.ManifestDigest != manifest || receipt.ClosureDigest != candidate.ClosureDigest {
		t.Fatalf("candidate receipt=%+v", receipt)
	}
}

func TestContentCandidateStageReplayDriftAndExactQuery(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	candidates := taxonomyreleasestore.NewContentCandidateStore(mongoDB)
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := mongoDB.Collection(taxonomyreleasestore.ContentCandidateCollection).DeleteMany(ctx, bson.M{}); err != nil {
		t.Fatal(err)
	}
	seedCandidateNode(t, "candidate-a", "Topic/旅行")
	manifest := "sha256:" + strings.Repeat("a", 64)
	verifiedAt := time.Date(2026, 9, 6, 4, 0, 0, 0, time.UTC)
	candidate, err := candidates.BuildContentCandidate(
		ctx, "alpha", "qwq_data", "candidate-a", manifest, "content", 1, verifiedAt,
	)
	if err != nil {
		t.Fatalf("build candidate: %v", err)
	}
	first, replayed, err := candidates.StageVerified(ctx, candidate)
	if err != nil || replayed || first.Status != "verified" {
		t.Fatalf("first stage=%+v replayed=%v err=%v", first, replayed, err)
	}
	replay, replayed, err := candidates.StageVerified(ctx, candidate)
	if err != nil || !replayed || replay.CanonicalDigest != first.CanonicalDigest {
		t.Fatalf("same digest replay=%+v replayed=%v err=%v", replay, replayed, err)
	}

	drifted := candidate
	drifted.CanonicalDigest = "sha256:" + strings.Repeat("b", 64)
	if _, _, err := candidates.StageVerified(ctx, drifted); err == nil {
		t.Fatal("candidate projection drift was accepted")
	}
	wrongManifest := candidate
	wrongManifest.ManifestDigest = "sha256:" + strings.Repeat("c", 64)
	if _, _, err := candidates.StageVerified(ctx, wrongManifest); err == nil {
		t.Fatal("same release fence accepted a different manifest")
	}

	found, ok, err := candidates.ReadVerifiedContentCandidate(ctx, "alpha", "qwq_data", "candidate-a", manifest)
	if err != nil || !ok || found.ClosureDigest != candidate.ClosureDigest {
		t.Fatalf("exact candidate=%+v found=%v err=%v", found, ok, err)
	}
	missingDigest := "sha256:" + strings.Repeat("d", 64)
	missing, ok, err := candidates.ReadVerifiedContentCandidate(ctx, "alpha", "qwq_data", "missing", missingDigest)
	if err != nil || ok || missing.ReleaseID != "missing" || missing.ManifestDigest != missingDigest {
		t.Fatalf("not found candidate=%+v found=%v err=%v", missing, ok, err)
	}

	if _, err := mongoDB.Collection("tag_nodes").UpdateOne(ctx, bson.M{"releaseId": "candidate-a"}, bson.M{"$set": bson.M{"label": "drifted"}}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := candidates.ReadVerifiedContentCandidate(ctx, "alpha", "qwq_data", "candidate-a", manifest); err == nil {
		t.Fatal("query accepted node closure drift")
	}
}

func TestContentCandidateStageBDoesNotActivatePriorA(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	prior := newReleaseFacade(t)
	if _, err := prior.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID: "prior-a", SourceOwner: "prior_taxonomy",
		CanonicalDigest: "prior-a", ReleaseKind: releasemodel.ReleaseKindContent, NodeCount: 1,
	}); err != nil {
		t.Fatal(err)
	}
	seedSnapshot(t, "prior-a", 1)
	if _, err := prior.Activate(ctx, "prior-a"); err != nil {
		t.Fatal(err)
	}

	candidates := taxonomyreleasestore.NewContentCandidateStore(mongoDB)
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := mongoDB.Collection(taxonomyreleasestore.ContentCandidateCollection).DeleteMany(ctx, bson.M{}); err != nil {
		t.Fatal(err)
	}
	seedCandidateNode(t, "content-b", "Topic/美食")
	candidate, err := candidates.BuildContentCandidate(
		ctx, "alpha", "qwq_data", "content-b", "sha256:"+strings.Repeat("e", 64),
		"content", 1, time.Now().UTC(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := candidates.StageVerified(ctx, candidate); err != nil {
		t.Fatal(err)
	}
	store := taxonomyreleasestore.NewStore(mongoDB)
	active, found, err := store.FindActive(ctx)
	if err != nil || !found || active.ReleaseID != "prior-a" {
		t.Fatalf("stage B changed active A: active=%+v found=%v err=%v", active, found, err)
	}
	if count, err := mongoDB.Collection("tag_taxonomy_releases").CountDocuments(ctx, bson.M{"_id": "content-b"}); err != nil || count != 0 {
		t.Fatalf("Data candidate leaked into prior release store count=%d err=%v", count, err)
	}
}

func TestContentCandidateQueryRequiresCanonicalIndexes(t *testing.T) {
	cleanReleases(t)
	ctx := context.Background()
	candidates := taxonomyreleasestore.NewContentCandidateStore(mongoDB)
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if err := mongoDB.Collection(taxonomyreleasestore.ContentCandidateCollection).Indexes().DropOne(ctx, taxonomyreleasestore.ContentCandidateIdentityIndex); err != nil {
		t.Fatal(err)
	}
	_, _, err := candidates.ReadVerifiedContentCandidate(
		ctx, "alpha", "qwq_data", "missing", "sha256:"+strings.Repeat("f", 64),
	)
	if err == nil {
		t.Fatal("query accepted missing canonical candidate index")
	}
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
}

func seedCandidateNode(t *testing.T, releaseID, tagRef string) {
	t.Helper()
	created, err := tagNodeStore.Create(context.Background(), &nodemodel.TagNode{
		TagRef: tagRef, Group: "Topic", NodeKind: "definition", Label: "tag",
		DisplayLabel: "tag", Depth: 1, ReleaseID: releaseID, LifecycleStatus: "active",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !created {
		t.Fatalf("candidate node %s/%s already exists", releaseID, tagRef)
	}
}
