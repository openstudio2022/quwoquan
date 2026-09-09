// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package homepage_import_test

import (
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

func TestLoadHomepageProjectionsRejectsRetiredOrMissingReleaseClass(t *testing.T) {
	for _, class := range []string{"research", "commercial", "", "preview", " production "} {
		t.Run(class, func(t *testing.T) {
			root := t.TempDir()
			seedPublishEntity(t, root, "地点/景区/九寨沟", true)
			inputs, _, err := homepageimport.LoadHomepageProjections(
				root, nil, releaseMediaAuthority(t, root),
				runtimemedia.MediaDeliveryBases{Image: "https://media.example.com"}, class,
			)
			if err == nil || len(inputs) != 0 {
				t.Fatalf("retired class %q must fail closed without a projection: inputs=%v err=%v", class, inputs, err)
			}
		})
	}
}

func TestLoadHomepageProjectionsBindsProductionAssetsToPublic(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)
	inputs, issues, err := homepageimport.LoadHomepageProjections(
		root, nil, releaseMediaAuthority(t, root),
		runtimemedia.MediaDeliveryBases{Image: "https://media.example.com"}, "production",
	)
	if err != nil || len(issues) != 0 || len(inputs) != 1 {
		t.Fatalf("expected one production projection: inputs=%d issues=%v err=%v", len(inputs), issues, err)
	}
	if len(inputs[0].IntroductionAssets) != 1 {
		t.Fatalf("production fixture must exercise one real media binding: %+v", inputs[0].IntroductionAssets)
	}
	for _, asset := range inputs[0].IntroductionAssets {
		if asset.AssetID == "" || asset.URL == "" {
			t.Fatalf("production asset must retain identity and delivery: %+v", asset)
		}
		if asset.AccessMode != "public" {
			t.Fatalf("production asset %s accessMode=%q, want public", asset.AssetID, asset.AccessMode)
		}
	}
}
