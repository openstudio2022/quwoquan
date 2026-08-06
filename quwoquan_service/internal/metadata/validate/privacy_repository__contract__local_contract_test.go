package validate_test

import (
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestRepositoryPrivacyGovernanceHasNoUnresolvedPolicy(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	_, issues, err := compiler.Validate(metadataDir, validate.ProfileCommercial)
	if err != nil {
		t.Fatalf("compile source-derived ContractGraph: %v", err)
	}
	for _, current := range issues {
		if strings.HasPrefix(current.Code, "CONTRACT.PRIVACY.") {
			t.Errorf(
				"privacy governance failure %s|%s|%s: %s",
				current.Code,
				current.SubjectID,
				current.SourcePath,
				current.Message,
			)
		}
	}
}
