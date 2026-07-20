// Command import 把数据工程 control-plane 路径制 taxonomy 灌入 mongo tag_nodes，
// 并按 TagTaxonomyRelease 聚合落发布记录：canonicalDigest（节点树内容哈希）幂等
// Stage → 单 active CAS Activate。同一 taxonomy 重复导入不产生第二个 release。
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/application/taxonomyrelease"
	persistence "quwoquan_service/services/tag-service/internal/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/infrastructure/taxonomyreleasestore"
)

type definition struct {
	Label   string `json:"label"`
	LabelEn string `json:"labelEn"`
}

type taxonomyNode struct {
	tagRef       string
	group        string
	label        string
	labelEn      string
	parentTagRef string
	ancestors    string
	depth        int
}

var validGroups = map[string]bool{"Topic": true, "Entity": true, "Audience": true, "Format": true}

func main() {
	tagsDir := flag.String("tags-dir", "../quwoquan_data/control_plane/governance/taxonomy", "path to canonical control-plane taxonomy tree")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	releaseID := flag.String("release-id", "", "data release id (default: derived from content digest)")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported tag nodes")
	flag.Parse()

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	db := client.Database(*dbName)
	coll := db.Collection("tag_nodes")
	store := persistence.NewMongoTagNodeStore(coll)
	if err := store.EnsureIndexes(ctx); err != nil {
		log.Printf("WARN: ensure tag_nodes indexes: %v", err)
	}

	// 第一趟：收集全部节点并计算 canonical digest（节点集内容哈希，顺序无关）。
	nodes, err := collectTaxonomyNodes(*tagsDir)
	if err != nil {
		log.Fatalf("collect taxonomy nodes: %v", err)
	}
	if len(nodes) == 0 {
		log.Fatalf("taxonomy tree %s has no importable nodes", *tagsDir)
	}
	digest := canonicalDigest(nodes)
	resolvedReleaseID := strings.TrimSpace(*releaseID)
	if resolvedReleaseID == "" {
		resolvedReleaseID = "taxonomy-" + digest[:16]
	}

	// Stage：同 digest 重复导入幂等复用首个 release（含其 releaseId）。
	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		log.Printf("WARN: ensure tag_taxonomy_releases indexes: %v", err)
	}
	releaseFacade, err := taxonomyrelease.NewFacade(releaseStore)
	if err != nil {
		log.Fatalf("taxonomy release facade: %v", err)
	}
	release, err := releaseFacade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID:       resolvedReleaseID,
		SourceOwner:     *sourceOwner,
		CanonicalDigest: digest,
		NodeCount:       len(nodes),
	})
	if err != nil {
		log.Fatalf("stage taxonomy release: %v", err)
	}

	// 第二趟：以 release.ReleaseID（可能是幂等复用的首个 id）灌节点。
	count := 0
	for _, node := range nodes {
		now := time.Now().UTC()
		setDoc := bson.M{
			"tagRef":               node.tagRef,
			"group":                node.group,
			"label":                node.label,
			"displayLabel":         displayLabelForTag(node.label),
			"labelEn":              node.labelEn,
			"aliases":              "",
			"ancestors":            node.ancestors,
			"parentTagRef":         node.parentTagRef,
			"depth":                node.depth,
			"updatedAt":            now,
			"releaseId":            release.ReleaseID,
			"visibleFromReleaseId": release.ReleaseID,
			"sourceOwner":          *sourceOwner,
			"lifecycleStatus":      "active",
		}
		if _, uerr := coll.UpdateOne(ctx,
			bson.M{"tagRef": node.tagRef},
			bson.M{"$set": setDoc, "$setOnInsert": bson.M{"createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); uerr != nil {
			log.Fatalf("upsert tag node %s: %v", node.tagRef, uerr)
		}
		count++
	}

	// Activate：单 active CAS 切换；已 active 时 no-op 重放安全。
	activated, err := releaseFacade.Activate(ctx, release.ReleaseID)
	if err != nil {
		log.Fatalf("activate taxonomy release %s: %v", release.ReleaseID, err)
	}
	log.Printf("OK: imported %d tag nodes into %s.tag_nodes (release=%s digest=%s status=%s)",
		count, *dbName, activated.ReleaseID, digest[:16], activated.Status)
}

// collectTaxonomyNodes 遍历目录树收集全部合法节点。
func collectTaxonomyNodes(tagsDir string) ([]taxonomyNode, error) {
	var nodes []taxonomyNode
	walkErr := filepath.WalkDir(tagsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		name := d.Name()
		if name != "_definition.json" &&
			name != "_group.json" &&
			name != "_dimension.json" {
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
		rel, relErr := filepath.Rel(tagsDir, filepath.Dir(path))
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
		nodes = append(nodes, taxonomyNode{
			tagRef:       tagRef,
			group:        group,
			label:        def.Label,
			labelEn:      def.LabelEn,
			parentTagRef: parentTagRef,
			ancestors:    ancestors,
			depth:        len(segs) - 1,
		})
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].tagRef < nodes[j].tagRef })
	return nodes, nil
}

// canonicalDigest 对排序后的节点集算内容哈希（releaseId 无关，纯内容身份）。
func canonicalDigest(nodes []taxonomyNode) string {
	hasher := sha256.New()
	for _, node := range nodes {
		fmt.Fprintf(hasher, "%s\x00%s\x00%s\x00%s\x00%s\x00%d\n",
			node.tagRef, node.group, node.label, node.labelEn, node.parentTagRef, node.depth)
	}
	return hex.EncodeToString(hasher.Sum(nil))
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
