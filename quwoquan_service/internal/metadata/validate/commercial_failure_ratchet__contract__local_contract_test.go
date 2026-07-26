package validate_test

import (
	"testing"

	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCommercialContractGraphHasNoFailures(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	_, issues, err := compiler.Validate(
		metadataDir,
		validate.ProfileCommercial,
	)
	if err != nil {
		t.Fatalf("compile commercial ContractGraph: %v", err)
	}
	if len(issues) != 0 {
		for _, issue := range issues {
			t.Errorf(
				"commercial ContractGraph failure %s|%s|%s: %s",
				issue.Code,
				issue.SubjectID,
				issue.SourcePath,
				issue.Message,
			)
		}
	}
}
