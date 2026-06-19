package recommendation

import (
	"testing"

	"quwoquan_service/runtime/recpolicy"
)

func admissionCfg() recpolicy.ABAdmissionConfig {
	return recpolicy.ABAdmissionConfig{
		MinSamplesPerBucket: 1000,
		MaxBucketSkewPct:    5.0,
		SignificanceLevel:   0.05,
		MinDetectableEffect: 0.02,
		PrimaryMetric:       "ctr",
		Rollback:            recpolicy.ABRollbackConfig{RegressionRatio: 0.95, AutoRollback: false},
	}
}

func TestEvaluateABAdmission_ValidNoRollback(t *testing.T) {
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 5000, Conversions: 500},     // 10.0% ctr
			{Bucket: "challenger", DesignPct: 50, Samples: 5000, Conversions: 510}, // 10.2% ctr
		},
	}
	res := EvaluateABAdmission(obs, admissionCfg())
	if !res.Valid {
		t.Fatalf("expected valid, reasons=%v", res.Reasons)
	}
	if len(res.RollbackCandidates) != 0 {
		t.Fatalf("expected no rollback candidates, got %v", res.RollbackCandidates)
	}
}

func TestEvaluateABAdmission_InsufficientSamples(t *testing.T) {
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 500, Conversions: 50},
			{Bucket: "challenger", DesignPct: 50, Samples: 500, Conversions: 52},
		},
	}
	if res := EvaluateABAdmission(obs, admissionCfg()); res.Valid {
		t.Fatalf("expected invalid for low samples, got valid")
	}
}

func TestEvaluateABAdmission_SampleRatioMismatch(t *testing.T) {
	// 90/10 realized split vs 50/50 design → SRM skew > 5%.
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 9000, Conversions: 900},
			{Bucket: "challenger", DesignPct: 50, Samples: 1000, Conversions: 100},
		},
	}
	res := EvaluateABAdmission(obs, admissionCfg())
	if res.Valid {
		t.Fatalf("expected invalid for SRM, got valid")
	}
}

func TestEvaluateABAdmission_RollbackCandidate(t *testing.T) {
	// Challenger 8% vs control 10%: relDrop 0.2 ≥ MDE, below 0.95×control, large n → significant.
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 10000, Conversions: 1000},
			{Bucket: "challenger", DesignPct: 50, Samples: 10000, Conversions: 800},
		},
	}
	res := EvaluateABAdmission(obs, admissionCfg())
	if !res.Valid {
		t.Fatalf("expected valid measurement, reasons=%v", res.Reasons)
	}
	if len(res.RollbackCandidates) != 1 || res.RollbackCandidates[0] != "challenger" {
		t.Fatalf("expected challenger rollback candidate, got %v", res.RollbackCandidates)
	}
}

func TestEvaluateABAdmission_SmallRegressionNotSignificant(t *testing.T) {
	// Challenger 9.8% vs control 10%: tiny drop, below MDE → not a rollback candidate.
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 10000, Conversions: 1000},
			{Bucket: "challenger", DesignPct: 50, Samples: 10000, Conversions: 980},
		},
	}
	res := EvaluateABAdmission(obs, admissionCfg())
	if len(res.RollbackCandidates) != 0 {
		t.Fatalf("expected no rollback for sub-MDE drop, got %v", res.RollbackCandidates)
	}
}

func TestEvaluateABAdmission_DisabledConfigNoGating(t *testing.T) {
	obs := ABExperimentObservation{
		ExperimentID:  "exp1",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 1, Conversions: 0},
			{Bucket: "challenger", DesignPct: 50, Samples: 1, Conversions: 0},
		},
	}
	// Zero config disables gating: valid regardless of (here degenerate) data.
	res := EvaluateABAdmission(obs, recpolicy.ABAdmissionConfig{})
	if !res.Valid || len(res.RollbackCandidates) != 0 {
		t.Fatalf("disabled config should pass through valid with no rollback, got %+v", res)
	}
}

func TestEvaluateAndRecordABAdmission_RecordsValidity(t *testing.T) {
	obs := ABExperimentObservation{
		ExperimentID:  "exp_rec",
		ControlBucket: "control",
		Buckets: []BucketObservation{
			{Bucket: "control", DesignPct: 50, Samples: 5000, Conversions: 500},
			{Bucket: "challenger", DesignPct: 50, Samples: 5000, Conversions: 505},
		},
	}
	// Exercises the emitter wrapper; must not panic and must return the verdict.
	if res := EvaluateAndRecordABAdmission(obs, admissionCfg()); !res.Valid {
		t.Fatalf("expected valid, reasons=%v", res.Reasons)
	}
}
