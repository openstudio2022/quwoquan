// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
package tag_taxonomy_release_test

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestCanonicalTaxonomyProjectsRuntimeDimensionMetadata(t *testing.T) {
	serviceRoot := findServiceRoot(t)
	taxonomyRoot := filepath.Join(
		filepath.Dir(serviceRoot),
		"quwoquan_data",
		"control_plane",
		"governance",
		"taxonomy",
	)
	command := exec.Command(
		"go",
		"run",
		"./services/tag-service/cmd/import",
		"--tags-dir",
		taxonomyRoot,
		"--validate-only",
	)
	command.Dir = serviceRoot
	output, err := command.Output()
	if err != nil {
		t.Fatalf("validate canonical taxonomy: %v", err)
	}
	var report struct {
		NodeCount int `json:"nodeCount"`
		Nodes     []struct {
			TagRef      string `json:"tagRef"`
			NodeKind    string `json:"nodeKind"`
			Description string `json:"description"`
			MaxDepth    int    `json:"maxDepth"`
			PathPolicy  string `json:"pathPolicy"`
		} `json:"nodes"`
	}
	if err := json.Unmarshal(output, &report); err != nil {
		t.Fatalf("decode taxonomy validation report: %v", err)
	}
	if report.NodeCount == 0 {
		t.Fatal("canonical taxonomy must not be empty")
	}

	var dimension *struct {
		TagRef      string `json:"tagRef"`
		NodeKind    string `json:"nodeKind"`
		Description string `json:"description"`
		MaxDepth    int    `json:"maxDepth"`
		PathPolicy  string `json:"pathPolicy"`
	}
	for index := range report.Nodes {
		if report.Nodes[index].TagRef == "Topic/旅行/玩法" {
			dimension = &report.Nodes[index]
			break
		}
	}
	if dimension == nil {
		t.Fatal("Topic/旅行/玩法 dimension is missing")
	}
	if dimension.NodeKind != "dimension" ||
		dimension.Description == "" ||
		dimension.MaxDepth != 2 ||
		dimension.PathPolicy != "any-depth" {
		t.Fatalf("dimension projection = %#v", *dimension)
	}
}

func TestImmutableContentReleaseProjectsExactTagReceipt(t *testing.T) {
	serviceRoot := findServiceRoot(t)
	releaseRoot := filepath.Join(t.TempDir(), "release-a")
	tagRoot := filepath.Join(
		releaseRoot,
		"payload",
		"objects",
		"tags",
		"Topic",
		"旅行",
	)
	if err := os.MkdirAll(tagRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	writeReleaseHeader(t, releaseRoot, "release-a", "content")
	writeJSONFile(t, filepath.Join(releaseRoot, "payload", "desired_state.json"), map[string]any{
		"schema":    "quwoquan_data.release_desired_state",
		"releaseId": "release-a",
		"desiredRefs": map[string]any{
			"tags": []string{"Topic/旅行"},
		},
	})
	writeJSONFile(t, filepath.Join(tagRoot, "_definition.json"), map[string]any{
		"label":   "旅行",
		"labelEn": "travel",
	})
	writeReleaseAttestation(t, serviceRoot, releaseRoot, "release-a", "content", 1)
	reportPath := filepath.Join(t.TempDir(), "tag-import.json")
	command := exec.Command(
		"go",
		"run",
		"./services/tag-service/cmd/import",
		"--release-root",
		releaseRoot,
		"--release-id",
		"release-a",
		"--env",
		"gamma",
		"--activation-mode",
		"stage-only",
		"--report",
		reportPath,
		"--dry-run",
	)
	command.Dir = serviceRoot
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("dry-run immutable release tags: %v\n%s", err, output)
	}
	raw, err := os.ReadFile(reportPath)
	if err != nil {
		t.Fatal(err)
	}
	var report struct {
		Schema      string   `json:"schema"`
		Status      string   `json:"status"`
		Environment string   `json:"environment"`
		ReleaseID   string   `json:"releaseId"`
		ReleaseKind string   `json:"releaseKind"`
		NodeCount   int      `json:"nodeCount"`
		TagRefs     []string `json:"tagRefs"`
	}
	if err := json.Unmarshal(raw, &report); err != nil {
		t.Fatal(err)
	}
	if report.Schema != "quwoquan.tag_import_report" ||
		report.Status != "dry-run" ||
		report.Environment != "gamma" ||
		report.ReleaseID != "release-a" ||
		report.ReleaseKind != "content" ||
		report.NodeCount != 1 ||
		len(report.TagRefs) != 1 ||
		report.TagRefs[0] != "Topic/旅行" {
		t.Fatalf("unexpected tag import receipt: %#v", report)
	}
}

func TestImmutableEmptyBaselineProjectsZeroNodeReceipt(t *testing.T) {
	serviceRoot := findServiceRoot(t)
	releaseRoot := filepath.Join(t.TempDir(), "baseline-a")
	writeReleaseHeader(t, releaseRoot, "baseline-a", "empty_baseline")
	writeJSONFile(t, filepath.Join(releaseRoot, "payload", "desired_state.json"), map[string]any{
		"schema":    "quwoquan_data.release_desired_state",
		"releaseId": "baseline-a",
		"desiredRefs": map[string]any{
			"tags": []string{},
		},
	})
	writeReleaseAttestation(t, serviceRoot, releaseRoot, "baseline-a", "empty_baseline", 0)
	reportPath := filepath.Join(t.TempDir(), "tag-import.json")
	command := exec.Command(
		"go",
		"run",
		"./services/tag-service/cmd/import",
		"--release-root",
		releaseRoot,
		"--env",
		"gamma",
		"--activation-mode",
		"stage-only",
		"--report",
		reportPath,
		"--dry-run",
	)
	command.Dir = serviceRoot
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("dry-run immutable empty baseline: %v\n%s", err, output)
	}
	var report struct {
		ReleaseID   string   `json:"releaseId"`
		ReleaseKind string   `json:"releaseKind"`
		NodeCount   int      `json:"nodeCount"`
		TagRefs     []string `json:"tagRefs"`
	}
	raw, err := os.ReadFile(reportPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &report); err != nil {
		t.Fatal(err)
	}
	if report.ReleaseID != "baseline-a" ||
		report.ReleaseKind != "empty_baseline" ||
		report.NodeCount != 0 ||
		len(report.TagRefs) != 0 {
		t.Fatalf("unexpected empty baseline receipt: %#v", report)
	}
}

func writeJSONFile(t *testing.T, path string, value any) {
	t.Helper()
	payload, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, payload, 0o644); err != nil {
		t.Fatal(err)
	}
}

func findServiceRoot(t *testing.T) string {
	t.Helper()
	current, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(current, "go.mod")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatal("quwoquan_service root not found")
		}
		current = parent
	}
}

func writeReleaseHeader(t *testing.T, releaseRoot, releaseID, releaseKind string) {
	t.Helper()
	merkle := "sha256:" + strings.Repeat("b", 64)
	writeJSONFile(t, filepath.Join(releaseRoot, "payload", "release.json"), map[string]any{
		"schema": "quwoquan_data.release", "releaseId": releaseID,
		"sourceOwner": "qwq_data", "releaseKind": releaseKind, "releaseClass": "research", "canonicalMerkle": merkle,
	})
}

func writeReleaseAttestation(t *testing.T, serviceRoot, releaseRoot, releaseID, releaseKind string, tagCount int) {
	t.Helper()
	command := exec.Command("python3", "-c", `
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / ".." / "quwoquan_data" / "scripts"))
from core.release_layout import payload_digest
print(payload_digest(pathlib.Path(sys.argv[2])))
`, serviceRoot, releaseRoot)
	digest, err := command.Output()
	if err != nil {
		t.Fatalf("calculate fixture payload digest: %v", err)
	}
	writeJSONFile(t, filepath.Join(releaseRoot, "attestations", "release.json"), map[string]any{
		"schema": "quwoquan_data.release_attestation", "releaseId": releaseID,
		"sourceOwner": "qwq_data", "releaseKind": releaseKind, "releaseClass": "research",
		"canonicalMerkle": "sha256:" + strings.Repeat("b", 64),
		"tagCount":        tagCount, "payloadSha256": strings.TrimSpace(string(digest)),
	})
}
