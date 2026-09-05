//go:build mongo_integration

// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t1
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t2
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t3
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t4

package api_integration

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func writeImportFixtureFile(t *testing.T, path, content string) {
	t.Helper()
	if strings.Contains(filepath.ToSlash(path), "/posts/") &&
		strings.HasSuffix(path, "manifest.json") &&
		strings.Contains(content, `"contentType"`) {
		prefix := `{"contentId":"fixture-` + fmt.Sprintf("%x", len(path)) + `","version":1,"sourceType":"data","variantPurpose":"original","admission":{"processResult":"completed","qualityResult":"passed","usageScope":"research","evidenceRef":"audit/attestation.json","evidenceDigest":"sha256:` + strings.Repeat("a", 64) + `"},"status":"active","contentIdentity":"work",`
		content = strings.Replace(content, "{", prefix, 1)
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
		{PostRef: "posts/article/体验/甲居藏寨体验/1", ContentID: "content-jiaju-001", ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", Admission: ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "research", EvidenceRef: "audit/attestation.json", EvidenceDigest: "sha256:" + strings.Repeat("a", 64)}, PoolStatus: "active", ContentIdentity: "work", ContentType: "article", Title: "甲居藏寨体验", Angle: "体验", Seq: 1,
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
		{PostRef: "posts/article/攻略/色达攻略/1", ContentID: "content-seda-001", ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", Admission: ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "research", EvidenceRef: "audit/attestation.json", EvidenceDigest: "sha256:" + strings.Repeat("b", 64)}, PoolStatus: "active", ContentIdentity: "work", ContentType: "article", Title: "色达攻略", Angle: "攻略", Seq: 1,
			EntityRefs: []string{"地点/景区/色达"}, NormalizedEntityRefs: []string{"entity:景区:色达"}, ArticleMarkdown: "# 色达攻略\n", ArticleDigest: "sha256:4444444444444444444444444444444444444444444444444444444444444444",
			CreatedAt:   time.Date(2026, 4, 1, 8, 0, 0, 0, time.UTC),
			UpdatedAt:   time.Date(2026, 4, 1, 8, 0, 0, 0, time.UTC),
			PublishedAt: time.Date(2026, 4, 2, 8, 0, 0, 0, time.UTC)},
	}
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
	postRef := "posts/article/体验/甲居藏寨体验/1"
	id := RuntimePostID(postRef)
	if id == "" {
		t.Fatal("RuntimePostID must not be empty")
	}
	if id != RuntimePostID(postRef) {
		t.Fatalf("RuntimePostID must be stable: %q", id)
	}
	if id == postRef || strings.Contains(id, "/") {
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
	if got.ID != RuntimePostID("content-jiaju-001") || got.PostID != got.ID || got.PostRef != "posts/article/体验/甲居藏寨体验/1" {
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

func TestMongoLegacyReleaseStateWriterFailsClosed(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	err := UpsertReleaseState(
		context.Background(), db.Collection("data_release_state"), "alpha",
		ImportOptions{ReleaseID: "legacy", ManifestDigest: "sha256:" + strings.Repeat("a", 64)},
		time.Now().UTC(), bson.M{"postsUpserted": 1},
	)
	if err == nil || !strings.Contains(err.Error(), "StageImportedPostRelease") {
		t.Fatalf("legacy blind active writer did not fail closed: %v", err)
	}
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
	if err := feed.FindOne(ctx, bson.M{"postId": RuntimePostID("content-jiaju-001")}).Decode(&item); err != nil {
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
	if err := feed.FindOne(ctx, bson.M{"postId": RuntimePostID("content-seda-001")}).Decode(&second); err != nil {
		t.Fatal(err)
	}
	if second.Status != "published" {
		t.Fatalf("色达攻略 feed item not discoverable: %+v", second)
	}
}
