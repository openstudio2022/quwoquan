package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestGeneratedManifestRetiresOnlyUntrackedGeneratedOutputs(t *testing.T) {
	appRoot := t.TempDir()
	beginGeneratedManifestForTest(t, appRoot, "canonical-graph")
	generatedRoot := filepath.Join(
		appRoot,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"content",
	)
	if err := os.MkdirAll(generatedRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	current := filepath.Join(generatedRoot, "current.g.dart")
	stale := filepath.Join(generatedRoot, "stale.g.dart")
	manual := filepath.Join(generatedRoot, "manual.dart")
	currentPayload := []byte("// Code generated. DO NOT EDIT.\n")
	for path, payload := range map[string][]byte{
		current: currentPayload,
		stale:   []byte("// Code generated. DO NOT EDIT.\n"),
		manual:  []byte("// maintained by the App owner\n"),
	} {
		if err := os.WriteFile(path, payload, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	recordGeneratedFile(current, currentPayload)
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{current, manual} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("kept output %s: %v", path, err)
		}
	}
	if _, err := os.Stat(stale); !os.IsNotExist(err) {
		t.Fatalf("stale generated output still exists: %v", err)
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
