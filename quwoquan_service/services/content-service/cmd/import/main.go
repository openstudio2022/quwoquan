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
	log.Printf("[import] OK env=%s upserted posts=%d entities=%d", *env, np, ne)
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
			"template": p.Template, "generatorModel": p.GeneratorModel,
			"articleMarkdown": p.ArticleMarkdown, "articleDigest": p.ArticleDigest,
			"updatedAt": now,
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postRef": p.PostRef},
			bson.M{"$set": doc, "$setOnInsert": bson.M{"createdAt": now}},
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
