package importer_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/services/content-service/internal/content/post/application/importer"
)

func TestDataWorkerEnvironmentIncludesRepoRootOnPythonPath(t *testing.T) {
	scriptsRoot := filepath.Join(string(filepath.Separator), "workspace", "quwoquan_data", "scripts")
	repoRoot := filepath.Clean(filepath.Join(scriptsRoot, "..", ".."))
	env := importer.DataWorkerEnvironment(
		[]string{"PATH=/usr/bin", "PYTHONPATH=/stale"},
		"/evidence",
		"/publish",
		scriptsRoot,
	)

	var pythonPath string
	for _, row := range env {
		key, value, found := strings.Cut(row, "=")
		if found && key == "PYTHONPATH" {
			pythonPath = value
			break
		}
	}
	if pythonPath == "" {
		t.Fatal("PYTHONPATH missing from data worker environment")
	}
	parts := strings.Split(pythonPath, string(os.PathListSeparator))
	if len(parts) < 2 {
		t.Fatalf("PYTHONPATH must include scripts and repo root, got %q", pythonPath)
	}
	if parts[0] != scriptsRoot {
		t.Fatalf("PYTHONPATH[0] = %q, want scripts root %q", parts[0], scriptsRoot)
	}
	if parts[1] != repoRoot {
		t.Fatalf("PYTHONPATH[1] = %q, want repo root %q", parts[1], repoRoot)
	}
	for _, row := range env {
		if strings.HasPrefix(row, "PYTHONPATH=") && strings.Contains(row, "/stale") {
			t.Fatalf("stale PYTHONPATH was not overridden: %s", row)
		}
	}
}
