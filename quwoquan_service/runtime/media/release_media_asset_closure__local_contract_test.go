// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001
package runtimemedia

import (
	"encoding/json"
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
	for _, asset := range assets {
		rightsRef := "objects/" + asset.Owner +
			"/rights_snapshots/" + asset.AssetID + ".json"
		writeReleaseMediaClosureJSON(
			t,
			filepath.Join(
				root,
				"payload",
				filepath.FromSlash(rightsRef),
			),
			map[string]any{
				"schema":  "quwoquan_data.asset_rights_snapshot",
				"assetId": asset.AssetID,
				"manifestAsset": map[string]any{
					"assetId": asset.AssetID,
					"sha256":  asset.SHA256,
				},
			},
		)
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
	assets, err := LoadReleaseMediaAssets(root, "release-geo-media")
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

func TestReleaseMediaAuthorityRejectsBrokenRightsClosure(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(t *testing.T, root string)
	}{
		{
			name: "missing-rights-snapshot",
			mutate: func(t *testing.T, root string) {
				t.Helper()
				if err := os.Remove(filepath.Join(
					root,
					"payload",
					"objects",
					"creators",
					"creator-a",
					"rights_snapshots",
					"creator-avatar.json",
				)); err != nil {
					t.Fatal(err)
				}
			},
		},
		{
			name: "rights-identity-drift",
			mutate: func(t *testing.T, root string) {
				t.Helper()
				path := filepath.Join(
					root,
					"payload",
					"objects",
					"entities",
					"地点",
					"景区",
					"实体甲",
					"rights_snapshots",
					"entity-cover.json",
				)
				writeReleaseMediaClosureJSON(t, path, map[string]any{
					"assetId": "other",
					"manifestAsset": map[string]any{
						"assetId": "other",
						"sha256":  "sha256:" + strings.Repeat("2", 64),
					},
				})
			},
		},
		{
			name: "rights-path-escape",
			mutate: func(t *testing.T, root string) {
				t.Helper()
				path := filepath.Join(root, "payload", "media_manifest.json")
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				var document map[string]any
				if err := json.Unmarshal(raw, &document); err != nil {
					t.Fatal(err)
				}
				row := document["assets"].([]any)[0].(map[string]any)
				row["rightsSnapshotRefs"] = []string{
					"objects/creators/creator-a/rights_snapshots/../avatar.json",
				}
				writeReleaseMediaClosureJSON(t, path, document)
			},
		},
		{
			name: "rights-owner-drift",
			mutate: func(t *testing.T, root string) {
				t.Helper()
				path := filepath.Join(root, "payload", "media_manifest.json")
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				var document map[string]any
				if err := json.Unmarshal(raw, &document); err != nil {
					t.Fatal(err)
				}
				row := document["assets"].([]any)[0].(map[string]any)
				row["rightsSnapshotRefs"] = []string{
					"objects/entities/地点/景区/实体甲/rights_snapshots/entity-cover.json",
				}
				writeReleaseMediaClosureJSON(t, path, document)
			},
		},
		{
			name: "owner-without-rights",
			mutate: func(t *testing.T, root string) {
				t.Helper()
				path := filepath.Join(root, "payload", "media_manifest.json")
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				var document map[string]any
				if err := json.Unmarshal(raw, &document); err != nil {
					t.Fatal(err)
				}
				row := document["assets"].([]any)[0].(map[string]any)
				row["ownerRefs"] = []string{
					"creators/creator-a",
					"entities/地点/景区/实体甲",
				}
				writeReleaseMediaClosureJSON(t, path, document)
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root, _ := releaseMediaClosureFixture(t)
			test.mutate(t, root)
			if _, err := LoadReleaseMediaAssets(
				root,
				"release-geo-media",
			); err == nil {
				t.Fatal("broken rights closure must fail closed")
			}
		})
	}
}
