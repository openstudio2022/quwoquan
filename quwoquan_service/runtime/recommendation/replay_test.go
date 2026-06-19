package recommendation

import (
	"math"
	"testing"
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

func TestComputeReplayReport_EmptyDatasetSafe(t *testing.T) {
	r := ComputeReplayReport(ReplayDataset{}, 0)
	if r.K != 10 || r.Requests != 0 {
		t.Fatalf("empty dataset: K=%d requests=%d, want K=10 requests=0", r.K, r.Requests)
	}
}
