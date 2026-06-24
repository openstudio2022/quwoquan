package local_contract

import (
	"testing"

	recommendation "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

func TestBuildRecommendationProjectionFields_DataEngineeringTravelQuality(t *testing.T) {
	fields := recommendation.BuildRecommendationProjectionFields(map[string]any{
		"authorId":             "builtin_travel_blogger",
		"creatorProfileId":     "qwq_creator_travel_blogger_001",
		"creatorDisclosure":    map[string]any{"type": "platform_virtual_creator"},
		"experienceClaimMode":  "editorial_synthesis",
		"authorQualitySignals": map[string]any{"qualityScore": 0.85},
		"tagRefs":              []string{"Topic/旅行"},
		"entityRefs":           []string{"地点/景区/甲居藏寨"},
		"semanticMentions":     []any{map[string]any{"targetRef": "地点/景区/甲居藏寨"}},
		"sourceTaskId":         "旅行/环线/川西环线",
		"coverUrl":             "https://img.example.com/cover.jpg",
		"status":               "published",
		"visibility":           "public",
	})

	if got := fields["supplySource"]; got != recommendation.SupplySourceDataEngineering {
		t.Fatalf("supplySource=%v want %s", got, recommendation.SupplySourceDataEngineering)
	}
	if got := fields["contentVertical"]; got != recommendation.ContentVerticalTravelPhotography {
		t.Fatalf("contentVertical=%v want %s", got, recommendation.ContentVerticalTravelPhotography)
	}
	quality, ok := fields["qualityScore"].(float64)
	if !ok || quality < 0.80 || quality > 1 {
		t.Fatalf("qualityScore=%v want high projected score", fields["qualityScore"])
	}
	if recScore := fields["recScore"]; recScore != quality {
		t.Fatalf("recScore=%v must mirror qualityScore=%v on projection", recScore, quality)
	}
	if got := fields["semanticMentionCoverage"]; got != 1.0 {
		t.Fatalf("semanticMentionCoverage=%v want 1.0", got)
	}
	if got := fields["mediaCompleteness"]; got != 1.0 {
		t.Fatalf("mediaCompleteness=%v want 1.0", got)
	}
}

func TestBuildRecommendationProjectionFields_UGCMissingSignalsConservative(t *testing.T) {
	fields := recommendation.BuildRecommendationProjectionFields(map[string]any{
		"authorId":    "user_123",
		"contentType": "micro",
		"status":      "published",
		"visibility":  "public",
	})

	if got := fields["supplySource"]; got != recommendation.SupplySourceUGC {
		t.Fatalf("supplySource=%v want %s", got, recommendation.SupplySourceUGC)
	}
	if got := fields["contentVertical"]; got != recommendation.ContentVerticalGeneral {
		t.Fatalf("contentVertical=%v want %s", got, recommendation.ContentVerticalGeneral)
	}
	quality, ok := fields["qualityScore"].(float64)
	if !ok || quality <= 0 || quality > 0.45 {
		t.Fatalf("qualityScore=%v must be conservative for missing signals", fields["qualityScore"])
	}
}
