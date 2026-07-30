package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestAuthoritativeBusinessFieldCannotHaveTwoCrossContextAggregateOwners(t *testing.T) {
	contractGraph := &graph.ContractGraph{BusinessObjectMaps: []ast.BusinessObjectMap{{
		Domain: "user",
		Objects: []ast.BusinessObjectBoundary{
			{
				CanonicalObject: "UserAccount",
				BoundedContext:  "account",
				ObjectKind:      ast.ObjectKindAggregateRoot,
				SourceDocument:  "user/account/user_account/fields.yaml",
				FieldRoles: map[string][]string{
					"authoritative_state": {"userId", "createdAt", "phone"},
				},
			},
			{
				CanonicalObject: "Persona",
				BoundedContext:  "persona_management",
				ObjectKind:      ast.ObjectKindAggregateRoot,
				SourceDocument:  "user/persona_management/persona/fields.yaml",
				FieldRoles: map[string][]string{
					"authoritative_state": {"userId", "createdAt", "phone"},
				},
			},
		},
	}}}

	assertGovernanceIssueCodes(t, validateAuthoritativeFieldOwnership(contractGraph),
		"CONTRACT.FIELD.CROSS_CONTEXT_AUTHORITATIVE_DUPLICATE",
	)
}

func TestAuthoritativeOwnershipAllowsLocalIdentityAndTechnicalState(t *testing.T) {
	contractGraph := &graph.ContractGraph{BusinessObjectMaps: []ast.BusinessObjectMap{{
		Domain: "user",
		Objects: []ast.BusinessObjectBoundary{
			{
				CanonicalObject: "UserAccount",
				BoundedContext:  "account",
				ObjectKind:      ast.ObjectKindAggregateRoot,
				FieldRoles: map[string][]string{
					"authoritative_state": {"userId", "createdAt", "status", "version"},
				},
			},
			{
				CanonicalObject: "Persona",
				BoundedContext:  "persona_management",
				ObjectKind:      ast.ObjectKindAggregateRoot,
				FieldRoles: map[string][]string{
					"authoritative_state": {"userId", "createdAt", "status", "version"},
				},
			},
		},
	}}}

	if issues := validateAuthoritativeFieldOwnership(contractGraph); len(issues) != 0 {
		t.Fatalf("local identity and technical state must not collide: %+v", issues)
	}
}
