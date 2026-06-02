package main

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// 真实 mongo 写入路径覆盖。需要 QWQ_TEST_MONGO_URI（CI/本地起临时 mongod 后设置）。
// 未设置时跳过，避免无 mongo 环境失败；本地用 run_mongo_import_test.sh 起临时实例后跑。
func testDB(t *testing.T) (*mongo.Database, func()) {
	t.Helper()
	uri := os.Getenv("QWQ_TEST_MONGO_URI")
	if uri == "" {
		t.Skip("QWQ_TEST_MONGO_URI not set; skipping mongo integration test")
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
		{PostRef: "posts/article/体验/甲居藏寨体验/1", ContentType: "article", Title: "甲居藏寨体验", Angle: "体验", Seq: 1,
			EntityRefs: []string{"地点/景区/甲居藏寨"}, TagRefs: []string{"Topic/旅行"}, Template: "journal",
			GeneratorModel: "agent/x", ArticleMarkdown: "# 甲居藏寨体验\n正文\n", ArticleDigest: "d1",
			SourceTaskId: "旅行/环线/川西环线/川西大环线自驾"},
		{PostRef: "posts/article/攻略/色达攻略/1", ContentType: "article", Title: "色达攻略", Angle: "攻略", Seq: 1,
			EntityRefs: []string{"地点/景区/色达"}, ArticleMarkdown: "# 色达攻略\n", ArticleDigest: "d2"},
	}
}

func sampleEntities() []EntityDoc {
	return []EntityDoc{
		{EntityRef: "地点/景区/甲居藏寨", Domain: "地点", Etype: "景区", Name: "甲居藏寨", Label: "甲居藏寨",
			TagRefs: []string{"Entity/地点/景区"}, Page: "# 甲居藏寨\n", HasPage: true,
			ConditionProfile: map[string]any{"regions": []any{"高原", "山地"}, "seasons": []any{"夏", "秋"}, "altitudeMeters": 3500},
			SourceTaskId:     "旅行/环线/川西环线/川西大环线自驾"},
		{EntityRef: "地点/景区/色达", Domain: "地点", Etype: "景区", Name: "色达", Label: "色达", HasPage: false},
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
		ID              string    `bson:"_id"`
		Title           string    `bson:"title"`
		Angle           string    `bson:"angle"`
		EntityRefs      []string  `bson:"entityRefs"`
		TagRefs         []string  `bson:"tagRefs"`
		Body            string    `bson:"body"`
		Summary         string    `bson:"summary"`
		ArticleMarkdown string    `bson:"articleMarkdown"`
		ArticleTemplate string    `bson:"articleTemplate"`
		MarkdownDigest  string    `bson:"articleMarkdownDigest"`
		SourceTaskId    string    `bson:"sourceTaskId"`
		CreatedAt       time.Time `bson:"createdAt"`
		UpdatedAt       time.Time `bson:"updatedAt"`
	}
	if err := coll.FindOne(ctx, bson.M{"postRef": "posts/article/体验/甲居藏寨体验/1"}).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if got.Title != "甲居藏寨体验" || got.Angle != "体验" || got.ArticleMarkdown == "" {
		t.Fatalf("fields wrong: %+v", got)
	}
	if got.ID != "posts/article/体验/甲居藏寨体验/1" {
		t.Fatalf("post _id must use stable postRef, got %q", got.ID)
	}
	if len(got.EntityRefs) != 1 || got.EntityRefs[0] != "地点/景区/甲居藏寨" {
		t.Fatalf("entityRefs wrong: %+v", got.EntityRefs)
	}
	if len(got.TagRefs) != 1 || got.TagRefs[0] != "Topic/旅行" {
		t.Fatalf("tagRefs wrong: %+v", got.TagRefs)
	}
	if got.Body != got.ArticleMarkdown || got.Body == "" {
		t.Fatalf("body must mirror articleMarkdown for online read/search: %+v", got)
	}
	if got.Summary != "d1" || got.MarkdownDigest != "d1" {
		t.Fatalf("summary/digest must mirror articleDigest: %+v", got)
	}
	if got.ArticleTemplate != "journal" {
		t.Fatalf("articleTemplate must mirror template: %+v", got)
	}
	if got.SourceTaskId != "旅行/环线/川西环线/川西大环线自驾" {
		t.Fatalf("sourceTaskId not persisted: %q", got.SourceTaskId)
	}
	if got.CreatedAt.IsZero() || got.UpdatedAt.IsZero() {
		t.Fatalf("createdAt/updatedAt must be set: %+v", got)
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

	// 重跑同一批（更晚时间）：文档数不变；createdAt 不变；updatedAt 刷新。
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
	if !second.UpdatedAt.After(first.UpdatedAt) {
		t.Fatalf("updatedAt must advance: %v -> %v", first.UpdatedAt, second.UpdatedAt)
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
		SourceTaskId     string         `bson:"sourceTaskId"`
		ConditionProfile map[string]any `bson:"conditionProfile"`
	}
	if err := coll.FindOne(ctx, bson.M{"entityRef": "地点/景区/甲居藏寨"}).Decode(&withPage); err != nil {
		t.Fatal(err)
	}
	if !withPage.HasPage || withPage.Page == "" {
		t.Fatalf("甲居藏寨 should have page: %+v", withPage)
	}
	if withPage.SourceTaskId == "" || withPage.ConditionProfile == nil {
		t.Fatalf("entity sourceTaskId/conditionProfile not persisted: %+v", withPage)
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

func TestMongoUniqueIndexEnforced(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	coll := db.Collection("posts")
	EnsureUnique(ctx, coll, "postRef", "idx_post_ref")

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
		}
	}
	if !found {
		t.Fatalf("idx_post_ref index not created: %+v", idxs)
	}
}

func TestMongoLoadThenUpsertFromPublishTree(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()

	root := fixturePublish(t)
	// 只灌入 sample bundle 子集
	posts, err := LoadPosts(root, toSet([]string{"posts/article/攻略/色达攻略/1"}))
	if err != nil {
		t.Fatal(err)
	}
	ents, err := LoadEntities(root, toSet([]string{"地点/景区/色达"}))
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
		PostRef     string    `bson:"postRef"`
		Status      string    `bson:"status"`
		Visibility  string    `bson:"visibility"`
		PublishedAt time.Time `bson:"publishedAt"`
	}
	if err := pc.FindOne(ctx, bson.M{"postRef": "posts/article/攻略/色达攻略/1"}).Decode(&inserted); err != nil {
		t.Fatal(err)
	}
	if inserted.Status != "published" || inserted.Visibility != "public" {
		t.Fatalf("post must be searchable/discoverable (published/public): %+v", inserted)
	}
	if inserted.PublishedAt.IsZero() {
		t.Fatalf("post publishedAt must be populated: %+v", inserted)
	}
}

// TestMongoUpsertDiscoveryFeed 验证 Path A 同写 rm_discovery_feed：
// postId=postRef、status/visibility 可召回、sourceTaskId 透传、conditionProfile 从主实体 join 冗余。
func TestMongoUpsertDiscoveryFeed(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()

	root := fixturePublish(t)
	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	ents, err := LoadEntities(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	feed := db.Collection("rm_discovery_feed")
	n, err := UpsertDiscoveryFeed(ctx, feed, posts, conditionProfileIndex(ents), time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("want 2 feed items, got %d", n)
	}
	var item struct {
		PostId           string         `bson:"postId"`
		Status           string         `bson:"status"`
		Visibility       string         `bson:"visibility"`
		TagRefs          []string       `bson:"tagRefs"`
		SourceTaskId     string         `bson:"sourceTaskId"`
		ConditionProfile map[string]any `bson:"conditionProfile"`
		RecScore         float64        `bson:"recScore"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": "posts/article/体验/甲居藏寨体验/1"}).Decode(&item); err != nil {
		t.Fatal(err)
	}
	if item.Status != "published" || item.Visibility != "public" {
		t.Fatalf("feed item must be discoverable (published/public): %+v", item)
	}
	if item.SourceTaskId != "旅行/环线/川西环线/川西大环线自驾" {
		t.Fatalf("feed sourceTaskId missing: %+v", item)
	}
	if item.ConditionProfile == nil {
		t.Fatalf("feed conditionProfile not joined from entity: %+v", item)
	}
	if _, ok := item.ConditionProfile["altitudeMeters"]; !ok {
		t.Fatalf("conditionProfile.altitudeMeters missing: %+v", item.ConditionProfile)
	}
	// 无画像实体的文章：conditionProfile 应缺省（nil），不阻断 tag/hot/explore 召回。
	var second struct {
		Status       string `bson:"status"`
		SourceTaskId string `bson:"sourceTaskId"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": "posts/article/攻略/色达攻略/1"}).Decode(&second); err != nil {
		t.Fatal(err)
	}
	if second.Status != "published" {
		t.Fatalf("色达攻略 feed item not discoverable: %+v", second)
	}
}
