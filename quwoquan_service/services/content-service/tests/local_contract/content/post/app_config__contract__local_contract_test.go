package local_contract

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func TestProductionImagePackagesRecommendationMetadata(t *testing.T) {
	dockerfile, err := os.ReadFile(filepath.Join(
		quwoquanServiceRoot(t),
		"services/content-service/build/Dockerfile",
	))
	if err != nil {
		t.Fatalf("read production Dockerfile: %v", err)
	}
	content := string(dockerfile)
	for _, required := range []string{
		"COPY services/content-service/resources/ /app/resources/",
		"ENV QWQ_SEGMENTS_PATH=/app/resources/policies/content/post/recommendation_segments.yaml",
		"ENV QWQ_REC_POLICY_PATH=/app/resources/policies/content/post/recommendation_policy.yaml",
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
	if _, exists := response["packageVersion"]; exists {
		t.Fatal("app config must expose configHash as its only snapshot identity")
	}
	configHash, _ := response["configHash"].(string)
	canonical := make(map[string]any, len(response)-2)
	for key, value := range response {
		if key != "configHash" && key != "fetchedAt" {
			canonical[key] = value
		}
	}
	encoded, err := json.Marshal(canonical)
	if err != nil {
		t.Fatalf("marshal canonical app config: %v", err)
	}
	digest := sha256.Sum256(encoded)
	wantHash := "sha256:" + hex.EncodeToString(digest[:])
	if configHash != wantHash {
		t.Fatalf("configHash=%q want canonical digest %q", configHash, wantHash)
	}
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
