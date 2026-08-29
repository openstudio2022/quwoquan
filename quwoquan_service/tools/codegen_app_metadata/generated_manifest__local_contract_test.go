package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"
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

func TestGeneratedManifestRetiresZeroConsumerMixedOutputs(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	retired := []string{
		"lib/service/content_service/content/post/adapters/generated/content_post_immersive_wire_keys.g.dart",
		"lib/service/content_service/content/post/application/generated/content_metadata.g.dart",
		"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/intersection_kind_metadata.g.dart",
		"lib/service/search_service/search/search_index_view/application/generated/search_contract.g.dart",
		"lib/service/search_service/search/search_index_view/application/generated/search_registry.g.dart",
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
			t.Fatalf("retired zero-consumer output still exists at %s: %v", path, err)
		}
	}
}

func TestGeneratedDartFormattingRefreshesManifestFromFinalBytes(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	original := map[string][]byte{
		"lib/generated/b.g.dart": []byte("class B{}\n"),
		"lib/generated/a.g.dart": []byte("class A{}\n"),
		"generated/receipt.json": []byte("{}\n"),
	}
	formatted := map[string][]byte{
		"lib/generated/a.g.dart": []byte("class A {}\n"),
		"lib/generated/b.g.dart": []byte("class B {}\n"),
	}
	for relative, payload := range original {
		path := filepath.Join(appRoot, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, payload, 0o644); err != nil {
			t.Fatal(err)
		}
		recordGeneratedFile(path, payload)
	}

	err := formatGeneratedDartOutputsWith(
		func(root string, relativePaths []string) (map[string][]byte, error) {
			if root != appRoot {
				t.Fatalf("formatter root = %q, want %q", root, appRoot)
			}
			if got, want := strings.Join(relativePaths, "\n"), "lib/generated/a.g.dart\nlib/generated/b.g.dart"; got != want {
				t.Fatalf("formatter paths = %q, want %q", got, want)
			}
			return formatted, nil
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	for relative, payload := range formatted {
		output := generatedManifestOutputs[relative]
		sum := sha256.Sum256(payload)
		if output.SHA256 != hex.EncodeToString(sum[:]) || output.Bytes != len(payload) {
			t.Fatalf("manifest output for %s does not describe final bytes: %#v", relative, output)
		}
	}
	if got := generatedManifestOutputs["generated/receipt.json"].Bytes; got != len(original["generated/receipt.json"]) {
		t.Fatalf("non-Dart manifest output bytes = %d", got)
	}
}

func TestGeneratedDartFormattingFailsClosed(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	path := filepath.Join(appRoot, "lib", "generated", "a.g.dart")
	payload := []byte("class A{}\n")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, payload, 0o644); err != nil {
		t.Fatal(err)
	}
	recordGeneratedFile(path, payload)

	formatErr := errors.New("formatter failed")
	err := formatGeneratedDartOutputsWith(
		func(string, []string) (map[string][]byte, error) {
			return nil, formatErr
		},
	)
	if !errors.Is(err, formatErr) {
		t.Fatalf("formatter error = %v, want %v", err, formatErr)
	}
}

func TestGeneratedDartFormattingRejectsIncompleteOutputSet(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	for _, relative := range []string{
		"lib/generated/a.g.dart",
		"lib/generated/b.g.dart",
	} {
		path := filepath.Join(appRoot, filepath.FromSlash(relative))
		payload := []byte("class A{}\n")
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, payload, 0o644); err != nil {
			t.Fatal(err)
		}
		recordGeneratedFile(path, payload)
	}

	err := formatGeneratedDartOutputsWith(
		func(string, []string) (map[string][]byte, error) {
			return map[string][]byte{
				"lib/generated/a.g.dart": []byte("class A {}\n"),
			}, nil
		},
	)
	if err == nil || !strings.Contains(err.Error(), "output path set") {
		t.Fatalf("incomplete formatter output error = %v", err)
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
