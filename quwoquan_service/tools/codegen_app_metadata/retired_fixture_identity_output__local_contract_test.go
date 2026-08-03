package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRemoveUntrackedGeneratedOutputsRemovesRetiredSingleTrackOutputs(t *testing.T) {
	appDir := t.TempDir()
	beginGeneratedManifest(appDir, "canonical-graph")
	retired := []string{
		"lib/cloud/user/generated/prefab_user_metadata.g.dart",
		"lib/cloud/runtime/generated/integration/location_poi_dto.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/integration/location_queries.requests.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/notification/app_message_contracts.requests.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/notification/incoming_call_delivery_contracts.requests.g.dart",
	}
	for _, relativePath := range retired {
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("create generated directory for %s: %v", relativePath, err)
		}
		if err := os.WriteFile(
			path,
			[]byte("// Code generated from retired single-track source. DO NOT EDIT.\n"),
			0o600,
		); err != nil {
			t.Fatalf("write retired generated output %s: %v", relativePath, err)
		}
	}

	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}

	for _, relativePath := range retired {
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired output %s must be removed, stat error: %v", relativePath, err)
		}
	}
}
