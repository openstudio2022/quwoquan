package validate_test

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

// TestUserChatCircleHTTPErrorEmissionsAreExhaustive locks the recovered domain
// model contract: an object-local producer uses its local operation name, while
// a sibling-object producer must use its unique canonical operation ID.
func TestUserChatCircleHTTPErrorEmissionsAreExhaustive(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	contractGraph, _, err := compiler.Validate(
		metadataDir,
		validate.ProfileCommercial,
	)
	if err != nil {
		t.Fatalf("compile commercial ContractGraph: %v", err)
	}

	targetDomain := map[string]bool{"user": true, "chat": true, "circle": true}
	type ownedError struct {
		objectID string
		value    ast.ErrorDefinition
	}
	definitions := map[string]ownedError{}
	for _, packet := range contractGraph.Governance.Objects {
		for _, definition := range packet.Errors {
			definitions[definition.Code] = ownedError{
				objectID: packet.ObjectID,
				value:    definition,
			}
		}
	}

	for _, operation := range contractGraph.Operations {
		if !targetDomain[operation.Domain] {
			continue
		}
		for _, code := range operation.ErrorCodes {
			definition, exists := definitions[code]
			if !exists {
				continue
			}
			expected := operation.ID
			if definition.objectID == operation.ObjectID {
				expected = operation.LocalID
			}
			if !hasHTTPErrorEmission(definition.value, expected) {
				t.Errorf(
					"%s error %s must bind exact producer %s (owner=%s)",
					operation.ID,
					code,
					expected,
					definition.objectID,
				)
			}
		}
	}
}

func hasHTTPErrorEmission(definition ast.ErrorDefinition, operation string) bool {
	for _, emission := range definition.EmittedBy {
		if emission.Surface != "http" {
			continue
		}
		for _, current := range emission.Operations {
			if current == operation {
				return true
			}
		}
	}
	return false
}
