package recommendationlocalcontract

import (
	"testing"
	"time"

	"quwoquan_service/runtime/recommendation"
)

func TestOfflineReplayEvaluationCommercialReportLocalContract(t *testing.T) {
	start := time.Date(2026, 6, 24, 0, 0, 0, 0, time.UTC)
	report := recommendation.ComputeReplayReportWithOptions(recommendation.ReplayDataset{
		EligibleContentCount:      5,
		DataWindowStart:           start,
		DataWindowEnd:             start.Add(24 * time.Hour),
		PolicyVersion:             "policy-v2",
		RankingVersion:            "rec-v2",
		ReasonVersion:             "reason-v2",
		ScorerVariant:             "rule-commercial",
		TimeDecayFeatureFreshness: 0.98,
		Requests: []recommendation.ReplayRequest{{
			FeedRequestID: "frq_contract",
			ChannelID:     "home",
			Vertical:      "discovery",
			Items: []recommendation.ReplayItem{
				{ContentID: "c1", AuthorID: "a1", RecallPath: "collab_i2i", SupplySource: "ugc", IntersectionClass: "fact", Clicked: true, Score: 0.9},
				{ContentID: "c2", AuthorID: "a2", RecallPath: "tag_recall", SupplySource: "data_engineering", IntersectionClass: "affinity", Clicked: true, Score: 0.5},
				{ContentID: "c3", AuthorID: "a3", RecallPath: "hot_recall", SupplySource: "data_engineering", IntersectionClass: "affinity", Score: 0.4},
			},
		}},
	}, 3, recommendation.ReplayReportOptions{
		Thresholds: recommendation.ReplayPromotionThresholds{
			MinRequests:                  1,
			MinServedItems:               3,
			MinTimeDecayFeatureFreshness: 0.95,
			MaxNegativeFeedbackRate:      0.08,
			MaxRepeatExposureRate:        0.01,
		},
	})

	if report.Invalid || !report.PromotionAllowed {
		t.Fatalf("commercial replay report should be promotable: %+v", report)
	}
	if report.PolicyVersion == "" || report.RankingVersion == "" || report.ReasonVersion == "" || report.ScorerVariant == "" {
		t.Fatalf("replay report must carry version attribution: %+v", report)
	}
	if report.MAPAtK <= 0 || report.CollaborativeRecallLift <= 0 {
		t.Fatalf("replay report must compute MAP and collaborative lift: %+v", report)
	}
	if report.FactExplanationCTR <= report.AffinityExplanationCTR {
		t.Fatalf("fact explanation CTR should beat affinity in fixture: fact=%.4f affinity=%.4f", report.FactExplanationCTR, report.AffinityExplanationCTR)
	}
	if report.SupplySourceShare["ugc"] == 0 || report.SupplySourceShare["data_engineering"] == 0 {
		t.Fatalf("replay report must bucket UGC and data_engineering supply: %+v", report.SupplySourceShare)
	}
}
