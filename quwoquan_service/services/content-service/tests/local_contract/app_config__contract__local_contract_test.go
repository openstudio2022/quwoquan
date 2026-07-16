package local_contract

import (
	"os"
	"strings"
	"testing"

	postapp "quwoquan_service/services/content-service/internal/application/post"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestProductionImagePackagesRecommendationMetadata(t *testing.T) {
	dockerfile, err := os.ReadFile("../../deploy/Dockerfile")
	if err != nil {
		t.Fatalf("read production Dockerfile: %v", err)
	}
	content := string(dockerfile)
	for _, required := range []string{
		"COPY contracts/metadata/recommendation/rec_model/segments.yaml /etc/quwoquan/metadata/recommendation/segments.yaml",
		"COPY contracts/metadata/recommendation/rec_model/policy.yaml /etc/quwoquan/metadata/recommendation/policy.yaml",
		"ENV QWQ_SEGMENTS_PATH=/etc/quwoquan/metadata/recommendation/segments.yaml",
		"ENV QWQ_REC_POLICY_PATH=/etc/quwoquan/metadata/recommendation/policy.yaml",
	} {
		if !strings.Contains(content, required) {
			t.Fatalf("production image must package recommendation metadata contract %q", required)
		}
	}
}

func TestGetAppConfigUsesGenericCanaryMatrixPayload(t *testing.T) {
	service := postapp.NewPostService(
		postapp.BindDataPorts(testsupport.NewPostStore(nil)),
		postapp.WithStoryRuntimeConfig(postapp.StoryRuntimeConfig{
			ExperimentBucket: "rollout_20",
			CurrentStage:     "20%",
			CanaryMatrix: []postapp.StoryCanaryStage{
				{Stage: "5%", RolloutPercent: 5},
				{Stage: "20%", RolloutPercent: 20},
			},
		}),
	)

	response := service.GetAppConfig()
	content, _ := response["content"].(map[string]any)
	if content == nil {
		t.Fatalf("missing content config: %+v", response)
	}
	grayRelease, _ := content["gray_release"].(map[string]any)
	if grayRelease == nil {
		t.Fatalf("missing gray release config: %+v", content)
	}
	canaryMatrix, ok := grayRelease["canary_matrix"].([]any)
	if !ok || len(canaryMatrix) != 2 {
		t.Fatalf("unexpected generic canary matrix: %#v", grayRelease["canary_matrix"])
	}
}
