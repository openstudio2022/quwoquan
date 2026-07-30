package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestGatewayErrorSurfaceIsOwnedOnceWithoutCopyingOperationRegistry(t *testing.T) {
	status := 429
	valid := &graph.ContractGraph{
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "gateway.RateLimitBucket",
			Domain:   "gateway",
			Errors: []ast.ErrorDefinition{{
				Code:       "GATEWAY.USER.rate_limited",
				HTTPStatus: &status,
				EmittedBy:  []ast.ErrorEmission{{Surface: "gateway"}},
				SourcePath: "gateway/edge_security/rate_limit_bucket/errors.yaml",
			}},
		}}},
	}
	if issues := validateErrorGovernance(valid); len(issues) != 0 {
		t.Fatalf("canonical gateway error should be valid, got %+v", issues)
	}

	foreign := *valid
	foreign.Governance.Objects = append([]ast.ObjectGovernance(nil), valid.Governance.Objects...)
	foreign.Governance.Objects[0].Domain = "content"
	issues := validateErrorGovernance(&foreign)
	if !gatewayIssueCodePresent(issues, "CONTRACT.ERROR.GATEWAY_SURFACE_OWNER") {
		t.Fatalf("foreign gateway surface owner must fail, got %+v", issues)
	}

	duplicatedRegistry := *valid
	duplicatedRegistry.Governance.Objects = append([]ast.ObjectGovernance(nil), valid.Governance.Objects...)
	duplicatedRegistry.Governance.Objects[0].Errors = append(
		[]ast.ErrorDefinition(nil),
		valid.Governance.Objects[0].Errors...,
	)
	duplicatedRegistry.Governance.Objects[0].Errors[0].EmittedBy = []ast.ErrorEmission{{
		Surface:    "gateway",
		Operations: []string{"content.post.CreatePost"},
	}}
	issues = validateErrorGovernance(&duplicatedRegistry)
	if !gatewayIssueCodePresent(issues, "CONTRACT.ERROR.GATEWAY_SURFACE_OPERATION") {
		t.Fatalf("gateway surface must not copy the operation registry, got %+v", issues)
	}
}

func gatewayIssueCodePresent(issues []Issue, code string) bool {
	for _, current := range issues {
		if current.Code == code {
			return true
		}
	}
	return false
}
