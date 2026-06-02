// Command import 把 publish 主线的 posts/entities 灌入运行库（mongo）。
//
// 唯一内容真相源是 quwoquan_data/publish；本工具只读消费其目录树，按可选 sample bundle
// 过滤某环境子集，幂等 upsert 到 content/entity 两个库，可重跑。
//
// 用法:
//
//	go run ./services/content-service/cmd/import \
//	  --publish-root ../quwoquan_data/publish \
//	  --sample-bundle ../quwoquan_data/publish/sample_bundles/gamma.json \
//	  --mongo-uri mongodb://localhost:27017 --env gamma
package main

import (
	"context"
	"flag"
	"log"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func main() {
	publishRoot := flag.String("publish-root", "../quwoquan_data/publish", "path to publish mainline")
	sampleBundle := flag.String("sample-bundle", "", "optional sample bundle json (env subset); empty = full")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	postsDB := flag.String("posts-db", "quwoquan_content", "target db for posts")
	entitiesDB := flag.String("entities-db", "quwoquan_entity", "target db for entities")
	env := flag.String("env", "", "environment label (for logging)")
	dryRun := flag.Bool("dry-run", false, "load + report only, do not write mongo")
	flag.Parse()

	var postFilter, entityFilter map[string]bool
	if *sampleBundle != "" {
		bundle, err := loadSampleBundle(*sampleBundle)
		if err != nil {
			log.Fatalf("load sample bundle: %v", err)
		}
		postFilter = toSet(bundle.Posts)
		entityFilter = toSet(bundle.Entities)
	}

	posts, err := LoadPosts(*publishRoot, postFilter)
	if err != nil {
		log.Fatalf("load posts: %v", err)
	}
	entities, err := LoadEntities(*publishRoot, entityFilter)
	if err != nil {
		log.Fatalf("load entities: %v", err)
	}
	log.Printf("[import] env=%s loaded posts=%d entities=%d", *env, len(posts), len(entities))

	if *dryRun {
		log.Printf("[import] dry-run: not writing mongo")
		return
	}

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	postsColl := client.Database(*postsDB).Collection("posts")
	EnsureUnique(ctx, postsColl, "postRef", "idx_post_ref")
	entityColl := client.Database(*entitiesDB).Collection("entities")
	EnsureUnique(ctx, entityColl, "entityRef", "idx_entity_ref")

	now := time.Now().UTC()
	np, err := UpsertPosts(ctx, postsColl, posts, now)
	if err != nil {
		log.Fatalf("upsert posts: %v", err)
	}
	ne, err := UpsertEntities(ctx, entityColl, entities, now)
	if err != nil {
		log.Fatalf("upsert entities: %v", err)
	}

	// 同写发现流 ReadModel（rm_discovery_feed），让冷启动内容进入 tag/hot/explore 等召回通道；
	// 与在线 DiscoveryFeedProjector / BulkImport 路径字段一致（sourceTaskId + conditionProfile）。
	feedColl := client.Database(*postsDB).Collection("rm_discovery_feed")
	condByEntity := conditionProfileIndex(entities)
	nf, err := UpsertDiscoveryFeed(ctx, feedColl, posts, condByEntity, now)
	if err != nil {
		log.Fatalf("upsert discovery feed: %v", err)
	}
	log.Printf("[import] OK env=%s upserted posts=%d entities=%d discoveryFeed=%d", *env, np, ne, nf)
}

// EnsureUnique 幂等建唯一索引（已存在则忽略）。
func EnsureUnique(ctx context.Context, coll *mongo.Collection, key, name string) {
	if _, err := coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: key, Value: 1}},
		Options: options.Index().SetName(name).SetUnique(true),
	}); err != nil {
		log.Printf("WARN: ensure %s: %v", name, err)
	}
}

// UpsertPosts 幂等 upsert 文章到运行库；createdAt 仅插入时写，updatedAt 每次刷新。
func UpsertPosts(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time) (int, error) {
	n := 0
	for _, p := range posts {
		doc := bson.M{
			"postRef": p.PostRef, "contentType": p.ContentType, "title": p.Title,
			"angle": p.Angle, "seq": p.Seq, "entityRefs": p.EntityRefs, "tagRefs": p.TagRefs,
			"template": p.Template, "generatorModel": p.GeneratorModel, "articleTemplate": p.Template,
			"body": p.ArticleMarkdown, "summary": p.ArticleDigest,
			"articleMarkdown": p.ArticleMarkdown, "articleDigest": p.ArticleDigest, "articleMarkdownDigest": p.ArticleDigest,
			"sourceTaskId": p.SourceTaskId,
			// Path A 导入的 publish 主线文章默认视为已公开发布，保证
			// 在线 search/feed 与 rm_discovery_feed 的 discoverability 口径一致。
			"status":      "published",
			"visibility":  "public",
			"publishedAt": now,
			"updatedAt":   now,
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postRef": p.PostRef},
			bson.M{"$set": doc, "$setOnInsert": bson.M{"_id": p.PostRef, "createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

// UpsertEntities 幂等 upsert 实体到运行库。
func UpsertEntities(ctx context.Context, coll *mongo.Collection, entities []EntityDoc, now time.Time) (int, error) {
	n := 0
	for _, e := range entities {
		doc := bson.M{
			"entityRef": e.EntityRef, "domain": e.Domain, "etype": e.Etype, "name": e.Name,
			"label": e.Label, "tagRefs": e.TagRefs, "page": e.Page, "hasPage": e.HasPage,
			"conditionProfile": e.ConditionProfile, "sourceTaskId": e.SourceTaskId,
			"updatedAt": now,
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"entityRef": e.EntityRef},
			bson.M{"$set": doc, "$setOnInsert": bson.M{"createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

// conditionProfileIndex 建立 entityRef→conditionProfile 映射，供发现流投影按主实体冗余条件画像。
func conditionProfileIndex(entities []EntityDoc) map[string]map[string]any {
	idx := make(map[string]map[string]any, len(entities))
	for _, e := range entities {
		if len(e.ConditionProfile) > 0 {
			idx[e.EntityRef] = e.ConditionProfile
		}
	}
	return idx
}

// UpsertDiscoveryFeed 把发布主线内容同写发现流 ReadModel（rm_discovery_feed）。
// postId 用稳定 postRef；conditionProfile 取首个命中实体的画像冗余。
// status/visibility 固定 published/public（冷启动内容均为公开发布），保证召回可见。
// authorId/coverUrl 由 manifest 契约补齐（P1 produce 侧）后再透传；缺省留空不影响 tag/hot/explore 召回。
func UpsertDiscoveryFeed(ctx context.Context, coll *mongo.Collection, posts []PostDoc, condByEntity map[string]map[string]any, now time.Time) (int, error) {
	n := 0
	for _, p := range posts {
		var cond map[string]any
		for _, er := range p.EntityRefs {
			if c, ok := condByEntity[er]; ok {
				cond = c
				break
			}
		}
		set := bson.M{
			"postId":           p.PostRef,
			"title":            p.Title,
			"contentType":      p.ContentType,
			"contentIdentity":  "work",
			"tagRefs":          p.TagRefs,
			"entityRefs":       p.EntityRefs,
			"sourceTaskId":     p.SourceTaskId,
			"conditionProfile": cond,
			"status":           "published",
			"visibility":       "public",
			"publishedAt":      now,
			"updatedAt":        now,
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postId": p.PostRef},
			bson.M{"$set": set, "$setOnInsert": bson.M{
				"likeCount": int64(0), "commentCount": int64(0),
				"favoriteCount": int64(0), "viewCount": int64(0), "recScore": 0.0,
			}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}
