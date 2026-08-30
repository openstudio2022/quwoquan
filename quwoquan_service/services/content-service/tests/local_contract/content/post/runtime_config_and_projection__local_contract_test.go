// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package local_contract

import (
	"testing"

	"quwoquan_service/runtime/servicekit"
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

// TestDeclaredEnvOverrideCanDisableRecommendationModelService 保留「部署面可以
// 关停模型服务」这条能力，取证对象从手写 ApplyRecommendationModelEnvOverrides
// 换成声明式覆盖引擎：键名随迁移带上服务前缀
// （CONTENT_REC_MODEL_SERVICE_ENABLED），关停语义不变。
func TestDeclaredEnvOverrideCanDisableRecommendationModelService(t *testing.T) {
	t.Setenv("CONTENT_REC_MODEL_SERVICE_ENABLED", "false")
	holder := struct {
		RecModelService postruntimeconfig.RecommendationModelConfig `yaml:"rec_model_service" envPrefix:"REC_MODEL_SERVICE"`
	}{
		RecModelService: postruntimeconfig.RecommendationModelConfig{Enabled: true},
	}

	if err := servicekit.ApplyEnvOverrides("CONTENT", &holder); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if holder.RecModelService.Enabled {
		t.Fatal("CONTENT_REC_MODEL_SERVICE_ENABLED=false must disable the model service")
	}
}
