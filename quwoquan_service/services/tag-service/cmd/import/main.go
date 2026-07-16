// Command import 把数据工程 control-plane 路径制 taxonomy 灌入 mongo tag_nodes。
// 本工具只读消费 canonical taxonomy 目录结构，幂等 upsert，可重跑。
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

	persistence "quwoquan_service/services/tag-service/internal/infrastructure/persistence"
)

type definition struct {
	Label   string `json:"label"`
	LabelEn string `json:"labelEn"`
}

var validGroups = map[string]bool{"Topic": true, "Entity": true, "Audience": true, "Format": true}

func main() {
	tagsDir := flag.String("tags-dir", "../quwoquan_data/control_plane/governance/taxonomy", "path to canonical control-plane taxonomy tree")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	releaseID := flag.String("release-id", "adhoc", "data release id")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported tag nodes")
	flag.Parse()

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	coll := client.Database(*dbName).Collection("tag_nodes")
	store := persistence.NewMongoTagNodeStore(coll)
	if err := store.EnsureIndexes(ctx); err != nil {
		log.Printf("WARN: ensure tag_nodes indexes: %v", err)
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
		parentTagRef := ""
		ancestors := ""
		if len(segs) > 1 {
			parentTagRef = strings.Join(segs[:len(segs)-1], "/")
			ancestors = parentTagRef
		}
		now := time.Now().UTC()
		setDoc := bson.M{
			"tagRef":               tagRef,
			"group":                group,
			"label":                def.Label,
			"displayLabel":         displayLabelForTag(def.Label),
			"labelEn":              def.LabelEn,
			"aliases":              "",
			"ancestors":            ancestors,
			"parentTagRef":         parentTagRef,
			"depth":                len(segs) - 1,
			"updatedAt":            now,
			"releaseId":            *releaseID,
			"visibleFromReleaseId": *releaseID,
			"sourceOwner":          *sourceOwner,
			"lifecycleStatus":      "active",
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

func displayLabelForTag(label string) string {
	trimmed := strings.TrimSpace(label)
	if trimmed == "" {
		return ""
	}
	replacements := map[string]string{
		"广西壮族自治区":  "广西",
		"宁夏回族自治区":  "宁夏",
		"新疆维吾尔自治区": "新疆",
		"内蒙古自治区":   "内蒙古",
		"西藏自治区":    "西藏",
		"香港特别行政区":  "香港",
		"澳门特别行政区":  "澳门",
	}
	if value, ok := replacements[trimmed]; ok {
		return value
	}
	for _, suffix := range []string{
		"朝鲜族自治州",
		"蒙古自治州",
		"藏族自治州",
		"回族自治州",
		"哈尼族彝族自治州",
		"壮族苗族自治州",
		"土家族苗族自治州",
		"傣族自治州",
		"白族自治州",
		"傈僳族自治州",
		"自治州",
		"地区",
		"盟",
		"特别行政区",
		"自治区",
		"省",
		"市",
		"区",
		"县",
	} {
		if strings.HasSuffix(trimmed, suffix) && len([]rune(trimmed)) > len([]rune(suffix)) {
			return strings.TrimSuffix(trimmed, suffix)
		}
	}
	return trimmed
}
