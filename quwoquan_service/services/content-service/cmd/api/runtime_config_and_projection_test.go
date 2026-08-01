package main

import "testing"

func TestApplyEnvOverridesCanDisableRecommendationModelService(t *testing.T) {
	t.Setenv("REC_MODEL_SERVICE_ENABLED", "false")
	cfg := config{}
	cfg.RecModelService.Enabled = true

	applyEnvOverrides(&cfg)

	if cfg.RecModelService.Enabled {
		t.Fatal("REC_MODEL_SERVICE_ENABLED=false must disable the model service")
	}
}
