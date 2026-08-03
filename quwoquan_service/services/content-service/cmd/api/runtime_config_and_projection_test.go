package main

import "testing"

func TestContentReleaseWorkloadIncludesCommercialContentSlice(t *testing.T) {
	for _, workload := range []string{"content-release", "content-commercial", "CONTENT-COMMERCIAL"} {
		t.Run(workload, func(t *testing.T) {
			t.Setenv("QWQ_WORKLOAD", workload)
			if !contentSliceWorkload() {
				t.Fatalf("workload %q must use the bounded content data plane", workload)
			}
		})
	}
	t.Setenv("QWQ_WORKLOAD", "full")
	if contentSliceWorkload() {
		t.Fatal("full workload must not be classified as a bounded content slice")
	}
}

func TestApplyEnvOverridesCanDisableRecommendationModelService(t *testing.T) {
	t.Setenv("REC_MODEL_SERVICE_ENABLED", "false")
	cfg := config{}
	cfg.RecModelService.Enabled = true

	applyEnvOverrides(&cfg)

	if cfg.RecModelService.Enabled {
		t.Fatal("REC_MODEL_SERVICE_ENABLED=false must disable the model service")
	}
}
