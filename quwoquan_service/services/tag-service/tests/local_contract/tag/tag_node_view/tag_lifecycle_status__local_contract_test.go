package local_contract

import (
	"context"
	"testing"
	"time"

	nodecontract "quwoquan_service/services/tag-service/generated/tag/tag_node_view/contract/tag"
	application "quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/lifecycle"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

func TestOnlyDeprecatedLifecycleStatusIsUnusable(t *testing.T) {
	usable := []string{"active", "trending", "seasonal", "campaign"}
	for _, status := range usable {
		if !lifecycle.IsUsable(status) {
			t.Fatalf("lifecycleStatus %q must stay usable", status)
		}
	}
	if lifecycle.IsUsable("deprecated") {
		t.Fatal("deprecated must be the one unusable lifecycleStatus")
	}
}

func TestUnrecognizedLifecycleStatusIsRejectedRatherThanAssumedActive(t *testing.T) {
	for _, status := range []string{"", " active", "ACTIVE", "hot"} {
		if _, ok := lifecycle.Parse(status); ok {
			t.Fatalf("lifecycleStatus %q must not parse", status)
		}
		if lifecycle.IsUsable(status) {
			t.Fatalf("lifecycleStatus %q must not be usable", status)
		}
	}
}

func TestUsableStatusesMatchesTheInMemoryPredicate(t *testing.T) {
	usable := lifecycle.UsableStatuses()
	if len(usable) != 4 {
		t.Fatalf("UsableStatuses() = %v, want 4 values", usable)
	}
	for _, status := range usable {
		if !lifecycle.IsUsable(status) {
			t.Fatalf("storage filter admits %q but IsUsable rejects it", status)
		}
	}
	all := lifecycle.AllStatuses()
	if len(all) != 5 {
		t.Fatalf("AllStatuses() = %v, want 5 values", all)
	}
	usable[0] = "mutated"
	if lifecycle.UsableStatuses()[0] != "active" {
		t.Fatal("UsableStatuses() must hand back a copy of the vocabulary")
	}
}

func TestOnlyWindowedStatusesRequireAHeatWindow(t *testing.T) {
	for _, status := range []string{"seasonal", "campaign"} {
		if !lifecycle.RequiresHeatWindow(status) {
			t.Fatalf("lifecycleStatus %q must require a heat window", status)
		}
	}
	for _, status := range []string{"active", "trending", "deprecated", "hot"} {
		if lifecycle.RequiresHeatWindow(status) {
			t.Fatalf("lifecycleStatus %q must not require a heat window", status)
		}
	}
}

func TestResolveAndChildrenAdmitTrendingSeasonalAndCampaignTags(t *testing.T) {
	window := &nodecontract.TagHeatWindow{
		StartAt:    time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
		EndAt:      time.Date(2026, 5, 31, 0, 0, 0, 0, time.UTC),
		Recurrence: "annual",
	}
	nodes := map[string]*model.TagNode{
		"Topic/时间": {
			TagRef: "Topic/时间", Group: "Topic", Label: "时间",
			ReleaseID: "release-current", LifecycleStatus: "active",
		},
		"Topic/时间/樱花季": {
			TagRef: "Topic/时间/樱花季", ParentTagRef: "Topic/时间", Group: "Topic", Label: "樱花季",
			ReleaseID: "release-current", LifecycleStatus: "seasonal", HeatWindow: window,
		},
		"Topic/时间/城市漫步周": {
			TagRef: "Topic/时间/城市漫步周", ParentTagRef: "Topic/时间", Group: "Topic", Label: "城市漫步周",
			ReleaseID: "release-current", LifecycleStatus: "campaign", HeatWindow: window,
		},
		"Topic/时间/机位打卡": {
			TagRef: "Topic/时间/机位打卡", ParentTagRef: "Topic/时间", Group: "Topic", Label: "机位打卡",
			ReleaseID: "release-current", LifecycleStatus: "trending",
		},
		"Topic/时间/生肖年": {
			TagRef: "Topic/时间/生肖年", ParentTagRef: "Topic/时间", Group: "Topic", Label: "生肖年",
			ReleaseID: "release-current", LifecycleStatus: "deprecated",
		},
	}
	service := application.NewTagService(
		migratedTagNodeReader{nodes: nodes},
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{releaseID: "release-current", found: true},
	)
	ctx := context.Background()

	for _, tagRef := range []string{"Topic/时间/樱花季", "Topic/时间/城市漫步周", "Topic/时间/机位打卡"} {
		view, err := service.Resolve(ctx, tagRef)
		if err != nil {
			t.Fatal(err)
		}
		if view == nil {
			t.Fatalf("Resolve(%s) dropped a usable tag", tagRef)
		}
	}
	if view, err := service.Resolve(ctx, "Topic/时间/生肖年"); err != nil || view != nil {
		t.Fatalf("Resolve(deprecated) = %#v, %v", view, err)
	}

	children, err := service.ListChildren(ctx, "Topic/时间", 50)
	if err != nil {
		t.Fatal(err)
	}
	if len(children) != 3 {
		t.Fatalf("ListChildren() returned %d children, want 3 non-deprecated", len(children))
	}
	windowed := 0
	for _, child := range children {
		if child.TagRef == "Topic/时间/生肖年" {
			t.Fatal("ListChildren() must not surface a deprecated child")
		}
		if child.HeatWindow == nil {
			continue
		}
		windowed++
		if child.HeatWindow.Recurrence != "annual" {
			t.Fatalf("child %s lost its heat window recurrence", child.TagRef)
		}
	}
	if windowed != 2 {
		t.Fatalf("%d children carried a heat window, want 2", windowed)
	}
}

func TestDeprecatedParentIsNotBrowsable(t *testing.T) {
	service := application.NewTagService(
		migratedTagNodeReader{nodes: map[string]*model.TagNode{
			"Topic/季节": {
				TagRef: "Topic/季节", Group: "Topic", Label: "季节",
				ReleaseID: "release-current", LifecycleStatus: "deprecated",
			},
		}},
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{releaseID: "release-current", found: true},
	)
	if _, err := service.ListChildren(context.Background(), "Topic/季节", 10); err == nil {
		t.Fatal("a deprecated parent must not be browsable")
	}
}
