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
