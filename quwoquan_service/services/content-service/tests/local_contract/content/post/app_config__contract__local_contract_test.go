// spec_ref: specs/feature-tree/discovery-content/content-service-contract-foundation/privacy-ui-config-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
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
			FeatureFlags: map[string]bool{
				"enable_article_book_reader": true,
				"unknown_parallel_flag":      true,
			},
			ExperimentBucket: "rollout_20",
			CurrentStage:     "20%",
			CanaryMatrix: []postapp.StoryCanaryStage{
				{Stage: "5%", RolloutPercent: 5},
				{Stage: "20%", RolloutPercent: 20},
			},
		}),
	)

	response := service.GetAppConfig()
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal canonical app config: %v", err)
	}
	canonical := map[string]any{}
	if err := json.Unmarshal(encoded, &canonical); err != nil {
		t.Fatalf("decode canonical app config: %v", err)
	}
	if _, exists := canonical["packageVersion"]; exists {
		t.Fatal("app config must expose configHash as its only snapshot identity")
	}
	delete(canonical, "configHash")
	delete(canonical, "fetchedAt")
	encoded, err = json.Marshal(canonical)
	if err != nil {
		t.Fatalf("marshal app config hash input: %v", err)
	}
	digest := sha256.Sum256(encoded)
	wantHash := "sha256:" + hex.EncodeToString(digest[:])
	if response.ConfigHash != wantHash {
		t.Fatalf("configHash=%q want canonical digest %q", response.ConfigHash, wantHash)
	}
	if response.Content.FeatureFlags.EnableArticleBookReader == nil ||
		!*response.Content.FeatureFlags.EnableArticleBookReader {
		t.Fatal("known runtime feature flag must be present in the typed contract")
	}
	contentMap, _ := canonical["content"].(map[string]any)
	featureFlags, _ := contentMap["feature_flags"].(map[string]any)
	if _, exists := featureFlags["unknown_parallel_flag"]; exists {
		t.Fatal("unknown feature flag must not escape the canonical closed contract")
	}
	if len(response.Content.GrayRelease.CanaryMatrix) != 2 {
		t.Fatalf("unexpected typed canary matrix: %#v", response.Content.GrayRelease.CanaryMatrix)
	}
}
