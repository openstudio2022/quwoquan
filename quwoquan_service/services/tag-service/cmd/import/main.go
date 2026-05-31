// Command import 把数据工程路径制 taxonomy（publish/tags 目录树）灌入 mongo tag_nodes。
// 唯一标签真相源为 publish/tags（单一发布主线）；本工具只读消费其目录结构，幂等 upsert，可重跑。
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type definition struct {
	Label   string `json:"label"`
	LabelEn string `json:"labelEn"`
}

var validGroups = map[string]bool{"Topic": true, "Entity": true, "Audience": true, "Format": true}

func main() {
	tagsDir := flag.String("tags-dir", "../quwoquan_data/publish/tags", "path to publish/tags directory tree")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	flag.Parse()

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	coll := client.Database(*dbName).Collection("tag_nodes")
	if _, err := coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "tagRef", Value: 1}},
		Options: options.Index().SetName("idx_tag_ref").SetUnique(true),
	}); err != nil {
		log.Printf("WARN: ensure idx_tag_ref: %v", err)
	}

	count := 0
	walkErr := filepath.WalkDir(*tagsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		name := d.Name()
		if name != "_definition.json" && name != "_group.json" {
			return nil
		}
		raw, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		var def definition
		if jerr := json.Unmarshal(raw, &def); jerr != nil {
			return jerr
		}
		rel, relErr := filepath.Rel(*tagsDir, filepath.Dir(path))
		if relErr != nil {
			return relErr
		}
		if rel == "." {
			return nil // 根 _taxonomy.json，无 tagRef
		}
		tagRef := filepath.ToSlash(rel)
		segs := strings.Split(tagRef, "/")
		group := segs[0]
		if !validGroups[group] {
			return nil
		}
		ancestors := ""
		if len(segs) > 1 {
			ancestors = strings.Join(segs[:len(segs)-1], "/")
		}
		now := time.Now().UTC()
		setDoc := bson.M{
			"tagRef":    tagRef,
			"group":     group,
			"label":     def.Label,
			"labelEn":   def.LabelEn,
			"aliases":   "",
			"ancestors": ancestors,
			"depth":     len(segs) - 1,
			"updatedAt": now,
		}
		if _, uerr := coll.UpdateOne(ctx,
			bson.M{"tagRef": tagRef},
			bson.M{"$set": setDoc, "$setOnInsert": bson.M{"createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); uerr != nil {
			return uerr
		}
		count++
		return nil
	})
	if walkErr != nil {
		log.Fatalf("walk tags dir: %v", walkErr)
	}
	log.Printf("OK: imported %d tag nodes into %s.tag_nodes", count, *dbName)
}
