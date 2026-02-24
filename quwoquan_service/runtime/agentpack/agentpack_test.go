package agentpack

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestScanFeatureTree(t *testing.T) {
	dir := t.TempDir()

	// Build a minimal feature tree structure
	runtimeDir := filepath.Join(dir, "runtime")
	ctxDir := filepath.Join(runtimeDir, "runtime-context")
	skillDir := filepath.Join(runtimeDir, "runtime-skill")

	os.MkdirAll(ctxDir, 0755)
	os.MkdirAll(skillDir, 0755)

	os.WriteFile(filepath.Join(ctxDir, "spec.md"), []byte("# spec"), 0644)
	os.WriteFile(filepath.Join(ctxDir, "tasks.md"), []byte("- [x] task1\n- [x] task2\n"), 0644)
	os.WriteFile(filepath.Join(skillDir, "spec.md"), []byte("# spec"), 0644)
	os.WriteFile(filepath.Join(skillDir, "tasks.md"), []byte("- [x] task1\n- [ ] task2\n"), 0644)

	index, err := ScanFeatureTree(dir)
	if err != nil {
		t.Fatalf("ScanFeatureTree: %v", err)
	}

	if len(index.Features) != 1 {
		t.Fatalf("expected 1 top-level feature (runtime), got %d", len(index.Features))
	}

	runtimeNode := index.Features[0]
	if runtimeNode.ID != "runtime" {
		t.Errorf("expected 'runtime', got %q", runtimeNode.ID)
	}
	if len(runtimeNode.Children) != 2 {
		t.Fatalf("expected 2 children, got %d", len(runtimeNode.Children))
	}

	// runtime-context should be completed (all tasks checked)
	ctxNode := findChild(runtimeNode.Children, "runtime-context")
	if ctxNode == nil {
		t.Fatal("runtime-context not found")
	}
	if ctxNode.Status != "completed" {
		t.Errorf("runtime-context status: got %q, want completed", ctxNode.Status)
	}

	// runtime-skill should be in_progress (some tasks checked)
	skillNode := findChild(runtimeNode.Children, "runtime-skill")
	if skillNode == nil {
		t.Fatal("runtime-skill not found")
	}
	if skillNode.Status != "in_progress" {
		t.Errorf("runtime-skill status: got %q, want in_progress", skillNode.Status)
	}
}

func TestSearchFeatures(t *testing.T) {
	index := &TreeIndex{
		Features: []FeatureNode{
			{
				ID: "runtime", Name: "runtime",
				Children: []FeatureNode{
					{ID: "runtime-context", Name: "三层上下文", Tags: []string{"context", "profile"}},
					{ID: "runtime-recommendation", Name: "推荐引擎", Tags: []string{"recommendation", "feed"}},
					{ID: "runtime-skill", Name: "Skill框架", Tags: []string{"skill", "assistant"}},
				},
			},
		},
	}

	results := SearchFeatures(index, "推荐")
	if len(results) != 1 {
		t.Errorf("expected 1 result for '推荐', got %d", len(results))
	}

	results = SearchFeatures(index, "context")
	if len(results) != 1 {
		t.Errorf("expected 1 result for 'context', got %d", len(results))
	}

	results = SearchFeatures(index, "runtime")
	if len(results) < 1 {
		t.Error("expected results for 'runtime'")
	}
}

func TestWriteAndReadIndex(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "tree_index.yaml")

	index := &TreeIndex{
		Version:   1,
		UpdatedAt: time.Now().UTC(),
		Features: []FeatureNode{
			{ID: "test", Name: "test feature", Status: "completed"},
		},
	}

	if err := WriteIndex(index, path); err != nil {
		t.Fatalf("WriteIndex: %v", err)
	}

	loaded, err := ReadIndex(path)
	if err != nil {
		t.Fatalf("ReadIndex: %v", err)
	}

	if len(loaded.Features) != 1 {
		t.Fatalf("expected 1 feature, got %d", len(loaded.Features))
	}
	if loaded.Features[0].ID != "test" {
		t.Errorf("expected 'test', got %q", loaded.Features[0].ID)
	}
}

func TestIngestTaskPack(t *testing.T) {
	index := &TreeIndex{
		Features: []FeatureNode{
			{ID: "runtime", Domain: "runtime", Name: "runtime"},
		},
	}

	pack := TaskPack{
		Feature: FeatureInfo{
			ID:     "runtime-new-feature",
			Name:   "新特性",
			Level:  "L2_feature",
			Domain: "runtime",
		},
	}

	IngestTaskPack(index, pack)

	if len(index.Features[0].Children) != 1 {
		t.Fatalf("expected 1 child after ingest, got %d", len(index.Features[0].Children))
	}
	if index.Features[0].Children[0].ID != "runtime-new-feature" {
		t.Errorf("expected 'runtime-new-feature', got %q", index.Features[0].Children[0].ID)
	}
}

func findChild(nodes []FeatureNode, id string) *FeatureNode {
	for i, n := range nodes {
		if n.ID == id {
			return &nodes[i]
		}
	}
	return nil
}
