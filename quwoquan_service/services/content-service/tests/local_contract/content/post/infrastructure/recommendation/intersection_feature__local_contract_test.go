package recommendation_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
)

func TestIsIntersectionEngagementAction(t *testing.T) {
	cases := []struct {
		action string
		depth  int
		want   bool
	}{
		{"impression", 0, false}, // 单纯曝光不计入揭示偏好
		{"dwell", 1, false},
		{"impression", 2, true}, // 深度阅读视为参与
		{"click", 0, true},
		{"like", 0, true},
		{"follow", 0, true},
		{"join_circle", 0, true},
		{"add_contact", 0, true},
		{"share", 0, true},
		{"comment", 0, true},
	}
	for _, c := range cases {
		if got := IsIntersectionEngagementAction(c.action, c.depth); got != c.want {
			t.Fatalf("IsIntersectionEngagementAction(%q,%d)=%v want %v", c.action, c.depth, got, c.want)
		}
	}
}

func TestDeriveIntersectionFeatures_MapsKindsAndTop(t *testing.T) {
	got := DeriveIntersectionFeatures(map[string]int{
		"sharedFollowees":  3,
		"sharedCircle":     5,
		"coCommented":      2,
		"coVisitedEntity":  1,
		"followeeInObject": 4,
		"followeeViewing":  1,
		"unknownKind":      9, // 未登记 kind 不映射到事实字段，但仍可成为 top
	})
	if got.SharedFolloweesCount != 3 {
		t.Fatalf("sharedFollowees=%d want 3", got.SharedFolloweesCount)
	}
	if got.SharedCircleCount != 5 {
		t.Fatalf("sharedCircle=%d want 5", got.SharedCircleCount)
	}
	if got.CoCommentedCount != 2 {
		t.Fatalf("coCommented=%d want 2", got.CoCommentedCount)
	}
	if got.CoVisitedEntityCount != 1 {
		t.Fatalf("coVisitedEntity=%d want 1", got.CoVisitedEntityCount)
	}
	if got.FolloweeInObjectActive != 1 {
		t.Fatalf("followeeInObjectActive=%d want 1", got.FolloweeInObjectActive)
	}
	if got.FolloweeViewingActive != 1 {
		t.Fatalf("followeeViewingActive=%d want 1", got.FolloweeViewingActive)
	}
	if got.SourceRefTop != "unknownKind" { // count 9 是最大
		t.Fatalf("sourceRefTop=%q want unknownKind", got.SourceRefTop)
	}
}

func TestDeriveIntersectionFeatures_DeterministicTieBreak(t *testing.T) {
	// 计数相同时按字典序取最小 kind，保证可复现。
	got := DeriveIntersectionFeatures(map[string]int{
		"sharedCircle":    4,
		"sharedFollowees": 4,
	})
	if got.SourceRefTop != "sharedCircle" {
		t.Fatalf("tie-break sourceRefTop=%q want sharedCircle", got.SourceRefTop)
	}
}

func TestDeriveIntersectionFeatures_EmptyAndZeroCounts(t *testing.T) {
	if got := DeriveIntersectionFeatures(nil); got.SourceRefTop != "" {
		t.Fatalf("nil histogram should yield empty top, got %+v", got)
	}
	got := DeriveIntersectionFeatures(map[string]int{"sharedCircle": 0, "coCommented": -1})
	if got.SourceRefTop != "" || got.SharedCircleCount != 0 || got.CoCommentedCount != 0 {
		t.Fatalf("zero/negative counts must be ignored, got %+v", got)
	}
}
