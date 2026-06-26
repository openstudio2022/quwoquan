package recommendation

import (
	"fmt"
	"math"
	"strings"

	"quwoquan_service/runtime/recpolicy"
)

// Online AB admission evaluation.
//
// Config truth source: recpolicy.ABAdmissionConfig (policy.yaml abAdmission).
// This file is the single runtime/offline consumer that decides whether an
// experiment is trustworthy (Valid) and which challenger buckets are rollback
// candidates. Admission outcomes feed recommendation_feed_ab_experiment_validity_total
// (SLI ab_experiment_validity) via RecordABExperimentValidity.

// BucketObservation is the measured outcome of one experiment bucket over the
// evaluation window. Conversions is the primary-metric numerator (e.g. clicks),
// Samples the denominator (e.g. impressions); PrimaryRate = Conversions/Samples.
type BucketObservation struct {
	Bucket      string
	DesignPct   int // intended split from ExperimentBucket.WeightPct
	Samples     int
	Conversions int
	Guardrails  ABGuardrailMetrics
}

// PrimaryRate is the observed primary-metric rate for the bucket.
func (b BucketObservation) PrimaryRate() float64 {
	if b.Samples <= 0 {
		return 0
	}
	return float64(b.Conversions) / float64(b.Samples)
}

// ABExperimentObservation is the full measured state of one experiment.
type ABExperimentObservation struct {
	ExperimentID  string
	ControlBucket string
	Buckets       []BucketObservation
}

// ABGuardrailMetrics captures commercial protection metrics for one bucket over
// the same evaluation window as the primary metric.
type ABGuardrailMetrics struct {
	NegativeFeedbackRate    float64
	RepeatExposureRate      float64
	UnknownAttributionRate  float64
	BehaviorIngestDropRate  float64
	P95LatencyMs            float64
	ScenarioConsumptionRate float64
	TravelMisrouteRate      float64
}

// ABGuardrailThresholds defines promotion-blocking guardrails. Zero values are
// treated as unset so local dry-runs can start with only sample/SRM checks.
type ABGuardrailThresholds struct {
	MaxNegativeFeedbackRate    float64
	MaxRepeatExposureRate      float64
	MaxUnknownAttributionRate  float64
	MaxBehaviorIngestDropRate  float64
	MaxP95LatencyMs            float64
	MinScenarioConsumptionRate float64
	MaxTravelMisrouteRate      float64
}

// ABAdmissionResult is the admission verdict for one experiment.
type ABAdmissionResult struct {
	ExperimentID       string
	Valid              bool
	Reasons            []string // why invalid (empty when valid)
	RollbackCandidates []string // challenger buckets in significant regression
}

// ABBucketReport is the normalized report row for one bucket.
type ABBucketReport struct {
	Bucket               string   `json:"bucket"`
	DesignPct            int      `json:"designPct"`
	ActualPct            float64  `json:"actualPct"`
	Samples              int      `json:"samples"`
	Conversions          int      `json:"conversions"`
	PrimaryRate          float64  `json:"primaryRate"`
	RelativeLift         float64  `json:"relativeLift"`
	SignificantVsControl bool     `json:"significantVsControl"`
	GuardrailViolations  []string `json:"guardrailViolations,omitempty"`
}

// ABExperimentReport is the fixed online AB analysis template used by
// recommendation promotion reviews. It is derived from the same admission result
// that feeds recommendation_feed_ab_experiment_validity_total.
type ABExperimentReport struct {
	ExperimentID        string           `json:"experimentId"`
	ControlBucket       string           `json:"controlBucket"`
	PrimaryMetric       string           `json:"primaryMetric"`
	MinSamplesPerBucket int              `json:"minSamplesPerBucket"`
	MaxBucketSkewPct    float64          `json:"maxBucketSkewPct"`
	SignificanceLevel   float64          `json:"significanceLevel"`
	MinDetectableEffect float64          `json:"minDetectableEffect"`
	Valid               bool             `json:"valid"`
	Reasons             []string         `json:"reasons,omitempty"`
	RollbackCandidates  []string         `json:"rollbackCandidates,omitempty"`
	PromotionAllowed    bool             `json:"promotionAllowed"`
	Buckets             []ABBucketReport `json:"buckets"`
}

// EvaluateABAdmission decides whether an experiment's measurements are
// trustworthy and flags rollback candidates. It is pure (no metric emission) so
// it is unit-testable; EvaluateAndRecordABAdmission wraps it for runtime use.
//
//   - Valid requires: every bucket clears minSamplesPerBucket AND the realized
//     split is within maxBucketSkewPct of design (sample-ratio-mismatch guard).
//   - Rollback candidate: a challenger whose primary rate is below control ×
//     rollback.regressionRatio, where the relative drop clears minDetectableEffect
//     and the two-proportion difference is significant at significanceLevel.
//
// A zero-value config disables admission gating: the experiment is reported Valid
// with no rollback analysis (callers should not act on validity in that case).
func EvaluateABAdmission(obs ABExperimentObservation, cfg recpolicy.ABAdmissionConfig) ABAdmissionResult {
	return EvaluateABAdmissionWithGuardrails(obs, cfg, ABGuardrailThresholds{})
}

// EvaluateABAdmissionWithGuardrails extends admission with commercial protection
// guardrails. Guardrail violations make the experiment invalid for promotion but
// keep rollback-candidate detection on the primary metric intact.
func EvaluateABAdmissionWithGuardrails(obs ABExperimentObservation, cfg recpolicy.ABAdmissionConfig, thresholds ABGuardrailThresholds) ABAdmissionResult {
	res := ABAdmissionResult{ExperimentID: obs.ExperimentID, Valid: true}

	if (cfg == recpolicy.ABAdmissionConfig{}) {
		return res
	}
	if len(obs.Buckets) == 0 {
		res.Valid = false
		res.Reasons = append(res.Reasons, "no bucket observations")
		return res
	}

	totalSamples := 0
	for _, b := range obs.Buckets {
		totalSamples += b.Samples
	}

	for _, b := range obs.Buckets {
		if b.Samples < cfg.MinSamplesPerBucket {
			res.Valid = false
			res.Reasons = append(res.Reasons, fmt.Sprintf("bucket %s samples %d < min %d", b.Bucket, b.Samples, cfg.MinSamplesPerBucket))
		}
		if totalSamples > 0 && b.DesignPct > 0 {
			actualPct := 100 * float64(b.Samples) / float64(totalSamples)
			if math.Abs(actualPct-float64(b.DesignPct)) > cfg.MaxBucketSkewPct {
				res.Valid = false
				res.Reasons = append(res.Reasons, fmt.Sprintf("bucket %s split %.1f%% skewed from design %d%% (>%.1f%%)", b.Bucket, actualPct, b.DesignPct, cfg.MaxBucketSkewPct))
			}
			if violations := guardrailViolations(b.Guardrails, thresholds); len(violations) > 0 {
				res.Valid = false
				for _, violation := range violations {
					res.Reasons = append(res.Reasons, fmt.Sprintf("bucket %s guardrail %s", b.Bucket, violation))
				}
			}
		}
	}

	control, ok := findBucket(obs.Buckets, obs.ControlBucket)
	if !ok {
		res.Valid = false
		res.Reasons = append(res.Reasons, fmt.Sprintf("control bucket %q not observed", obs.ControlBucket))
		return res
	}

	controlRate := control.PrimaryRate()
	for _, b := range obs.Buckets {
		if b.Bucket == control.Bucket {
			continue
		}
		rate := b.PrimaryRate()
		if controlRate <= 0 {
			continue
		}
		relDrop := (controlRate - rate) / controlRate
		below := rate < controlRate*cfg.Rollback.RegressionRatio
		if below && relDrop >= cfg.MinDetectableEffect &&
			twoProportionSignificant(control, b, cfg.SignificanceLevel) {
			res.RollbackCandidates = append(res.RollbackCandidates, b.Bucket)
		}
	}
	return res
}

// EvaluateAndRecordABAdmission runs EvaluateABAdmission and records the validity
// outcome to Prometheus (skipped when admission gating is disabled).
func EvaluateAndRecordABAdmission(obs ABExperimentObservation, cfg recpolicy.ABAdmissionConfig) ABAdmissionResult {
	res := EvaluateABAdmission(obs, cfg)
	if (cfg != recpolicy.ABAdmissionConfig{}) {
		RecordABExperimentValidity(obs.ExperimentID, res.Valid)
	}
	return res
}

// BuildABExperimentReport produces the report template reviewed by product,
// algorithm, data engineering, and operations before promotion.
func BuildABExperimentReport(obs ABExperimentObservation, cfg recpolicy.ABAdmissionConfig, thresholds ABGuardrailThresholds) ABExperimentReport {
	res := EvaluateABAdmissionWithGuardrails(obs, cfg, thresholds)
	report := ABExperimentReport{
		ExperimentID:        obs.ExperimentID,
		ControlBucket:       obs.ControlBucket,
		PrimaryMetric:       cfg.PrimaryMetric,
		MinSamplesPerBucket: cfg.MinSamplesPerBucket,
		MaxBucketSkewPct:    cfg.MaxBucketSkewPct,
		SignificanceLevel:   cfg.SignificanceLevel,
		MinDetectableEffect: cfg.MinDetectableEffect,
		Valid:               res.Valid,
		Reasons:             append([]string(nil), res.Reasons...),
		RollbackCandidates:  append([]string(nil), res.RollbackCandidates...),
	}
	totalSamples := 0
	for _, b := range obs.Buckets {
		totalSamples += b.Samples
	}
	control, hasControl := findBucket(obs.Buckets, obs.ControlBucket)
	for _, b := range obs.Buckets {
		row := ABBucketReport{
			Bucket:              b.Bucket,
			DesignPct:           b.DesignPct,
			Samples:             b.Samples,
			Conversions:         b.Conversions,
			PrimaryRate:         b.PrimaryRate(),
			GuardrailViolations: guardrailViolations(b.Guardrails, thresholds),
		}
		if totalSamples > 0 {
			row.ActualPct = 100 * float64(b.Samples) / float64(totalSamples)
		}
		if hasControl && b.Bucket != control.Bucket && control.PrimaryRate() > 0 {
			row.RelativeLift = b.PrimaryRate()/control.PrimaryRate() - 1
			row.SignificantVsControl = twoProportionSignificant(control, b, cfg.SignificanceLevel)
		}
		report.Buckets = append(report.Buckets, row)
	}
	report.PromotionAllowed = report.Valid &&
		len(report.RollbackCandidates) == 0 &&
		!report.hasGuardrailViolations()
	return report
}

func (r ABExperimentReport) hasGuardrailViolations() bool {
	for _, b := range r.Buckets {
		if len(b.GuardrailViolations) > 0 {
			return true
		}
	}
	return false
}

func findBucket(buckets []BucketObservation, name string) (BucketObservation, bool) {
	for _, b := range buckets {
		if b.Bucket == name {
			return b, true
		}
	}
	return BucketObservation{}, false
}

func guardrailViolations(m ABGuardrailMetrics, th ABGuardrailThresholds) []string {
	var out []string
	if th.MaxNegativeFeedbackRate > 0 && m.NegativeFeedbackRate > th.MaxNegativeFeedbackRate {
		out = append(out, "negative_feedback_rate")
	}
	if th.MaxRepeatExposureRate > 0 && m.RepeatExposureRate > th.MaxRepeatExposureRate {
		out = append(out, "repeat_exposure_rate")
	}
	if th.MaxUnknownAttributionRate > 0 && m.UnknownAttributionRate > th.MaxUnknownAttributionRate {
		out = append(out, "unknown_attribution_rate")
	}
	if th.MaxBehaviorIngestDropRate > 0 && m.BehaviorIngestDropRate > th.MaxBehaviorIngestDropRate {
		out = append(out, "behavior_ingest_drop_rate")
	}
	if th.MaxP95LatencyMs > 0 && m.P95LatencyMs > th.MaxP95LatencyMs {
		out = append(out, "p95_latency_ms")
	}
	if th.MinScenarioConsumptionRate > 0 && m.ScenarioConsumptionRate < th.MinScenarioConsumptionRate {
		out = append(out, "scenario_consumption_rate")
	}
	if th.MaxTravelMisrouteRate > 0 && m.TravelMisrouteRate > th.MaxTravelMisrouteRate {
		out = append(out, "travel_misroute_rate")
	}
	for i := range out {
		out[i] = strings.TrimSpace(out[i])
	}
	return out
}

// twoProportionSignificant runs a two-sided two-proportion z-test and reports
// whether the difference is significant at alpha (p-value < alpha). Uses the
// pooled-variance Wald statistic and the normal survival function via math.Erfc.
func twoProportionSignificant(a, b BucketObservation, alpha float64) bool {
	if a.Samples <= 0 || b.Samples <= 0 {
		return false
	}
	n1, n2 := float64(a.Samples), float64(b.Samples)
	p1, p2 := a.PrimaryRate(), b.PrimaryRate()
	pPool := float64(a.Conversions+b.Conversions) / (n1 + n2)
	denom := pPool * (1 - pPool) * (1/n1 + 1/n2)
	if denom <= 0 {
		return false
	}
	z := (p1 - p2) / math.Sqrt(denom)
	pValue := math.Erfc(math.Abs(z) / math.Sqrt2) // two-sided
	return pValue < alpha
}
