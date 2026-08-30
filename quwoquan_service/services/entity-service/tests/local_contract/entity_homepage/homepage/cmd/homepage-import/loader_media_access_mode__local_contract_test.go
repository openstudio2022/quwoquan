// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// homepage-import 的逐资产媒体交付绑定（DEC-033）：accessMode 只由 release
// header 的 releaseClass 断言——research → signed_grant（URL 为相对私有 CAS
// key），commercial → public（URL 为 canonical public slice）；未知类别缺席，
// importer 不得造值，也不得从 URL 形态反推交付形态。
package homepage_import_test

import (
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

// researchReleaseMediaAuthority 构造 research release 的媒体 authority：每个
// 资产只有相对 CAS privateObjectKey，没有 publicSliceKey（DEC-031 单一交付身份）。
func researchReleaseMediaAuthority(
	t *testing.T,
	root string,
) map[string]runtimemedia.ReleaseMediaAsset {
	t.Helper()
	authority := releaseMediaAuthority(t, root)
	for assetID, asset := range authority {
		digest := strings.TrimPrefix(asset.SHA256, "sha256:")
		asset.PublicSliceKey = ""
		asset.PrivateObjectKey = "media/objects/sha256/" +
			digest[:2] + "/" + digest[2:4] + "/" + digest + ".jpg"
		authority[assetID] = asset
	}
	return authority
}

func TestLoadHomepageProjectionsBindsResearchAssetsToSignedGrant(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)

	inputs, issues, err := homepageimport.LoadHomepageProjections(
		root,
		nil,
		researchReleaseMediaAuthority(t, root),
		runtimemedia.MediaDeliveryBases{Image: "https://media.example.com"},
		"research",
	)
	if err != nil {
		t.Fatalf("load research projections: %v", err)
	}
	if len(issues) != 0 || len(inputs) != 1 {
		t.Fatalf("expected 1 projection without issues, inputs=%d issues=%v", len(inputs), issues)
	}
	for _, asset := range inputs[0].IntroductionAssets {
		if asset.AccessMode != "signed_grant" {
			t.Fatalf("research asset %s accessMode = %q, want signed_grant", asset.AssetID, asset.AccessMode)
		}
		if !strings.HasPrefix(asset.URL, "media/objects/sha256/") {
			t.Fatalf("research asset %s must store the relative CAS key, got %q", asset.AssetID, asset.URL)
		}
	}
}

func TestLoadHomepageProjectionsBindsCommercialAssetsToPublic(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)

	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load commercial projections: %v", err)
	}
	if len(issues) != 0 || len(inputs) != 1 {
		t.Fatalf("expected 1 projection without issues, inputs=%d issues=%v", len(inputs), issues)
	}
	for _, asset := range inputs[0].IntroductionAssets {
		if asset.AccessMode != "public" {
			t.Fatalf("commercial asset %s accessMode = %q, want public", asset.AssetID, asset.AccessMode)
		}
	}
}

func TestLoadHomepageProjectionsLeavesUnknownReleaseClassAccessModeAbsent(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)

	inputs, _, err := homepageimport.LoadHomepageProjections(
		root,
		nil,
		releaseMediaAuthority(t, root),
		runtimemedia.MediaDeliveryBases{Image: "https://media.example.com"},
		"",
	)
	if err != nil {
		t.Fatalf("load projections: %v", err)
	}
	if len(inputs) != 1 {
		t.Fatalf("expected 1 projection, got %d", len(inputs))
	}
	for _, asset := range inputs[0].IntroductionAssets {
		if asset.AccessMode != "" {
			t.Fatalf("unknown release class must leave accessMode absent, got %q", asset.AccessMode)
		}
	}
}
