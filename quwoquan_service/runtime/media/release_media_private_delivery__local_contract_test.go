// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package runtimemedia

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func mutateReleaseDeliveryManifest(t *testing.T, root string, mutate func(map[string]any)) {
	t.Helper()
	path := filepath.Join(root, "payload", "media_manifest.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var manifest map[string]any
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	mutate(manifest)
	writeReleaseMediaClosureJSON(t, path, manifest)
}

func TestReleaseDeliveryRejectsPrivateAndNonCanonicalIdentities(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{
			name: "private-object-key-only",
			mutate: func(manifest map[string]any) {
				asset := manifest["assets"].([]any)[0].(map[string]any)
				delete(asset, "publicSliceKey")
				asset["privateObjectKey"] = "media/objects/sha256/aa/bb/source.jpg"
			},
		},
		{
			name: "private-object-key-alongside-public-slice",
			mutate: func(manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["privateObjectKey"] = "media/objects/sha256/aa/bb/source.jpg"
			},
		},
		{
			name: "private-key-as-public-slice",
			mutate: func(manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["publicSliceKey"] = "media/objects/sha256/aa/bb/source.jpg"
			},
		},
		{
			name: "missing-public-slice",
			mutate: func(manifest map[string]any) {
				delete(manifest["assets"].([]any)[0].(map[string]any), "publicSliceKey")
			},
		},
		{
			name: "public-slice-identity-drift",
			mutate: func(manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["publicSliceKey"] = BuildContentMediaPublicSliceKey("avatar", "other-avatar", 1, "image/webp")
			},
		},
		{
			name: "retired-release-class",
			mutate: func(manifest map[string]any) {
				manifest["releaseClass"] = "research"
			},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			root, _ := releaseMediaClosureFixture(t)
			mutateReleaseDeliveryManifest(t, root, test.mutate)
			if _, err := LoadReleaseMediaAssets(root, "release-geo-media"); err == nil {
				t.Fatal("retired or non-canonical release delivery must fail closed")
			}
		})
	}
}

func TestReleasePublicDeliveryPreservesUnverifiedRightsRecords(t *testing.T) {
	for _, status := range []string{"unverified", "unknown", "restricted"} {
		t.Run(status, func(t *testing.T) {
			root, expected := releaseMediaClosureFixture(t)
			asset := expected[0]
			rightsPath := filepath.Join(root, "payload", "objects", filepath.FromSlash(asset.Owner), "rights_snapshots", asset.AssetID+".json")
			writeReleaseMediaClosureJSON(t, rightsPath, map[string]any{
				"assetId":       asset.AssetID,
				"manifestAsset": map[string]any{"assetId": asset.AssetID, "sha256": asset.SHA256},
				"rightsStatus":  status, "authorizationRequired": true,
				"distributionDecision": "blocked", "usageScope": "research",
			})
			before, err := os.ReadFile(rightsPath)
			if err != nil {
				t.Fatal(err)
			}
			assets, err := LoadReleaseMediaAssets(root, "release-geo-media")
			if err != nil {
				t.Fatalf("rights records must not select a release delivery class: %v", err)
			}
			resolved, err := ResolveReleaseMediaAsset(assets, MediaDeliveryBases{Avatar: "https://avatar.example.com"}, asset.AssetID, asset.Kind, asset.SHA256, asset.Owner)
			if err != nil {
				t.Fatal(err)
			}
			wantURL := BuildPublicMediaURL("https://avatar.example.com", assets[asset.AssetID].PublicSliceKey, 1)
			if wantURL == "" || resolved.PublicURL != wantURL || resolved.DeliveryRef != wantURL {
				t.Fatalf("release asset must resolve to canonical public delivery: %+v", resolved)
			}
			after, err := os.ReadFile(rightsPath)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(before, after) {
				t.Fatal("public delivery must not rewrite immutable rights records")
			}
		})
	}
}

func TestReleasePublicDeliveryAllowsSharedDigestWithDistinctAssetSlices(t *testing.T) {
	root, expected := releaseMediaClosureFixture(t)
	sharedSHA := expected[1].SHA256
	second := expected[3]
	mutateReleaseDeliveryManifest(t, root, func(manifest map[string]any) {
		manifest["assets"].([]any)[3].(map[string]any)["sha256"] = sharedSHA
	})
	writeReleaseMediaClosureJSON(t,
		filepath.Join(root, "payload", "objects", filepath.FromSlash(second.Owner), "rights_snapshots", second.AssetID+".json"),
		map[string]any{
			"assetId":       second.AssetID,
			"manifestAsset": map[string]any{"assetId": second.AssetID, "sha256": sharedSHA},
		},
	)
	assets, err := LoadReleaseMediaAssets(root, "release-geo-media")
	if err != nil {
		t.Fatalf("shared content digest with distinct asset identities must remain valid: %v", err)
	}
	firstAsset, secondAsset := assets[expected[1].AssetID], assets[second.AssetID]
	if len(assets) != len(expected) || firstAsset.SHA256 != secondAsset.SHA256 ||
		firstAsset.PublicSliceKey == secondAsset.PublicSliceKey {
		t.Fatalf("shared bytes must keep independent public asset identities: first=%+v second=%+v", firstAsset, secondAsset)
	}
}
