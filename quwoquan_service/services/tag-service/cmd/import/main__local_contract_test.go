package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCollectTaxonomyNodesIncludesDimensionRoots(t *testing.T) {
	root := t.TempDir()
	dimensionDir := filepath.Join(root, "Audience", "用户", "职业")
	leafDir := filepath.Join(dimensionDir, "产品运营", "产品经理")
	if err := os.MkdirAll(leafDir, 0o755); err != nil {
		t.Fatalf("mkdir taxonomy: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(dimensionDir, "_dimension.json"),
		[]byte(`{"label":"职业身份","labelEn":"Occupation"}`),
		0o600,
	); err != nil {
		t.Fatalf("write dimension: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(leafDir, "_definition.json"),
		[]byte(`{"label":"产品经理","labelEn":"Product Manager"}`),
		0o600,
	); err != nil {
		t.Fatalf("write leaf: %v", err)
	}

	nodes, err := collectTaxonomyNodes(root)
	if err != nil {
		t.Fatalf("collect taxonomy: %v", err)
	}
	if len(nodes) != 2 {
		t.Fatalf("nodes=%d, want dimension root + leaf", len(nodes))
	}
	if nodes[0].tagRef != "Audience/用户/职业" {
		t.Fatalf("dimension root missing: %+v", nodes)
	}
	if nodes[1].parentTagRef != "Audience/用户/职业/产品运营" {
		t.Fatalf("leaf parent=%q", nodes[1].parentTagRef)
	}
	if canonicalDigest(nodes) == "" {
		t.Fatal("canonical digest must include dimension roots")
	}
}
