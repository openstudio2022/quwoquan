// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
//
// homepage-import 不接受 release 类别参数；逐资产按 canonical release
// authority 输出公开 slice 和 public accessMode，环境只注入媒体 endpoint。
package homepage_import_test

import (
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

func TestLoadHomepageProjectionsBindsClasslessReleaseAssetsToPublic(t *testing.T) {
	for _, base := range []string{"https://media.example.com", "https://other-media.example.com"} {
		t.Run(base, func(t *testing.T) {
			root := t.TempDir()
			seedPublishEntity(t, root, "地点/景区/九寨沟", true)
			authority := releaseMediaAuthority(t, root)
			inputs, issues, err := homepageimport.LoadHomepageProjections(
				root,
				nil,
				authority,
				runtimemedia.MediaDeliveryBases{Image: base},
			)
			if err != nil {
				t.Fatalf("load classless release projections: %v", err)
			}
			if len(issues) != 0 || len(inputs) != 1 || len(inputs[0].IntroductionAssets) != 1 {
				t.Fatalf("expected one projection with one asset and no issues: inputs=%+v issues=%v", inputs, issues)
			}
			for _, asset := range inputs[0].IntroductionAssets {
				binding := authority[asset.AssetID]
				wantURL := runtimemedia.BuildPublicMediaURL(base, binding.PublicSliceKey, binding.Version)
				if asset.AccessMode != "public" || wantURL == "" || asset.URL != wantURL ||
					strings.Contains(asset.URL, "media/objects/") {
					t.Fatalf("asset must retain canonical public delivery: %+v", asset)
				}
			}
		})
	}
}
