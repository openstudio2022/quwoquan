package recommendation

import (
	"math"
	"sort"
)

// Offline replay evaluation skeleton.
//
// A replay run re-scores a captured set of feed requests (the dataset) and scores
// ranking quality against ground-truth engagement/negative labels. This file owns
// the dataset shape and the metric computation; ComputeReplayReport is the single
// place metrics are derived, and ReplayReport.Emit is the single place they are
// published to Prometheus (recommendation_offline_eval_metric_value{metric=...},
// the source referenced by recommendation_slo.yaml offline_* SLIs).
//
// Scope (skeleton): per-run point metrics. Negative-feedback convergence is a
// cross-run comparison (NegativeFeedbackRate of report vN vs vN-1) performed by
// the replay harness, not in a single report.

// ReplayItem is one served candidate in a replayed feed, in served rank order.
// Score MUST be a calibrated click/engagement probability in [0,1] for
// CalibrationError to be meaningful; ranking metrics only use rank order + labels.
type ReplayItem struct {
	ContentID         string
	AuthorID          string
	ContentType       string
	Score             float64 // calibrated predicted positive probability ∈ [0,1]
	Relevant          bool    // ground-truth positive (engaged: click/dwell/interaction)
	Negative          bool    // ground-truth negative feedback (dislike/report/hide)
	DuplicateExposure bool    // already served to this user in an earlier request
}

// ReplayRequest is one replayed feed response (one feedRequestId), items ranked.
type ReplayRequest struct {
	FeedRequestID string
	UserID        string
	Items         []ReplayItem
}

// ReplayDataset is a captured collection of feed requests plus the catalog size
// used as the coverage denominator.
type ReplayDataset struct {
	Requests             []ReplayRequest
	EligibleContentCount int
}

// ReplayReport holds the offline evaluation point metrics for one replay run.
type ReplayReport struct {
	K                    int     `json:"k"`
	Requests             int     `json:"requests"`
	NDCGAtK              float64 `json:"ndcgAtK"`
	RecallAtK            float64 `json:"recallAtK"`
	CoverageRate         float64 `json:"coverageRate"`
	DiversityRate        float64 `json:"diversityRate"`
	RepeatExposureRate   float64 `json:"repeatExposureRate"`
	NegativeFeedbackRate float64 `json:"negativeFeedbackRate"`
	CalibrationError     float64 `json:"calibrationError"`
}

// ComputeReplayReport computes the offline evaluation report over the dataset at
// cutoff k. Requests with no items are skipped; k<=0 defaults to 10.
func ComputeReplayReport(ds ReplayDataset, k int) ReplayReport {
	if k <= 0 {
		k = 10
	}
	report := ReplayReport{K: k}

	var (
		ndcgSum, recallSum, diversitySum float64
		ndcgN, recallN, diversityN       int
		servedTopK, dupTopK, negTopK     int
		distinctServed                   = map[string]struct{}{}
		calBins                          [10]struct {
			predSum float64
			posSum  float64
			n       int
		}
	)

	for _, req := range ds.Requests {
		if len(req.Items) == 0 {
			continue
		}
		report.Requests++
		top := req.Items
		if len(top) > k {
			top = top[:k]
		}

		ndcgSum += ndcgAtK(top)
		ndcgN++

		if totalRel := countRelevant(req.Items); totalRel > 0 {
			recallSum += float64(countRelevant(top)) / float64(totalRel)
			recallN++
		}

		diversitySum += distinctAuthorRatio(top)
		diversityN++

		for _, it := range top {
			servedTopK++
			distinctServed[it.ContentID] = struct{}{}
			if it.DuplicateExposure {
				dupTopK++
			}
			if it.Negative {
				negTopK++
			}
			// Calibration: bin by predicted probability decile.
			p := clamp01(it.Score)
			bin := int(p * 10)
			if bin > 9 {
				bin = 9
			}
			calBins[bin].predSum += p
			calBins[bin].n++
			if it.Relevant {
				calBins[bin].posSum += 1
			}
		}
	}

	if ndcgN > 0 {
		report.NDCGAtK = ndcgSum / float64(ndcgN)
	}
	if recallN > 0 {
		report.RecallAtK = recallSum / float64(recallN)
	}
	if diversityN > 0 {
		report.DiversityRate = diversitySum / float64(diversityN)
	}
	if ds.EligibleContentCount > 0 {
		report.CoverageRate = float64(len(distinctServed)) / float64(ds.EligibleContentCount)
	}
	if servedTopK > 0 {
		report.RepeatExposureRate = float64(dupTopK) / float64(servedTopK)
		report.NegativeFeedbackRate = float64(negTopK) / float64(servedTopK)
	}
	report.CalibrationError = expectedCalibrationError(calBins[:], servedTopK)
	return report
}

// Emit publishes every report metric to Prometheus via the single offline-eval
// gauge, so dashboards/alerts read the same metric names as recommendation_slo.yaml.
func (r ReplayReport) Emit() {
	RecordOfflineEvalMetric("ndcg_at_k", r.NDCGAtK)
	RecordOfflineEvalMetric("recall_at_k", r.RecallAtK)
	RecordOfflineEvalMetric("coverage_rate", r.CoverageRate)
	RecordOfflineEvalMetric("diversity_rate", r.DiversityRate)
	RecordOfflineEvalMetric("repeat_exposure_rate", r.RepeatExposureRate)
	RecordOfflineEvalMetric("negative_feedback_rate", r.NegativeFeedbackRate)
	RecordOfflineEvalMetric("calibration_error", r.CalibrationError)
}

func ndcgAtK(items []ReplayItem) float64 {
	dcg := 0.0
	for i, it := range items {
		if it.Relevant {
			dcg += 1.0 / math.Log2(float64(i+2))
		}
	}
	// IDCG: all relevant items ranked first.
	rel := countRelevant(items)
	idcg := 0.0
	for i := 0; i < rel; i++ {
		idcg += 1.0 / math.Log2(float64(i+2))
	}
	if idcg == 0 {
		return 0
	}
	return dcg / idcg
}

func countRelevant(items []ReplayItem) int {
	n := 0
	for _, it := range items {
		if it.Relevant {
			n++
		}
	}
	return n
}

func distinctAuthorRatio(items []ReplayItem) float64 {
	if len(items) == 0 {
		return 0
	}
	seen := map[string]struct{}{}
	for _, it := range items {
		seen[it.AuthorID] = struct{}{}
	}
	return float64(len(seen)) / float64(len(items))
}

// expectedCalibrationError is the sample-weighted gap between predicted positive
// probability and actual positive rate across deciles (standard ECE).
func expectedCalibrationError(bins []struct {
	predSum float64
	posSum  float64
	n       int
}, total int) float64 {
	if total == 0 {
		return 0
	}
	ece := 0.0
	for _, b := range bins {
		if b.n == 0 {
			continue
		}
		avgPred := b.predSum / float64(b.n)
		avgPos := b.posSum / float64(b.n)
		ece += (float64(b.n) / float64(total)) * math.Abs(avgPred-avgPos)
	}
	return ece
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

// SortRequestItemsByScore re-orders each request's items by descending Score. The
// replay harness uses this to produce the candidate ranking under a new policy
// before scoring, keeping the dataset capture (served order) separate from the
// re-scored order under evaluation.
func SortRequestItemsByScore(ds ReplayDataset) {
	for ri := range ds.Requests {
		items := ds.Requests[ri].Items
		sort.SliceStable(items, func(i, j int) bool { return items[i].Score > items[j].Score })
	}
}
