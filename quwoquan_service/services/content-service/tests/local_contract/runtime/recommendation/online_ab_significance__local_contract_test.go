package recommendationlocalcontract

import (
	"testing"

	"quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/recpolicy"
)

func TestOnlineABSignificanceCommercialReportLocalContract(t *testing.T) {
	cfg := recpolicy.ABAdmissionConfig{
		MinSamplesPerBucket: 1000,
		MaxBucketSkewPct:    5.0,
		SignificanceLevel:   0.05,
		MinDetectableEffect: 0.02,
		PrimaryMetric:       "ctr",
		Rollback:            recpolicy.ABRollbackConfig{RegressionRatio: 0.95},
	}
	guardrails := recommendation.ABGuardrailThresholds{
		MaxNegativeFeedbackRate:    0.08,
		MaxRepeatExposureRate:      0.01,
		MaxUnknownAttributionRate:  0.05,
		MaxBehaviorIngestDropRate:  0.01,
		MaxP95LatencyMs:            200,
		MinScenarioConsumptionRate: 0.02,
		MaxTravelMisrouteRate:      0.01,
	}
	report := recommendation.BuildABExperimentReport(recommendation.ABExperimentObservation{
		ExperimentID:  "rec_commercial_contract",
		ControlBucket: "control",
		Buckets: []recommendation.BucketObservation{
			{
				Bucket: "control", DesignPct: 50, Samples: 10000, Conversions: 1000,
				Guardrails: recommendation.ABGuardrailMetrics{ScenarioConsumptionRate: 0.06},
			},
			{
				Bucket: "challenger", DesignPct: 50, Samples: 10000, Conversions: 1110,
				Guardrails: recommendation.ABGuardrailMetrics{
					NegativeFeedbackRate:    0.04,
					RepeatExposureRate:      0.002,
					P95LatencyMs:            120,
					ScenarioConsumptionRate: 0.06,
				},
			},
		},
	}, cfg, guardrails)

	if !report.Valid || !report.PromotionAllowed {
		t.Fatalf("AB report should be valid and promotable: %+v", report)
	}
	if report.PrimaryMetric != "ctr" || report.MinSamplesPerBucket != 1000 || report.SignificanceLevel != 0.05 {
		t.Fatalf("AB report must carry admission config: %+v", report)
	}
	if len(report.Buckets) != 2 || report.Buckets[1].RelativeLift <= 0 || !report.Buckets[1].SignificantVsControl {
		t.Fatalf("challenger lift/significance missing: %+v", report.Buckets)
	}

	regressed := recommendation.BuildABExperimentReport(recommendation.ABExperimentObservation{
		ExperimentID:  "rec_commercial_guardrail",
		ControlBucket: "control",
		Buckets: []recommendation.BucketObservation{
			{
				Bucket: "control", DesignPct: 50, Samples: 5000, Conversions: 500,
				Guardrails: recommendation.ABGuardrailMetrics{ScenarioConsumptionRate: 0.06},
			},
			{
				Bucket: "challenger", DesignPct: 50, Samples: 5000, Conversions: 560,
				Guardrails: recommendation.ABGuardrailMetrics{
					NegativeFeedbackRate:    0.12,
					ScenarioConsumptionRate: 0.06,
				},
			},
		},
	}, cfg, guardrails)
	if regressed.Valid || regressed.PromotionAllowed {
		t.Fatalf("guardrail breach must invalidate AB report: %+v", regressed)
	}
}
