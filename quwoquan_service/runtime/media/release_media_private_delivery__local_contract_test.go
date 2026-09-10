// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039
package runtimemedia

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func TestReleaseDeliveryRejectsPrivateAndNonCanonicalIdentities(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"private-object-key-only", func(d map[string]any) {
			asset := firstReleaseMediaClosureAsset(d)
			delete(asset, "publicSliceKey")
			asset["privateObjectKey"] = "media/objects/sha256/aa/bb/source.jpg"
		}},
		{"private-key-as-public-slice", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["publicSliceKey"] = "media/objects/sha256/aa/bb/source.jpg"
		}},
		{"missing-public-slice", func(d map[string]any) { delete(firstReleaseMediaClosureAsset(d), "publicSliceKey") }},
		{"public-slice-identity-drift", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["publicSliceKey"] = BuildContentMediaPublicSliceKey("avatar", "other-avatar", 1, "image/webp")
		}},
		{"retired-release-class", func(d map[string]any) { d["releaseClass"] = "production" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			root, _ := releaseMediaClosureFixture(t)
			mutateReleaseMediaClosureJSON(t, root, "media_manifest.json", test.mutate)
			if _, err := LoadReleaseMediaAssets(root, "release-geo-media"); err == nil {
				t.Fatal("retired or non-canonical release delivery must fail closed")
			}
		})
	}
}

func TestReleaseMediaRejectsPrivateObjectKeyEvenEmpty(t *testing.T) {
	for _, value := range []any{nil, "", "media/objects/sha256/aa/aa/private.jpg"} {
		root, _ := releaseMediaClosureFixture(t)
		mutateReleaseMediaClosureJSON(t, root, "media_manifest.json", func(d map[string]any) {
			firstReleaseMediaClosureAsset(d)["privateObjectKey"] = value
		})
		if _, err := LoadReleaseMediaAssets(root, "release-geo-media"); err == nil {
			t.Fatalf("retired privateObjectKey=%v must be rejected, not ignored", value)
		}
	}
}

func TestReleasePublicDeliveryPreservesUnverifiedRightsRecords(t *testing.T) {
	for _, status := range []string{"unverified", "unknown", "restricted"} {
		t.Run(status, func(t *testing.T) {
			root, expected := releaseMediaClosureFixture(t)
			asset := expected[0]
			sourceRef := "objects/" + asset.Owner + "/sources/" + asset.AssetID + "/source.json"
			mutateReleaseMediaClosureJSON(t, root, sourceRef, func(d map[string]any) {
				d["assets"] = []map[string]any{{
					"assetId": "original-source-avatar", "rightsStatus": status,
					"authorizationRequired": true, "distributionDecision": "blocked", "usageScope": "research",
				}}
			})
			rightsPath := filepath.Join(root, "payload", filepath.FromSlash(sourceRef))
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
				t.Fatal("public delivery must not rewrite immutable source rights records")
			}
		})
	}
}

func TestReleasePublicDeliveryAllowsSharedDigestWithDistinctAssetSlices(t *testing.T) {
	root, expected := releaseMediaClosureFixture(t)
	sharedSHA := expected[1].SHA256
	second := expected[3]
	mutateReleaseMediaClosureJSON(t, root, "media_manifest.json", func(d map[string]any) {
		d["assets"].([]any)[3].(map[string]any)["sha256"] = sharedSHA
	})
	mutateReleaseMediaClosureJSON(t, root, "objects/"+second.Owner+"/manifest.json", func(d map[string]any) {
		firstReleaseMediaClosureAsset(d)["sha256"] = sharedSHA
	})
	assets, err := LoadReleaseMediaAssets(root, "release-geo-media")
	if err != nil {
		t.Fatalf("shared content digest with distinct asset identities must remain valid: %v", err)
	}
	firstAsset, secondAsset := assets[expected[1].AssetID], assets[second.AssetID]
	if len(assets) != len(expected) || firstAsset.SHA256 != secondAsset.SHA256 || firstAsset.PublicSliceKey == secondAsset.PublicSliceKey {
		t.Fatalf("shared bytes must keep independent public asset identities: first=%+v second=%+v", firstAsset, secondAsset)
	}
}
