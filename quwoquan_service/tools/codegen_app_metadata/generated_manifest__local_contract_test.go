package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestGeneratedManifestRetiresOnlyOwnedGeneratedOutputs(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	current := filepath.Join(
		appRoot,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"cloud_api_defaults.g.dart",
	)
	retired := filepath.Join(
		appRoot,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"assistant",
		"assistant_api_metadata.g.dart",
	)
	retiredPageIDs := filepath.Join(
		appRoot,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"app_request_page_ids.g.dart",
	)
	unknownGeneratedSibling := filepath.Join(
		appRoot,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"content",
		"unknown_generated_sibling.g.dart",
	)
	manualSibling := filepath.Join(
		filepath.Dir(unknownGeneratedSibling),
		"manual.dart",
	)
	currentPayload := []byte("// Code generated. DO NOT EDIT.\n")
	for path, payload := range map[string][]byte{
		current:                 currentPayload,
		retired:                 []byte("// Code generated. DO NOT EDIT.\n"),
		retiredPageIDs:          []byte("// Code generated. DO NOT EDIT.\n"),
		unknownGeneratedSibling: []byte("// Code generated. DO NOT EDIT.\n"),
		manualSibling:           []byte("// maintained by the App owner\n"),
	} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, payload, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	recordGeneratedFile(current, currentPayload)
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{current, unknownGeneratedSibling, manualSibling} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("kept output %s: %v", path, err)
		}
	}
	for _, path := range []string{retired, retiredPageIDs} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired generated output still exists at %s: %v", path, err)
		}
	}
}

func TestGeneratedManifestRetiresLegacyAPIMetadataAndPolicyOutputs(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	retired := []string{
		"lib/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart",
		"lib/cloud/runtime/generated/auth/auth_policy.g.dart",
		"lib/cloud/runtime/generated/chat/chat_api_metadata.g.dart",
		"lib/cloud/runtime/generated/circle/circle_api_metadata.g.dart",
		"lib/cloud/runtime/generated/content/content_api_metadata.g.dart",
		"lib/cloud/runtime/generated/entity/entity_api_metadata.g.dart",
		"lib/cloud/runtime/generated/integration/integration_api_metadata.g.dart",
		"lib/cloud/runtime/generated/integration/integration_location_metadata.g.dart",
		"lib/cloud/runtime/generated/notification/notification_api_metadata.g.dart",
		"lib/cloud/runtime/generated/ops/ops_api_metadata.g.dart",
		"lib/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart",
		"lib/cloud/runtime/generated/recommendation/recommendation_api_metadata.g.dart",
		"lib/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart",
		"lib/cloud/runtime/generated/search/search_api_metadata.g.dart",
		"lib/cloud/runtime/generated/tag/tag_api_metadata.g.dart",
		"lib/cloud/runtime/generated/travel/travel_api_metadata.g.dart",
		"lib/cloud/runtime/generated/user/user_api_metadata.g.dart",
	}
	for _, relative := range retired {
		path := filepath.Join(appRoot, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(
			path,
			[]byte("// Code generated. DO NOT EDIT.\n"),
			0o644,
		); err != nil {
			t.Fatal(err)
		}
	}

	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}
	for _, relative := range retired {
		path := filepath.Join(appRoot, filepath.FromSlash(relative))
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired generated output still exists at %s: %v", path, err)
		}
	}
}

func beginGeneratedManifestForTest(t *testing.T, appRoot, graphSHA256 string) {
	t.Helper()
	previousRoot := generatedManifestAppRoot
	previousGraph := generatedManifestGraph
	previousOutputs := generatedManifestOutputs
	beginGeneratedManifest(appRoot, graphSHA256)
	t.Cleanup(func() {
		generatedManifestAppRoot = previousRoot
		generatedManifestGraph = previousGraph
		generatedManifestOutputs = previousOutputs
	})
}
