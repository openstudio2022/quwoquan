package releaseimport_test

import (
	"context"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"os"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/commandmeta"
	rt "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	tombstone "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/adapters/inbound/post"
	tombstore "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/infrastructure/persistence"
	app "quwoquan_service/services/content-service/internal/content/post/application"
	public "quwoquan_service/services/content-service/internal/content/post/application/public"
	persist "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	safety "quwoquan_service/services/content-service/internal/content/post/infrastructure/safety"
	testsupport "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	mediafence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediareferencefence"
	"reflect"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/discovery-content/spec.md
func TestCandidatePostSafetyIdentityIndexModel(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required; index shape is verified by Mongo readback")
	}
	// The external package cannot inspect the private index model. The following
	// behavioral test creates it through StageImportedPostRelease and verifies the
	// actual Mongo key, name, and non-unique option.
	TestDataSafetyBindingAndModerationMongo(t)
}

type testSourceAuthority struct{}

func (testSourceAuthority) VerifyRecovery(context.Context) error                       { return nil }
func (testSourceAuthority) VerifySource(context.Context, string, string, string) error { return nil }

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestDataSafetyBindingAndModerationMongo(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("data_safety"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, x := context.WithTimeout(context.Background(), 20*time.Second)
		defer x()
		_ = runtime.Close(c)
	}()
	db := runtime.Database
	manager, err := safety.New(db, "alpha", []byte(strings.Repeat("s", 32)), testSourceAuthority{})
	if err != nil {
		t.Fatal(err)
	}
	if err = manager.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	ctx = WithPostSafety(ctx, manager)
	now := time.Now().UTC().Truncate(time.Millisecond)
	stage := func(name string) ImportedReleaseBinding {
		opts := ImportOptions{ReleaseID: name, ManifestDigest: "sha256:" + strings.Repeat(string(name[len(name)-1]), 64), ReleaseKind: "content", ActivationMode: "stage-only", Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data"}
		p := PostDoc{PostRef: "posts/article/shared", ContentID: "shared", ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", PoolStatus: "active", ContentType: "article", Title: "安全测试", AuthorID: "data-author", AuthorDisplayName: "作者", ArticleMarkdown: "# 安全测试", Admission: ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "production", EvidenceRef: "audit/test", EvidenceDigest: "sha256:" + strings.Repeat("a", 64)}, CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now}
		if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{p}, map[string]ReleaseMediaAsset{}, now, opts); err != nil {
			t.Fatal("stage", err)
		}
		return ReleaseBindingFromImportOptions(opts)
	}
	a, b := stage("safety-a"), stage("safety-b")
	indexes, err := db.Collection("data_release_candidate_posts").Indexes().List(ctx)
	if err != nil {
		t.Fatal(err)
	}
	var indexDocs []bson.M
	if err = indexes.All(ctx, &indexDocs); err != nil {
		t.Fatal(err)
	}
	foundSafetyIndex := false
	for _, index := range indexDocs {
		if index["name"] != "idx_data_release_candidate_post_safety_identity" {
			continue
		}
		foundSafetyIndex = true
		if unique, present := index["unique"]; present && unique == true {
			t.Fatalf("safety identity index must be non-unique: %#v", index)
		}
		wantKey := bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "postId", Value: int32(1)}}
		if key, ok := index["key"].(bson.D); !ok || !reflect.DeepEqual(key, wantKey) {
			t.Fatalf("safety identity index key = %#v, want %#v", index["key"], wantKey)
		}
	}
	if !foundSafetyIndex {
		t.Fatalf("safety identity index missing: %#v", indexDocs)
	}
	safetyCursor, err := db.Collection("data_release_candidate_posts").Find(ctx, bson.M{"environment": "alpha", "sourceOwner": "qwq_data", "postId": RuntimePostID("shared")}, options.Find().SetHint("idx_data_release_candidate_post_safety_identity"))
	if err != nil {
		t.Fatal(err)
	}
	var retainedCandidates []bson.M
	if err = safetyCursor.All(ctx, &retainedCandidates); err != nil {
		t.Fatal(err)
	}
	if len(retainedCandidates) != 2 {
		t.Fatalf("safety identity query returned %d retained candidates, want 2", len(retainedCandidates))
	}
	binding := func(b ImportedReleaseBinding) rt.ReleaseCandidateBinding {
		return rt.ReleaseCandidateBinding{Environment: "alpha", SourceOwner: b.SourceOwner, ReleaseID: b.ReleaseID, ManifestDigest: b.ManifestDigest}
	}
	reader := NewPostCandidateReader(db, nil)
	for _, target := range []ImportedReleaseBinding{a, b} {
		if _, err := reader.ReadPostCandidate(ctx, binding(target)); err != nil {
			t.Fatal("valid candidate", err)
		}
	}
	if _, err := reader.ReadPostCandidate(context.Background(), binding(a)); err == nil {
		t.Fatal("missing authority accepted")
	}
	result, err := activateForTest(ctx, db, "alpha", a, ExpectedActiveRelease{Empty: true, SourceOwner: "qwq_data"}, now)
	if err != nil {
		t.Fatal("private CAS", err)
	}
	refs, _ := mediafence.New(db)
	store := persist.NewMongoPostStore(db.Collection("posts"), tombstone.NewStorePort(tombstore.NewMongoStore(db)), refs)
	if err = store.BindSafety(manager, "alpha"); err != nil {
		t.Fatal(err)
	}
	service := app.NewPostService(app.BindDataPorts(store), app.WithPublicationAdmission(testsupport.AllowPublicationRateGate{}, testsupport.FixedPublicationSafetyGate{}))
	ordinary := app.SubmitPostPublicationCommand{PublishIntentID: "safety-ordinary", LocalDraftID: "safety-draft", AuthorID: "ordinary-author", Content: postmodel.Post{ContentType: "micro", Body: "合法普通内容", Visibility: "public"}}
	publication, e := service.SubmitPostPublication(commandmeta.WithIdempotencyKey(ctx, "safety-ordinary"), ordinary)
	if e != nil {
		t.Fatal("ordinary with explicit test authority", e)
	}
	if _, e = service.DeletePost(commandmeta.WithIdempotencyKey(ctx, "safety-ordinary-delete"), publication.PostID, "ordinary-author"); e != nil {
		t.Fatal("ordinary delete", e)
	}
	if _, found, e := store.FindTombstone(ctx, publication.PostID); e != nil || !found {
		t.Fatal("410 fact missing", e)
	}
	id := RuntimePostID("shared")
	post, found, err := store.Load(ctx, id)
	if err != nil || !found {
		t.Fatal(err)
	}
	// 决定输入为现役Case绑定字段；不是平台Creator登录。HTTP operator授权由原Case入口拥有，本测试只到application。
	decision := app.ApplyPostModerationDecisionCommand{EventID: "decision-reject", CaseID: "case", CaseVersion: 1, PostID: id, PostVersion: post.Version, ContentDigest: post.ContentDigest, ReviewerID: "operator", Status: "rejected", DecidedAt: now.Add(time.Second)}
	if decision.ContentDigest == "" {
		if _, err = service.ApplyPostModerationDecision(ctx, decision); err == nil {
			t.Fatal("missing bound digest accepted")
		}
		t.Log("BLOCKER: imported Post lacks contentDigest for operator Case decision")
	}
	if _, err = service.UpdatePostSettings(commandmeta.WithIdempotencyKey(ctx, "wrong-owner"), id, "intruder", map[string]any{"visibility": "private"}); err == nil {
		t.Fatal("unauthorized owner accepted")
	}
	// 仅测试已真实归属的非平台作者，不构造平台Creator登录；调用现役Post owner权限。
	if _, err = service.UpdatePostSettings(commandmeta.WithIdempotencyKey(ctx, "restrict-owned-data"), id, "data-author", map[string]any{"visibility": "private"}); err != nil {
		t.Fatal("owner safety settings", err)
	}
	for _, target := range []ImportedReleaseBinding{a, b} {
		if _, err = reader.ReadPostCandidate(ctx, binding(target)); !errors.Is(err, public.ErrPostSafetyNotReady) {
			t.Fatal("unsafe source passed", target, err)
		}
	}
	if _, err = activateForTest(ctx, db, "alpha", b, ExpectedActiveRelease{SourceOwner: "qwq_data", ReleaseID: a.ReleaseID, ManifestDigest: a.ManifestDigest, Revision: result.Active.Revision}, now.Add(2*time.Second)); err == nil {
		t.Fatal("unsafe candidate CAS")
	}
	var actual bson.M
	if err = db.Collection("posts").FindOne(ctx, bson.M{"_id": id}).Decode(&actual); err != nil {
		t.Fatal(err)
	}
	if actual["sourceOwner"] != "qwq_data" || actual["releaseId"] != a.ReleaseID {
		t.Fatal("Data metadata lost")
	}
	var out struct {
		Payload []byte `bson:"payloadJson"`
		Version int64  `bson:"aggregateVersion"`
	}
	if err = db.Collection("content_outbox").FindOne(ctx, bson.M{"eventType": "PostSettingsUpdated"}).Decode(&out); err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	_ = json.Unmarshal(out.Payload, &payload)
	if payload["sourceOwner"] != "qwq_data" || payload["sourceVersion"] != float64(out.Version) || payload["safetyRevision"] != float64(2) {
		t.Fatal("atomic event binding", payload)
	}
}
