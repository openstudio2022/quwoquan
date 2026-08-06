package main

import (
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestImpactHelpTypeMetadataPreparesCanonicalPresentationOwner(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize metadata source: %v", err)
	}
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-impact-graph")
	if err := writeImpactHelpTypeMetadata(appDir, metadataDir); err != nil {
		t.Fatalf("write impact help type metadata: %v", err)
	}

	canonicalRelative := filepath.ToSlash(filepath.Join(
		"lib",
		"service",
		"recommendation_service",
		"recommendation",
		"recommendation_feature_profile_view",
		"presentation",
		"generated",
		"impact_help_type_metadata.g.dart",
	))
	legacyRelative := "lib/cloud/runtime/generated/recommendation/" +
		"impact_help_type_metadata.g.dart"
	canonical, err := os.ReadFile(filepath.Join(appDir, canonicalRelative))
	if err != nil {
		t.Fatalf("read canonical impact metadata: %v", err)
	}
	if len(canonical) == 0 {
		t.Fatal("canonical impact metadata is empty")
	}
	if _, err := os.Stat(filepath.Join(appDir, legacyRelative)); !os.IsNotExist(err) {
		t.Fatalf("legacy impact metadata must not be emitted, stat err=%v", err)
	}
	output, ok := generatedManifestOutputs[canonicalRelative]
	if !ok {
		t.Fatalf("generated manifest did not record %s", canonicalRelative)
	}
	if output.Owner != "app-only-emitter" {
		t.Fatalf("generated owner for %s = %q", canonicalRelative, output.Owner)
	}
}
