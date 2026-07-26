// Command import-objects 把对象↔tagRef 倒排（object_tag_index）幂等灌入 mongo。
//
// 真相源是各源对象的 tagRefs（content.tagRefs / circle.tags / user.interestTags），
// 经数据工程生成 flat manifest，或由环境 seed manifest 显式选择 contract seed ref
// 后由本工具回填；
// object_tag_index 是派生倒排，幂等可重跑、可重建（删表后重灌得到同一结果）。
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"strings"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/application/importmanifest"
	persistence "quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
)

func main() {
	file := flag.String("objects-file", "", "path to object-tag manifest JSON (required)")
	seedRefs := flag.String("seed-refs", "", "comma-separated seed refs declared by the environment manifest")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	releaseID := flag.String("release-id", "", "data release id (required)")
	sourceOwner := flag.String("source-owner", "", "source owner for imported object tag index (required)")
	flag.Parse()
	objectsFile := strings.TrimSpace(*file)
	resolvedReleaseID := strings.TrimSpace(*releaseID)
	resolvedSourceOwner := strings.TrimSpace(*sourceOwner)
	if objectsFile == "" {
		log.Fatal("objects-file is required")
	}
	if resolvedReleaseID == "" {
		log.Fatal("release-id is required")
	}
	if resolvedSourceOwner == "" {
		log.Fatal("source-owner is required")
	}

	raw, err := os.ReadFile(objectsFile)
	if err != nil {
		log.Fatalf("read objects file: %v", err)
	}
	entries, err := importmanifest.Decode(raw, splitCSV(*seedRefs))
	if err != nil {
		log.Fatalf("parse objects file: %v", err)
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
		log.Fatalf("ensure indexes: %v", err)
	}

	count := 0
	for _, e := range entries {
		if err := store.UpsertObjectTagsFromRelease(
			ctx,
			e.ObjectID,
			e.ObjectType,
			e.TagRefs,
			resolvedReleaseID,
			resolvedSourceOwner,
		); err != nil {
			log.Fatalf("upsert %s/%s: %v", e.ObjectType, e.ObjectID, err)
		}
		count++
	}
	log.Printf("OK: upserted %d object_tag_index docs into %s.object_tag_index", count, *dbName)
}

func splitCSV(value string) []string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return strings.Split(value, ",")
}
