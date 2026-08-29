// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
package runtimemedia

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func privateCASKey(digestHex string, suffix string) string {
	return "media/objects/sha256/" + digestHex[:2] + "/" + digestHex[2:4] + "/" +
		digestHex + suffix
}

func releasePrivateDeliveryFixture(
	t *testing.T,
	mutate func(rows []map[string]any),
) string {
	t.Helper()
	root := t.TempDir()
	digests := map[string]string{
		"entity-cover":   strings.Repeat("a", 64),
		"article-inline": strings.Repeat("b", 64),
	}
	owners := map[string]string{
		"entity-cover":   "entities/地点/景区/实体甲",
		"article-inline": "posts/article/攻略/实体甲/1",
	}
	rows := make([]map[string]any, 0, len(digests))
	for _, assetID := range []string{"entity-cover", "article-inline"} {
		digest := digests[assetID]
		owner := owners[assetID]
		rightsRef := "objects/" + owner + "/rights_snapshots/" + assetID + ".json"
		writeReleaseMediaClosureJSON(
			t,
			filepath.Join(root, "payload", filepath.FromSlash(rightsRef)),
			map[string]any{
				"schema":  "quwoquan_data.asset_rights_snapshot",
				"assetId": assetID,
				"manifestAsset": map[string]any{
					"assetId": assetID,
					"sha256":  "sha256:" + digest,
				},
			},
		)
		rows = append(rows, map[string]any{
			"assetId":            assetID,
			"kind":               "image",
			"version":            1,
			"contentType":        "image/jpeg",
			"privateObjectKey":   privateCASKey(digest, ".jpg"),
			"sha256":             "sha256:" + digest,
			"bytes":              1,
			"ownerRefs":          []string{owner},
			"rightsSnapshotRefs": []string{rightsRef},
		})
	}
	if mutate != nil {
		mutate(rows)
	}
	writeReleaseMediaClosureJSON(
		t,
		filepath.Join(root, "payload", "media_manifest.json"),
		map[string]any{
			"schema":      releaseMediaManifestSchema,
			"releaseId":   "release-research-media",
			"sourceOwner": releaseMediaSourceOwner,
			"assets":      rows,
			"issues":      []string{},
			"counts": map[string]any{
				"assets": len(rows),
				"issues": 0,
			},
		},
	)
	return root
}

func TestResearchDeliveryResolvesRelativeCASKeyWithoutPublicURL(t *testing.T) {
	root := releasePrivateDeliveryFixture(t, nil)
	assets, err := LoadReleaseMediaAssets(root, "release-research-media", "research")
	if err != nil {
		t.Fatalf("load research media authority: %v", err)
	}
	resolved, err := ResolveReleaseMediaAsset(
		assets,
		MediaDeliveryBases{Image: "https://cdn.example.com"},
		"entity-cover",
		"image",
		"sha256:"+strings.Repeat("a", 64),
		"entities/地点/景区/实体甲",
	)
	if err != nil {
		t.Fatalf("resolve research asset: %v", err)
	}
	if resolved.PublicURL != "" {
		t.Fatalf("research delivery must not produce a public URL, got %q", resolved.PublicURL)
	}
	key := resolved.DeliveryRef
	if key != privateCASKey(strings.Repeat("a", 64), ".jpg") {
		t.Fatalf("research DeliveryRef must be the CAS key, got %q", key)
	}
	// Probe-negative form: no public slice segment, no absolute URL.
	if strings.Contains(key, "/s/") ||
		strings.HasPrefix(key, "http://") ||
		strings.HasPrefix(key, "https://") {
		t.Fatalf("research DeliveryRef has an anonymous delivery form: %q", key)
	}
}

func TestResearchDeliveryRejectsPublicSliceAndDigestDrift(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(rows []map[string]any)
	}{
		{
			name: "public-slice-present",
			mutate: func(rows []map[string]any) {
				rows[0]["publicSliceKey"] = BuildContentMediaPublicSliceKey(
					"image", "entity-cover", 1, "image/jpeg",
				)
				delete(rows[0], "privateObjectKey")
			},
		},
		{
			name: "cas-key-digest-drift",
			mutate: func(rows []map[string]any) {
				rows[0]["privateObjectKey"] = privateCASKey(strings.Repeat("f", 64), ".jpg")
			},
		},
		{
			name: "cas-key-malformed",
			mutate: func(rows []map[string]any) {
				rows[0]["privateObjectKey"] = "media/image/p/asset/entity-cover/v1/source.jpg"
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := releasePrivateDeliveryFixture(t, test.mutate)
			if _, err := LoadReleaseMediaAssets(
				root,
				"release-research-media",
				"research",
			); err == nil {
				t.Fatal("invalid research delivery identity must fail closed")
			}
		})
	}
}

func TestCommercialDeliveryRejectsPrivateObjectKey(t *testing.T) {
	root, _ := releaseMediaClosureFixture(t)
	if _, err := LoadReleaseMediaAssets(
		root,
		"release-geo-media",
		"research",
	); err == nil {
		t.Fatal("public slice manifest must not load as research delivery")
	}
	if _, err := LoadReleaseMediaAssets(
		root,
		"release-geo-media",
		"prod-gray",
	); err == nil {
		t.Fatal("unknown release class must fail closed")
	}
}

func TestResearchDeliveryRefIsSignableByPrivateDeliverySigner(t *testing.T) {
	root := releasePrivateDeliveryFixture(t, nil)
	assets, err := LoadReleaseMediaAssets(root, "release-research-media", "research")
	if err != nil {
		t.Fatalf("load research media authority: %v", err)
	}
	resolved, err := ResolveReleaseMediaAsset(
		assets,
		MediaDeliveryBases{Image: "https://cdn.example.com"},
		"entity-cover",
		"image",
		"sha256:"+strings.Repeat("a", 64),
		"entities/地点/景区/实体甲",
	)
	if err != nil {
		t.Fatalf("resolve research asset: %v", err)
	}
	// DEC-031: the CAS delivery ref must be consumable by the existing
	// short-lived grant signer without any layout translation.
	signed := SignCDNURLUntil(
		"https://media.example.com",
		resolved.DeliveryRef,
		"test-sign-key",
		time.Now().Add(300*time.Second),
	)
	if signed == "" {
		t.Fatalf(
			"private delivery signer rejected research DeliveryRef %q",
			resolved.DeliveryRef,
		)
	}
	if !strings.Contains(signed, "sign=") || !strings.Contains(signed, "&t=") {
		t.Fatalf("signed URL lacks signature elements: %q", signed)
	}
}

func TestResearchDeliveryAllowsContentAddressedSharing(t *testing.T) {
	sharedDigest := strings.Repeat("a", 64)
	root := releasePrivateDeliveryFixture(t, func(rows []map[string]any) {
		rows[1]["privateObjectKey"] = privateCASKey(sharedDigest, ".jpg")
		rows[1]["sha256"] = "sha256:" + sharedDigest
		// Keep the rights snapshot binding consistent with the new digest.
	})
	// Rewrite the second asset's rights snapshot to bind the shared digest.
	writeReleaseMediaClosureJSON(
		t,
		filepath.Join(
			root,
			"payload",
			"objects", "posts", "article", "攻略", "实体甲", "1",
			"rights_snapshots", "article-inline.json",
		),
		map[string]any{
			"schema":  "quwoquan_data.asset_rights_snapshot",
			"assetId": "article-inline",
			"manifestAsset": map[string]any{
				"assetId": "article-inline",
				"sha256":  "sha256:" + sharedDigest,
			},
		},
	)
	assets, err := LoadReleaseMediaAssets(root, "release-research-media", "research")
	if err != nil {
		t.Fatalf("content-addressed sharing must stay valid for research delivery: %v", err)
	}
	if len(assets) != 2 {
		t.Fatalf("expected both shared-body assets, got %d", len(assets))
	}
}
