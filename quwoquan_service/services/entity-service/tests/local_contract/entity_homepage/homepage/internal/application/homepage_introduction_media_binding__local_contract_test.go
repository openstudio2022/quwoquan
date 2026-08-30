// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// HomepageIntroduction 读模型的媒体交付绑定出场（DEC-033）：cover 携带配对的
// coverAssetId/coverAccessMode，introduction assets 逐项保留 accessMode；
// 绑定只来自真实资产投影，配不上时缺席，禁止以 homepageId 冒充媒体资产标识。
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
)

const researchCASCoverURL = "media/objects/sha256/aa/bb/cover0000.jpg"

func intakeResearchBoundHomepage(t *testing.T, service *application.HomepageService) *application.Homepage {
	t.Helper()
	homepage, err := service.IntakeHomepageCandidate(
		context.Background(),
		application.HomepageInput{
			Title:                "都江堰",
			HomepageType:         "sight",
			IntroductionMarkdown: threeSegmentPageMarkdown,
			IntroductionAssets: []application.HomepageIntroductionAsset{
				{AssetID: "cover_asset", URL: researchCASCoverURL, AccessMode: "signed_grant", Caption: "都江堰全景", Role: "cover"},
				{AssetID: "inline_asset_1", URL: "media/objects/sha256/aa/bb/inline001.jpg", AccessMode: "signed_grant", Caption: "鱼嘴分水堤"},
				{AssetID: "related_asset_1", URL: "media/objects/sha256/aa/bb/rel00001.jpg", AccessMode: "signed_grant"},
				{AssetID: "related_asset_2", URL: "media/objects/sha256/aa/bb/rel00002.jpg", AccessMode: "signed_grant"},
			},
		},
		"data_pipeline",
	)
	if err != nil {
		t.Fatalf("intake failed: %v", err)
	}
	return homepage
}

func TestIntroductionCarriesCoverAndAssetDeliveryBindings(t *testing.T) {
	service := newEmptyHomepageService()
	homepage := intakeResearchBoundHomepage(t, service)
	introduction, err := service.GetHomepageIntroduction(context.Background(), homepage.ID)
	if err != nil {
		t.Fatalf("introduction failed: %v", err)
	}

	if introduction.CoverURL != researchCASCoverURL {
		t.Fatalf("cover must come from frontmatter coverImage asset, got %q", introduction.CoverURL)
	}
	if introduction.CoverAssetID != "cover_asset" {
		t.Fatalf("coverAssetId must pair the cover asset, got %q", introduction.CoverAssetID)
	}
	if introduction.CoverAccessMode != "signed_grant" {
		t.Fatalf("coverAccessMode must carry the asset delivery mode, got %q", introduction.CoverAccessMode)
	}
	for _, section := range introduction.Sections {
		for _, asset := range section.Assets {
			if asset.AccessMode != "signed_grant" {
				t.Fatalf(
					"section %s asset %s accessMode = %q, want signed_grant",
					section.Kind, asset.AssetID, asset.AccessMode,
				)
			}
		}
	}
}

func TestIntroductionLegacyPublicAssetsLeaveAccessModeAbsent(t *testing.T) {
	// 存量 public 交付（导入时未声明 accessMode）：cover 仍配对 assetId，
	// accessMode 缺席（契约 NULLABLE，null 只允许出现在存量 public 交付）。
	service := newEmptyHomepageService()
	homepage := intakeThreeSegmentHomepage(t, service)
	introduction, err := service.GetHomepageIntroduction(context.Background(), homepage.ID)
	if err != nil {
		t.Fatalf("introduction failed: %v", err)
	}
	if introduction.CoverAssetID != "cover_asset" {
		t.Fatalf("legacy cover must still pair assetId, got %q", introduction.CoverAssetID)
	}
	if introduction.CoverAccessMode != "" {
		t.Fatalf("legacy cover accessMode must stay absent, got %q", introduction.CoverAccessMode)
	}
}

func TestIntroductionWithoutMarkdownPairsCoverFromCoverAsset(t *testing.T) {
	// 无 page.md 的主档：coverUrl 来自 role=cover 资产（导入线同 URL 写入主档），
	// 读模型按 URL 同值配对出 coverAssetId/coverAccessMode。
	service := newEmptyHomepageService()
	homepage, err := service.IntakeHomepageCandidate(
		context.Background(),
		application.HomepageInput{
			Title:        "青城山",
			HomepageType: "sight",
			CoverURL:     researchCASCoverURL,
			IntroductionAssets: []application.HomepageIntroductionAsset{
				{AssetID: "cover_asset", URL: researchCASCoverURL, AccessMode: "signed_grant", Role: "cover"},
			},
		},
		"data_pipeline",
	)
	if err != nil {
		t.Fatalf("intake failed: %v", err)
	}
	introduction, err := service.GetHomepageIntroduction(context.Background(), homepage.ID)
	if err != nil {
		t.Fatalf("introduction failed: %v", err)
	}
	if introduction.CoverAssetID != "cover_asset" || introduction.CoverAccessMode != "signed_grant" {
		t.Fatalf(
			"cover binding must pair by cover asset URL, got assetId=%q accessMode=%q",
			introduction.CoverAssetID, introduction.CoverAccessMode,
		)
	}
}
