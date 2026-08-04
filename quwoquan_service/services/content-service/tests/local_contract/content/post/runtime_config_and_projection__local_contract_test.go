// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package local_contract

import (
	"testing"

	postruntimeconfig "quwoquan_service/services/content-service/internal/content/post/infrastructure/runtimeconfig"
)

func TestContentReleaseWorkloadIncludesCommercialContentSlice(t *testing.T) {
	for _, workload := range []string{"content-release", "content-commercial", "CONTENT-COMMERCIAL"} {
		t.Run(workload, func(t *testing.T) {
			t.Setenv("QWQ_WORKLOAD", workload)
			if !postruntimeconfig.ContentSliceWorkload() {
				t.Fatalf("workload %q must use the bounded content data plane", workload)
			}
		})
	}
	t.Setenv("QWQ_WORKLOAD", "full")
	if postruntimeconfig.ContentSliceWorkload() {
		t.Fatal("full workload must not be classified as a bounded content slice")
	}
}

func TestApplyEnvOverridesCanDisableRecommendationModelService(t *testing.T) {
	t.Setenv("REC_MODEL_SERVICE_ENABLED", "false")
	cfg := postruntimeconfig.RecommendationModelConfig{Enabled: true}

	postruntimeconfig.ApplyRecommendationModelEnvOverrides(&cfg)

	if cfg.Enabled {
		t.Fatal("REC_MODEL_SERVICE_ENABLED=false must disable the model service")
	}
}
