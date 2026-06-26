package recommendation

import (
	"math"
	"testing"
	"time"
)

func TestComputeReplayReport_RankingMetrics(t *testing.T) {
	ds := ReplayDataset{
		EligibleContentCount: 10,
		Requests: []ReplayRequest{
			{
				FeedRequestID: "frq_1",
				UserID:        "u1",
				Items: []ReplayItem{
					{ContentID: "A", AuthorID: "a1", Score: 0.9, Relevant: true},
					{ContentID: "B", AuthorID: "a2", Score: 0.5, Relevant: false, DuplicateExposure: true},
					{ContentID: "C", AuthorID: "a3", Score: 0.3, Relevant: true, Negative: true},
				},
			},
		},
	}
	r := ComputeReplayReport(ds, 3)

	if r.Requests != 1 {
		t.Fatalf("requests = %d, want 1", r.Requests)
	}
	// NDCG@3: relevances [1,0,1]; DCG=1/log2(2)+1/log2(4)=1.5; IDCG=1/log2(2)+1/log2(3)=1.6309.
	wantNDCG := 1.5 / (1.0 + 1.0/math.Log2(3))
	if math.Abs(r.NDCGAtK-wantNDCG) > 1e-6 {
		t.Errorf("NDCG = %.6f, want %.6f", r.NDCGAtK, wantNDCG)
	}
	if math.Abs(r.RecallAtK-1.0) > 1e-9 {
		t.Errorf("Recall = %.6f, want 1.0", r.RecallAtK)
	}
	if math.Abs(r.DiversityRate-1.0) > 1e-9 {
		t.Errorf("Diversity = %.6f, want 1.0 (3 distinct authors / 3)", r.DiversityRate)
	}
	if math.Abs(r.CoverageRate-0.3) > 1e-9 {
		t.Errorf("Coverage = %.6f, want 0.3 (3 distinct / 10)", r.CoverageRate)
	}
	if math.Abs(r.RepeatExposureRate-1.0/3.0) > 1e-9 {
		t.Errorf("RepeatExposure = %.6f, want 1/3", r.RepeatExposureRate)
	}
	if math.Abs(r.NegativeFeedbackRate-1.0/3.0) > 1e-9 {
		t.Errorf("NegativeFeedback = %.6f, want 1/3", r.NegativeFeedbackRate)
	}
	if r.CalibrationError < 0 || r.CalibrationError > 1 {
		t.Errorf("CalibrationError = %.6f out of [0,1]", r.CalibrationError)
	}
}

func TestComputeReplayReport_KTruncation(t *testing.T) {
	// Relevant item only at rank 5; Recall@3 must be 0, Recall@5 must be 1.
	items := []ReplayItem{
		{ContentID: "A", AuthorID: "a1", Score: 0.9},
		{ContentID: "B", AuthorID: "a2", Score: 0.8},
		{ContentID: "C", AuthorID: "a3", Score: 0.7},
		{ContentID: "D", AuthorID: "a4", Score: 0.6},
		{ContentID: "E", AuthorID: "a5", Score: 0.5, Relevant: true},
	}
	ds := ReplayDataset{EligibleContentCount: 5, Requests: []ReplayRequest{{FeedRequestID: "f", Items: items}}}

	if r3 := ComputeReplayReport(ds, 3); r3.RecallAtK != 0 {
		t.Errorf("Recall@3 = %.4f, want 0", r3.RecallAtK)
	}
	if r5 := ComputeReplayReport(ds, 5); math.Abs(r5.RecallAtK-1.0) > 1e-9 {
		t.Errorf("Recall@5 = %.4f, want 1.0", r5.RecallAtK)
	}
}

func TestReplayReport_EmitNoPanic(t *testing.T) {
	ds := ReplayDataset{EligibleContentCount: 4, Requests: []ReplayRequest{{
		FeedRequestID: "f", Items: []ReplayItem{{ContentID: "A", AuthorID: "a1", Score: 0.5, Relevant: true}},
	}}}
	// Emit writes to the registered gauge; must not panic.
	ComputeReplayReport(ds, 10).Emit()
}

func TestComputeReplayReportWithOptions_CommercialAttributionAndPromotion(t *testing.T) {
	windowStart := time.Date(2026, 6, 24, 0, 0, 0, 0, time.UTC)
	windowEnd := windowStart.Add(24 * time.Hour)
	ds := ReplayDataset{
		EligibleContentCount:      8,
		DataWindowStart:           windowStart,
		DataWindowEnd:             windowEnd,
		PolicyVersion:             "policy-v2",
		RankingVersion:            "rec-v2",
		ReasonVersion:             "reason-v2",
		ScorerVariant:             "rule-commercial",
		TimeDecayFeatureFreshness: 0.97,
		Requests: []ReplayRequest{
			{
				FeedRequestID: "frq_home",
				UserID:        "u1",
				ChannelID:     "home",
				Vertical:      "discovery",
				Items: []ReplayItem{
					{
						ContentID: "collab_fact_click", AuthorID: "a1", Score: 0.95,
						RecallPath: "collab_i2i", SupplySource: "ugc",
						IntersectionClass: "fact", IntersectionSourceRef: "sharedFollowees",
						Clicked: true, Impressed: true,
					},
					{
						ContentID: "tag_affinity_click", AuthorID: "a2", Score: 0.80,
						RecallPath: "tag_recall", SupplySource: "data_engineering",
						IntersectionClass: "affinity", IntersectionSourceRef: "similarInterest",
						Clicked: true, Impressed: true,
					},
					{
						ContentID: "tag_affinity_skip", AuthorID: "a3", Score: 0.30,
						RecallPath: "tag_recall", SupplySource: "data_engineering",
						IntersectionClass: "affinity", IntersectionSourceRef: "similarInterest",
						Impressed: true,
					},
				},
			},
		},
	}

	report := ComputeReplayReportWithOptions(ds, 3, ReplayReportOptions{
		Thresholds: ReplayPromotionThresholds{
			MinRequests:                  1,
			MinServedItems:               3,
			MinRecallAtK:                 0.9,
			MinDiversityRate:             0.9,
			MinTimeDecayFeatureFreshness: 0.95,
			MaxNegativeFeedbackRate:      0.08,
			MaxRepeatExposureRate:        0.01,
		},
	})

	if report.Invalid {
		t.Fatalf("expected valid report, reasons=%v", report.InvalidReasons)
	}
	if !report.PromotionAllowed || report.RollbackRecommended {
		t.Fatalf("promotion verdict drifted: %+v", report)
	}
	if report.PolicyVersion != "policy-v2" ||
		report.RankingVersion != "rec-v2" ||
		report.ReasonVersion != "reason-v2" ||
		report.ScorerVariant != "rule-commercial" {
		t.Fatalf("version metadata missing: %+v", report)
	}
	if report.MAPAtK <= 0 {
		t.Fatalf("MAP@K should be computed, got %.4f", report.MAPAtK)
	}
	if math.Abs(report.CollaborativeRecallLift-1.0) > 1e-9 {
		t.Fatalf("collab lift = %.4f, want 1.0", report.CollaborativeRecallLift)
	}
	if math.Abs(report.FactExplanationCTR-1.0) > 1e-9 {
		t.Fatalf("fact explanation ctr = %.4f, want 1", report.FactExplanationCTR)
	}
	if math.Abs(report.AffinityExplanationCTR-0.5) > 1e-9 {
		t.Fatalf("affinity explanation ctr = %.4f, want 0.5", report.AffinityExplanationCTR)
	}
	if math.Abs(report.SupplySourceShare["data_engineering"]-2.0/3.0) > 1e-9 {
		t.Fatalf("data engineering share = %.4f", report.SupplySourceShare["data_engineering"])
	}
	if report.TimeDecayFeatureFreshness != 0.97 {
		t.Fatalf("time decay freshness = %.4f", report.TimeDecayFeatureFreshness)
	}
}

func TestComputeReplayReportWithOptions_InvalidSamplesBlockPromotion(t *testing.T) {
	report := ComputeReplayReportWithOptions(ReplayDataset{}, 10, ReplayReportOptions{
		Thresholds: ReplayPromotionThresholds{MinRequests: 2, MinServedItems: 5},
	})
	if !report.Invalid {
		t.Fatalf("empty replay dataset must be invalid")
	}
	if report.PromotionAllowed {
		t.Fatalf("invalid replay dataset must block promotion")
	}
	if len(report.InvalidReasons) == 0 {
		t.Fatalf("invalid report should explain sample failure")
	}
}

func TestComputeReplayReportWithOptions_GuardrailRegressionRecommendsRollback(t *testing.T) {
	ds := ReplayDataset{
		EligibleContentCount: 2,
		Requests: []ReplayRequest{{
			FeedRequestID: "frq_rollback",
			Items: []ReplayItem{
				{ContentID: "a", AuthorID: "a1", Score: 0.9, Clicked: true, Negative: true},
				{ContentID: "b", AuthorID: "a2", Score: 0.8, DuplicateExposure: true},
			},
		}},
	}

	report := ComputeReplayReportWithOptions(ds, 2, ReplayReportOptions{
		Thresholds: ReplayPromotionThresholds{
			MinRequests:             1,
			MinServedItems:          2,
			MaxNegativeFeedbackRate: 0.08,
			MaxRepeatExposureRate:   0.01,
		},
	})
	if report.Invalid {
		t.Fatalf("dataset itself should be valid: %v", report.InvalidReasons)
	}
	if report.PromotionAllowed {
		t.Fatalf("guardrail regression must block promotion: %+v", report)
	}
	if !report.RollbackRecommended {
		t.Fatalf("negative/repeat guardrail breach should recommend rollback")
	}
}

func TestComputeReplayReport_EmptyDatasetSafe(t *testing.T) {
	r := ComputeReplayReport(ReplayDataset{}, 0)
	if r.K != 10 || r.Requests != 0 {
		t.Fatalf("empty dataset: K=%d requests=%d, want K=10 requests=0", r.K, r.Requests)
	}
}
