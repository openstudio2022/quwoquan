//go:build mongo_integration

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func releaseCASOptions(releaseID, digest string, version int64) ImportOptions {
	return ImportOptions{
		ReleaseID: releaseID, ManifestDigest: digest, ReleaseClass: "research", ReleaseKind: "content",
		ActivationMode: "stage-only", Mode: "sync", DeletePolicy: "tombstone",
		SourceOwner: "qwq_data", ProjectionVersion: version,
	}
}

func releaseCASPost(contentID, postRef string, now time.Time) PostDoc {
	return PostDoc{
		PostRef: postRef, ContentID: contentID, ContentVersion: 1,
		PoolSourceType: "data", VariantPurpose: "original", PoolStatus: "active",
		ContentType: "article", ContentIdentity: "work", Title: contentID,
		AuthorID: "builtin_travel_blogger", ArticleMarkdown: "# " + contentID,
		Admission: ContentAdmission{
			ProcessResult: "completed", QualityResult: "passed", UsageScope: "research",
			EvidenceRef: "audit/attestation.json", EvidenceDigest: "sha256:" + strings.Repeat("a", 64),
		},
		CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now,
	}
}

func releaseCASMedia(assetID, _ string) map[string]ReleaseMediaAsset {
	assetDigest := "sha256:" + strings.Repeat("9", 64)
	plain := strings.TrimPrefix(assetDigest, "sha256:")
	return map[string]ReleaseMediaAsset{
		assetID: {
			AssetID: assetID, Kind: "image", Version: 1, ContentType: "image/jpeg",
			PrivateObjectKey: "media/objects/sha256/" + plain[:2] + "/" + plain[2:4] + "/" + plain + ".jpg",
			SHA256:           assetDigest, Bytes: 128,
		},
	}
}

func assertLiveReleaseCounts(t *testing.T, db *mongo.Database, posts, media, outbox int64) {
	t.Helper()
	ctx := context.Background()
	checks := []struct {
		collection string
		want       int64
	}{
		{collection: "posts", want: posts},
		{collection: "media_assets", want: media},
		{collection: "content_outbox", want: outbox},
	}
	for _, check := range checks {
		count, err := db.Collection(check.collection).CountDocuments(ctx, bson.M{})
		if err != nil || count != check.want {
			t.Fatalf("live %s count=%d want=%d err=%v", check.collection, count, check.want, err)
		}
	}
}

func assertLivePost(t *testing.T, db *mongo.Database, post PostDoc, opts ImportOptions, status, lifecycle string) {
	t.Helper()
	var row struct {
		ReleaseID       string `bson:"releaseId"`
		ManifestDigest  string `bson:"manifestDigest"`
		Status          string `bson:"status"`
		LifecycleStatus string `bson:"lifecycleStatus"`
	}
	if err := db.Collection("posts").FindOne(context.Background(), bson.M{
		"_id": RuntimePostID(post.ContentID),
	}).Decode(&row); err != nil {
		t.Fatalf("read live Post %s: %v", post.ContentID, err)
	}
	if row.ReleaseID != opts.ReleaseID || row.ManifestDigest != opts.ManifestDigest ||
		row.Status != status || row.LifecycleStatus != lifecycle {
		t.Fatalf("live Post %s mismatch: %+v", post.ContentID, row)
	}
}

func assertLiveMedia(t *testing.T, db *mongo.Database, assetID, releaseID, digest string) {
	t.Helper()
	var row struct {
		ReleaseID      string `bson:"sourceReleaseId"`
		ManifestDigest string `bson:"sourceManifestDigest"`
		Status         string `bson:"processingStatus"`
	}
	if err := db.Collection("media_assets").FindOne(context.Background(), bson.M{"_id": assetID}).Decode(&row); err != nil {
		t.Fatalf("read live media %s: %v", assetID, err)
	}
	if row.ReleaseID != releaseID || row.ManifestDigest != digest || row.Status != "ready" {
		t.Fatalf("live media %s mismatch: %+v", assetID, row)
	}
}

func mustRawDocument(t *testing.T, collection *mongo.Collection, filter bson.M) bson.Raw {
	t.Helper()
	raw, err := collection.FindOne(context.Background(), filter).Raw()
	if err != nil {
		t.Fatalf("read raw document %s: %v", collection.Name(), err)
	}
	return append(bson.Raw(nil), raw...)
}

func rawDocumentClosure(t *testing.T, collection *mongo.Collection, filter bson.M) []bson.Raw {
	t.Helper()
	cursor, err := collection.Find(context.Background(), filter)
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(context.Background())
	type keyedRaw struct {
		key string
		raw bson.Raw
	}
	var keyed []keyedRaw
	for cursor.Next(context.Background()) {
		raw := append(bson.Raw(nil), cursor.Current...)
		id, _ := raw.Lookup("_id").StringValueOK()
		keyed = append(keyed, keyedRaw{key: id, raw: raw})
	}
	if err := cursor.Err(); err != nil {
		t.Fatal(err)
	}
	sort.Slice(keyed, func(left, right int) bool {
		return keyed[left].key < keyed[right].key
	})
	result := make([]bson.Raw, 0, len(keyed))
	for _, row := range keyed {
		result = append(result, row.raw)
	}
	return result
}

func equalRawDocuments(left, right []bson.Raw) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if !bytes.Equal(left[index], right[index]) {
			return false
		}
	}
	return true
}

func TestMongoCandidateStageAndActivationCASLifecycle(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	a := releaseCASOptions("release-cas-a", "sha256:"+strings.Repeat("a", 64), now.UnixMilli())
	b := releaseCASOptions("release-cas-b", "sha256:"+strings.Repeat("b", 64), now.UnixMilli()+1)
	postA := releaseCASPost("content-cas-a", "posts/article/cas/a/1", now)
	postB := releaseCASPost("content-cas-b", "posts/article/cas/b/1", now)
	mediaA := releaseCASMedia("asset-shared", a.ManifestDigest)
	mediaB := releaseCASMedia("asset-shared", b.ManifestDigest)

	stagedA, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{postA}, mediaA, now, a)
	if err != nil {
		t.Fatalf("stage A: %v", err)
	}
	if stagedA.MediaAssetsProjected != 1 {
		t.Fatalf("stage A media closure mismatch: %+v", stagedA)
	}
	assertLiveReleaseCounts(t, db, 0, 0, 0)
	if active, err := ReadActiveImportedPostRelease(ctx, db, "alpha", a.SourceOwner); err != nil || active.Found {
		t.Fatalf("first stage changed active pointer active=%+v err=%v", active, err)
	}

	activatedA, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(a), ExpectedActiveRelease{
			Empty: true, SourceOwner: a.SourceOwner, Revision: 0,
		}, now.Add(time.Second),
	)
	if err != nil || activatedA.Active.ReleaseID != a.ReleaseID || activatedA.Active.Revision != 1 ||
		activatedA.PostsMaterialized != 1 || activatedA.MediaAssetsMaterialized != 1 ||
		activatedA.OutboxEventsAppended != 1 {
		t.Fatalf("first expected-empty activation result=%+v err=%v", activatedA, err)
	}
	assertLivePost(t, db, postA, a, "published", "active")
	assertLiveMedia(t, db, "asset-shared", a.ReleaseID, a.ManifestDigest)
	var pointerA struct {
		Kind   string `bson:"kind"`
		Status string `bson:"status"`
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{"kind": "active_pointer"}).Decode(&pointerA); err != nil || pointerA.Kind != "active_pointer" || pointerA.Status != "active" {
		t.Fatalf("active pointer shape=%+v err=%v", pointerA, err)
	}
	if activatedA.Active.ProjectionVersion <= stagedA.ProjectionVersion {
		t.Fatalf("activation version=%d must exceed candidate version=%d", activatedA.Active.ProjectionVersion, stagedA.ProjectionVersion)
	}
	assertLiveReleaseCounts(t, db, 1, 1, 1)
	postABytes := mustRawDocument(t, db.Collection("posts"), bson.M{"_id": RuntimePostID(postA.ContentID)})
	mediaABytes := mustRawDocument(t, db.Collection("media_assets"), bson.M{"_id": "asset-shared"})
	outboxABytes := rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})

	if _, err := StageImportedPostRelease(
		ctx, db, "alpha", []PostDoc{postB}, mediaB, now.Add(2*time.Second), b,
	); err != nil {
		t.Fatalf("stage B: %v", err)
	}
	assertLivePost(t, db, postA, a, "published", "active")
	if count, err := db.Collection("posts").CountDocuments(ctx, bson.M{"releaseId": b.ReleaseID}); err != nil || count != 0 {
		t.Fatalf("stage B leaked live Post count=%d err=%v", count, err)
	}
	if count, err := db.Collection("media_assets").CountDocuments(ctx, bson.M{"sourceReleaseId": b.ReleaseID}); err != nil || count != 0 {
		t.Fatalf("stage B leaked live media count=%d err=%v", count, err)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{"_id": bson.M{"$regex": b.ReleaseID}}); err != nil || count != 0 {
		t.Fatalf("stage B leaked live outbox count=%d err=%v", count, err)
	}
	active, err := ReadActiveImportedPostRelease(ctx, db, "alpha", a.SourceOwner)
	if err != nil || active.ReleaseID != a.ReleaseID || active.Revision != 1 {
		t.Fatalf("stage B moved pointer active=%+v err=%v", active, err)
	}
	if !bytes.Equal(postABytes, mustRawDocument(t, db.Collection("posts"), bson.M{"_id": RuntimePostID(postA.ContentID)})) ||
		!bytes.Equal(mediaABytes, mustRawDocument(t, db.Collection("media_assets"), bson.M{"_id": "asset-shared"})) ||
		!equalRawDocuments(outboxABytes, rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})) {
		t.Fatal("stage B changed live A bytes")
	}

	stale := ExpectedActiveRelease{
		SourceOwner: a.SourceOwner, ReleaseID: "stale", ManifestDigest: a.ManifestDigest, Revision: 1,
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(b), stale, now.Add(3*time.Second),
	); !IsReleaseActivationCASConflict(err) || !strings.Contains(err.Error(), ReleaseActivationCASConflictCode) {
		t.Fatalf("stale activation did not return typed CAS conflict: %v", err)
	}
	if !bytes.Equal(postABytes, mustRawDocument(t, db.Collection("posts"), bson.M{"_id": RuntimePostID(postA.ContentID)})) ||
		!equalRawDocuments(outboxABytes, rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})) {
		t.Fatal("stale activation changed live A bytes")
	}

	expectedA := ExpectedActiveRelease{
		SourceOwner: a.SourceOwner, ReleaseID: a.ReleaseID,
		ManifestDigest: a.ManifestDigest, Revision: 1,
	}
	activatedB, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(b), expectedA, now.Add(4*time.Second),
	)
	if err != nil || activatedB.Active.ReleaseID != b.ReleaseID || activatedB.Active.Revision != 2 ||
		activatedB.PostsRemoved != 1 || activatedB.OutboxEventsAppended != 2 {
		t.Fatalf("activate B result=%+v err=%v", activatedB, err)
	}
	assertLivePost(t, db, postB, b, "published", "active")
	assertLivePost(t, db, postA, a, "deleted", "tombstone")
	var deletion struct {
		Payload []byte `bson:"payloadJson"`
	}
	if err := db.Collection("content_outbox").FindOne(ctx, bson.M{
		"eventType": "PostDeleted", "aggregateId": RuntimePostID(postA.ContentID),
		"aggregateVersion": activatedB.Active.ProjectionVersion,
	}).Decode(&deletion); err != nil || !bytes.Contains(deletion.Payload, []byte(`"postId":"`+RuntimePostID(postA.ContentID)+`"`)) {
		t.Fatalf("B deletion event payload=%s err=%v", deletion.Payload, err)
	}
	outboxAfterB := rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})
	outboxCountAfterB := int64(len(outboxAfterB))
	postBAfterActivation := mustRawDocument(t, db.Collection("posts"), bson.M{"_id": RuntimePostID(postB.ContentID)})
	mediaBAfterActivation := mustRawDocument(t, db.Collection("media_assets"), bson.M{"_id": "asset-shared"})
	var activeReceipt struct {
		ExpectedEmpty          bool   `bson:"expectedEmpty"`
		ExpectedSourceOwner    string `bson:"expectedSourceOwner"`
		ExpectedReleaseID      string `bson:"expectedReleaseId"`
		ExpectedManifestDigest string `bson:"expectedManifestDigest"`
		ExpectedRevision       int64  `bson:"expectedRevision"`
	}
	if err := db.Collection("data_release_stage_receipts").FindOne(ctx, bson.M{
		"releaseId": b.ReleaseID, "stage": "active",
	}).Decode(&activeReceipt); err != nil || activeReceipt.ExpectedEmpty ||
		activeReceipt.ExpectedSourceOwner != expectedA.SourceOwner ||
		activeReceipt.ExpectedReleaseID != expectedA.ReleaseID ||
		activeReceipt.ExpectedManifestDigest != expectedA.ManifestDigest ||
		activeReceipt.ExpectedRevision != expectedA.Revision {
		t.Fatalf("active receipt predecessor=%+v err=%v", activeReceipt, err)
	}
	activeReceiptsBefore, _ := db.Collection("data_release_stage_receipts").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": a.SourceOwner, "releaseId": b.ReleaseID, "stage": "active",
	})
	replayed, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(b), expectedA, now.Add(5*time.Second),
	)
	activeReceiptsAfter, _ := db.Collection("data_release_stage_receipts").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": a.SourceOwner, "releaseId": b.ReleaseID, "stage": "active",
	})
	outboxCountAfterReplay, countErr := db.Collection("content_outbox").CountDocuments(ctx, bson.M{})
	if err != nil || countErr != nil || !replayed.Replayed || activeReceiptsAfter != activeReceiptsBefore ||
		outboxCountAfterReplay != outboxCountAfterB ||
		!equalRawDocuments(outboxAfterB, rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})) ||
		!bytes.Equal(postBAfterActivation, mustRawDocument(t, db.Collection("posts"), bson.M{"_id": RuntimePostID(postB.ContentID)})) ||
		!bytes.Equal(mediaBAfterActivation, mustRawDocument(t, db.Collection("media_assets"), bson.M{"_id": "asset-shared"})) {
		t.Fatalf("same exact activation replay changed live facts result=%+v err=%v", replayed, err)
	}

	expectedB := ExpectedActiveRelease{
		SourceOwner: b.SourceOwner, ReleaseID: b.ReleaseID,
		ManifestDigest: b.ManifestDigest, Revision: 2,
	}
	rolledBack, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(a), expectedB, now.Add(6*time.Second),
	)
	if err != nil || rolledBack.Active.ReleaseID != a.ReleaseID || rolledBack.Active.Revision != 3 ||
		rolledBack.Active.ProjectionVersion <= activatedB.Active.ProjectionVersion {
		t.Fatalf("rollback B->A result=%+v err=%v", rolledBack, err)
	}
	assertLivePost(t, db, postA, a, "published", "active")
	assertLivePost(t, db, postB, b, "deleted", "tombstone")
	assertLiveMedia(t, db, "asset-shared", a.ReleaseID, a.ManifestDigest)
	for eventType, postID := range map[string]string{
		"PostPublished": RuntimePostID(postA.ContentID),
		"PostDeleted":   RuntimePostID(postB.ContentID),
	} {
		if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{
			"eventType": eventType, "aggregateId": postID,
			"aggregateVersion": rolledBack.Active.ProjectionVersion,
		}); err != nil || count != 1 {
			t.Fatalf("rollback %s count=%d err=%v", eventType, count, err)
		}
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(b), expectedB, now.Add(7*time.Second),
	); !IsReleaseActivationCASConflict(err) {
		t.Fatalf("stale rollback expectation did not conflict: %v", err)
	}
	if count, err := db.Collection("data_release_state").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": a.SourceOwner, "kind": "active_pointer",
	}); err != nil || count != 1 {
		t.Fatalf("active pointer uniqueness count=%d err=%v", count, err)
	}
}

func TestMongoActivationMaterializeFailureRollsBackLiveAndPointer(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	a := releaseCASOptions("release-materialize-a", "sha256:"+strings.Repeat("c", 64), now.UnixMilli())
	b := releaseCASOptions("release-materialize-b", "sha256:"+strings.Repeat("d", 64), now.UnixMilli()+1)
	postA := releaseCASPost("content-materialize-a", "posts/article/materialize/a/1", now)
	postB := releaseCASPost("content-materialize-b", "posts/article/materialize/b/1", now)
	mediaA := releaseCASMedia("asset-materialize-a", a.ManifestDigest)
	mediaB := releaseCASMedia("asset-materialize-b", b.ManifestDigest)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{postA}, mediaA, now, a); err != nil {
		t.Fatal(err)
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(a), ExpectedActiveRelease{
			Empty: true, SourceOwner: a.SourceOwner, Revision: 0,
		}, now.Add(time.Second),
	); err != nil {
		t.Fatal(err)
	}
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{postB}, mediaB, now.Add(2*time.Second), b); err != nil {
		t.Fatal(err)
	}
	// Install a legal unique-index conflict after candidate verification. The
	// activation transaction reaches Post materialization first, then media
	// materialization fails; every prior live write must abort with the pointer.
	var candidateMedia struct {
		SourceSessionID string `bson:"sourceSessionId"`
	}
	if err := db.Collection("data_release_candidate_media_assets").FindOne(ctx, bson.M{
		"releaseId": b.ReleaseID, "assetId": "asset-materialize-b",
	}).Decode(&candidateMedia); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Collection("media_assets").InsertOne(ctx, bson.M{
		"_id": "conflicting-live-media", "sourceSessionId": candidateMedia.SourceSessionID,
		"processingStatus": "ready",
	}); err != nil {
		t.Fatal(err)
	}
	pointerBefore := mustRawDocument(t, db.Collection("data_release_state"), bson.M{"kind": "active_pointer"})
	postsBefore := rawDocumentClosure(t, db.Collection("posts"), bson.M{})
	outboxBefore := rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})
	mediaBefore := rawDocumentClosure(t, db.Collection("media_assets"), bson.M{})
	_, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(b), ExpectedActiveRelease{
			SourceOwner: a.SourceOwner, ReleaseID: a.ReleaseID,
			ManifestDigest: a.ManifestDigest, Revision: 1,
		}, now.Add(3*time.Second),
	)
	if err == nil || !strings.Contains(err.Error(), "ownership or digest conflicts") {
		t.Fatalf("activation materialize ownership conflict did not abort: %v", err)
	}
	if !bytes.Equal(pointerBefore, mustRawDocument(t, db.Collection("data_release_state"), bson.M{"kind": "active_pointer"})) ||
		!equalRawDocuments(postsBefore, rawDocumentClosure(t, db.Collection("posts"), bson.M{})) ||
		!equalRawDocuments(outboxBefore, rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})) ||
		!equalRawDocuments(mediaBefore, rawDocumentClosure(t, db.Collection("media_assets"), bson.M{})) {
		t.Fatal("failed activation materialization changed live closure or pointer")
	}
}

func TestMongoConcurrentCandidatesOnlyOneActivationCASWins(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	base := releaseCASOptions("release-concurrent-base", "sha256:"+strings.Repeat("e", 64), now.UnixMilli())
	left := releaseCASOptions("release-concurrent-left", "sha256:"+strings.Repeat("f", 64), now.UnixMilli()+1)
	right := releaseCASOptions("release-concurrent-right", "sha256:"+strings.Repeat("1", 64), now.UnixMilli()+2)
	for _, candidate := range []ImportOptions{base, left, right} {
		post := releaseCASPost("content-"+candidate.ReleaseID, "posts/article/concurrent/"+candidate.ReleaseID+"/1", now)
		if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now, candidate); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", ReleaseBindingFromImportOptions(base), ExpectedActiveRelease{
			Empty: true, SourceOwner: base.SourceOwner, Revision: 0,
		}, now,
	); err != nil {
		t.Fatal(err)
	}
	basePostsBefore := rawDocumentClosure(t, db.Collection("posts"), bson.M{})
	baseOutboxBefore := rawDocumentClosure(t, db.Collection("content_outbox"), bson.M{})
	expected := ExpectedActiveRelease{
		SourceOwner: base.SourceOwner, ReleaseID: base.ReleaseID,
		ManifestDigest: base.ManifestDigest, Revision: 1,
	}
	targets := []ImportedReleaseBinding{ReleaseBindingFromImportOptions(left), ReleaseBindingFromImportOptions(right)}
	type concurrentActivationResult struct {
		target ImportedReleaseBinding
		err    error
	}
	results := make(chan concurrentActivationResult, len(targets))
	var wg sync.WaitGroup
	for _, target := range targets {
		wg.Add(1)
		go func(target ImportedReleaseBinding) {
			defer wg.Done()
			_, err := ActivateImportedPostRelease(ctx, db, "alpha", target, expected, now.Add(time.Second))
			results <- concurrentActivationResult{target: target, err: err}
		}(target)
	}
	wg.Wait()
	close(results)
	successes, conflicts := 0, 0
	var loserBinding ImportedReleaseBinding
	for activation := range results {
		switch {
		case activation.err == nil:
			successes++
		case IsReleaseActivationCASConflict(activation.err):
			conflicts++
			loserBinding = activation.target
		default:
			t.Fatalf("unexpected concurrent activation error: %v", activation.err)
		}
	}
	if successes != 1 || conflicts != 1 {
		t.Fatalf("concurrent CAS successes=%d conflicts=%d", successes, conflicts)
	}
	active, err := ReadActiveImportedPostRelease(ctx, db, "alpha", base.SourceOwner)
	if err != nil || (active.ReleaseID != left.ReleaseID && active.ReleaseID != right.ReleaseID) {
		t.Fatalf("concurrent winner pointer=%+v err=%v", active, err)
	}
	winnerPost := releaseCASPost("content-"+active.ReleaseID, "posts/article/concurrent/"+active.ReleaseID+"/1", now)
	var winnerLive struct {
		ReleaseID       string `bson:"releaseId"`
		LifecycleStatus string `bson:"lifecycleStatus"`
	}
	if err := db.Collection("posts").FindOne(ctx, bson.M{"_id": RuntimePostID(winnerPost.ContentID)}).Decode(&winnerLive); err != nil ||
		winnerLive.ReleaseID != active.ReleaseID || winnerLive.LifecycleStatus != "active" {
		t.Fatalf("concurrent winner live Post=%+v err=%v", winnerLive, err)
	}
	if loserBinding.ReleaseID == "" || loserBinding.ReleaseID == active.ReleaseID {
		t.Fatalf("concurrent loser binding=%+v winner=%+v", loserBinding, active)
	}
	if count, err := db.Collection("posts").CountDocuments(ctx, bson.M{
		"releaseId": loserBinding.ReleaseID, "lifecycleStatus": "active",
	}); err != nil || count != 0 {
		t.Fatalf("concurrent loser left active Posts count=%d err=%v", count, err)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{
		"_id": bson.M{"$regex": loserBinding.ReleaseID},
	}); err != nil || count != 0 {
		t.Fatalf("concurrent loser left outbox count=%d err=%v", count, err)
	}
	if len(basePostsBefore) == 0 || len(baseOutboxBefore) == 0 {
		t.Fatal("concurrent baseline live closure was not established")
	}
	if count, err := db.Collection("data_release_state").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": base.SourceOwner, "kind": "active_pointer",
	}); err != nil || count != 1 {
		t.Fatalf("concurrent activation pointer count=%d err=%v", count, err)
	}
}

func TestMongoReleaseStateRejectsLegacyShapeAndEnforcesUniquePointer(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	state := db.Collection("data_release_state")
	if _, err := state.InsertOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data", "status": "active",
		"activeReleaseId": "legacy",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadActiveImportedPostRelease(ctx, db, "alpha", "qwq_data"); err == nil || !strings.Contains(err.Error(), "legacy") {
		t.Fatalf("legacy shape did not fail closed: %v", err)
	}
	if _, err := state.DeleteMany(ctx, bson.M{}); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	opts := releaseCASOptions("release-pointer-index", "sha256:"+strings.Repeat("2", 64), now.UnixMilli())
	if _, err := StageImportedPostRelease(ctx, db, "alpha", nil, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	first := bson.M{
		"kind": "active_pointer", "environment": "alpha", "sourceOwner": opts.SourceOwner,
		"activeReleaseId": opts.ReleaseID, "manifestDigest": opts.ManifestDigest, "revision": int64(1),
	}
	if _, err := state.InsertOne(ctx, first); err != nil {
		t.Fatal(err)
	}
	first["_id"] = "duplicate-pointer"
	if _, err := state.InsertOne(ctx, first); !mongo.IsDuplicateKeyError(err) {
		t.Fatalf("duplicate pointer was not rejected: %v", err)
	}
}

func TestMongoVerifiedCandidateReplayIsReadOnlyAndDetectsDrift(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	opts := releaseCASOptions("release-immutable", "sha256:"+strings.Repeat("7", 64), 1)
	post := releaseCASPost("content-immutable", "posts/article/immutable/1", now)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	filter := bson.M{"releaseId": opts.ReleaseID}
	before := rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), filter)
	stateBefore := mustRawDocument(t, db.Collection("data_release_state"), bson.M{"releaseId": opts.ReleaseID})
	receiptsBefore := rawDocumentClosure(t, db.Collection("data_release_stage_receipts"), filter)
	sequencesBefore := rawDocumentClosure(t, db.Collection("data_release_sequences"), bson.M{})
	replayed, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now.Add(time.Hour), opts)
	if err != nil || !replayed.Replayed {
		t.Fatalf("immutable replay=%+v err=%v", replayed, err)
	}
	if !equalRawDocuments(before, rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), filter)) ||
		!bytes.Equal(stateBefore, mustRawDocument(t, db.Collection("data_release_state"), bson.M{"releaseId": opts.ReleaseID})) ||
		!equalRawDocuments(receiptsBefore, rawDocumentClosure(t, db.Collection("data_release_stage_receipts"), filter)) ||
		!equalRawDocuments(sequencesBefore, rawDocumentClosure(t, db.Collection("data_release_sequences"), bson.M{})) {
		t.Fatal("verified candidate replay changed bytes")
	}
	if _, err := db.Collection("data_release_candidate_posts").UpdateOne(ctx, filter, bson.M{"$set": bson.M{"title": "drift"}}); err != nil {
		t.Fatal(err)
	}
	drifted := rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), filter)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now.Add(2*time.Hour), opts); err == nil || !strings.Contains(err.Error(), "digest drift") {
		t.Fatalf("candidate drift was accepted: %v", err)
	}
	if !equalRawDocuments(drifted, rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), filter)) {
		t.Fatal("failed candidate replay modified drifted bytes")
	}
}

func TestMongoCanonicalControlIndexesReenterAndRejectNamedDrift(t *testing.T) {
	indexName := "uq_data_release_state_active_pointer"
	canonicalKeys := bson.D{
		{Key: "environment", Value: 1},
		{Key: "sourceOwner", Value: 1},
		{Key: "kind", Value: 1},
	}
	canonicalOptions := func() *options.IndexOptionsBuilder {
		return options.Index().SetName(indexName).SetUnique(true).
			SetPartialFilterExpression(bson.D{{Key: "kind", Value: "active_pointer"}})
	}
	tests := []struct {
		name    string
		keys    bson.D
		options *options.IndexOptionsBuilder
	}{
		{
			name:    "key order drift",
			keys:    bson.D{{Key: "sourceOwner", Value: 1}, {Key: "environment", Value: 1}, {Key: "kind", Value: 1}},
			options: canonicalOptions(),
		},
		{
			name: "unique drift", keys: canonicalKeys,
			options: options.Index().SetName(indexName).
				SetPartialFilterExpression(bson.D{{Key: "kind", Value: "active_pointer"}}),
		},
		{
			name: "partial drift", keys: canonicalKeys,
			options: options.Index().SetName(indexName).SetUnique(true).
				SetPartialFilterExpression(bson.D{{Key: "kind", Value: "candidate"}}),
		},
	}

	t.Run("canonical reentry", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		opts := releaseCASOptions("release-index-reentry", "sha256:"+strings.Repeat("8", 64), 1)
		if _, err := StageImportedPostRelease(ctx, db, "alpha", nil, nil, time.Now().UTC(), opts); err != nil {
			t.Fatal(err)
		}
		if _, err := StageImportedPostRelease(ctx, db, "alpha", nil, nil, time.Now().UTC().Add(time.Second), opts); err != nil {
			t.Fatalf("canonical control indexes failed reentry: %v", err)
		}
	})

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			db, cleanup := testDB(t)
			defer cleanup()
			ctx := context.Background()
			state := db.Collection("data_release_state")
			if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{
				Keys: test.keys, Options: test.options,
			}); err != nil {
				t.Fatal(err)
			}
			opts := releaseCASOptions("release-index-drift", "sha256:"+strings.Repeat("9", 64), 1)
			_, err := StageImportedPostRelease(ctx, db, "alpha", nil, nil, time.Now().UTC(), opts)
			if err == nil || !strings.Contains(err.Error(), ReleaseLegacyStateMigrationRequiredCode) {
				t.Fatalf("named index drift did not return typed migration blocker: %v", err)
			}
		})
	}
}

func TestMongoActivationPreservesRichMediaDescriptorAndRejectsCollisions(t *testing.T) {
	t.Run("same Data asset preserves rich descriptor", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		now := time.Now().UTC().Truncate(time.Millisecond)
		opts := releaseCASOptions("release-rich-media", "sha256:"+strings.Repeat("3", 64), 1)
		post := releaseCASPost("content-rich-media", "posts/article/rich-media/1", now)
		media := releaseCASMedia("asset-rich", opts.ManifestDigest)
		if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, media, now, opts); err != nil {
			t.Fatal(err)
		}
		candidate := media["asset-rich"]
		if _, err := db.Collection("media_assets").InsertOne(ctx, bson.M{
			"_id": "asset-rich", "ownerId": opts.SourceOwner,
			"sourceSessionId": "data-release/asset-rich", "sha256": candidate.SHA256,
			"processingStatus": "ready", "captureMetadata": bson.M{"camera": "preserve-me"},
		}); err != nil {
			t.Fatal(err)
		}
		if _, err := ActivateImportedPostRelease(ctx, db, "alpha", ReleaseBindingFromImportOptions(opts), ExpectedActiveRelease{Empty: true, SourceOwner: opts.SourceOwner}, now); err != nil {
			t.Fatal(err)
		}
		var live bson.M
		if err := db.Collection("media_assets").FindOne(ctx, bson.M{"_id": "asset-rich"}).Decode(&live); err != nil {
			t.Fatal(err)
		}
		if _, ok := live["captureMetadata"]; !ok {
			t.Fatalf("activation cleared rich descriptor: %#v", live)
		}
	})

	for name, existing := range map[string]bson.M{
		"ugc owner collision": {"_id": "asset-collision", "ownerId": "ugc_persona", "sourceSessionId": "ugc/session", "sha256": "sha256:" + strings.Repeat("9", 64)},
		"different sha":       {"_id": "asset-collision", "ownerId": "qwq_data", "sourceSessionId": "data-release/asset-collision", "sha256": "sha256:" + strings.Repeat("4", 64)},
	} {
		t.Run(name, func(t *testing.T) {
			db, cleanup := testDB(t)
			defer cleanup()
			ctx := context.Background()
			now := time.Now().UTC().Truncate(time.Millisecond)
			opts := releaseCASOptions("release-media-collision", "sha256:"+strings.Repeat("5", 64), 1)
			post := releaseCASPost("content-media-collision", "posts/article/media-collision/1", now)
			if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, releaseCASMedia("asset-collision", opts.ManifestDigest), now, opts); err != nil {
				t.Fatal(err)
			}
			if _, err := db.Collection("media_assets").InsertOne(ctx, existing); err != nil {
				t.Fatal(err)
			}
			_, err := ActivateImportedPostRelease(ctx, db, "alpha", ReleaseBindingFromImportOptions(opts), ExpectedActiveRelease{Empty: true, SourceOwner: opts.SourceOwner}, now)
			if err == nil || !strings.Contains(err.Error(), "ownership or digest conflicts") {
				t.Fatalf("collision accepted: %v", err)
			}
			if active, readErr := ReadActiveImportedPostRelease(ctx, db, "alpha", opts.SourceOwner); readErr != nil || active.Found {
				t.Fatalf("collision changed pointer active=%+v err=%v", active, readErr)
			}
		})
	}
}

func TestMongoCandidateKeepsCanonicalPostFields(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	opts := releaseCASOptions("release-canonical-fields", "sha256:"+strings.Repeat("6", 64), 1)
	post := releaseCASPost("content-canonical-fields", "posts/article/canonical-fields/1", now)
	post.SourcePlatform = "wikipedia"
	post.SourceAttribution.AttributionText = "Canonical source"
	post.Creator = bson.M{"name": "creator-snapshot"}
	post.Template = "journal"
	post.ArticleAssetManifest = &ArticleAssetManifestDoc{
		Schema: ArticleAssetManifestSchema, MarkdownDialect: "qwq-rich-md",
		ArticleMarkdownDigest: "sha256:" + strings.Repeat("1", 64),
		DocumentSha256:        "sha256:" + strings.Repeat("2", 64),
		AssetManifestSha256:   "sha256:" + strings.Repeat("3", 64),
		DocumentVersionSha256: "sha256:" + strings.Repeat("4", 64),
	}
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	var candidate bson.M
	if err := db.Collection("data_release_candidate_posts").FindOne(ctx, bson.M{"releaseId": opts.ReleaseID}).Decode(&candidate); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"sourceAttribution", "creator", "template", "articleTemplate", "articleAssetManifest", "semanticMentions", "licenseProof"} {
		if _, ok := candidate[field]; !ok {
			t.Fatalf("candidate missing canonical field %q: %#v", field, candidate)
		}
	}
	if _, err := ActivateImportedPostRelease(ctx, db, "alpha", ReleaseBindingFromImportOptions(opts), ExpectedActiveRelease{Empty: true, SourceOwner: opts.SourceOwner}, now); err != nil {
		t.Fatal(err)
	}
	var live bson.M
	if err := db.Collection("posts").FindOne(ctx, bson.M{"_id": RuntimePostID(post.ContentID)}).Decode(&live); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"sourceAttribution", "creator", "template", "articleTemplate", "articleAssetManifest"} {
		if _, ok := live[field]; !ok {
			t.Fatalf("live Post missing canonical field %q: %#v", field, live)
		}
	}
}

func TestMongoConcurrentStageAllocatesDistinctVersions(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	left := releaseCASOptions("release-stage-left", "sha256:"+strings.Repeat("a", 64), 1)
	right := releaseCASOptions("release-stage-right", "sha256:"+strings.Repeat("b", 64), 1)
	type stageResult struct {
		result ImportedReleaseApplyResult
		err    error
	}
	results := make(chan stageResult, 2)
	for _, candidate := range []ImportOptions{left, right} {
		candidate := candidate
		go func() {
			result, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{releaseCASPost("content-"+candidate.ReleaseID, "posts/article/"+candidate.ReleaseID+"/1", now)}, nil, now, candidate)
			results <- stageResult{result: result, err: err}
		}()
	}
	versions := map[int64]struct{}{}
	for range 2 {
		staged := <-results
		if staged.err != nil {
			t.Fatal(staged.err)
		}
		versions[staged.result.ProjectionVersion] = struct{}{}
	}
	if len(versions) != 2 {
		t.Fatalf("concurrent stage projection versions collided: %#v", versions)
	}
}

func TestMongoVerifiedCandidateQueryIsExactAndReadOnly(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	opts := releaseCASOptions("release-query-candidate", "sha256:"+strings.Repeat("c", 64), 1)
	post := releaseCASPost("content-query-candidate", "posts/article/query-candidate/1", now)
	media := releaseCASMedia("asset-query-candidate", opts.ManifestDigest)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, media, now, opts); err != nil {
		t.Fatal(err)
	}
	stateBefore := rawDocumentClosure(t, db.Collection("data_release_state"), bson.M{})
	postsBefore := rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), bson.M{})
	factsBefore := rawDocumentClosure(t, db.Collection("data_release_candidate_outbox"), bson.M{})
	mediaBefore := rawDocumentClosure(t, db.Collection("data_release_candidate_media_assets"), bson.M{})
	candidate, err := ReadVerifiedImportedPostReleaseCandidate(
		ctx, db, "alpha", opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest,
	)
	if err != nil || !candidate.Found || candidate.ReleaseClass != opts.ReleaseClass ||
		candidate.ReleaseKind != opts.ReleaseKind || candidate.Mode != opts.Mode ||
		candidate.DeletePolicy != opts.DeletePolicy || candidate.ProjectionVersion <= 0 ||
		candidate.VerifiedAt.IsZero() || candidate.Counts.PostsExpected != 1 ||
		candidate.Counts.PostsProjected != 1 || candidate.Counts.OutboxExpected != 1 ||
		candidate.Counts.OutboxProjected != 1 || candidate.Counts.MediaExpected != 1 ||
		candidate.Counts.MediaProjected != 1 {
		t.Fatalf("candidate=%+v err=%v", candidate, err)
	}
	for label, digest := range map[string]string{
		"posts": candidate.ClosureDigests.Posts,
		"facts": candidate.ClosureDigests.Facts,
		"media": candidate.ClosureDigests.Media,
	} {
		if !strings.HasPrefix(digest, "sha256:") || len(digest) != len("sha256:")+64 {
			t.Fatalf("%s closure digest=%q", label, digest)
		}
	}
	if !equalRawDocuments(stateBefore, rawDocumentClosure(t, db.Collection("data_release_state"), bson.M{})) ||
		!equalRawDocuments(postsBefore, rawDocumentClosure(t, db.Collection("data_release_candidate_posts"), bson.M{})) ||
		!equalRawDocuments(factsBefore, rawDocumentClosure(t, db.Collection("data_release_candidate_outbox"), bson.M{})) ||
		!equalRawDocuments(mediaBefore, rawDocumentClosure(t, db.Collection("data_release_candidate_media_assets"), bson.M{})) {
		t.Fatal("verified candidate query mutated persisted closure")
	}

	missingDigest := "sha256:" + strings.Repeat("d", 64)
	missing, err := ReadVerifiedImportedPostReleaseCandidate(
		ctx, db, "alpha", opts.SourceOwner, opts.ReleaseID, missingDigest,
	)
	if err != nil || missing.Found || missing.ReleaseID != opts.ReleaseID || missing.ManifestDigest != missingDigest {
		t.Fatalf("exact candidate absence=%+v err=%v", missing, err)
	}

	directory := t.TempDir()
	missingReport := filepath.Join(directory, "missing-candidate.json")
	if err := RunReleaseControl(ctx, []string{
		"--operation", "query-candidate", "--mongo-uri", testMongoURI,
		"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
		"--release-id", opts.ReleaseID, "--manifest-digest", missingDigest,
		"--report", missingReport,
	}); err != nil {
		t.Fatalf("missing query-candidate CLI: %v", err)
	}
	missingBytes, err := os.ReadFile(missingReport)
	if err != nil {
		t.Fatal(err)
	}
	var missingJSON map[string]any
	if err := json.Unmarshal(missingBytes, &missingJSON); err != nil || missingJSON["status"] != "not_found" {
		t.Fatalf("missing candidate report=%s err=%v", missingBytes, err)
	}
	for _, field := range []string{"releaseClass", "projectionVersion", "verifiedAt", "closureDigests", "counts"} {
		if _, exists := missingJSON[field]; exists {
			t.Fatalf("missing candidate report exposed %q: %s", field, missingBytes)
		}
	}

	candidateReport := filepath.Join(directory, "candidate.json")
	if err := RunReleaseControl(ctx, []string{
		"--operation", "query-candidate", "--mongo-uri", testMongoURI,
		"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
		"--release-id", opts.ReleaseID, "--manifest-digest", opts.ManifestDigest,
		"--report", candidateReport,
	}); err != nil {
		t.Fatalf("query-candidate CLI: %v", err)
	}
	var candidateReceipt ContentReleaseCandidateReceipt
	candidateBytes, err := os.ReadFile(candidateReport)
	if err != nil || json.Unmarshal(candidateBytes, &candidateReceipt) != nil ||
		candidateReceipt.Status != "found" || candidateReceipt.Counts == nil ||
		candidateReceipt.Counts.PostsProjected != 1 {
		t.Fatalf("candidate CLI report=%s err=%v", candidateBytes, err)
	}

	if _, err := db.Collection("data_release_candidate_posts").UpdateOne(
		ctx, bson.M{"releaseId": opts.ReleaseID}, bson.M{"$set": bson.M{"title": "drift"}},
	); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadVerifiedImportedPostReleaseCandidate(
		ctx, db, "alpha", opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest,
	); err == nil || !strings.Contains(err.Error(), "digest drift") {
		t.Fatalf("drifted exact candidate was exposed: %v", err)
	}
}

func TestMongoVerifiedCandidateQueryRejectsMissingRequiredIndex(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	opts := releaseCASOptions("release-query-index", "sha256:"+strings.Repeat("1", 64), 1)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", nil, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	if err := db.Collection("data_release_candidate_outbox").Indexes().DropOne(
		ctx, "uq_data_release_candidate_outbox_event",
	); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadVerifiedImportedPostReleaseCandidate(
		ctx, db, "alpha", opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest,
	); err == nil || !strings.Contains(err.Error(), ReleaseLegacyStateMigrationRequiredCode) {
		t.Fatalf("missing required candidate index was accepted: %v", err)
	}
}

func TestMongoReleaseControlReportsActivationReplayAndConflict(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	opts := releaseCASOptions("release-control-report", "sha256:"+strings.Repeat("e", 64), 1)
	post := releaseCASPost("content-control-report", "posts/article/control-report/1", now)
	if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, nil, now, opts); err != nil {
		t.Fatal(err)
	}
	activationArgs := func(report string) []string {
		return []string{
			"--operation", "activate", "--mongo-uri", testMongoURI,
			"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
			"--release-id", opts.ReleaseID, "--manifest-digest", opts.ManifestDigest,
			"--expected-active-empty", "--report", report,
		}
	}
	directory := t.TempDir()
	emptyActiveReport := filepath.Join(directory, "empty-active.json")
	if err := RunReleaseControl(ctx, []string{
		"--operation", "query-active", "--mongo-uri", testMongoURI,
		"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
		"--report", emptyActiveReport,
	}); err != nil {
		t.Fatalf("empty query-active CLI: %v", err)
	}
	emptyActiveBytes, err := os.ReadFile(emptyActiveReport)
	if err != nil {
		t.Fatal(err)
	}
	var emptyActiveJSON map[string]any
	if err := json.Unmarshal(emptyActiveBytes, &emptyActiveJSON); err != nil || emptyActiveJSON["status"] != "not_found" {
		t.Fatalf("empty active report=%s err=%v", emptyActiveBytes, err)
	}
	if _, exists := emptyActiveJSON["releaseId"]; exists {
		t.Fatalf("empty active report exposed releaseId: %s", emptyActiveBytes)
	}

	activatedReport := filepath.Join(directory, "activated.json")
	if err := RunReleaseControl(ctx, activationArgs(activatedReport)); err != nil {
		t.Fatalf("activate CLI: %v", err)
	}
	var activated ContentReleaseActivationReceipt
	activatedBytes, err := os.ReadFile(activatedReport)
	if err != nil || json.Unmarshal(activatedBytes, &activated) != nil ||
		activated.Status != "activated" || activated.PreviousActive.Found ||
		activated.PreviousActive.SourceOwner != opts.SourceOwner || activated.PreviousActive.Revision != 0 ||
		activated.Active.ReleaseID != opts.ReleaseID || activated.Active.Revision != 1 ||
		activated.Active.ProjectionVersion <= 0 || activated.Counts.PostsMaterialized != 1 ||
		activated.Counts.OutboxEventsAppended != 1 {
		t.Fatalf("activation CLI report=%s err=%v", activatedBytes, err)
	}
	readback, err := ReadActiveImportedPostRelease(ctx, db, "alpha", opts.SourceOwner)
	if err != nil || readback.ReleaseID != activated.Active.ReleaseID ||
		readback.ManifestDigest != activated.Active.ManifestDigest ||
		readback.ProjectionVersion != activated.Active.ProjectionVersion ||
		readback.Revision != activated.Active.Revision ||
		!readback.ActivatedAt.Equal(activated.Active.ActivatedAt) {
		t.Fatalf("activation readback=%+v report=%+v err=%v", readback, activated.Active, err)
	}

	activeReport := filepath.Join(directory, "active.json")
	if err := RunReleaseControl(ctx, []string{
		"--operation", "query-active", "--mongo-uri", testMongoURI,
		"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
		"--report", activeReport,
	}); err != nil {
		t.Fatalf("query-active CLI: %v", err)
	}
	var activeReceipt ContentReleaseActiveReceipt
	activeBytes, err := os.ReadFile(activeReport)
	if err != nil || json.Unmarshal(activeBytes, &activeReceipt) != nil ||
		activeReceipt.Status != "found" || activeReceipt.ReleaseID != opts.ReleaseID ||
		activeReceipt.Revision != readback.Revision {
		t.Fatalf("active CLI report=%s err=%v", activeBytes, err)
	}

	replayReport := filepath.Join(directory, "replayed.json")
	if err := RunReleaseControl(ctx, activationArgs(replayReport)); err != nil {
		t.Fatalf("replay CLI: %v", err)
	}
	var replayed ContentReleaseActivationReceipt
	replayBytes, err := os.ReadFile(replayReport)
	if err != nil || json.Unmarshal(replayBytes, &replayed) != nil ||
		replayed.Status != "replayed" || replayed.PreviousActive.Found ||
		replayed.PreviousActive.Revision != 0 || replayed.Active.Revision != readback.Revision ||
		replayed.Active.ProjectionVersion != readback.ProjectionVersion ||
		replayed.Counts.PostsMaterialized != 0 || replayed.Counts.OutboxEventsAppended != 0 {
		t.Fatalf("replay CLI report=%s err=%v", replayBytes, err)
	}

	conflictReport := filepath.Join(directory, "conflict.json")
	staleArgs := []string{
		"--operation", "activate", "--mongo-uri", testMongoURI,
		"--posts-db", db.Name(), "--env", "alpha", "--source-owner", opts.SourceOwner,
		"--release-id", opts.ReleaseID, "--manifest-digest", opts.ManifestDigest,
		"--expected-active-release-id", "stale-release",
		"--expected-active-manifest-digest", "sha256:" + strings.Repeat("f", 64),
		"--expected-active-revision", "1", "--report", conflictReport,
	}
	if err := RunReleaseControl(ctx, staleArgs); !IsReleaseActivationCASConflict(err) {
		t.Fatalf("CLI stale activation error=%v", err)
	}
	if _, err := os.Lstat(conflictReport); !os.IsNotExist(err) {
		t.Fatalf("failed activation created success report: %v", err)
	}
}
