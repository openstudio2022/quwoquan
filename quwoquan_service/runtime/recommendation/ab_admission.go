package recommendation

import (
	"fmt"
	"math"

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

// ABAdmissionResult is the admission verdict for one experiment.
type ABAdmissionResult struct {
	ExperimentID       string
	Valid              bool
	Reasons            []string // why invalid (empty when valid)
	RollbackCandidates []string // challenger buckets in significant regression
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

func findBucket(buckets []BucketObservation, name string) (BucketObservation, bool) {
	for _, b := range buckets {
		if b.Bucket == name {
			return b, true
		}
	}
	return BucketObservation{}, false
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
