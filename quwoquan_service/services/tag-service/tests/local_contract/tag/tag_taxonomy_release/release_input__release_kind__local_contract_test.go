package tag_taxonomy_release

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestTagReleaseImporterAcceptsReleaseBoundEmptyBaseline(t *testing.T) {
	root := writeReleaseFixture(t, "baseline-001", "empty_baseline", nil)
	report := filepath.Join(t.TempDir(), "report.json")

	runTagImporter(t, true, root, report)

	var receipt struct {
		ReleaseID   string `json:"releaseId"`
		ReleaseKind string `json:"releaseKind"`
		NodeCount   int    `json:"nodeCount"`
	}
	readJSON(t, report, &receipt)
	if receipt.ReleaseID != "baseline-001" ||
		receipt.ReleaseKind != "empty_baseline" ||
		receipt.NodeCount != 0 {
		t.Fatalf("unexpected baseline receipt: %+v", receipt)
	}
}

func TestTagReleaseImporterRejectsEmptyContentRelease(t *testing.T) {
	root := writeReleaseFixture(t, "content-001", "content", nil)
	output := runTagImporter(t, false, root, filepath.Join(t.TempDir(), "report.json"))
	if !strings.Contains(output, "content release contains no tag snapshots") {
		t.Fatalf("unexpected importer failure: %s", output)
	}
}

func TestTagReleaseImporterRejectsNonEmptyBaseline(t *testing.T) {
	root := writeReleaseFixture(
		t,
		"baseline-002",
		"empty_baseline",
		[]string{"Topic/旅行"},
	)
	writeJSON(
		t,
		filepath.Join(
			root,
			"payload",
			"objects",
			"tags",
			"Topic",
			"旅行",
			"_definition.json",
		),
		map[string]any{
			"label":       "旅行",
			"description": "旅行主题",
		},
	)

	output := runTagImporter(t, false, root, filepath.Join(t.TempDir(), "report.json"))
	if !strings.Contains(output, "empty baseline release must contain zero tag snapshots") {
		t.Fatalf("unexpected importer failure: %s", output)
	}
}

func runTagImporter(
	t *testing.T,
	wantSuccess bool,
	releaseRoot string,
	reportPath string,
) string {
	t.Helper()
	command := exec.Command(
		"go",
		"run",
		"./services/tag-service/cmd/import",
		"--release-root",
		releaseRoot,
		"--dry-run",
		"--env",
		"alpha",
		"--report",
		reportPath,
	)
	command.Dir = serviceRoot(t)
	output, err := command.CombinedOutput()
	if wantSuccess && err != nil {
		t.Fatalf("tag importer failed: %v\n%s", err, output)
	}
	if !wantSuccess && err == nil {
		t.Fatalf("tag importer unexpectedly succeeded: %s", output)
	}
	return string(output)
}

func writeReleaseFixture(
	t *testing.T,
	releaseID string,
	releaseKind string,
	tagRefs []string,
) string {
	t.Helper()
	root := t.TempDir()
	writeJSON(t, filepath.Join(root, "payload", "release.json"), map[string]any{
		"schema":      "quwoquan_data.release",
		"releaseId":   releaseID,
		"releaseKind": releaseKind,
	})
	writeJSON(
		t,
		filepath.Join(root, "payload", "desired_state.json"),
		map[string]any{
			"schema":    "quwoquan_data.release_desired_state",
			"releaseId": releaseID,
			"desiredRefs": map[string]any{
				"tags": tagRefs,
			},
		},
	)
	return root
}

func writeJSON(t *testing.T, path string, payload any) {
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

func readJSON(t *testing.T, path string, target any) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, target); err != nil {
		t.Fatal(err)
	}
}

func serviceRoot(t *testing.T) string {
	t.Helper()
	_, current, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test path")
	}
	root := filepath.Clean(
		filepath.Join(
			filepath.Dir(current),
			"..",
			"..",
			"..",
			"..",
			"..",
			"..",
		),
	)
	if _, err := os.Stat(filepath.Join(root, "go.mod")); err != nil {
		t.Fatalf("resolve service root %s: %v", root, err)
	}
	return root
}
