package recommendation

import (
	"math"
	"sort"
	"strings"
	"time"
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
	ContentID             string
	AuthorID              string
	ContentType           string
	RecallPath            string
	SupplySource          string
	IntersectionClass     string
	IntersectionSourceRef string
	Score                 float64 // calibrated predicted positive probability ∈ [0,1]
	Relevant              bool    // ground-truth positive (engaged: click/dwell/interaction)
	Negative              bool    // ground-truth negative feedback (dislike/report/hide)
	DuplicateExposure     bool    // already served to this user in an earlier request
	Served                bool
	Impressed             bool
	Clicked               bool
	DwellMs               int
	Hidden                bool
	Takedown              bool
	ExplanationExpanded   bool
}

// ReplayRequest is one replayed feed response (one feedRequestId), items ranked.
type ReplayRequest struct {
	FeedRequestID string
	UserID        string
	ChannelID     string
	Vertical      string
	ScorerVariant string
	Items         []ReplayItem
}

// ReplayDataset is a captured collection of feed requests plus the catalog size
// used as the coverage denominator.
type ReplayDataset struct {
	Requests                             []ReplayRequest
	EligibleContentCount                 int
	DataWindowStart                      time.Time
	DataWindowEnd                        time.Time
	PolicyDigest                         string
	ScorerVariant                        string
	TimeDecayFeatureFreshness            float64
	BaselineNonCollaborativePositiveRate float64
	BaselineCollaborativePositiveRate    float64
}

// ReplayPromotionThresholds freezes the local promotion gate used by replay
// reports. Zero values disable the corresponding threshold, which keeps the
// report usable for dry-runs while still allowing commercial gates to be strict.
type ReplayPromotionThresholds struct {
	MinRequests                  int
	MinServedItems               int
	MinNDCGAtK                   float64
	MinRecallAtK                 float64
	MinCoverageRate              float64
	MinDiversityRate             float64
	MinCollaborativeRecallLift   float64
	MaxRepeatExposureRate        float64
	MaxNegativeFeedbackRate      float64
	MinTimeDecayFeatureFreshness float64
}

// ReplayReportOptions carries run metadata and promotion thresholds that are
// not intrinsic to the captured dataset.
type ReplayReportOptions struct {
	DataWindowStart time.Time
	DataWindowEnd   time.Time
	PolicyDigest    string
	ScorerVariant   string
	Thresholds      ReplayPromotionThresholds
}

// ReplayReport holds the offline evaluation point metrics for one replay run.
type ReplayReport struct {
	K                         int                `json:"k"`
	Requests                  int                `json:"requests"`
	ItemsEvaluated            int                `json:"itemsEvaluated"`
	DataWindowStart           time.Time          `json:"dataWindowStart,omitempty"`
	DataWindowEnd             time.Time          `json:"dataWindowEnd,omitempty"`
	PolicyDigest              string             `json:"policyDigest,omitempty"`
	ScorerVariant             string             `json:"scorerVariant,omitempty"`
	Invalid                   bool               `json:"invalid"`
	InvalidReasons            []string           `json:"invalidReasons,omitempty"`
	PromotionAllowed          bool               `json:"promotionAllowed"`
	RollbackRecommended       bool               `json:"rollbackRecommended"`
	NDCGAtK                   float64            `json:"ndcgAtK"`
	RecallAtK                 float64            `json:"recallAtK"`
	MAPAtK                    float64            `json:"mapAtK"`
	CoverageRate              float64            `json:"coverageRate"`
	DiversityRate             float64            `json:"diversityRate"`
	RepeatExposureRate        float64            `json:"repeatExposureRate"`
	NegativeFeedbackRate      float64            `json:"negativeFeedbackRate"`
	CalibrationError          float64            `json:"calibrationError"`
	CollaborativeRecallLift   float64            `json:"collaborativeRecallLift"`
	FactExplanationCTR        float64            `json:"factExplanationCtr"`
	AffinityExplanationCTR    float64            `json:"affinityExplanationCtr"`
	TimeDecayFeatureFreshness float64            `json:"timeDecayFeatureFreshness,omitempty"`
	SupplySourceShare         map[string]float64 `json:"supplySourceShare,omitempty"`
}

// ComputeReplayReport computes the offline evaluation report over the dataset at
// cutoff k. Requests with no items are skipped; k<=0 defaults to 10.
func ComputeReplayReport(ds ReplayDataset, k int) ReplayReport {
	return ComputeReplayReportWithOptions(ds, k, ReplayReportOptions{})
}

// ComputeReplayReportWithOptions computes a commercial replay report with
// dataset/run metadata, invalid-sample reasons, and promotion/rollback verdicts.
func ComputeReplayReportWithOptions(ds ReplayDataset, k int, opts ReplayReportOptions) ReplayReport {
	if k <= 0 {
		k = 10
	}
	opts = normalizeReplayOptions(ds, opts)
	report := ReplayReport{
		K:                         k,
		DataWindowStart:           opts.DataWindowStart,
		DataWindowEnd:             opts.DataWindowEnd,
		PolicyDigest:              opts.PolicyDigest,
		ScorerVariant:             opts.ScorerVariant,
		PromotionAllowed:          true,
		TimeDecayFeatureFreshness: ds.TimeDecayFeatureFreshness,
		SupplySourceShare:         map[string]float64{},
	}

	var (
		ndcgSum, recallSum, mapSum, diversitySum float64
		ndcgN, recallN, mapN, diversityN         int
		servedTopK, dupTopK, negTopK             int
		collabServed, collabPositive             int
		otherServed, otherPositive               int
		factServed, factClicks                   int
		affinityServed, affinityClicks           int
		distinctServed                           = map[string]struct{}{}
		supplyCounts                             = map[string]int{}
		calBins                                  [10]struct {
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
			mapSum += averagePrecisionAtK(top, totalRel)
			mapN++
		}

		diversitySum += distinctAuthorRatio(top)
		diversityN++

		for _, it := range top {
			servedTopK++
			report.ItemsEvaluated++
			distinctServed[it.ContentID] = struct{}{}
			if it.DuplicateExposure {
				dupTopK++
			}
			if itemNegative(it) {
				negTopK++
			}
			if isCollaborativeRecallPath(it.RecallPath) {
				collabServed++
				if itemRelevant(it) {
					collabPositive++
				}
			} else {
				otherServed++
				if itemRelevant(it) {
					otherPositive++
				}
			}
			switch normalizedIntersectionClass(it.IntersectionClass) {
			case "fact":
				factServed++
				if itemClicked(it) {
					factClicks++
				}
			case "affinity":
				affinityServed++
				if itemClicked(it) {
					affinityClicks++
				}
			}
			source := strings.TrimSpace(strings.ToLower(it.SupplySource))
			if source == "" {
				source = "unknown"
			}
			supplyCounts[source]++
			// Calibration: bin by predicted probability decile.
			p := clamp01(it.Score)
			bin := int(p * 10)
			if bin > 9 {
				bin = 9
			}
			calBins[bin].predSum += p
			calBins[bin].n++
			if itemRelevant(it) {
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
	if mapN > 0 {
		report.MAPAtK = mapSum / float64(mapN)
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
		for source, count := range supplyCounts {
			report.SupplySourceShare[source] = float64(count) / float64(servedTopK)
		}
	}
	report.CalibrationError = expectedCalibrationError(calBins[:], servedTopK)
	report.CollaborativeRecallLift = recallLift(collabPositive, collabServed, otherPositive, otherServed)
	if ds.BaselineCollaborativePositiveRate > 0 && ds.BaselineNonCollaborativePositiveRate > 0 {
		report.CollaborativeRecallLift = ds.BaselineCollaborativePositiveRate/ds.BaselineNonCollaborativePositiveRate - 1
	}
	report.FactExplanationCTR = safeRate(factClicks, factServed)
	report.AffinityExplanationCTR = safeRate(affinityClicks, affinityServed)
	report.applyPromotionGate(opts.Thresholds)
	return report
}

// Emit publishes every report metric to Prometheus via the single offline-eval
// gauge, so dashboards/alerts read the same metric names as recommendation_slo.yaml.
func (r ReplayReport) Emit() {
	RecordOfflineEvalMetric("ndcg_at_k", r.NDCGAtK)
	RecordOfflineEvalMetric("recall_at_k", r.RecallAtK)
	RecordOfflineEvalMetric("map_at_k", r.MAPAtK)
	RecordOfflineEvalMetric("coverage_rate", r.CoverageRate)
	RecordOfflineEvalMetric("diversity_rate", r.DiversityRate)
	RecordOfflineEvalMetric("repeat_exposure_rate", r.RepeatExposureRate)
	RecordOfflineEvalMetric("negative_feedback_rate", r.NegativeFeedbackRate)
	RecordOfflineEvalMetric("calibration_error", r.CalibrationError)
	RecordOfflineEvalMetric("collaborative_recall_lift", r.CollaborativeRecallLift)
	RecordOfflineEvalMetric("fact_explanation_ctr", r.FactExplanationCTR)
	RecordOfflineEvalMetric("affinity_explanation_ctr", r.AffinityExplanationCTR)
	if r.TimeDecayFeatureFreshness > 0 {
		RecordOfflineEvalMetric("time_decay_feature_freshness", r.TimeDecayFeatureFreshness)
	}
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
		if itemRelevant(it) {
			n++
		}
	}
	return n
}

func averagePrecisionAtK(items []ReplayItem, totalRelevant int) float64 {
	if totalRelevant <= 0 {
		return 0
	}
	hits := 0
	precisionSum := 0.0
	denominator := totalRelevant
	if denominator > len(items) {
		denominator = len(items)
	}
	for i, it := range items {
		if !itemRelevant(it) {
			continue
		}
		hits++
		precisionSum += float64(hits) / float64(i+1)
	}
	if denominator == 0 {
		return 0
	}
	return precisionSum / float64(denominator)
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

func normalizeReplayOptions(ds ReplayDataset, opts ReplayReportOptions) ReplayReportOptions {
	if opts.DataWindowStart.IsZero() {
		opts.DataWindowStart = ds.DataWindowStart
	}
	if opts.DataWindowEnd.IsZero() {
		opts.DataWindowEnd = ds.DataWindowEnd
	}
	if opts.PolicyDigest == "" {
		opts.PolicyDigest = ds.PolicyDigest
	}
	if opts.ScorerVariant == "" {
		opts.ScorerVariant = ds.ScorerVariant
	}
	if opts.Thresholds.MinRequests == 0 {
		opts.Thresholds.MinRequests = 1
	}
	if opts.Thresholds.MinServedItems == 0 {
		opts.Thresholds.MinServedItems = 1
	}
	return opts
}

func (r *ReplayReport) applyPromotionGate(th ReplayPromotionThresholds) {
	if r.Requests < th.MinRequests {
		r.InvalidReasons = append(r.InvalidReasons, "requests below minimum")
	}
	if r.ItemsEvaluated < th.MinServedItems {
		r.InvalidReasons = append(r.InvalidReasons, "served items below minimum")
	}
	if !r.DataWindowStart.IsZero() && !r.DataWindowEnd.IsZero() && !r.DataWindowEnd.After(r.DataWindowStart) {
		r.InvalidReasons = append(r.InvalidReasons, "invalid data window")
	}
	r.Invalid = len(r.InvalidReasons) > 0
	r.PromotionAllowed = !r.Invalid
	if thresholdFailed(th.MinNDCGAtK, r.NDCGAtK, true) ||
		thresholdFailed(th.MinRecallAtK, r.RecallAtK, true) ||
		thresholdFailed(th.MinCoverageRate, r.CoverageRate, true) ||
		thresholdFailed(th.MinDiversityRate, r.DiversityRate, true) ||
		thresholdFailed(th.MinCollaborativeRecallLift, r.CollaborativeRecallLift, true) ||
		thresholdFailed(th.MinTimeDecayFeatureFreshness, r.TimeDecayFeatureFreshness, true) {
		r.PromotionAllowed = false
	}
	if thresholdFailed(th.MaxRepeatExposureRate, r.RepeatExposureRate, false) ||
		thresholdFailed(th.MaxNegativeFeedbackRate, r.NegativeFeedbackRate, false) {
		r.PromotionAllowed = false
		r.RollbackRecommended = true
	}
}

func thresholdFailed(threshold, value float64, minimum bool) bool {
	if threshold == 0 {
		return false
	}
	if minimum {
		return value < threshold
	}
	return value > threshold
}

func itemRelevant(it ReplayItem) bool {
	return it.Relevant || it.Clicked || it.DwellMs >= 3000
}

func itemClicked(it ReplayItem) bool {
	return it.Clicked || it.Relevant
}

func itemNegative(it ReplayItem) bool {
	return it.Negative || it.Hidden || it.Takedown
}

func isCollaborativeRecallPath(path string) bool {
	switch strings.TrimSpace(strings.ToLower(path)) {
	case "collab_i2i", "collab_u2i", "itemcf", "swing_i2i":
		return true
	default:
		return false
	}
}

func normalizedIntersectionClass(raw string) string {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "fact":
		return "fact"
	case "affinity", "recommended", "recommendation":
		return "affinity"
	default:
		return ""
	}
}

func safeRate(num, den int) float64 {
	if den <= 0 {
		return 0
	}
	return float64(num) / float64(den)
}

func recallLift(collabPositive, collabServed, otherPositive, otherServed int) float64 {
	if collabServed <= 0 || otherServed <= 0 {
		return 0
	}
	otherRate := safeRate(otherPositive, otherServed)
	if otherRate <= 0 {
		return 0
	}
	return safeRate(collabPositive, collabServed)/otherRate - 1
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
