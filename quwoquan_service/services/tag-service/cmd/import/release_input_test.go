package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCollectReleaseTaxonomyNodesAcceptsReleaseBoundEmptyBaseline(t *testing.T) {
	root := t.TempDir()
	writeReleaseJSON(t, filepath.Join(root, "payload", "release.json"), map[string]any{
		"schema":      "quwoquan_data.release",
		"releaseId":   "baseline-001",
		"releaseKind": "empty_baseline",
	})
	writeReleaseJSON(t, filepath.Join(root, "payload", "desired_state.json"), map[string]any{
		"schema":    "quwoquan_data.release_desired_state",
		"releaseId": "baseline-001",
		"tags":      []string{},
	})

	releaseID, releaseKind, nodes, err := collectReleaseTaxonomyNodes(root)
	if err != nil {
		t.Fatalf("collect empty baseline: %v", err)
	}
	if releaseID != "baseline-001" || releaseKind != "empty_baseline" || len(nodes) != 0 {
		t.Fatalf("unexpected baseline projection: id=%s kind=%s nodes=%d", releaseID, releaseKind, len(nodes))
	}
}

func TestCollectReleaseTaxonomyNodesRejectsEmptyContentRelease(t *testing.T) {
	root := t.TempDir()
	writeReleaseJSON(t, filepath.Join(root, "payload", "release.json"), map[string]any{
		"schema":      "quwoquan_data.release",
		"releaseId":   "content-001",
		"releaseKind": "content",
	})
	writeReleaseJSON(t, filepath.Join(root, "payload", "desired_state.json"), map[string]any{
		"schema":    "quwoquan_data.release_desired_state",
		"releaseId": "content-001",
		"tags":      []string{},
	})

	if _, _, _, err := collectReleaseTaxonomyNodes(root); err == nil {
		t.Fatal("empty content release must be rejected")
	}
}

func TestValidateReleaseTaxonomyNodesRejectsNonEmptyBaseline(t *testing.T) {
	if err := validateReleaseTaxonomyNodes("empty_baseline", []taxonomyNode{{
		tagRef: "Topic",
		group:  "Topic",
	}}); err == nil {
		t.Fatal("non-empty baseline taxonomy must be rejected")
	}
}

func writeReleaseJSON(t *testing.T, path string, payload map[string]any) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", path, err)
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal %s: %v", path, err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}
