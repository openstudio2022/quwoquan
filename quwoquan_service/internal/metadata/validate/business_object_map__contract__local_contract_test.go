package validate

import (
	"encoding/json"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestValidateSpecificationRefRequiresExistingNonEmptyAnchor(t *testing.T) {
	documents := map[string]ast.SourceDocument{
		"content/content/post/object.yaml": {
			Path:    "content/content/post/object.yaml",
			Content: json.RawMessage(`{"business_rules":["author owns draft"],"lifecycle":{}}`),
		},
	}
	if err := validateSpecificationRef(documents, "content/content/post/object.yaml#business_rules"); err != nil {
		t.Fatalf("expected valid business rule ref: %v", err)
	}
	if err := validateSpecificationRef(documents, "content/content/post/object.yaml#lifecycle"); err == nil {
		t.Fatal("expected empty lifecycle anchor to fail")
	}
	if err := validateSpecificationRef(documents, "missing.yaml#business_rules"); err == nil {
		t.Fatal("expected missing document to fail")
	}
}

func TestValidateCounterSourcesRequiresCanonicalObject(t *testing.T) {
	boundaries := map[string]registeredBoundary{
		"content.ContentBehaviorFact": {},
		"content.Post":                {},
	}
	object := ast.BusinessObjectBoundary{
		CanonicalObject: "Post",
		CounterSources: map[string]string{
			"view": "content.ContentBehaviorFact.impressed",
		},
	}
	if issues := validateCounterSources("content/content/post/object.yaml", object, boundaries, nil); len(issues) != 0 {
		t.Fatalf("canonical counter source issues = %+v", issues)
	}

	object.CounterSources["view"] = "content.BehaviorFact.impressed"
	issues := validateCounterSources("content/content/post/object.yaml", object, boundaries, nil)
	if len(issues) != 1 || issues[0].Code != "CONTRACT.COUNTER_SOURCE.UNKNOWN_TARGET" {
		t.Fatalf("unknown counter source issues = %+v", issues)
	}
}

func TestValidateCounterSourcesRejectsAggregateMember(t *testing.T) {
	object := ast.BusinessObjectBoundary{
		CanonicalObject: "Post",
		CounterSources: map[string]string{
			"view": "content.PostCounter",
		},
	}
	members := map[string]registeredMember{
		"content.PostCounter": {OwnerID: "content.Post"},
	}
	issues := validateCounterSources("content/content/post/object.yaml", object, nil, members)
	if len(issues) != 1 || issues[0].Code != "CONTRACT.COUNTER_SOURCE.DIRECT_CHILD_ACCESS" {
		t.Fatalf("aggregate member counter source issues = %+v", issues)
	}
}

func TestProjectionRequiresCanonicalSourceRelationship(t *testing.T) {
	projection := ast.BusinessObjectBoundary{
		CanonicalObject: "SearchIndexView",
		ObjectKind:      ast.ObjectKindProjection,
	}
	issues := validateProjectionSourceRelationship("search/search_index_view/object.yaml", projection)
	if len(issues) != 1 || issues[0].Code != "CONTRACT.PROJECTION.MISSING_SOURCE_RELATIONSHIP" {
		t.Fatalf("missing projection source issues = %+v", issues)
	}

	projection.Relationships = []ast.ObjectRelationship{{Kind: "projection_source"}}
	if issues := validateProjectionSourceRelationship("search/search_index_view/object.yaml", projection); len(issues) != 0 {
		t.Fatalf("canonical projection source issues = %+v", issues)
	}

	aggregate := ast.BusinessObjectBoundary{
		CanonicalObject: "Post",
		ObjectKind:      ast.ObjectKindAggregateRoot,
	}
	if issues := validateProjectionSourceRelationship("content/post/object.yaml", aggregate); len(issues) != 0 {
		t.Fatalf("aggregate source issues = %+v", issues)
	}
}

func TestAggregateRootAccessAllowsRepositoryCLICommandFacade(t *testing.T) {
	t.Parallel()

	object := ast.BusinessObjectBoundary{
		CanonicalObject: "RecommendationModelRelease",
		ObjectKind:      ast.ObjectKindAggregateRoot,
		Access: ast.ObjectAccessPolicy{
			Commands:     "cli_facade",
			Queries:      "named_reader",
			CrossContext: "public_contract_only",
		},
	}
	if issues := validateObjectAccess("recommendation/recommendation_model_release/object.yaml", object); len(issues) != 0 {
		t.Fatalf("CLI-owned aggregate access issues = %+v", issues)
	}
}
