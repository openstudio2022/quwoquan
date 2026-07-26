package validate_test

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

func TestCommercialValidationRejectsGenericObjectMigrationGap(t *testing.T) {
	t.Parallel()

	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{{
			ID:           "content.post.PublishPost",
			LocalID:      "PublishPost",
			Domain:       "content",
			ObjectID:     "content.Post",
			Method:       "POST",
			Kind:         ast.OperationKindCommand,
			KindExplicit: true,
			SourcePath:   "content/content/post/operations.yaml",
			Commercial: ast.CommercialBinding{
				Status:      "blocked",
				Explicit:    true,
				BlockReason: "packet evidence is incomplete",
				GapID:       "APP_CLOUD_OBJECT_MIGRATION",
				TargetStory: "app-cloud-business-object-commercial-closure",
			},
		}},
	}

	issues := validate.Run(contractGraph, validate.ProfileCommercial)
	if !containsIssueCode(issues, "CONTRACT.OPERATION.GENERIC_COMMERCIAL_GAP_FORBIDDEN") {
		t.Fatalf("generic commercial gap must be rejected, got %+v", issues)
	}
}

func containsIssueCode(issues []validate.Issue, code string) bool {
	for _, current := range issues {
		if current.Code == code {
			return true
		}
	}
	return false
}
