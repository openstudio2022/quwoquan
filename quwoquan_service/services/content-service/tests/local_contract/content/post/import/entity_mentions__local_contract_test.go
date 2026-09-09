// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-042
package releaseimport_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
	"unicode/utf16"

	"go.mongodb.org/mongo-driver/v2/bson"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func homepageProofFixture(t *testing.T) (string, string, ReleaseBinding, map[string]bool) {
	t.Helper()
	root := t.TempDir()
	binding := ReleaseBinding{ReleaseID: "release-mentions", SourceOwner: "qwq_data", ManifestDigest: "sha256:" + strings.Repeat("a", 64), ReleaseClass: "production"}
	entries := []map[string]string{{"entityRef": "opaque-a", "homepageId": "hp-from-entity-a"}, {"entityRef": "opaque-b", "homepageId": "hp-from-entity-b"}}
	// 测试显式写 Entity 的既有摘要序列，不借 Content 帮助函数自证。
	raw := []byte(`[{"entityRef":"opaque-a","homepageId":"hp-from-entity-a"},{"entityRef":"opaque-b","homepageId":"hp-from-entity-b"}]`)
	sum := sha256.Sum256(raw)
	digest := "sha256:" + hex.EncodeToString(sum[:])
	mapping := map[string]string{}
	for _, entry := range entries {
		mapping[entry["entityRef"]] = entry["homepageId"]
	}
	report := map[string]any{
		"schema": "quwoquan_service.homepage_import_report", "env": "alpha", "releaseId": binding.ReleaseID,
		"sourceOwner": binding.SourceOwner, "manifestDigest": binding.ManifestDigest, "dryRun": false,
		"expected": 2, "projected": 2, "projectionVersion": 17, "closureDigest": "sha256:" + strings.Repeat("b", 64),
		"entityRefMappingDigest": digest, "entityRefToHomepageId": mapping, "issues": []any{},
	}
	candidate := map[string]any{
		"schema": "quwoquan.homepage_release_candidate_receipt", "status": "found",
		"identity": map[string]string{"environment": "alpha", "sourceOwner": binding.SourceOwner, "releaseId": binding.ReleaseID, "manifestDigest": binding.ManifestDigest},
		"counts":   map[string]int{"expected": 2, "projected": 2}, "projectionVersion": 17,
		"closureDigest": report["closureDigest"], "entityRefMappingDigest": digest,
	}
	writeMentionJSON(t, filepath.Join(root, "report.json"), report)
	writeMentionJSON(t, filepath.Join(root, "candidate.json"), candidate)
	return filepath.Join(root, "report.json"), filepath.Join(root, "candidate.json"), binding, ToSet([]string{"opaque-a", "opaque-b"})
}

func writeMentionJSON(t *testing.T, path string, value any) {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestHomepageEntityMappingRequiresCandidateAuthenticatedReport(t *testing.T) {
	for _, test := range []struct {
		name   string
		report bool
		mutate func(map[string]any)
	}{
		{"report environment", true, func(p map[string]any) { p["env"] = "beta" }},
		{"report release", true, func(p map[string]any) { p["releaseId"] = "other" }},
		{"report owner", true, func(p map[string]any) { p["sourceOwner"] = "other" }},
		{"report manifest", true, func(p map[string]any) { p["manifestDigest"] = "sha256:" + strings.Repeat("c", 64) }},
		{"report dry-run", true, func(p map[string]any) { p["dryRun"] = true }},
		{"report missing dry-run", true, func(p map[string]any) { delete(p, "dryRun") }},
		{"report counts", true, func(p map[string]any) { p["projected"] = 1 }},
		{"report missing counts", true, func(p map[string]any) { delete(p, "expected") }},
		{"report closure", true, func(p map[string]any) { p["closureDigest"] = "sha256:" + strings.Repeat("c", 64) }},
		{"report version", true, func(p map[string]any) { p["projectionVersion"] = 18 }},
		{"report mapping", true, func(p map[string]any) { p["entityRefToHomepageId"].(map[string]any)["opaque-a"] = "hp-tampered" }},
		{"report duplicate homepage", true, func(p map[string]any) { p["entityRefToHomepageId"].(map[string]any)["opaque-a"] = "hp-from-entity-b" }},
		{"report incomplete mapping", true, func(p map[string]any) { delete(p["entityRefToHomepageId"].(map[string]any), "opaque-a") }},
		{"candidate status", false, func(p map[string]any) { p["status"] = "not_found" }},
		{"candidate tuple", false, func(p map[string]any) {
			p["identity"].(map[string]any)["manifestDigest"] = "sha256:" + strings.Repeat("c", 64)
		}},
		{"candidate count", false, func(p map[string]any) { p["counts"].(map[string]any)["expected"] = 1 }},
		{"candidate digest", false, func(p map[string]any) { p["entityRefMappingDigest"] = "sha256:" + strings.Repeat("c", 64) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			report, candidate, binding, refs := homepageProofFixture(t)
			path := candidate
			if test.report {
				path = report
			}
			raw, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var payload map[string]any
			if err := json.Unmarshal(raw, &payload); err != nil {
				t.Fatal(err)
			}
			test.mutate(payload)
			writeMentionJSON(t, path, payload)
			if _, err := LoadHomepageEntityMapping(report, candidate, binding, "alpha", false, refs); err == nil {
				t.Fatal("drifted proof was accepted")
			}
		})
	}
	report, candidate, binding, refs := homepageProofFixture(t)
	if _, err := LoadHomepageEntityMapping(report, "", binding, "alpha", false, refs); err == nil {
		t.Fatal("bare report accepted")
	}
	mapping, err := LoadHomepageEntityMapping("missing-report", "", binding, "alpha", true, refs)
	if err != nil || len(mapping) != 0 {
		t.Fatalf("dry-run invented a mapping: %v %v", mapping, err)
	}
	if _, err := LoadHomepageEntityMapping(report, candidate, binding, "alpha", true, refs); err == nil {
		t.Fatal("dry-run consumed candidate")
	}
}

func TestImportedArticleMentionsUseExplicitIdentityAndTypedQuery(t *testing.T) {
	report, candidate, binding, refs := homepageProofFixture(t)
	mapping, err := LoadHomepageEntityMapping(report, candidate, binding, "alpha", false, refs)
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	for _, entry := range []struct{ location, ref, id string }{
		{"地点/中国/四川省/成都市/青羊区/公园/p0003/人民公园/9", "opaque-a", "entity:stable-a"},
		{"地点/中国/广东省/广州市/越秀区/公园/p0001/人民公园/2", "opaque-b", "entity:stable-b"},
	} {
		writeMentionJSON(t, filepath.Join(root, "entities", entry.location, "manifest.json"), map[string]string{
			"entityId": entry.id, "entityRef": "/entity/" + entry.ref, "label": "人民公园",
		})
	}
	const markdown = "路过🙂@[人民公园](entity:stable-a)，再看[人民公园](/entity/opaque-b)，未知@[山](entity:missing)。\n`@[示例](entity:stable-a)`\n```\n@[代码](entity:stable-a)\n```\n"
	writeFile(t, filepath.Join(root, "posts/article/导览/p0002/两座公园/1/manifest.json"), `{"contentType":"article","publishTitle":"两座公园","publishedAt":"2026-09-09T00:00:00Z"}`)
	writeFile(t, filepath.Join(root, "posts/article/导览/p0002/两座公园/1/article.md"), markdown)
	posts, err := LoadPosts(root, nil, "production")
	if err != nil {
		t.Fatal(err)
	}
	if err := BindPostEntityMentions(posts, root, mapping); err != nil {
		t.Fatal(err)
	}
	if posts[0].ArticleMarkdown != markdown {
		t.Fatal("projection changed source markdown")
	}
	document, err := BuildCanonicalImportedPostDocument(posts[0], time.Now().UTC(), ImportOptions{ReleaseClass: "production"}, "active")
	if err != nil {
		t.Fatal(err)
	}
	raw, err := bson.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	var query postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &query); err != nil {
		t.Fatal(err)
	}
	mentions := query.EntityMentions
	if len(mentions) != 2 || mentions[0].SubjectID != "entity:stable-a" || mentions[0].HomepageID != "hp-from-entity-a" || mentions[1].SubjectID != "entity:stable-b" || mentions[1].HomepageID != "hp-from-entity-b" {
		t.Fatalf("real import -> typed query: %+v", mentions)
	}
	units := utf16.Encode([]rune(markdown))
	for _, mention := range mentions {
		if mention.SubjectType != "entity" || mention.DisplayName != "人民公园" || string(utf16.Decode(units[mention.RangeStart:mention.RangeEnd])) != mention.DisplayName {
			t.Fatalf("invalid character range: %+v", mention)
		}
	}
	if mentions[0].RangeStart != 6 {
		t.Fatalf("UTF-16 character start=%d want=6", mentions[0].RangeStart)
	}
	posts[0].ContentType = "image"
	if err := BindPostEntityMentions(posts, root, mapping); err != nil || len(posts[0].EntityMentions) != 0 {
		t.Fatal("article-only projection leaked to image")
	}
	posts[0].ContentType = "article"
	if err := BindPostEntityMentions(posts, root, nil); err != nil || len(posts[0].EntityMentions) != 0 || posts[0].ArticleMarkdown != markdown {
		t.Fatal("unresolved mentions must preserve original text without navigation")
	}
}
