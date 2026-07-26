// Command import 把数据工程 control-plane 路径制 taxonomy 灌入 mongo tag_nodes，
// 并按 TagTaxonomyRelease 聚合落发布记录：相同 release identity + canonicalDigest
// 才能幂等 Stage → 单 active CAS Activate；不同 release identity 不得复用快照。
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

	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	persistence "quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
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
	ancestors    []string
	depth        int
}

var validGroups = map[string]bool{"Topic": true, "Entity": true, "Audience": true, "Format": true}

func main() {
	tagsDir := flag.String("tags-dir", "../quwoquan_data/control_plane/governance/taxonomy", "path to canonical control-plane taxonomy tree")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	dbName := flag.String("db", "quwoquan_tag", "target database")
	releaseID := flag.String("release-id", "", "immutable taxonomy release id (required; must match the consuming catalog)")
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
	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("ensure tag_taxonomy_releases indexes: %v", err)
	}
	if err := store.MigrateSnapshotIdentity(ctx); err != nil {
		log.Fatalf("migrate tag_nodes snapshot identity: %v", err)
	}
	releaseFacade, err := taxonomyrelease.NewFacade(releaseStore, store)
	if err != nil {
		log.Fatalf("taxonomy release facade: %v", err)
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
		log.Fatal("release-id is required so the staged taxonomy snapshot can bind to its consuming catalog")
	}

	// Stage：只有相同 release identity 的同 digest 重放可复用既有 release。
	release, err := releaseFacade.Stage(ctx, taxonomyrelease.StageCommand{
		ReleaseID:       resolvedReleaseID,
		SourceOwner:     *sourceOwner,
		CanonicalDigest: digest,
		NodeCount:       len(nodes),
	})
	if err != nil {
		log.Fatalf("stage taxonomy release: %v", err)
	}

	// 第二趟：以 release.ReleaseID（可能是幂等复用的首个 id）写入不可变快照。
	// 身份始终是 (releaseId, tagRef)，绝不按全局 tagRef 覆盖旧快照。
	count := 0
	for _, node := range nodes {
		if err := insertSnapshotNode(ctx, coll, release.ReleaseID, node); err != nil {
			log.Fatalf("write tag snapshot node %s/%s: %v", release.ReleaseID, node.tagRef, err)
		}
		count++
	}
	snapshotCount, err := coll.CountDocuments(ctx, bson.M{"releaseId": release.ReleaseID})
	if err != nil {
		log.Fatalf("count staged taxonomy snapshot: %v", err)
	}
	if snapshotCount != int64(len(nodes)) {
		log.Fatalf(
			"staged taxonomy snapshot incomplete or inconsistent: release=%s expected=%d actual=%d",
			release.ReleaseID, len(nodes), snapshotCount,
		)
	}

	// 仅完整 staged snapshot 写入成功后才切换 active；已 active 时 no-op 重放安全。
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
		ancestors := make([]string, 0, len(segs)-1)
		if len(segs) > 1 {
			parentTagRef = strings.Join(segs[:len(segs)-1], "/")
			for i := 1; i < len(segs); i++ {
				ancestors = append(ancestors, strings.Join(segs[:i], "/"))
			}
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

func insertSnapshotNode(
	ctx context.Context,
	coll *mongo.Collection,
	releaseID string,
	node taxonomyNode,
) error {
	now := time.Now().UTC()
	expected := model.TagNode{
		TagRef:          node.tagRef,
		Group:           node.group,
		Label:           node.label,
		DisplayLabel:    displayLabelForTag(node.label),
		LabelEn:         node.labelEn,
		Aliases:         []string{},
		Ancestors:       append([]string(nil), node.ancestors...),
		ParentTagRef:    node.parentTagRef,
		Depth:           node.depth,
		ReleaseID:       releaseID,
		LifecycleStatus: "active",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	_, err := coll.InsertOne(ctx, expected)
	if err == nil {
		return nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return err
	}

	var existing model.TagNode
	if err := coll.FindOne(ctx, bson.M{
		"releaseId": releaseID,
		"tagRef":    node.tagRef,
	}).Decode(&existing); err != nil {
		return fmt.Errorf("load duplicate snapshot node: %w", err)
	}
	if !sameSnapshotNode(existing, expected) {
		return fmt.Errorf("existing snapshot node conflicts with immutable release identity")
	}
	return nil
}

func sameSnapshotNode(actual, expected model.TagNode) bool {
	return actual.TagRef == expected.TagRef &&
		actual.Group == expected.Group &&
		actual.Label == expected.Label &&
		actual.DisplayLabel == expected.DisplayLabel &&
		actual.LabelEn == expected.LabelEn &&
		actual.ParentTagRef == expected.ParentTagRef &&
		actual.Depth == expected.Depth &&
		actual.ReleaseID == expected.ReleaseID &&
		actual.LifecycleStatus == expected.LifecycleStatus &&
		sameStrings(actual.Aliases, expected.Aliases) &&
		sameStrings(actual.Ancestors, expected.Ancestors)
}

func sameStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
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
