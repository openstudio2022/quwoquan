package main

import (
	"path/filepath"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func TestControlPlaneArtifactsExcludeManualDomainOnboarding(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile metadata: %v", err)
	}
	artifacts := collectArtifacts(source)
	foundPlatform := false
	for _, artifact := range artifacts {
		if artifact.fileName == "domain_onboarding_schema" || artifact.fileName == "domain_onboarding_domains" {
			t.Fatalf("manual onboarding artifact must not be generated: %s", artifact.fileName)
		}
		if artifact.fileName == "platform_control_plane" {
			foundPlatform = true
		}
	}
	if !foundPlatform {
		t.Fatal("platform control-plane artifact is missing")
	}
}
