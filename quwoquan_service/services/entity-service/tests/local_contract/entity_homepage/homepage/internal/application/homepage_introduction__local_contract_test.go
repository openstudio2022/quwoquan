package local_contract

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
)

const threeSegmentPageMarkdown = `---
title: 都江堰
coverImage: asset://cover_asset
---
# 都江堰

都江堰是战国时期修建的大型水利工程，以鱼嘴、飞沙堰、宝瓶口组织岷江水势。

## 历史沿革

李冰父子主持修建，两千余年持续灌溉成都平原。

:::figure id="fig_01" layout="fullWidth" caption="鱼嘴分水堤"
asset://inline_asset_1
:::

## 主要景观

宝瓶口与离堆公园是核心游览区。

## 相关图片

:::gallery ids="related_asset_1,related_asset_2" layout="grid"
:::
`

func intakeThreeSegmentHomepage(t *testing.T, service *application.HomepageService) *application.Homepage {
	t.Helper()
	homepage, err := service.IntakeHomepageCandidate(
		context.Background(),
		application.HomepageInput{
			Title:                "都江堰",
			HomepageType:         "sight",
			IntroductionMarkdown: threeSegmentPageMarkdown,
			IntroductionAssets: []application.HomepageIntroductionAsset{
				{AssetID: "cover_asset", URL: "https://cdn.example.com/cover.jpg", Caption: "都江堰全景", Role: "cover"},
				{AssetID: "inline_asset_1", URL: "https://cdn.example.com/inline1.jpg", Caption: "鱼嘴分水堤"},
				{AssetID: "related_asset_1", URL: "https://cdn.example.com/rel1.jpg"},
				{AssetID: "related_asset_2", URL: "https://cdn.example.com/rel2.jpg"},
			},
		},
		"data_pipeline",
	)
	if err != nil {
		t.Fatalf("intake failed: %v", err)
	}
	return homepage
}

func TestBuildIntroductionProjectsThreeSegmentPageMarkdown(t *testing.T) {
	service := newEmptyHomepageService()
	homepage := intakeThreeSegmentHomepage(t, service)
	introduction, err := service.GetHomepageIntroduction(context.Background(), homepage.ID)
	if err != nil {
		t.Fatalf("introduction failed: %v", err)
	}

	if introduction.CoverURL != "https://cdn.example.com/cover.jpg" {
		t.Fatalf("cover must come from frontmatter coverImage asset, got %q", introduction.CoverURL)
	}
	if !strings.Contains(introduction.Summary, "水利工程") {
		t.Fatalf("summary must derive from lead paragraph, got %q", introduction.Summary)
	}

	kinds := make([]string, 0, len(introduction.Sections))
	byKindTitle := map[string]application.HomepageIntroductionSection{}
	for _, section := range introduction.Sections {
		kinds = append(kinds, section.Kind)
		byKindTitle[section.Kind+"/"+section.Title] = section
	}
	wantKinds := []string{"overview", "body", "body", "relatedImages"}
	if strings.Join(kinds, ",") != strings.Join(wantKinds, ",") {
		t.Fatalf("expected section kinds %v, got %v", wantKinds, kinds)
	}

	history, ok := byKindTitle["body/历史沿革"]
	if !ok {
		t.Fatalf("missing body section 历史沿革")
	}
	if !strings.Contains(history.BodyMarkdown, `:::figure id="fig_01"`) {
		t.Fatalf("body markdown must preserve figure directive, got %q", history.BodyMarkdown)
	}
	if len(history.Assets) != 1 || history.Assets[0].AssetID != "inline_asset_1" {
		t.Fatalf("body section must bind inline asset, got %+v", history.Assets)
	}
	if history.Assets[0].Role != "inline" {
		t.Fatalf("body asset role must be inline, got %q", history.Assets[0].Role)
	}

	related, ok := byKindTitle["relatedImages/相关图片"]
	if !ok {
		t.Fatalf("missing relatedImages section")
	}
	if len(related.Assets) != 2 {
		t.Fatalf("related images must bind gallery assets, got %+v", related.Assets)
	}
	for _, asset := range related.Assets {
		if asset.Role != "related" {
			t.Fatalf("related asset role must be related, got %q", asset.Role)
		}
	}
	if strings.TrimSpace(related.BodyMarkdown) != "" {
		t.Fatalf("relatedImages section must not carry gallery markdown, got %q", related.BodyMarkdown)
	}
}

func TestBuildIntroductionUsesOnlyRealFieldsWithoutPageMarkdown(t *testing.T) {
	service := newEmptyHomepageService()
	homepage, err := service.IntakeHomepageCandidate(
		context.Background(),
		application.HomepageInput{
			Title:        "都江堰",
			HomepageType: "sight",
			CoverURL:     "https://cdn.example.com/fallback.jpg",
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
	if len(introduction.Sections) == 0 {
		t.Fatalf("real homepageType must produce keyFacts")
	}
	for _, section := range introduction.Sections {
		if section.Kind == "body" || section.Kind == "relatedImages" {
			t.Fatalf("field-derived introduction must not emit page.md projection kinds, got %q", section.Kind)
		}
	}
}

func TestIntakeHomepageCandidatePersistsIntroductionProjection(t *testing.T) {
	service := newEmptyHomepageService()
	homepage, err := service.IntakeHomepageCandidate(
		t.Context(),
		application.HomepageInput{
			Title:                "都江堰",
			HomepageType:         "sight",
			IntroductionMarkdown: threeSegmentPageMarkdown,
			IntroductionAssets: []application.HomepageIntroductionAsset{
				{AssetID: "cover_asset", URL: "https://cdn.example.com/cover.jpg", Caption: "都江堰全景", Role: "cover"},
			},
		},
		"data_pipeline",
	)
	if err != nil {
		t.Fatalf("intake failed: %v", err)
	}
	if homepage.CoverURL != "https://cdn.example.com/cover.jpg" {
		t.Fatalf("intake must derive cover from role=cover asset, got %q", homepage.CoverURL)
	}
	introduction, err := service.GetHomepageIntroduction(t.Context(), homepage.ID)
	if err != nil {
		t.Fatalf("introduction failed: %v", err)
	}
	hasBody := false
	for _, section := range introduction.Sections {
		if section.Kind == "body" {
			hasBody = true
		}
	}
	if !hasBody {
		t.Fatalf("intaken page markdown must project body sections, got %+v", introduction.Sections)
	}
}
