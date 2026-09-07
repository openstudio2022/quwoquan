//go:build mongo_integration

// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t1
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t2
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t3
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t4

package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func writeImportFixtureFile(t *testing.T, path, content string) {
	t.Helper()
	if strings.Contains(filepath.ToSlash(path), "/posts/") &&
		strings.HasSuffix(path, "manifest.json") &&
		strings.Contains(content, `"contentType"`) &&
		!strings.Contains(content, `"contentIdentity"`) {
		content = strings.Replace(content, "{", `{"contentIdentity":"work",`, 1)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func publishTreeFixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	writeImportFixtureFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/manifest.json"), `{
		"contentId":"qwq_data_article_seda_001",
		"version":1,
		"sourceType":"data",
		"variantPurpose":"original",
		"admission":{"processResult":"completed","qualityResult":"passed","usageScope":"research","evidenceRef":"evidence/content/qwq_data_article_seda_001.json","evidenceDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
		"status":"active",
		"authorId":"builtin_travel_blogger",
		"creatorProfileId":"qwq_creator_travel_blogger_001",
		"creatorArchetype":"travel_blogger",
		"creatorProfileVersion":"1.0.0",
		"creatorDisclosure":{"type":"platform_virtual_creator","displayText":"平台虚拟创作者","visible":true},
		"experienceClaimMode":"editorial_synthesis",
		"contentType":"article",
		"entityRefs":["地点/景区/色达"],
		"tagRefs":["Topic/旅行"],
		"publishTitle":"色达攻略",
		"publishAngle":"攻略",
		"publishSeq":1,
		"sourceTaskId":"execution:travel-article-scale",
		"createdAt":"2026-04-01T00:00:00Z",
		"updatedAt":"2026-04-01T00:00:00Z",
		"publishedAt":"2026-04-02T00:00:00Z"
	}`)
	writeImportFixtureFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/article.md"), "# 色达攻略\n")
	writeImportFixtureFile(t, filepath.Join(root, "entities/地点/景区/色达/_entity.json"), `{
		"label":"色达",
		"domain":"地点",
		"type":"景区",
		"tagRefs":["Entity/地点/景区"],
		"sourceTaskId":"execution:travel-homepage-scale"
	}`)
	return root
}

// 真实 mongo 写入路径覆盖。优先读取 QWQ_TEST_MONGO_URI / TEST_MONGO_URI；
// 未显式提供时由 TestMain 拉起 mongo:7-jammy testcontainer。本地若无 Docker，
// TestMain 会在整包层提前退出，避免单用例继续以 skip 形式“伪绿”。
func testDB(t *testing.T) (*mongo.Database, func()) {
	t.Helper()
	uri := strings.TrimSpace(testMongoURI)
	if uri == "" {
		t.Fatal("cmd/import tests require TestMain to provision mongo uri or exit before execution")
	}
	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(uri))
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	if err := client.Ping(ctx, nil); err != nil {
		t.Fatalf("ping: %v", err)
	}
	dbName := fmt.Sprintf("qwq_import_test_%d", time.Now().UnixNano())
	db := client.Database(dbName)
	return db, func() {
		_ = db.Drop(ctx)
		_ = client.Disconnect(ctx)
	}
}

func samplePosts() []PostDoc {
	return []PostDoc{
		{PostRef: "posts/article/体验/甲居藏寨体验/1", ContentID: "qwq_data_article_jiaju_001", ContentVersion: 1, ContentIdentity: "work", ContentType: "article", Title: "甲居藏寨体验", Angle: "体验", Seq: 1,
			EntityRefs: []string{"地点/景区/甲居藏寨"}, NormalizedEntityRefs: []string{"entity:景区:甲居藏寨"}, TagRefs: []string{"Topic/旅行"}, Template: "journal",
			IntersectionHints: []IntersectionHintDoc{
				{Dimension: "content", Source: "entityRef", ActionType: "view_object", ActionTargetID: "entity:景区:甲居藏寨"},
				{Dimension: "interest", Source: "tagRef", TagRefs: []string{"Topic/旅行"}, ActionType: "join", ActionTargetID: "Topic/旅行"},
			},
			AuthorID: "builtin_travel_blogger", CreatorProfileID: "qwq_creator_travel_blogger_001", CreatorArchetype: "travel_blogger",
			CreatorProfileVersion: "1.0.0", CreatorDisclosure: postmodel.PostCreatorDisclosure{Type: "platform_virtual_creator", DisplayText: "平台虚拟创作者", Visible: true},
			ExperienceClaimMode: "editorial_synthesis", AuthorQualitySignals: postmodel.PostAuthorQualitySignals{QualityScore: 0.85, FatigueScore: 0.2, RiskTier: "low"},
			ArticleMarkdown: "# 甲居藏寨体验\n正文\n", ArticleDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
			ArticleAssetManifest: &ArticleAssetManifestDoc{
				Schema:                ArticleAssetManifestSchema,
				MarkdownDialect:       "qwq-rich-md",
				ArticleMarkdownDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
				DocumentSha256:        "sha256:1111111111111111111111111111111111111111111111111111111111111111",
				AssetManifestSha256:   "sha256:2222222222222222222222222222222222222222222222222222222222222222",
				DocumentVersionSha256: "sha256:3333333333333333333333333333333333333333333333333333333333333333",
				Assets: []AssetManifestItem{
					{AssetID: "cover", ObjectKey: "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg", CDNURL: "https://img.example.com/media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg", Sha256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
				},
			},
			CreatedAt:   time.Date(2026, 5, 1, 8, 0, 0, 0, time.UTC),
			UpdatedAt:   time.Date(2026, 5, 3, 8, 0, 0, 0, time.UTC),
			PublishedAt: time.Date(2026, 5, 4, 8, 0, 0, 0, time.UTC)},
		{PostRef: "posts/article/攻略/色达攻略/1", ContentID: "qwq_data_article_seda_001", ContentVersion: 1, ContentIdentity: "work", ContentType: "article", Title: "色达攻略", Angle: "攻略", Seq: 1,
			EntityRefs: []string{"地点/景区/色达"}, NormalizedEntityRefs: []string{"entity:景区:色达"}, ArticleMarkdown: "# 色达攻略\n", ArticleDigest: "sha256:4444444444444444444444444444444444444444444444444444444444444444",
			CreatedAt:   time.Date(2026, 4, 1, 8, 0, 0, 0, time.UTC),
			UpdatedAt:   time.Date(2026, 4, 1, 8, 0, 0, 0, time.UTC),
			PublishedAt: time.Date(2026, 4, 2, 8, 0, 0, 0, time.UTC)},
	}
}

func sampleReleasePosts() []PostDoc {
	posts := samplePosts()
	contentIDs := []string{"qwq_data_article_jiaju_001", "qwq_data_article_seda_001"}
	for index := range posts {
		posts[index].ContentID = contentIDs[index]
		posts[index].ContentVersion = 1
	}
	return posts
}

func sampleEntities() []EntityDoc {
	return []EntityDoc{
		{EntityRef: "地点/景区/甲居藏寨", Domain: "地点", Etype: "景区", Name: "甲居藏寨", Label: "甲居藏寨",
			TagRefs: []string{"Entity/地点/景区"}, Page: "# 甲居藏寨\n", HasPage: true,
			AssetManifest: &EntityAssetManifestDoc{Assets: []AssetManifestItem{
				{AssetID: "甲居藏寨_homepage_detail", ObjectKey: "media/objects/sha256/bb/bb/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png", CDNURL: "https://img.example.com/media/objects/sha256/bb/bb/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png", Sha256: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
			}},
			ConditionProfile: map[string]any{"regions": []any{"高原", "山地"}, "seasons": []any{"夏", "秋"}, "altitudeMeters": 3500}},
		{EntityRef: "地点/景区/色达", Domain: "地点", Etype: "景区", Name: "色达", Label: "色达", HasPage: false},
	}
}

func TestRuntimePostIDIsRouteSafeAndStable(t *testing.T) {
	contentID := "qwq_data_article_jiaju_001"
	id := RuntimePostID(contentID)
	if id == "" {
		t.Fatal("RuntimePostID must not be empty")
	}
	if id != RuntimePostID(contentID) {
		t.Fatalf("RuntimePostID must be stable: %q", id)
	}
	if id == contentID || strings.Contains(id, "/") {
		t.Fatalf("RuntimePostID must be API path segment safe, got %q", id)
	}
}

func TestMongoUpsertPostsInsertAndFields(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	coll := db.Collection("posts")
	EnsureUnique(ctx, coll, "postRef", "idx_post_ref")

	n, err := UpsertPosts(ctx, coll, samplePosts(), time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("want 2 upserted, got %d", n)
	}
	count, _ := coll.CountDocuments(ctx, bson.M{})
	if count != 2 {
		t.Fatalf("want 2 docs, got %d", count)
	}
	var got struct {
		ID                   string                   `bson:"_id"`
		PostID               string                   `bson:"postId"`
		PostRef              string                   `bson:"postRef"`
		ContentIdentity      string                   `bson:"contentIdentity"`
		Title                string                   `bson:"title"`
		Angle                string                   `bson:"angle"`
		EntityRefs           []string                 `bson:"entityRefs"`
		TagRefs              []string                 `bson:"tagRefs"`
		IntersectionHints    []IntersectionHintDoc    `bson:"intersectionHints"`
		Body                 string                   `bson:"body"`
		Summary              string                   `bson:"summary"`
		ArticleMarkdown      string                   `bson:"articleMarkdown"`
		ArticleTemplate      string                   `bson:"articleTemplate"`
		MarkdownDigest       string                   `bson:"articleMarkdownDigest"`
		ArticleAssetManifest *ArticleAssetManifestDoc `bson:"articleAssetManifest"`
		AuthorID             string                   `bson:"authorId"`
		CreatorProfileID     string                   `bson:"creatorProfileId"`
		CreatorArchetype     string                   `bson:"creatorArchetype"`
		CreatorDisclosure    map[string]any           `bson:"creatorDisclosure"`
		ExperienceClaimMode  string                   `bson:"experienceClaimMode"`
		ModerationStatus     string                   `bson:"moderationStatus"`
		CreatedAt            time.Time                `bson:"createdAt"`
		UpdatedAt            time.Time                `bson:"updatedAt"`
		PublishedAt          time.Time                `bson:"publishedAt"`
	}
	if err := coll.FindOne(ctx, bson.M{"postRef": "posts/article/体验/甲居藏寨体验/1"}).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if got.Title != "甲居藏寨体验" || got.Angle != "体验" || got.ArticleMarkdown == "" {
		t.Fatalf("fields wrong: %+v", got)
	}
	if got.ID != RuntimePostID("qwq_data_article_jiaju_001") || got.PostID != got.ID || got.PostRef != "posts/article/体验/甲居藏寨体验/1" {
		t.Fatalf("post identity must use route-safe runtime id and preserve postRef, got %+v", got)
	}
	if got.ContentIdentity != "work" {
		t.Fatalf("canonical imported post must persist contentIdentity=work, got %+v", got)
	}
	if strings.Contains(got.ID, "/") {
		t.Fatalf("runtime post id must be path-segment safe, got %q", got.ID)
	}
	if len(got.EntityRefs) != 1 || got.EntityRefs[0] != "entity:景区:甲居藏寨" {
		t.Fatalf("entityRefs wrong: %+v", got.EntityRefs)
	}
	if len(got.TagRefs) != 1 || got.TagRefs[0] != "Topic/旅行" {
		t.Fatalf("tagRefs wrong: %+v", got.TagRefs)
	}
	if len(got.IntersectionHints) != 2 || got.IntersectionHints[0].ActionTargetID != "entity:景区:甲居藏寨" {
		t.Fatalf("intersectionHints not persisted: %+v", got.IntersectionHints)
	}
	if got.Body != got.ArticleMarkdown || got.Body == "" {
		t.Fatalf("body must mirror articleMarkdown for online read/search: %+v", got)
	}
	if got.Summary != "正文" || got.MarkdownDigest != "sha256:1111111111111111111111111111111111111111111111111111111111111111" {
		t.Fatalf("summary must be user-visible prose while digest remains canonical: %+v", got)
	}
	if got.ArticleTemplate != "journal" {
		t.Fatalf("articleTemplate must mirror template: %+v", got)
	}
	if got.AuthorID != "builtin_travel_blogger" || got.CreatorProfileID != "qwq_creator_travel_blogger_001" || got.CreatorArchetype != "travel_blogger" {
		t.Fatalf("creator projection not persisted: %+v", got)
	}
	if got.CreatorDisclosure["visible"] != true || got.ExperienceClaimMode != "editorial_synthesis" {
		t.Fatalf("creator boundary not persisted: %+v", got)
	}
	if got.ModerationStatus != "approved" {
		t.Fatalf("canonical release must project approved moderation status: %+v", got)
	}
	if got.ArticleAssetManifest == nil {
		t.Fatalf("articleAssetManifest not persisted: %+v", got)
	}
	if got.ArticleAssetManifest.DocumentSha256 == "" {
		t.Fatalf("documentSha256 not persisted: %+v", got.ArticleAssetManifest)
	}
	if got.CreatedAt.IsZero() || got.UpdatedAt.IsZero() {
		t.Fatalf("createdAt/updatedAt must be set: %+v", got)
	}
	if !got.CreatedAt.Equal(time.Date(2026, 5, 1, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("createdAt must come from manifest fact: %+v", got.CreatedAt)
	}
	if !got.UpdatedAt.Equal(time.Date(2026, 5, 3, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("updatedAt must come from manifest fact: %+v", got.UpdatedAt)
	}
	if !got.PublishedAt.Equal(time.Date(2026, 5, 4, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("publishedAt must come from manifest fact: %+v", got.PublishedAt)
	}
}

func TestMongoReleaseStatePersistsImmutableManifestBinding(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	const manifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	counts := bson.M{
		"postsUpserted": int64(3), "entitiesUpserted": int64(1), "feedUpserted": int64(3),
	}
	opts := ImportOptions{
		ReleaseID: "rel_pilot_002", ManifestDigest: manifestDigest,
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ExpectedRevision: 0, ProjectionVersion: now.UnixMilli(),
	}
	if err := EnsureImportedReleaseIndexes(ctx, db); err != nil {
		t.Fatalf("EnsureImportedReleaseIndexes: %v", err)
	}
	if err := UpsertReleaseState(ctx, db.Collection("data_release_state"), "alpha", opts, now, counts); err != nil {
		t.Fatalf("UpsertReleaseState: %v", err)
	}
	var state struct {
		ManifestDigest string `bson:"manifestDigest"`
		Readback       struct {
			Status string `bson:"status"`
			Counts struct {
				Posts          int64 `bson:"posts"`
				DiscoveryPosts int64 `bson:"discoveryPosts"`
			} `bson:"counts"`
		} `bson:"readback"`
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "activeReleaseId": "rel_pilot_002",
	}).Decode(&state); err != nil {
		t.Fatalf("read data release state: %v", err)
	}
	if state.ManifestDigest != manifestDigest || state.Readback.Status != "content_imported" ||
		state.Readback.Counts.Posts != 3 || state.Readback.Counts.DiscoveryPosts != 3 {
		t.Fatalf("immutable release state mismatch: %+v", state)
	}
}

func TestMongoContentOwnedReleaseApplyCommitsPostsOutboxAndActivePointerAtomically(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()
	for index := range posts {
		if strings.TrimSpace(posts[index].AuthorID) == "" {
			posts[index].AuthorID = "builtin_travel_blogger"
		}
	}
	first := ImportOptions{
		ReleaseID:      "rel_atomic_001",
		ManifestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	result, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, first)
	if err != nil {
		t.Fatalf("ApplyImportedPostRelease: %v", err)
	}
	if result.PostsUpserted != 2 || result.PostsRemoved != 0 ||
		result.OutboxEventsReady != 2 || result.OutboxEventsAppended != 2 || result.Replayed {
		t.Fatalf("unexpected first apply result: %+v", result)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); err != nil || count != 2 {
		t.Fatalf("durable Post outbox count=%d err=%v, want 2", count, err)
	}
	var state struct {
		ReleaseID       string    `bson:"releaseId"`
		ActiveReleaseID string    `bson:"activeReleaseId"`
		ManifestDigest  string    `bson:"manifestDigest"`
		Revision        int64     `bson:"revision"`
		SourceVersion   int64     `bson:"sourceVersion"`
		ActivatedAt     time.Time `bson:"activatedAt"`
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	}).Decode(&state); err != nil {
		t.Fatalf("read active release state: %v", err)
	}
	if state.ReleaseID != first.ReleaseID || state.ActiveReleaseID != first.ReleaseID ||
		state.ManifestDigest != first.ManifestDigest || state.Revision != result.Revision ||
		state.SourceVersion != result.ProjectionVersion || state.ActivatedAt.IsZero() {
		t.Fatalf("active release binding mismatch: %+v", state)
	}
	stageCursor, err := db.Collection("data_release_stage_receipts").Find(
		ctx,
		bson.M{
			"environment": "alpha",
			"releaseId":   first.ReleaseID,
			"status":      "passed",
		},
	)
	if err != nil {
		t.Fatalf("read committed release stage receipts: %v", err)
	}
	defer stageCursor.Close(ctx)
	var stageReceipts []struct {
		Stage             string `bson:"stage"`
		AttemptedCount    int    `bson:"attemptedCount"`
		SuccessCount      int    `bson:"successCount"`
		FirstTypedBlocker string `bson:"firstTypedBlocker"`
	}
	if err := stageCursor.All(ctx, &stageReceipts); err != nil {
		t.Fatalf("decode committed release stage receipts: %v", err)
	}
	stages := map[string]bool{}
	for _, receipt := range stageReceipts {
		stages[receipt.Stage] = true
		if receipt.AttemptedCount != len(posts) ||
			receipt.SuccessCount != len(posts) || receipt.FirstTypedBlocker != "" {
			t.Fatalf("stage receipt is not a successful bounded fact: %+v", receipt)
		}
	}
	for _, stage := range []string{"prepared", "imported", "projected", "verified", "active"} {
		if !stages[stage] {
			t.Fatalf("missing committed release stage receipt %q: %+v", stage, stageReceipts)
		}
	}

	replay, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now.Add(time.Minute), first)
	if err != nil {
		t.Fatalf("replay imported release: %v", err)
	}
	if !replay.Replayed || replay.ProjectionVersion != result.ProjectionVersion ||
		replay.OutboxEventsReady != 2 || replay.OutboxEventsAppended != 0 {
		t.Fatalf("same release replay is not idempotent: %+v", replay)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); err != nil || count != 2 {
		t.Fatalf("replay changed durable Post outbox count=%d err=%v", count, err)
	}

	second := ImportOptions{
		ReleaseID:      "rel_atomic_002",
		ManifestDigest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: result.ProjectionVersion + 1, ExpectedRevision: result.Revision,
	}
	switched, err := ApplyImportedPostRelease(ctx, db, "alpha", posts[:1], now.Add(time.Minute), second)
	if err != nil {
		t.Fatalf("switch imported release: %v", err)
	}
	if switched.Replayed || switched.ProjectionVersion <= result.ProjectionVersion ||
		switched.PostsRemoved != 1 || switched.OutboxEventsReady != 2 ||
		switched.OutboxEventsAppended != 2 {
		t.Fatalf("release switch did not advance lifecycle: %+v", switched)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); err != nil || count != 4 {
		t.Fatalf("release switch durable Post outbox count=%d err=%v, want 4", count, err)
	}
}

func TestMongoSameReleaseReplayValidatesAuthoritativeClosureReadOnly(t *testing.T) {
	testCases := []struct {
		name      string
		corrupt   func(context.Context, *mongo.Database, []PostDoc, ImportedReleaseApplyResult) error
		wantError bool
		wantFact  string
	}{
		{
			name: "complete closure",
		},
		{
			name: "missing post",
			corrupt: func(ctx context.Context, db *mongo.Database, posts []PostDoc, _ ImportedReleaseApplyResult) error {
				_, err := db.Collection("posts").DeleteOne(ctx, bson.M{"_id": RuntimePostID(posts[0].ContentID)})
				return err
			},
			wantError: true,
			wantFact:  "post_source_hash:" + RuntimePostID(sampleReleasePosts()[0].ContentID),
		},
		{
			name: "missing outbox",
			corrupt: func(ctx context.Context, db *mongo.Database, posts []PostDoc, result ImportedReleaseApplyResult) error {
				eventID := fmt.Sprintf(
					"data-release:%d:rel_replay_closure:%s:PostPublished",
					result.ProjectionVersion,
					RuntimePostID(posts[0].ContentID),
				)
				_, err := db.Collection("content_outbox").DeleteOne(ctx, bson.M{"_id": eventID})
				return err
			},
			wantError: true,
			wantFact:  "lifecycle_outbox",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			db, cleanup := testDB(t)
			defer cleanup()
			ctx := context.Background()
			now := time.Now().UTC().Truncate(time.Millisecond)
			posts := sampleReleasePosts()
			opts := ImportOptions{
				ReleaseID: "rel_replay_closure", ManifestDigest: "sha256:" + strings.Repeat("c", 64),
				Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
				ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
			}
			activated, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, opts)
			if err != nil {
				t.Fatalf("activate release: %v", err)
			}
			var stateBefore struct {
				Revision int64 `bson:"revision"`
			}
			if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
				"environment": "alpha", "sourceOwner": opts.SourceOwner,
			}).Decode(&stateBefore); err != nil {
				t.Fatal(err)
			}
			receiptsBefore, err := db.Collection("data_release_stage_receipts").CountDocuments(ctx, bson.M{})
			if err != nil {
				t.Fatal(err)
			}
			if testCase.corrupt != nil {
				if err := testCase.corrupt(ctx, db, posts, activated); err != nil {
					t.Fatal(err)
				}
			}
			replay, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now.Add(time.Minute), opts)
			if testCase.wantError {
				var consistency *ImportedReleaseConsistencyError
				if !errors.As(err, &consistency) || consistency.Fact != testCase.wantFact {
					t.Fatalf("replay error=%v consistency=%+v", err, consistency)
				}
			} else if err != nil || !replay.Replayed || replay.Revision != activated.Revision {
				t.Fatalf("complete replay result=%+v err=%v", replay, err)
			}
			var stateAfter struct {
				Revision int64 `bson:"revision"`
			}
			if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
				"environment": "alpha", "sourceOwner": opts.SourceOwner,
			}).Decode(&stateAfter); err != nil {
				t.Fatal(err)
			}
			receiptsAfter, err := db.Collection("data_release_stage_receipts").CountDocuments(ctx, bson.M{})
			if err != nil {
				t.Fatal(err)
			}
			if stateAfter.Revision != stateBefore.Revision || receiptsAfter != receiptsBefore {
				t.Fatalf("ordinary replay mutated control state: revision %d->%d receipts %d->%d", stateBefore.Revision, stateAfter.Revision, receiptsBefore, receiptsAfter)
			}
		})
	}
}

func TestMongoSameReleaseReplayUsesAuthoritativeRevision(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()[:1]
	initial := ImportOptions{
		ReleaseID: "rel_replay_authority", ManifestDigest: "sha256:" + strings.Repeat("d", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	activated, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, initial)
	if err != nil {
		t.Fatalf("activate release: %v", err)
	}
	replay := initial
	replay.ExpectedRevision = 0
	got, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now.Add(time.Second), replay)
	if err != nil {
		t.Fatalf("replay release: %v", err)
	}
	if !got.Replayed || got.Revision != activated.Revision || got.ProjectionVersion != activated.ProjectionVersion {
		t.Fatalf("replay result does not expose authoritative state: got=%+v active=%+v", got, activated)
	}
}

func TestMongoReleaseActivationCASHasOneWinnerAndStaleLoserCannotOverwrite(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()[:1]
	if strings.TrimSpace(posts[0].AuthorID) == "" {
		posts[0].AuthorID = "builtin_travel_blogger"
	}
	first := ImportOptions{
		ReleaseID: "rel_cas_base", ManifestDigest: "sha256:" + strings.Repeat("1", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	base, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, first)
	if err != nil {
		t.Fatalf("seed active release: %v", err)
	}
	if base.Revision != 1 {
		t.Fatalf("base revision=%d want=1", base.Revision)
	}

	candidates := []ImportOptions{
		{
			ReleaseID: "rel_cas_left", ManifestDigest: "sha256:" + strings.Repeat("2", 64),
			Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
			ProjectionVersion: base.ProjectionVersion + 1, ExpectedRevision: base.Revision,
		},
		{
			ReleaseID: "rel_cas_right", ManifestDigest: "sha256:" + strings.Repeat("3", 64),
			Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
			ProjectionVersion: base.ProjectionVersion + 2, ExpectedRevision: base.Revision,
		},
	}
	type outcome struct {
		index  int
		result ImportedReleaseApplyResult
		err    error
	}
	start := make(chan struct{})
	outcomes := make(chan outcome, len(candidates))
	for index := range candidates {
		index := index
		go func() {
			<-start
			result, applyErr := ApplyImportedPostRelease(
				ctx, db, "alpha", posts, now.Add(time.Duration(index+1)*time.Second), candidates[index],
			)
			outcomes <- outcome{index: index, result: result, err: applyErr}
		}()
	}
	close(start)
	var winner outcome
	var loser outcome
	successes := 0
	conflicts := 0
	for range candidates {
		got := <-outcomes
		if got.err == nil {
			successes++
			winner = got
			continue
		}
		var conflict *DataReleaseRevisionConflict
		if !errors.As(got.err, &conflict) || !errors.Is(got.err, postgenerated.ErrVersionConflict) {
			t.Fatalf("loser error is not typed revision conflict: %v", got.err)
		}
		conflicts++
		loser = got
	}
	if successes != 1 || conflicts != 1 {
		t.Fatalf("CAS race successes=%d conflicts=%d", successes, conflicts)
	}
	if winner.result.Revision != base.Revision+1 {
		t.Fatalf("winner revision=%d want=%d", winner.result.Revision, base.Revision+1)
	}
	state := struct {
		ActiveReleaseID string `bson:"activeReleaseId"`
		ManifestDigest  string `bson:"manifestDigest"`
		Revision        int64  `bson:"revision"`
		SourceVersion   int64  `bson:"sourceVersion"`
	}{}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	}).Decode(&state); err != nil {
		t.Fatalf("read CAS winner: %v", err)
	}
	if state.ActiveReleaseID != candidates[winner.index].ReleaseID ||
		state.ManifestDigest != candidates[winner.index].ManifestDigest ||
		state.Revision != winner.result.Revision ||
		state.SourceVersion != winner.result.ProjectionVersion {
		t.Fatalf("active pointer is not exact winner: %+v winner=%+v", state, winner)
	}
	count, err := db.Collection("data_release_state").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	})
	if err != nil || count != 1 {
		t.Fatalf("active pointer authority count=%d err=%v", count, err)
	}

	replay, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts, now.Add(10*time.Second), candidates[winner.index],
	)
	if err != nil || !replay.Replayed || replay.Revision != winner.result.Revision ||
		replay.OutboxEventsAppended != 0 || replay.PostsRemoved != 0 {
		t.Fatalf("winner replay result=%+v err=%v", replay, err)
	}
	if _, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts, now.Add(11*time.Second), candidates[loser.index],
	); err == nil {
		t.Fatal("stale loser retry unexpectedly overwrote winner")
	} else {
		var conflict *DataReleaseRevisionConflict
		if !errors.As(err, &conflict) {
			t.Fatalf("stale loser retry error is not typed conflict: %v", err)
		}
	}
}

func TestMongoConcurrentFirstActivationHasOneAuthoritativeWinner(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	if err := EnsureImportedReleaseIndexes(ctx, db); err != nil {
		t.Fatalf("ensure release indexes: %v", err)
	}
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()[:1]
	if strings.TrimSpace(posts[0].AuthorID) == "" {
		posts[0].AuthorID = "builtin_travel_blogger"
	}
	const contenders = 8
	start := make(chan struct{})
	errs := make(chan error, contenders)
	for index := 0; index < contenders; index++ {
		index := index
		go func() {
			<-start
			_, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now.Add(time.Duration(index)*time.Millisecond), ImportOptions{
				ReleaseID:      fmt.Sprintf("rel_first_%02d", index),
				ManifestDigest: fmt.Sprintf("sha256:%064x", index+1),
				Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
				ProjectionVersion: now.UnixMilli() + int64(index+1), ExpectedRevision: 0,
			})
			errs <- err
		}()
	}
	close(start)
	successes := 0
	conflicts := 0
	for index := 0; index < contenders; index++ {
		err := <-errs
		if err == nil {
			successes++
			continue
		}
		var conflict *DataReleaseRevisionConflict
		if !errors.As(err, &conflict) {
			t.Fatalf("first activation loser error is not typed conflict: %v", err)
		}
		conflicts++
	}
	if successes != 1 || conflicts != contenders-1 {
		t.Fatalf("first activation successes=%d conflicts=%d", successes, conflicts)
	}
	count, err := db.Collection("data_release_state").CountDocuments(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	})
	if err != nil || count != 1 {
		t.Fatalf("first activation authoritative count=%d err=%v", count, err)
	}
	var state struct {
		Revision      int64 `bson:"revision"`
		SourceVersion int64 `bson:"sourceVersion"`
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	}).Decode(&state); err != nil {
		t.Fatalf("read first winner: %v", err)
	}
	if state.Revision != 1 || state.SourceVersion <= 0 {
		t.Fatalf("first winner revision/sourceVersion invalid: %+v", state)
	}
}

func TestMongoEnsureReleaseIndexesFailsClosedOnDuplicatesAndMissingRevision(t *testing.T) {
	t.Run("duplicates", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		state := db.Collection("data_release_state")
		for index := 0; index < 2; index++ {
			if _, err := state.InsertOne(ctx, bson.M{
				"environment": "alpha", "sourceOwner": "qwq_data",
				"revision": int64(index + 1), "sourceVersion": int64(index + 10),
			}); err != nil {
				t.Fatal(err)
			}
		}
		err := EnsureImportedReleaseIndexes(ctx, db)
		if err == nil || !strings.Contains(err.Error(), "ACTIVE_POINTER_DUPLICATE") {
			t.Fatalf("duplicate release state did not fail closed: %v", err)
		}
	})
	t.Run("conflicting named index", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		state := db.Collection("data_release_state")
		if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "environment", Value: 1}},
			Options: options.Index().SetName("uq_data_release_state_environment_source_owner"),
		}); err != nil {
			t.Fatal(err)
		}
		err := EnsureImportedReleaseIndexes(ctx, db)
		if err == nil || !strings.Contains(err.Error(), "ACTIVE_POINTER_INDEX_DRIFT") {
			t.Fatalf("conflicting named index did not fail closed: %v", err)
		}
	})
	t.Run("missing revision", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		if _, err := db.Collection("data_release_state").InsertOne(ctx, bson.M{
			"environment": "alpha", "sourceOwner": "qwq_data",
		}); err != nil {
			t.Fatal(err)
		}
		err := EnsureImportedReleaseIndexes(ctx, db)
		if err == nil || !strings.Contains(err.Error(), "ACTIVE_POINTER_MIGRATION_REQUIRED") {
			t.Fatalf("missing revision release state did not fail closed: %v", err)
		}
	})
}

func TestMongoBackfillUnversionedReleaseStateIsCreateOnceAndUnblocksIndexes(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	activatedAt := time.Date(2026, 7, 1, 8, 30, 0, 0, time.UTC)
	if _, err := db.Collection("data_release_state").InsertOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data", "status": "active",
		"releaseId": "release-legacy", "activeReleaseId": "release-legacy",
		"manifestDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"activatedAt":    activatedAt,
	}); err != nil {
		t.Fatal(err)
	}
	result, err := BackfillUnversionedReleaseState(
		ctx, db, "alpha", "qwq_data", activatedAt.Add(time.Hour),
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.Revision != 1 || result.SourceVersion != activatedAt.UnixMilli() || result.Replayed {
		t.Fatalf("unexpected first backfill result: %+v", result)
	}
	replay, err := BackfillUnversionedReleaseState(
		ctx, db, "alpha", "qwq_data", activatedAt.Add(2*time.Hour),
	)
	if err != nil {
		t.Fatal(err)
	}
	if !replay.Replayed || replay != (ReleaseStateBackfillResult{
		Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-legacy",
		Revision: 1, SourceVersion: activatedAt.UnixMilli(), Replayed: true,
	}) {
		t.Fatalf("unexpected replay result: %+v", replay)
	}
	if err := EnsureImportedReleaseIndexes(ctx, db); err != nil {
		t.Fatalf("governed backfill did not unblock indexes: %v", err)
	}
	count, err := db.Collection("data_release_state_migration_receipts").CountDocuments(ctx, bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("migration receipt count=%d err=%v", count, err)
	}
}

func TestMongoBackfillUnversionedReleaseStateRejectsAmbiguousOrPartialState(t *testing.T) {
	t.Run("no pointer", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		_, err := BackfillUnversionedReleaseState(context.Background(), db, "alpha", "qwq_data", time.Now())
		if err == nil || !strings.Contains(err.Error(), "BACKFILL_CARDINALITY") {
			t.Fatalf("missing pointer must fail closed: %v", err)
		}
	})
	t.Run("partial version", func(t *testing.T) {
		db, cleanup := testDB(t)
		defer cleanup()
		ctx := context.Background()
		if _, err := db.Collection("data_release_state").InsertOne(ctx, bson.M{
			"environment": "alpha", "sourceOwner": "qwq_data", "status": "active",
			"releaseId": "release-partial", "activeReleaseId": "release-partial",
			"manifestDigest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			"activatedAt":    time.Now().UTC(), "revision": int64(1),
		}); err != nil {
			t.Fatal(err)
		}
		_, err := BackfillUnversionedReleaseState(ctx, db, "alpha", "qwq_data", time.Now())
		if err == nil || !strings.Contains(err.Error(), "BACKFILL_NOT_UNVERSIONED") {
			t.Fatalf("partial pointer must fail closed: %v", err)
		}
	})
}

func TestMongoActiveReleaseRepairCountMismatchRollsBackThenConverges(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()
	for index := range posts {
		if strings.TrimSpace(posts[index].AuthorID) == "" {
			posts[index].AuthorID = "builtin_travel_blogger"
		}
	}
	first := ImportOptions{
		ReleaseID: "rel_repair_001", ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	initial, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, first)
	if err != nil {
		t.Fatalf("initial release: %v", err)
	}
	second := ImportOptions{
		ReleaseID: "rel_repair_002", ManifestDigest: "sha256:" + strings.Repeat("b", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: initial.ProjectionVersion + 1, ExpectedRevision: initial.Revision,
	}
	activated, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(time.Minute), second,
	)
	if err != nil {
		t.Fatalf("activate release with deletion: %v", err)
	}
	if activated.PostDeletionEventsReady != 1 {
		t.Fatalf("deletion events=%d want=1", activated.PostDeletionEventsReady)
	}

	var deleted struct {
		ID          string          `bson:"_id"`
		AggregateID string          `bson:"aggregateId"`
		OccurredAt  time.Time       `bson:"occurredAt"`
		PayloadJSON json.RawMessage `bson:"payloadJson"`
	}
	if err := db.Collection("content_outbox").FindOne(
		ctx,
		bson.M{"eventType": "PostDeleted", "aggregateVersion": activated.ProjectionVersion},
	).Decode(&deleted); err != nil {
		t.Fatalf("read canonical PostDeleted: %v", err)
	}
	legacyPayload, err := json.Marshal(map[string]any{
		"postId":        deleted.AggregateID,
		"releaseId":     second.ReleaseID,
		"releaseDigest": second.ManifestDigest,
		"sourceOwner":   second.SourceOwner,
		"deletedAt":     deleted.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Collection("content_outbox").UpdateOne(
		ctx,
		bson.M{"_id": deleted.ID},
		bson.M{"$set": bson.M{"payloadJson": json.RawMessage(legacyPayload)}},
	); err != nil {
		t.Fatalf("install bounded legacy payload: %v", err)
	}
	postBefore, err := db.Collection("posts").FindOne(
		ctx,
		bson.M{"postRef": posts[0].PostRef},
	).Raw()
	if err != nil {
		t.Fatalf("read active Post before repair: %v", err)
	}
	stateBefore, err := db.Collection("data_release_state").FindOne(
		ctx,
		bson.M{"environment": "alpha", "sourceOwner": second.SourceOwner},
	).Raw()
	if err != nil {
		t.Fatalf("read active release state before repair: %v", err)
	}

	wrongCount := 2
	second.RequireReplay = true
	replayPostRef, err := CanonicalImportReportPostRef(posts[0].PostRef)
	if err != nil {
		t.Fatalf("derive replay source postRef: %v", err)
	}
	second.ReplayPostBindings = []ImportedPostBinding{{
		PostRef: replayPostRef, PostID: RuntimePostID(posts[0].ContentID),
		ContentID: posts[0].ContentID, ContentVersion: posts[0].ContentVersion,
		UsageScope: posts[0].Admission.UsageScope, ContentType: posts[0].ContentType,
		AuthorID: posts[0].AuthorID,
	}}
	second.ExpectedOutboxRepairCount = &wrongCount
	if _, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(2*time.Minute), second,
	); err == nil || !strings.Contains(err.Error(), "repair count mismatch") {
		t.Fatalf("wrong expected count did not abort transaction: %v", err)
	}
	var failedReceipt struct {
		Stage             string `bson:"stage"`
		Status            string `bson:"status"`
		FirstTypedBlocker string `bson:"firstTypedBlocker"`
	}
	if err := db.Collection("data_release_stage_receipts").FindOne(
		ctx,
		bson.M{
			"environment": "alpha",
			"releaseId":   second.ReleaseID,
			"status":      "failed",
		},
	).Decode(&failedReceipt); err != nil {
		t.Fatalf("read failed release stage receipt: %v", err)
	}
	if failedReceipt.Stage != "imported" ||
		failedReceipt.FirstTypedBlocker != "CONTENT.RELEASE.IMPORT_FAILED" {
		t.Fatalf("failed release receipt is not typed: %+v", failedReceipt)
	}
	var afterMismatch struct {
		PayloadJSON json.RawMessage `bson:"payloadJson"`
	}
	if err := db.Collection("content_outbox").FindOne(
		ctx, bson.M{"_id": deleted.ID},
	).Decode(&afterMismatch); err != nil {
		t.Fatal(err)
	}
	if string(afterMismatch.PayloadJSON) != string(legacyPayload) {
		t.Fatal("repair count mismatch committed payload CAS")
	}

	exactCount := 1
	second.ExpectedOutboxRepairCount = &exactCount
	repaired, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(3*time.Minute), second,
	)
	if err != nil {
		t.Fatalf("exact active-release repair: %v", err)
	}
	if !repaired.Replayed || repaired.OutboxEventsRepaired != 1 ||
		repaired.OutboxEventsAppended != 0 || repaired.PostsRemoved != 0 {
		t.Fatalf("unexpected repair result: %+v", repaired)
	}

	zeroCount := 0
	second.ExpectedOutboxRepairCount = &zeroCount
	idempotent, err := ApplyImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(4*time.Minute), second,
	)
	if err != nil {
		t.Fatalf("idempotent active-release repair: %v", err)
	}
	if idempotent.OutboxEventsRepaired != 0 || idempotent.OutboxEventsAppended != 0 {
		t.Fatalf("idempotent replay wrote outbox: %+v", idempotent)
	}
	postAfter, err := db.Collection("posts").FindOne(
		ctx,
		bson.M{"postRef": posts[0].PostRef},
	).Raw()
	if err != nil {
		t.Fatalf("read active Post after repair: %v", err)
	}
	stateAfter, err := db.Collection("data_release_state").FindOne(
		ctx,
		bson.M{"environment": "alpha", "sourceOwner": second.SourceOwner},
	).Raw()
	if err != nil {
		t.Fatalf("read active release state after repair: %v", err)
	}
	if !bytes.Equal(postBefore, postAfter) {
		t.Fatal("repair rail rewrote active Post bytes")
	}
	if !bytes.Equal(stateBefore, stateAfter) {
		t.Fatal("repair rail rewrote active release-state bytes")
	}
}

func TestMongoLegacyActiveReleaseRepairOnlyChangesFourPostDeletedPayloads(
	t *testing.T,
) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	all := make([]PostDoc, 0, 50)
	for index := 0; index < 50; index++ {
		all = append(all, PostDoc{
			PostRef:        fmt.Sprintf("posts/article/体验/legacy-repair-%02d/1", index),
			ContentID:      fmt.Sprintf("qwq_data_legacy_repair_%02d", index),
			ContentVersion: 1, ContentType: "article", ContentIdentity: "work",
			Title:    fmt.Sprintf("legacy repair %02d", index),
			AuthorID: "builtin_travel_blogger",
			Admission: ContentAdmission{
				ProcessResult: "completed", QualityResult: "passed", UsageScope: "research",
			},
			CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now,
		})
	}
	first := ImportOptions{
		ReleaseID: "legacy_repair_previous", ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	initial, err := ApplyImportedPostRelease(ctx, db, "alpha", all, now, first)
	if err != nil || initial.PostsUpserted != 50 {
		t.Fatalf("seed previous release result=%+v err=%v", initial, err)
	}
	desired := append([]PostDoc(nil), all[:46]...)
	active := ImportOptions{
		ReleaseID: "legacy_repair_active", ManifestDigest: "sha256:" + strings.Repeat("b", 64),
		Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: initial.ProjectionVersion + 1, ExpectedRevision: initial.Revision,
	}
	activated, err := ApplyImportedPostRelease(
		ctx, db, "alpha", desired, now.Add(time.Minute), active,
	)
	if err != nil || activated.PostsUpserted != 46 || activated.PostsRemoved != 4 {
		t.Fatalf("activate 46/4 release result=%+v err=%v", activated, err)
	}

	bindings := make([]ImportedPostBinding, 0, len(desired))
	posts := db.Collection("posts")
	for _, post := range desired {
		currentID := RuntimePostID(post.ContentID)
		if err := posts.FindOne(ctx, bson.M{"_id": currentID}).Err(); err != nil {
			t.Fatalf("read current Post %q: %v", post.PostRef, err)
		}
		reportRef, err := CanonicalImportReportPostRef(post.PostRef)
		if err != nil {
			t.Fatal(err)
		}
		bindings = append(bindings, ImportedPostBinding{
			PostRef: reportRef, PostID: currentID, ContentID: post.ContentID,
			ContentVersion: post.ContentVersion, UsageScope: post.Admission.UsageScope,
			ContentType: post.ContentType, AuthorID: post.AuthorID,
		})
	}

	outbox := db.Collection("content_outbox")
	cursor, err := outbox.Find(ctx, bson.M{
		"eventType": "PostDeleted", "aggregateVersion": activated.ProjectionVersion,
	})
	if err != nil {
		t.Fatal(err)
	}
	legacyPayloads := make(map[string][]byte, 4)
	for cursor.Next(ctx) {
		var deleted struct {
			ID          string          `bson:"_id"`
			AggregateID string          `bson:"aggregateId"`
			OccurredAt  time.Time       `bson:"occurredAt"`
			PayloadJSON json.RawMessage `bson:"payloadJson"`
		}
		if err := cursor.Decode(&deleted); err != nil {
			t.Fatal(err)
		}
		payload, err := json.Marshal(map[string]any{
			"postId": deleted.AggregateID, "releaseId": active.ReleaseID,
			"releaseDigest": active.ManifestDigest, "sourceOwner": active.SourceOwner,
			"deletedAt": deleted.OccurredAt.UTC().Format(time.RFC3339Nano),
		})
		if err != nil {
			t.Fatal(err)
		}
		if _, err := outbox.UpdateOne(
			ctx, bson.M{"_id": deleted.ID},
			bson.M{"$set": bson.M{"payloadJson": json.RawMessage(payload)}},
		); err != nil {
			t.Fatal(err)
		}
		legacyPayloads[deleted.ID] = append([]byte(nil), payload...)
	}
	if err := cursor.Close(ctx); err != nil {
		t.Fatal(err)
	}
	if len(legacyPayloads) != 4 {
		t.Fatalf("legacy tombstones=%d want=4", len(legacyPayloads))
	}

	readRawClosure := func(collection *mongo.Collection, filter bson.M) [][]byte {
		t.Helper()
		cursor, err := collection.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
		if err != nil {
			t.Fatal(err)
		}
		defer cursor.Close(ctx)
		var result [][]byte
		for cursor.Next(ctx) {
			result = append(result, append([]byte(nil), cursor.Current...))
		}
		if err := cursor.Err(); err != nil {
			t.Fatal(err)
		}
		return result
	}
	postBytesBefore := readRawClosure(posts, bson.M{
		"releaseId": active.ReleaseID, "lifecycleStatus": "active",
	})
	publishedBytesBefore := readRawClosure(outbox, bson.M{
		"eventType": "PostPublished", "aggregateVersion": activated.ProjectionVersion,
	})
	stateBefore, err := db.Collection("data_release_state").FindOne(
		ctx, bson.M{"environment": "alpha", "sourceOwner": active.SourceOwner},
	).Raw()
	if err != nil {
		t.Fatal(err)
	}

	expected := 4
	active.RequireReplay = true
	active.ExpectedOutboxRepairCount = &expected
	active.ReplayPostBindings = bindings
	repaired, err := ApplyImportedPostRelease(
		ctx, db, "alpha", desired, now.Add(2*time.Minute), active,
	)
	if err != nil {
		t.Fatalf("repair legacy 46/4 release: %v", err)
	}
	if !repaired.Replayed || repaired.PostsUpserted != 46 ||
		repaired.PostsRemoved != 0 || repaired.PostDeletionEventsReady != 4 ||
		repaired.OutboxEventsReady != 4 || repaired.OutboxEventsAppended != 0 ||
		repaired.OutboxEventsRepaired != 4 {
		t.Fatalf("unexpected legacy repair result: %+v", repaired)
	}
	if got := readRawClosure(posts, bson.M{
		"releaseId": active.ReleaseID, "lifecycleStatus": "active",
	}); !equalRawDocumentClosure(postBytesBefore, got) {
		t.Fatal("repair rail rewrote legacy active Post bytes")
	}
	if got := readRawClosure(outbox, bson.M{
		"eventType": "PostPublished", "aggregateVersion": activated.ProjectionVersion,
	}); !equalRawDocumentClosure(publishedBytesBefore, got) {
		t.Fatal("repair rail rewrote PostPublished bytes")
	}
	stateAfter, err := db.Collection("data_release_state").FindOne(
		ctx, bson.M{"environment": "alpha", "sourceOwner": active.SourceOwner},
	).Raw()
	if err != nil || !bytes.Equal(stateBefore, stateAfter) {
		t.Fatalf("repair rail rewrote release state err=%v", err)
	}

	expected = 0
	idempotent, err := ApplyImportedPostRelease(
		ctx, db, "alpha", desired, now.Add(3*time.Minute), active,
	)
	if err != nil || idempotent.OutboxEventsRepaired != 0 ||
		idempotent.OutboxEventsAppended != 0 {
		t.Fatalf("idempotent legacy repair result=%+v err=%v", idempotent, err)
	}
}

func equalRawDocumentClosure(left, right [][]byte) bool {
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

func TestMongoUpsertIsIdempotent(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	coll := db.Collection("posts")
	EnsureUnique(ctx, coll, "postRef", "idx_post_ref")

	t1 := time.Now().UTC().Truncate(time.Millisecond)
	if _, err := UpsertPosts(ctx, coll, samplePosts(), t1); err != nil {
		t.Fatal(err)
	}
	var first struct {
		CreatedAt time.Time `bson:"createdAt"`
		UpdatedAt time.Time `bson:"updatedAt"`
	}
	filter := bson.M{"postRef": "posts/article/攻略/色达攻略/1"}
	if err := coll.FindOne(ctx, filter).Decode(&first); err != nil {
		t.Fatal(err)
	}

	// 重跑同一批（更晚时间）但内容未变：文档数不变；三类时间事实都保持 manifest 真值。
	t2 := t1.Add(2 * time.Second)
	if _, err := UpsertPosts(ctx, coll, samplePosts(), t2); err != nil {
		t.Fatal(err)
	}
	count, _ := coll.CountDocuments(ctx, bson.M{})
	if count != 2 {
		t.Fatalf("re-run must not duplicate; want 2, got %d", count)
	}
	var second struct {
		CreatedAt time.Time `bson:"createdAt"`
		UpdatedAt time.Time `bson:"updatedAt"`
	}
	if err := coll.FindOne(ctx, filter).Decode(&second); err != nil {
		t.Fatal(err)
	}
	if !second.CreatedAt.Equal(first.CreatedAt) {
		t.Fatalf("createdAt must be stable: %v vs %v", first.CreatedAt, second.CreatedAt)
	}
	if !second.UpdatedAt.Equal(first.UpdatedAt) {
		t.Fatalf("updatedAt must stay on manifest fact on unchanged re-run: %v -> %v", first.UpdatedAt, second.UpdatedAt)
	}

	// 内容发生实质变更时，只有上游 manifest.updatedAt 变化才应反映到运行库；
	// importer 不再用导入时刻自行推进更新时间。
	t3 := t2.Add(2 * time.Second)
	changed := samplePosts()
	changed[1].ArticleMarkdown = "# 色达攻略\n新增更新段落\n"
	changed[1].UpdatedAt = time.Date(2026, 4, 5, 8, 0, 0, 0, time.UTC)
	if _, err := UpsertPosts(ctx, coll, changed, t3); err != nil {
		t.Fatal(err)
	}
	var third struct {
		CreatedAt   time.Time `bson:"createdAt"`
		UpdatedAt   time.Time `bson:"updatedAt"`
		PublishedAt time.Time `bson:"publishedAt"`
	}
	if err := coll.FindOne(ctx, filter).Decode(&third); err != nil {
		t.Fatal(err)
	}
	if !third.CreatedAt.Equal(first.CreatedAt) {
		t.Fatalf("createdAt must stay stable across content change: %v vs %v", first.CreatedAt, third.CreatedAt)
	}
	if !third.UpdatedAt.Equal(time.Date(2026, 4, 5, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("updatedAt must track manifest fact when content changes: %v", third.UpdatedAt)
	}
	if !third.PublishedAt.Equal(time.Date(2026, 4, 2, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("publishedAt must stay on first public time: %v", third.PublishedAt)
	}
}

func TestMongoReleaseAwareSyncTombstonesMissingSourceOwnedDocs(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	postsColl := db.Collection("posts")
	entitiesColl := db.Collection("entities")
	feedColl := db.Collection("rm_discovery_feed")

	opts1 := ImportOptions{ReleaseID: "rel_001", Mode: "upsert", DeletePolicy: "none", SourceOwner: "qwq_data"}
	now := time.Now().UTC()
	if _, err := UpsertPostsWithOptions(ctx, postsColl, samplePosts(), now, opts1); err != nil {
		t.Fatal(err)
	}
	if _, err := UpsertEntitiesWithOptions(ctx, entitiesColl, sampleEntities(), now, opts1); err != nil {
		t.Fatal(err)
	}
	if _, err := UpsertDiscoveryFeedWithOptions(ctx, feedColl, samplePosts(), ConditionProfileIndex(sampleEntities()), now, opts1); err != nil {
		t.Fatal(err)
	}

	keptPost := []PostDoc{samplePosts()[0]}
	keptEntity := []EntityDoc{sampleEntities()[0]}
	opts2 := ImportOptions{ReleaseID: "rel_002", Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data"}
	if _, err := UpsertPostsWithOptions(ctx, postsColl, keptPost, now.Add(time.Second), opts2); err != nil {
		t.Fatal(err)
	}
	if _, err := UpsertEntitiesWithOptions(ctx, entitiesColl, keptEntity, now.Add(time.Second), opts2); err != nil {
		t.Fatal(err)
	}
	tp, err := ApplyMissingPostPolicy(ctx, postsColl, keptPost, now.Add(time.Second), opts2)
	if err != nil {
		t.Fatal(err)
	}
	te, err := ApplyMissingEntityPolicy(ctx, entitiesColl, keptEntity, now.Add(time.Second), opts2)
	if err != nil {
		t.Fatal(err)
	}
	tf, err := ApplyMissingFeedPolicy(ctx, feedColl, keptPost, now.Add(time.Second), opts2)
	if err != nil {
		t.Fatal(err)
	}
	if tp != 1 || te != 1 || tf != 1 {
		t.Fatalf("want one tombstone in each collection, got posts=%d entities=%d feed=%d", tp, te, tf)
	}
	var tombstonedPost struct {
		Status             string    `bson:"status"`
		Visibility         string    `bson:"visibility"`
		LifecycleStatus    string    `bson:"lifecycleStatus"`
		DeletedByReleaseId string    `bson:"deletedByReleaseId"`
		DeletedAt          time.Time `bson:"deletedAt"`
	}
	if err := postsColl.FindOne(ctx, bson.M{"postRef": "posts/article/攻略/色达攻略/1"}).Decode(&tombstonedPost); err != nil {
		t.Fatal(err)
	}
	if tombstonedPost.Status != "deleted" || tombstonedPost.Visibility != "hidden" || tombstonedPost.LifecycleStatus != "tombstone" || tombstonedPost.DeletedByReleaseId != "rel_002" {
		t.Fatalf("post tombstone fields wrong: %+v", tombstonedPost)
	}
	replayAt := now.Add(2 * time.Second)
	replayedPosts, err := ApplyMissingPostPolicy(ctx, postsColl, keptPost, replayAt, opts2)
	if err != nil {
		t.Fatal(err)
	}
	replayedEntities, err := ApplyMissingEntityPolicy(ctx, entitiesColl, keptEntity, replayAt, opts2)
	if err != nil {
		t.Fatal(err)
	}
	replayedFeed, err := ApplyMissingFeedPolicy(ctx, feedColl, keptPost, replayAt, opts2)
	if err != nil {
		t.Fatal(err)
	}
	if replayedPosts != 0 || replayedEntities != 0 || replayedFeed != 0 {
		t.Fatalf(
			"same release replay must not rewrite tombstones, got posts=%d entities=%d feed=%d",
			replayedPosts,
			replayedEntities,
			replayedFeed,
		)
	}
	var replayedPost struct {
		DeletedAt time.Time `bson:"deletedAt"`
	}
	if err := postsColl.FindOne(ctx, bson.M{"postRef": "posts/article/攻略/色达攻略/1"}).Decode(&replayedPost); err != nil {
		t.Fatal(err)
	}
	if !replayedPost.DeletedAt.Equal(tombstonedPost.DeletedAt) {
		t.Fatalf("same release replay changed deletedAt: %v -> %v", tombstonedPost.DeletedAt, replayedPost.DeletedAt)
	}
	var kept struct {
		ReleaseID       string `bson:"releaseId"`
		SourceOwner     string `bson:"sourceOwner"`
		LifecycleStatus string `bson:"lifecycleStatus"`
		SourceHash      string `bson:"sourceHash"`
	}
	if err := postsColl.FindOne(ctx, bson.M{"postRef": "posts/article/体验/甲居藏寨体验/1"}).Decode(&kept); err != nil {
		t.Fatal(err)
	}
	if kept.ReleaseID != "rel_002" || kept.SourceOwner != "qwq_data" || kept.LifecycleStatus != "active" || kept.SourceHash == "" {
		t.Fatalf("kept release fields wrong: %+v", kept)
	}
}

func TestMongoUpsertEntitiesPageFlag(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	coll := db.Collection("entities")
	EnsureUnique(ctx, coll, "entityRef", "idx_entity_ref")

	n, err := UpsertEntities(ctx, coll, sampleEntities(), time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("want 2 entities, got %d", n)
	}
	var withPage struct {
		HasPage          bool           `bson:"hasPage"`
		Page             string         `bson:"page"`
		AssetManifest    map[string]any `bson:"assetManifest"`
		ConditionProfile map[string]any `bson:"conditionProfile"`
	}
	if err := coll.FindOne(ctx, bson.M{"entityRef": "地点/景区/甲居藏寨"}).Decode(&withPage); err != nil {
		t.Fatal(err)
	}
	if !withPage.HasPage || withPage.Page == "" {
		t.Fatalf("甲居藏寨 should have page: %+v", withPage)
	}
	if withPage.ConditionProfile == nil {
		t.Fatalf("entity conditionProfile not persisted: %+v", withPage)
	}
	if withPage.AssetManifest == nil {
		t.Fatalf("entity assetManifest not persisted: %+v", withPage)
	}
	var noPage struct {
		HasPage bool `bson:"hasPage"`
	}
	if err := coll.FindOne(ctx, bson.M{"entityRef": "地点/景区/色达"}).Decode(&noPage); err != nil {
		t.Fatal(err)
	}
	if noPage.HasPage {
		t.Fatalf("色达 should NOT have page")
	}
}

func TestMongoSparseUniqueIndexEnforced(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	coll := db.Collection("posts")
	EnsureSparseUnique(ctx, coll, "postRef", "idx_post_ref")

	cur, err := coll.Indexes().List(ctx)
	if err != nil {
		t.Fatal(err)
	}
	var idxs []bson.M
	if err := cur.All(ctx, &idxs); err != nil {
		t.Fatal(err)
	}
	found := false
	for _, ix := range idxs {
		if ix["name"] == "idx_post_ref" {
			found = true
			if unique, _ := ix["unique"].(bool); !unique {
				t.Fatalf("idx_post_ref must be unique: %+v", ix)
			}
			if sparse, _ := ix["sparse"].(bool); !sparse {
				t.Fatalf("idx_post_ref must be sparse so online drafts without postRef can coexist: %+v", ix)
			}
		}
	}
	if !found {
		t.Fatalf("idx_post_ref index not created: %+v", idxs)
	}
	if _, err := coll.InsertOne(ctx, bson.M{"_id": "online_draft_1"}); err != nil {
		t.Fatalf("insert draft without postRef: %v", err)
	}
	if _, err := coll.InsertOne(ctx, bson.M{"_id": "online_draft_2"}); err != nil {
		t.Fatalf("insert second draft without postRef: %v", err)
	}
}

func TestMongoLoadThenUpsertFromPublishTree(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()

	root := publishTreeFixture(t)
	// 只灌入 sample bundle 子集
	posts, err := LoadPosts(root, ToSet([]string{"article/攻略/色达攻略/1"}), "")
	if err != nil {
		t.Fatal(err)
	}
	ents, err := LoadEntities(root, ToSet([]string{"地点/景区/色达"}))
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	pc := db.Collection("posts")
	ec := db.Collection("entities")
	EnsureUnique(ctx, pc, "postRef", "idx_post_ref")
	EnsureUnique(ctx, ec, "entityRef", "idx_entity_ref")
	if _, err := UpsertPosts(ctx, pc, posts, now); err != nil {
		t.Fatal(err)
	}
	if _, err := UpsertEntities(ctx, ec, ents, now); err != nil {
		t.Fatal(err)
	}
	if c, _ := pc.CountDocuments(ctx, bson.M{}); c != 1 {
		t.Fatalf("want 1 post (sample subset), got %d", c)
	}
	if c, _ := ec.CountDocuments(ctx, bson.M{}); c != 1 {
		t.Fatalf("want 1 entity (sample subset), got %d", c)
	}
	var inserted struct {
		PostRef          string    `bson:"postRef"`
		Status           string    `bson:"status"`
		Visibility       string    `bson:"visibility"`
		ModerationStatus string    `bson:"moderationStatus"`
		PublishedAt      time.Time `bson:"publishedAt"`
	}
	if err := pc.FindOne(ctx, bson.M{"postRef": "posts/article/攻略/色达攻略/1"}).Decode(&inserted); err != nil {
		t.Fatal(err)
	}
	if inserted.Status != "published" || inserted.Visibility != "public" || inserted.ModerationStatus != "approved" {
		t.Fatalf("post must satisfy the feed visibility contract: %+v", inserted)
	}
	if inserted.PublishedAt.IsZero() {
		t.Fatalf("post publishedAt must be populated: %+v", inserted)
	}
}

// TestMongoUpsertDiscoveryFeed 验证 Path A 同写 rm_discovery_feed：
// postId=运行时安全 ID、postRef 保留发布证据、status/visibility 可召回、
// producer lineage 不透传，conditionProfile 从主实体 join 冗余。
func TestMongoUpsertDiscoveryFeed(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()

	posts := samplePosts()
	ents := sampleEntities()
	feed := db.Collection("rm_discovery_feed")
	n, err := UpsertDiscoveryFeed(ctx, feed, posts, ConditionProfileIndex(ents), time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("want 2 feed items, got %d", n)
	}
	var item struct {
		PostId                   string                `bson:"postId"`
		PostRef                  string                `bson:"postRef"`
		ContentIdentity          string                `bson:"contentIdentity"`
		Status                   string                `bson:"status"`
		Visibility               string                `bson:"visibility"`
		TagRefs                  []string              `bson:"tagRefs"`
		IntersectionHints        []IntersectionHintDoc `bson:"intersectionHints"`
		CreatorProfileID         string                `bson:"creatorProfileId"`
		CreatorArchetype         string                `bson:"creatorArchetype"`
		ConditionProfile         map[string]any        `bson:"conditionProfile"`
		RecScore                 float64               `bson:"recScore"`
		QualityScore             float64               `bson:"qualityScore"`
		ContentVertical          string                `bson:"contentVertical"`
		SupplySource             string                `bson:"supplySource"`
		IntersectionFactStrength float64               `bson:"intersectionFactStrength"`
		IntersectionFreshness    float64               `bson:"intersectionFreshness"`
		IntersectionClass        string                `bson:"intersectionClass"`
		IntersectionSourceRefTop string                `bson:"intersectionSourceRefTop"`
		SemanticCoverage         float64               `bson:"semanticMentionCoverage"`
		MediaCompleteness        float64               `bson:"mediaCompleteness"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": RuntimePostID("qwq_data_article_jiaju_001")}).Decode(&item); err != nil {
		t.Fatal(err)
	}
	if item.PostRef != "posts/article/体验/甲居藏寨体验/1" || strings.Contains(item.PostId, "/") {
		t.Fatalf("feed identity must be route-safe and preserve postRef: %+v", item)
	}
	if item.ContentIdentity != "work" {
		t.Fatalf("feed projection must preserve canonical contentIdentity=work: %+v", item)
	}
	if item.Status != "published" || item.Visibility != "public" {
		t.Fatalf("feed item must be discoverable (published/public): %+v", item)
	}
	if len(item.IntersectionHints) != 2 || item.IntersectionHints[1].ActionTargetID != "Topic/旅行" {
		t.Fatalf("feed intersectionHints missing: %+v", item.IntersectionHints)
	}
	if item.CreatorProfileID != "qwq_creator_travel_blogger_001" || item.CreatorArchetype != "travel_blogger" {
		t.Fatalf("feed creator projection missing: %+v", item)
	}
	if item.ConditionProfile == nil {
		t.Fatalf("feed conditionProfile not joined from entity: %+v", item)
	}
	if item.QualityScore <= 0 || item.RecScore != item.QualityScore {
		t.Fatalf("feed qualityScore/recScore not projected: %+v", item)
	}
	if item.IntersectionFactStrength != 2 || item.IntersectionFreshness != 1 || item.IntersectionClass != "fact" {
		t.Fatalf("feed intersection ranking projection missing: %+v", item)
	}
	if item.IntersectionSourceRefTop != "entity:景区:甲居藏寨" {
		t.Fatalf("feed intersectionSourceRefTop wrong: %+v", item)
	}
	if item.ContentVertical != "travel_photography" || item.SupplySource != "data_engineering" {
		t.Fatalf("feed vertical/source projection mismatch: %+v", item)
	}
	if item.SemanticCoverage <= 0 || item.MediaCompleteness <= 0 {
		t.Fatalf("feed semantic/media projection missing: %+v", item)
	}
	if _, ok := item.ConditionProfile["altitudeMeters"]; !ok {
		t.Fatalf("conditionProfile.altitudeMeters missing: %+v", item.ConditionProfile)
	}
	// 无画像实体的文章：conditionProfile 应缺省（nil），不阻断 tag/hot/explore 召回。
	var second struct {
		Status string `bson:"status"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": RuntimePostID("qwq_data_article_seda_001")}).Decode(&second); err != nil {
		t.Fatal(err)
	}
	if second.Status != "published" {
		t.Fatalf("色达攻略 feed item not discoverable: %+v", second)
	}
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016.t3
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016.t4
func TestMongoStagedReleaseIsVerifiedBeforeActivation(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	posts := sampleReleasePosts()
	for index := range posts {
		if strings.TrimSpace(posts[index].AuthorID) == "" {
			posts[index].AuthorID = "builtin_travel_blogger"
		}
	}
	previous := ImportOptions{
		ReleaseID:      "rel_staged_prev",
		ManifestDigest: "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	seeded, err := ApplyImportedPostRelease(ctx, db, "alpha", posts, now, previous)
	if err != nil {
		t.Fatalf("seed previous active release: %v", err)
	}

	candidate := ImportOptions{
		ReleaseID:      "rel_staged_next",
		ManifestDigest: "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
		Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: seeded.ProjectionVersion + 1, ExpectedRevision: seeded.Revision,
	}
	staged, err := StageImportedPostRelease(ctx, db, "alpha", posts[:1], now.Add(time.Minute), candidate)
	if err != nil {
		t.Fatalf("stage candidate release: %v", err)
	}
	if staged.PostsStaged != 1 || staged.CandidateRevision != candidate.ProjectionVersion ||
		staged.PreviousReleaseID != previous.ReleaseID || staged.PreviousRevision != seeded.Revision {
		t.Fatalf("unexpected stage result: %+v", staged)
	}
	var pointer struct {
		ActiveReleaseID string `bson:"activeReleaseId"`
		Revision        int64  `bson:"revision"`
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	}).Decode(&pointer); err != nil {
		t.Fatalf("read pointer after stage: %v", err)
	}
	if pointer.ActiveReleaseID != previous.ReleaseID || pointer.Revision != seeded.Revision {
		t.Fatalf("stage must not move the active pointer: %+v", pointer)
	}
	if count, err := db.Collection("posts").CountDocuments(ctx, bson.M{
		"releaseId": candidate.ReleaseID,
	}); err != nil || count != 0 {
		t.Fatalf("stage must not write active posts: count=%d err=%v", count, err)
	}
	if count, err := db.Collection("posts_candidate").CountDocuments(ctx, bson.M{
		"releaseId": candidate.ReleaseID, "lifecycleStatus": "candidate",
	}); err != nil || count != 1 {
		t.Fatalf("candidate collection count=%d err=%v, want 1", count, err)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); err != nil || count != 2 {
		t.Fatalf("stage must not append lifecycle outbox: count=%d err=%v", count, err)
	}

	// 真实 CLI 中 stage 与 activate 在不同时刻运行，激活解析出的 sourceVersion 必然
	// 不等于 candidateRevision；这里显式拉开两者以暴露复制 version 的漂移。
	activateOpts := candidate
	activateOpts.ProjectionVersion = candidate.ProjectionVersion + 5
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(2*time.Minute), activateOpts, staged.CandidateRevision,
	); err == nil || !strings.Contains(err.Error(), "CANDIDATE_VERIFICATION_REQUIRED") {
		t.Fatalf("activate without verified evidence must fail closed: %v", err)
	}
	// 候选缺失：闭包声称 N 篇但候选集合只有 1 篇 → typed CONTENT.USER.release_candidate_missing。
	if _, err := VerifyImportedPostReleaseCandidate(
		ctx, db, "alpha", posts, now.Add(2*time.Minute), candidate, staged.CandidateRevision,
	); err == nil || !errors.Is(err, postgenerated.ErrReleaseCandidateMissing) {
		t.Fatalf("verify against a drifted closure must fail closed with ErrReleaseCandidateMissing: %v", err)
	}
	// 候选漂移：候选文档 sourceHash 与不可变清单不一致 → typed CONTENT.USER.release_candidate_drift；
	// 篡改后恢复原值，后续 verify/activate 继续走真实路径。
	candidateFilter := bson.M{"releaseId": candidate.ReleaseID, "lifecycleStatus": "candidate"}
	var candidateDoc struct {
		SourceHash string `bson:"sourceHash"`
	}
	if err := db.Collection("posts_candidate").FindOne(ctx, candidateFilter).Decode(&candidateDoc); err != nil {
		t.Fatalf("read staged candidate: %v", err)
	}
	if _, err := db.Collection("posts_candidate").UpdateOne(ctx, candidateFilter, bson.M{
		"$set": bson.M{"sourceHash": "sha256:" + strings.Repeat("f", 64)},
	}); err != nil {
		t.Fatalf("tamper staged candidate: %v", err)
	}
	if _, err := VerifyImportedPostReleaseCandidate(
		ctx, db, "alpha", posts[:1], now.Add(2*time.Minute), candidate, staged.CandidateRevision,
	); err == nil || !errors.Is(err, postgenerated.ErrReleaseCandidateDrift) {
		t.Fatalf("verify against a tampered candidate must fail closed with ErrReleaseCandidateDrift: %v", err)
	}
	if _, err := db.Collection("posts_candidate").UpdateOne(ctx, candidateFilter, bson.M{
		"$set": bson.M{"sourceHash": candidateDoc.SourceHash},
	}); err != nil {
		t.Fatalf("restore staged candidate: %v", err)
	}
	readback, err := VerifyImportedPostReleaseCandidate(
		ctx, db, "alpha", posts[:1], now.Add(2*time.Minute), candidate, staged.CandidateRevision,
	)
	if err != nil || len(readback.PostIDs) != 1 || readback.PostIDs[0] != RuntimePostID(posts[0].ContentID) {
		t.Fatalf("candidate readback=%+v err=%v", readback, err)
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(3*time.Minute), activateOpts, staged.CandidateRevision+1,
	); err == nil {
		t.Fatal("activate must bind the verified candidateRevision exactly")
	}

	activated, err := ActivateImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(3*time.Minute), activateOpts, staged.CandidateRevision,
	)
	if err != nil {
		t.Fatalf("activate verified candidate: %v", err)
	}
	if activated.PostsUpserted != 1 || activated.PostsRemoved != 1 || activated.OutboxEventsAppended != 2 ||
		activated.Revision != seeded.Revision+1 || activated.PreviousReleaseID != previous.ReleaseID {
		t.Fatalf("unexpected activation result: %+v", activated)
	}
	if err := db.Collection("data_release_state").FindOne(ctx, bson.M{
		"environment": "alpha", "sourceOwner": "qwq_data",
	}).Decode(&pointer); err != nil {
		t.Fatalf("read pointer after activate: %v", err)
	}
	if pointer.ActiveReleaseID != candidate.ReleaseID || pointer.Revision != activated.Revision {
		t.Fatalf("activate must switch the pointer through CAS: %+v", pointer)
	}
	var activePost struct {
		LifecycleStatus string `bson:"lifecycleStatus"`
		ReleaseID       string `bson:"releaseId"`
		ManifestDigest  string `bson:"manifestDigest"`
		Version         int64  `bson:"version"`
	}
	if err := db.Collection("posts").FindOne(ctx, bson.M{
		"_id": RuntimePostID(posts[0].ContentID),
	}).Decode(&activePost); err != nil {
		t.Fatalf("read activated post: %v", err)
	}
	if activePost.LifecycleStatus != "active" || activePost.ReleaseID != candidate.ReleaseID ||
		activePost.ManifestDigest != candidate.ManifestDigest {
		t.Fatalf("activated post is not bound to the candidate identity: %+v", activePost)
	}
	// 候选阶段的 version 是 candidateRevision；激活后 Post version 必须等于 pointer
	// 与 outbox 使用的 sourceVersion，否则 replay closure 会把它判为漂移。
	if activePost.Version != activated.ProjectionVersion || activePost.Version == staged.CandidateRevision {
		t.Fatalf("activated post version=%d must equal activation sourceVersion=%d (candidateRevision=%d)",
			activePost.Version, activated.ProjectionVersion, staged.CandidateRevision)
	}
	closureOpts := activateOpts
	closureOpts.ProjectionVersion = activated.ProjectionVersion
	if _, err := ValidateImportedReleaseReplayClosure(
		ctx, db.Collection("posts"), db.Collection("content_outbox"), posts[:1], closureOpts, now.Add(3*time.Minute),
	); err != nil {
		t.Fatalf("activated release must satisfy the replay closure: %v", err)
	}
	if count, err := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); err != nil || count != 4 {
		t.Fatalf("activation outbox count=%d err=%v, want 4", count, err)
	}
	if _, err := ActivateImportedPostRelease(
		ctx, db, "alpha", posts[:1], now.Add(4*time.Minute), activateOpts, staged.CandidateRevision,
	); err == nil || !strings.Contains(err.Error(), "CANDIDATE_ALREADY_ACTIVE") {
		t.Fatalf("re-activating the active candidate must route to the replay rail: %v", err)
	}
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016.t3
func TestMongoReleaseMediaMembershipAccumulatesAcrossReleases(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	assets := map[string]ReleaseMediaAsset{
		"asset-shared": {
			AssetID: "asset-shared", Kind: "image", Version: 1, ContentType: "image/webp",
			PrivateObjectKey: "media/objects/sha256/aa/bb/" + strings.Repeat("a", 64) + ".webp",
			SHA256:           "sha256:" + strings.Repeat("a", 64), Bytes: 1024,
			OwnerRefs: []string{"posts/image/shared/1"}, RightsSnapshotRefs: []string{},
		},
	}
	coll := db.Collection("media_assets")
	for _, releaseID := range []string{"rel_media_prev", "rel_media_next", "rel_media_prev"} {
		if _, err := UpsertReleaseMediaAssetProjections(ctx, coll, assets, "qwq_data", releaseID, now); err != nil {
			t.Fatalf("project release %s: %v", releaseID, err)
		}
	}
	var document struct {
		SourceReleaseID  string   `bson:"sourceReleaseId"`
		SourceReleaseIDs []string `bson:"sourceReleaseIds"`
	}
	if err := coll.FindOne(ctx, bson.M{"_id": "asset-shared"}).Decode(&document); err != nil {
		t.Fatalf("read shared asset: %v", err)
	}
	sort.Strings(document.SourceReleaseIDs)
	// previous 与 candidate 同时保留；单值只是最近一次导入的诊断，不参与授权。
	if strings.Join(document.SourceReleaseIDs, ",") != "rel_media_next,rel_media_prev" ||
		document.SourceReleaseID != "rel_media_prev" {
		t.Fatalf("shared asset membership drifted: %+v", document)
	}
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016.t3
func TestMongoEmptyBaselineCandidateVerifiesAndActivatesWithEmptyArrays(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	baseline := ImportOptions{
		ReleaseID:      "rel_empty_baseline",
		ManifestDigest: "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		Mode:           "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data",
		ProjectionVersion: now.UnixMilli(), ExpectedRevision: 0,
	}
	staged, err := StageImportedPostRelease(ctx, db, "alpha", nil, now, baseline)
	if err != nil || staged.PostsStaged != 0 {
		t.Fatalf("stage empty baseline result=%+v err=%v", staged, err)
	}
	readback, err := VerifyImportedPostReleaseCandidate(
		ctx, db, "alpha", nil, now.Add(time.Minute), baseline, staged.CandidateRevision,
	)
	if err != nil {
		t.Fatalf("verify empty baseline: %v", err)
	}
	// import_report.schema.json 要求数组；nil 切片会序列化为 null 并让 Data 侧契约校验失败。
	if readback.PostIDs == nil || readback.SourceHashes == nil ||
		len(readback.PostIDs) != 0 || len(readback.SourceHashes) != 0 {
		t.Fatalf("empty baseline readback must carry empty arrays: %+v", readback)
	}
	activateOpts := baseline
	activateOpts.ProjectionVersion = baseline.ProjectionVersion + 1
	activated, err := ActivateImportedPostRelease(
		ctx, db, "alpha", nil, now.Add(2*time.Minute), activateOpts, staged.CandidateRevision,
	)
	if err != nil || activated.PostsUpserted != 0 || activated.Revision != 1 || activated.CandidateCleanupError != "" {
		t.Fatalf("activate empty baseline result=%+v err=%v", activated, err)
	}
	if count, err := db.Collection("posts_candidate").CountDocuments(ctx, bson.M{
		"releaseId": baseline.ReleaseID,
	}); err != nil || count != 0 {
		t.Fatalf("candidate rows must be cleaned after activation: count=%d err=%v", count, err)
	}
}
