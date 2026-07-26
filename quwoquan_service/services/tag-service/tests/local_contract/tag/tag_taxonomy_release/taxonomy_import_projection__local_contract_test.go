// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-001
package tag_taxonomy_release_test

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
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
