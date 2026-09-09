// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001.t2
package runtimemedia

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type releaseMediaClosureFixtureAsset struct {
	AssetID string
	Kind    string
	MIME    string
	SHA256  string
	Owner   string
}

func writeReleaseMediaClosureJSON(t *testing.T, path string, value any) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
}

func releaseMediaClosureFixture(
	t *testing.T,
) (string, []releaseMediaClosureFixtureAsset) {
	t.Helper()
	root := t.TempDir()
	assets := []releaseMediaClosureFixtureAsset{
		{
			AssetID: "creator-avatar",
			Kind:    "avatar",
			MIME:    "image/webp",
			SHA256:  "sha256:" + strings.Repeat("1", 64),
			Owner:   "creators/creator-a",
		},
		{
			AssetID: "entity-cover",
			Kind:    "image",
			MIME:    "image/jpeg",
			SHA256:  "sha256:" + strings.Repeat("2", 64),
			Owner:   "entities/地点/景区/实体甲",
		},
		{
			AssetID: "article-inline",
			Kind:    "image",
			MIME:    "image/png",
			SHA256:  "sha256:" + strings.Repeat("3", 64),
			Owner:   "posts/article/攻略/实体甲/1",
		},
		{
			AssetID: "image-work",
			Kind:    "image",
			MIME:    "image/jpeg",
			SHA256:  "sha256:" + strings.Repeat("4", 64),
			Owner:   "posts/image/画报/实体甲/1",
		},
		{
			AssetID: "video-primary",
			Kind:    "video",
			MIME:    "video/mp4",
			SHA256:  "sha256:" + strings.Repeat("5", 64),
			Owner:   "posts/video/体验/实体甲/1",
		},
		{
			AssetID: "video-poster",
			Kind:    "image",
			MIME:    "image/webp",
			SHA256:  "sha256:" + strings.Repeat("6", 64),
			Owner:   "posts/video/体验/实体甲/1",
		},
	}

	rows := make([]map[string]any, 0, len(assets))
	ownerAssets := make(map[string][]map[string]any)
	for _, asset := range assets {
		sourceRef := "sources/" + asset.AssetID + "/source.json"
		rightsRef := "objects/" + asset.Owner + "/" + sourceRef
		sourcePath := filepath.Join(root, "payload", filepath.FromSlash(rightsRef))
		evidence := []byte("取得时的来源证据：" + asset.AssetID)
		writeReleaseMediaClosureJSON(t, sourcePath, map[string]any{
			"schema":        "quwoquan_data.publish_source",
			"sourceId":      asset.AssetID,
			"sourceUrl":     "https://source.example.com/" + asset.AssetID,
			"sourceUseMode": "licensed_adaptation",
			"fetchedAt":     "2026-09-09T00:00:00Z",
			"metadata":      map[string]any{"license": "原始取得记录"},
			"assets": []map[string]any{{
				"assetId": asset.AssetID, "licenseName": "CC BY 4.0",
				"accessPolicy": "open", "distributionDecision": "production_allowed",
				"rightsAuditStatus": "verified", "rightsAuditIssues": []string{},
			}},
			"evidence": []map[string]any{{
				"path": "evidence.html", "sha256": fmt.Sprintf("sha256:%x", sha256.Sum256(evidence)),
				"bytes": len(evidence), "kind": "source_snapshot",
			}},
		})
		if err := os.WriteFile(filepath.Join(filepath.Dir(sourcePath), "evidence.html"), evidence, 0o644); err != nil {
			t.Fatal(err)
		}
		ownerAssets[asset.Owner] = append(ownerAssets[asset.Owner], map[string]any{
			"assetId": asset.AssetID, "sha256": asset.SHA256,
			"bytes": 1, "path": "assets/" + asset.AssetID + ".bin",
			"sourceRefs": []string{sourceRef},
		})
		rows = append(rows, map[string]any{
			"assetId":     asset.AssetID,
			"kind":        asset.Kind,
			"version":     1,
			"contentType": asset.MIME,
			"publicSliceKey": BuildContentMediaPublicSliceKey(
				asset.Kind,
				asset.AssetID,
				1,
				asset.MIME,
			),
			"sha256":             asset.SHA256,
			"bytes":              1,
			"ownerRefs":          []string{asset.Owner},
			"rightsSnapshotRefs": []string{rightsRef},
		})
	}
	for owner, bindings := range ownerAssets {
		name := "manifest.json"
		if strings.HasPrefix(owner, "creators/") {
			name = "profile.json"
		}
		writeReleaseMediaClosureJSON(t, filepath.Join(root, "payload", "objects", filepath.FromSlash(owner), name), map[string]any{
			"assets": bindings,
		})
	}
	writeReleaseMediaClosureJSON(
		t,
		filepath.Join(root, "payload", "media_manifest.json"),
		map[string]any{
			"schema":      releaseMediaManifestSchema,
			"releaseId":   "release-geo-media",
			"sourceOwner": releaseMediaSourceOwner,
			"assets":      rows,
			"issues":      []string{},
			"counts": map[string]any{
				"assets": len(rows),
				"issues": 0,
			},
		},
	)
	return root, assets
}

func TestReleaseMediaAuthorityClosesAllGeoContentCarriers(t *testing.T) {
	root, expected := releaseMediaClosureFixture(t)
	assets, err := LoadReleaseMediaAssets(root, "release-geo-media", "production")
	if err != nil {
		t.Fatal(err)
	}
	if len(assets) != len(expected) {
		t.Fatalf("asset closure count = %d, want %d", len(assets), len(expected))
	}

	bases := MediaDeliveryBases{
		Avatar: "https://avatar.example.com",
		Image:  "https://image.example.com",
		Video:  "https://video.example.com",
	}
	for _, expectedAsset := range expected {
		resolved, resolveErr := ResolveReleaseMediaAsset(
			assets,
			bases,
			expectedAsset.AssetID,
			expectedAsset.Kind,
			expectedAsset.SHA256,
			expectedAsset.Owner,
		)
		if resolveErr != nil {
			t.Fatalf("%s: %v", expectedAsset.AssetID, resolveErr)
		}
		if resolved.PublicURL == "" ||
			!strings.HasPrefix(resolved.PublicURL, "https://") ||
			strings.Contains(resolved.PublicURL, "media/objects/sha256/") ||
			strings.Contains(resolved.PublicSliceKey, "media/objects/sha256/") {
			t.Fatalf(
				"%s did not resolve to a public-only slice: %+v",
				expectedAsset.AssetID,
				resolved,
			)
		}
	}
}

func mutateReleaseMediaClosureJSON(t *testing.T, root, ref string, mutate func(map[string]any)) {
	t.Helper()
	filePath := filepath.Join(root, "payload", filepath.FromSlash(ref))
	raw, err := os.ReadFile(filePath)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	mutate(document)
	writeReleaseMediaClosureJSON(t, filePath, document)
}

func firstReleaseMediaClosureAsset(document map[string]any) map[string]any {
	return document["assets"].([]any)[0].(map[string]any)
}

func TestReleaseMediaAuthorityRejectsBrokenRightsClosure(t *testing.T) {
	const source = "objects/creators/creator-a/sources/creator-avatar/source.json"
	const profile = "objects/creators/creator-a/profile.json"
	const entityManifest = "objects/entities/地点/景区/实体甲/manifest.json"
	tests := []struct {
		name, ref string
		mutate    func(map[string]any)
	}{
		{"source-owner-drift", "media_manifest.json", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["rightsSnapshotRefs"] = []string{"objects/entities/地点/景区/实体甲/sources/entity-cover/source.json"}
		}},
		{"owner-and-source-cannot-authorize-other-asset", "media_manifest.json", func(d map[string]any) {
			row := firstReleaseMediaClosureAsset(d)
			row["ownerRefs"] = []string{"entities/地点/景区/实体甲"}
			row["rightsSnapshotRefs"] = []string{"objects/entities/地点/景区/实体甲/sources/entity-cover/source.json"}
		}},
		{"owner-without-source", "media_manifest.json", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["ownerRefs"] = []string{"creators/creator-a", "entities/地点/景区/实体甲"}
		}},
		{"old-snapshot-ref-rejected", "media_manifest.json", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["rightsSnapshotRefs"] = []string{"objects/creators/creator-a/rights_snapshots/creator-avatar.json"}
		}},
		{"source-path-escape", "media_manifest.json", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["rightsSnapshotRefs"] = []string{"objects/creators/creator-a/sources/../creator-avatar/source.json"}
		}},
		{"profile-asset-drift", profile, func(d map[string]any) { firstReleaseMediaClosureAsset(d)["assetId"] = "other" }},
		{"manifest-asset-drift", entityManifest, func(d map[string]any) { firstReleaseMediaClosureAsset(d)["assetId"] = "other" }},
		{"profile-digest-drift", profile, func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["sha256"] = "sha256:" + strings.Repeat("f", 64)
		}},
		{"manifest-digest-drift", entityManifest, func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["sha256"] = "sha256:" + strings.Repeat("f", 64)
		}},
		{"source-not-adopted-by-asset", profile, func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["sourceRefs"] = []string{"sources/other/source.json"}
		}},
		{"asset-source-path-escape", profile, func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["sourceRefs"] = []string{"sources/../creator-avatar/source.json"}
		}},
		{"duplicate-asset-identity", profile, func(d map[string]any) { d["assets"] = append(d["assets"].([]any), firstReleaseMediaClosureAsset(d)) }},
		{"source-schema-drift", source, func(d map[string]any) { d["schema"] = "quwoquan_data.asset_rights_snapshot" }},
		{"source-id-drift", source, func(d map[string]any) { d["sourceId"] = "other" }},
		{"unknown-source-mode", source, func(d map[string]any) { d["sourceUseMode"] = "private" }},
		{"missing-metadata", source, func(d map[string]any) { delete(d, "metadata") }},
		{"null-assets", source, func(d map[string]any) { d["assets"] = nil }},
		{"null-asset-row", source, func(d map[string]any) { d["assets"] = []any{nil} }},
		{"unknown-source-field", source, func(d map[string]any) { d["generatedRights"] = true }},
		{"missing-evidence", source, func(d map[string]any) { d["evidence"] = []any{} }},
		{"evidence-path-escape", source, func(d map[string]any) { d["evidence"].([]any)[0].(map[string]any)["path"] = "../evidence.html" }},
		{"evidence-absolute-path", source, func(d map[string]any) { d["evidence"].([]any)[0].(map[string]any)["path"] = "/tmp/evidence.html" }},
		{"evidence-digest-drift", source, func(d map[string]any) {
			d["evidence"].([]any)[0].(map[string]any)["sha256"] = "sha256:" + strings.Repeat("f", 64)
		}},
		{"evidence-size-drift", source, func(d map[string]any) { d["evidence"].([]any)[0].(map[string]any)["bytes"] = 1 }},
		{"unknown-evidence-kind", source, func(d map[string]any) { d["evidence"].([]any)[0].(map[string]any)["kind"] = "generated_rights" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root, _ := releaseMediaClosureFixture(t)
			mutateReleaseMediaClosureJSON(t, root, test.ref, test.mutate)
			if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err == nil {
				t.Fatal("broken source closure must fail closed")
			}
		})
	}
}

func TestReleaseMediaAuthorityRejectsMissingOrEscapingSourceFiles(t *testing.T) {
	refs := []string{
		"media_manifest.json",
		"objects/creators/creator-a/profile.json",
		"objects/entities/地点/景区/实体甲/manifest.json",
		"objects/creators/creator-a/sources/creator-avatar/source.json",
		"objects/creators/creator-a/sources/creator-avatar/evidence.html",
		"objects/creators/creator-a/sources/creator-avatar",
	}
	for _, ref := range refs {
		for _, action := range []string{"missing", "symlink"} {
			t.Run(action+"/"+ref, func(t *testing.T) {
				root, _ := releaseMediaClosureFixture(t)
				filePath := filepath.Join(root, "payload", filepath.FromSlash(ref))
				outside := filepath.Join(t.TempDir(), "original")
				if err := os.Rename(filePath, outside); err != nil {
					t.Fatal(err)
				}
				if action == "symlink" {
					if err := os.Symlink(outside, filePath); err != nil {
						t.Fatal(err)
					}
				}
				if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err == nil {
					t.Fatal("missing file or symlink escape must fail closed")
				}
			})
		}
	}
}

func TestReleaseMediaSourcePreservesOriginalRightsWithoutInventingPublishedIdentity(t *testing.T) {
	root, _ := releaseMediaClosureFixture(t)
	mutateReleaseMediaClosureJSON(t, root, "objects/creators/creator-a/sources/creator-avatar/source.json", func(d map[string]any) {
		// source.assets 记录原始资产，而不是生成的发布资产 identity 副本。
		d["assets"] = []map[string]any{{
			"assetId": "original-source-image", "license": "原始许可事实",
			"accessPolicy": "tos_restricted", "watermarkStatus": "unknown",
			"derivedModifications": []string{"crop"},
		}}
	})
	if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err != nil {
		t.Fatalf("owner adoption must bind identity without rewriting original rights: %v", err)
	}
}

func TestReleaseMediaAuthorityRejectsTrailingDocuments(t *testing.T) {
	for _, ref := range []string{
		"media_manifest.json", "objects/creators/creator-a/profile.json",
		"objects/creators/creator-a/sources/creator-avatar/source.json",
	} {
		for _, trailing := range []string{"{}", "broken-json"} {
			t.Run(ref+"/"+trailing, func(t *testing.T) {
				root, _ := releaseMediaClosureFixture(t)
				filePath := filepath.Join(root, "payload", filepath.FromSlash(ref))
				file, err := os.OpenFile(filePath, os.O_APPEND|os.O_WRONLY, 0o644)
				if err != nil {
					t.Fatal(err)
				}
				if _, err := file.WriteString(trailing); err != nil {
					t.Fatal(err)
				}
				if err := file.Close(); err != nil {
					t.Fatal(err)
				}
				if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err == nil {
					t.Fatal("trailing JSON data must fail closed")
				}
			})
		}
	}
}
