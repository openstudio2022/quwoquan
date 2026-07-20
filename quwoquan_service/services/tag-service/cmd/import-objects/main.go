// Command import-objects 把对象↔tagRef 倒排（object_tag_index）幂等灌入 mongo。
//
// 真相源是各源对象的 tagRefs（content.tagRefs / circle.tags / user.interestTags），
// 经数据工程或 contract fixture 聚合为 manifest 后由本工具回填；
// object_tag_index 是派生倒排，幂等可重跑、可重建（删表后重灌得到同一结果）。
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	persistence "quwoquan_service/services/tag-service/internal/infrastructure/persistence"
)

type objectTagEntry struct {
	ObjectID   string   `json:"objectId"`
	ObjectType string   `json:"objectType"`
	TagRefs    []string `json:"tagRefs"`
}

// manifest 支持三种 JSON 形态，统一抽取 object_tag_index 条目：
//  1. {"seedSets": {"<name>": {"object_tag_index": [ ... ]}}}（contract fixture，gamma/演示同源）
//  2. {"object_tag_index": [ ... ]}（扁平 manifest，数据工程产出）
//  3. [ ... ]（纯数组）
type manifest struct {
	SeedSets       map[string]scenarioBlock `json:"seedSets"`
	ObjectTagIndex []objectTagEntry         `json:"object_tag_index"`
}

type scenarioBlock struct {
	ObjectTagIndex []objectTagEntry `json:"object_tag_index"`
}

func extractEntries(raw []byte) ([]objectTagEntry, error) {
	var arr []objectTagEntry
	if err := json.Unmarshal(raw, &arr); err == nil && len(arr) > 0 {
		return arr, nil
	}
	var m manifest
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, err
	}
	out := append([]objectTagEntry(nil), m.ObjectTagIndex...)
	for _, sc := range m.SeedSets {
		out = append(out, sc.ObjectTagIndex...)
	}
	return out, nil
}

func main() {
	file := flag.String("objects-file", "contracts/metadata/tag/test_fixtures/scenarios/tag_scenarios.json", "path to object-tag manifest JSON (contract fixture or flat manifest)")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	releaseID := flag.String("release-id", "adhoc", "data release id")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported object tag index")
	flag.Parse()

	raw, err := os.ReadFile(*file)
	if err != nil {
		log.Fatalf("read objects file: %v", err)
	}
	entries, err := extractEntries(raw)
	if err != nil {
		log.Fatalf("parse objects file: %v", err)
	}
	if len(entries) == 0 {
		log.Fatalf("no object_tag_index entries found in %s", *file)
	}

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	coll := client.Database(*dbName).Collection("object_tag_index")
	store := persistence.NewMongoObjectTagIndexStore(coll)
	if err := store.EnsureIndexes(ctx); err != nil {
		log.Printf("WARN: ensure indexes: %v", err)
	}

	count := 0
	for _, e := range entries {
		if e.ObjectID == "" || e.ObjectType == "" {
			log.Printf("WARN: skip entry with empty objectId/objectType: %+v", e)
			continue
		}
		if err := store.UpsertObjectTags(ctx, e.ObjectID, e.ObjectType, e.TagRefs); err != nil {
			log.Fatalf("upsert %s/%s: %v", e.ObjectType, e.ObjectID, err)
		}
		now := time.Now().UTC()
		if _, err := coll.UpdateOne(ctx,
			bson.M{"objectId": e.ObjectID, "objectType": e.ObjectType},
			bson.M{"$set": bson.M{
				"releaseId": *releaseID, "visibleFromReleaseId": *releaseID,
				"sourceOwner": *sourceOwner, "lifecycleStatus": "active",
				"releaseUpdatedAt": now,
			}},
		); err != nil {
			log.Fatalf("annotate release %s/%s: %v", e.ObjectType, e.ObjectID, err)
		}
		count++
	}
	log.Printf("OK: upserted %d object_tag_index docs into %s.object_tag_index", count, *dbName)
}
