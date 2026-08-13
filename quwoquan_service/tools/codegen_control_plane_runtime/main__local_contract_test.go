package main

import (
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestControlPlaneArtifactsExcludeManualDomainOnboarding(t *testing.T) {
	metadataDir := contractsview.Build(t)
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

func TestControlPlaneOperationSecurityUsesCanonicalOperationReferences(t *testing.T) {
	metadataDir := contractsview.Build(t)
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile metadata: %v", err)
	}
	operations := collectOperationSecurity(collectArtifacts(source))
	if len(operations) == 0 {
		t.Fatal("control-plane operation references must generate security selections")
	}
	foundPlatform := false
	foundProductCrossDomain := false
	for _, operation := range operations {
		if operation.contractOperationID == "" {
			t.Fatal("generated security selection must retain canonical operation id")
		}
		if operation.domain == "platform" {
			foundPlatform = true
		}
		if operation.domain == "product" &&
			(operation.contractOperationID == "content.report.ListReports" ||
				operation.contractOperationID == "entity.homepage.ListHomepageCandidates") {
			foundProductCrossDomain = true
		}
	}
	if !foundPlatform || !foundProductCrossDomain {
		t.Fatalf("expected platform and cross-domain product references, got %#v", operations)
	}
}
