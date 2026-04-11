package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/runtime/codegen"
	"quwoquan_service/runtime/registry"
)

func TestCircleModelCodegen_IncludesCoreFields(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	if _, err := os.Stat(metadataDir); err != nil {
		t.Skipf("metadata dir not found: %v", err)
	}
	reg, err := registry.LoadFromDirectory(metadataDir)
	if err != nil {
		t.Fatalf("load registry: %v", err)
	}
	out := t.TempDir()
	g := codegen.NewGenerator(
		reg,
		out,
		codegen.WithTypedEnums(),
		codegen.WithSliceEntityRefs(),
		codegen.WithSkipViewEntities(),
		codegen.WithGoFieldIDSuffix(),
	)
	if err := g.GenerateDomainModelOnly("Circle"); err != nil {
		t.Fatalf("GenerateDomainModelOnly: %v", err)
	}
	b, err := os.ReadFile(filepath.Join(out, "domain", "circle", "model", "circle.go"))
	if err != nil {
		t.Fatalf("read model: %v", err)
	}
	s := string(b)
	for _, needle := range []string{
		"type Circle struct",
		"SubCategory",
		"Kind",
		"DisplaySubjectType",
		"FollowEnabled",
		"DefaultPublicGroupID",
		"LinkedHomepageID",
		"type CircleGroup struct",
		"type CircleJoinPolicy",
		"CircleJoinPolicyInviteOnly",
		"[]CircleSectionConfig",
	} {
		if !strings.Contains(s, needle) {
			t.Errorf("generated model missing %q", needle)
		}
	}
}
