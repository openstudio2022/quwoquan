package codegen

import (
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestMetadataTypeToGoRejectsUnknownAndUntypedCollections(t *testing.T) {
	t.Parallel()

	for _, value := range []string{"opaque_payload", "array", "list", "embedded_list"} {
		value := value
		t.Run(value, func(t *testing.T) {
			t.Parallel()
			if goType, err := metadataTypeToGo(value); err == nil {
				t.Fatalf("metadataTypeToGo(%q) = %q, want hard failure", value, goType)
			}
		})
	}
}

func TestFieldGoTypePreservesExplicitCollectionElementTypes(t *testing.T) {
	t.Parallel()

	generator := &DomainGenerator{}
	for fieldType, want := range map[string]string{
		"[]string":  "[]string",
		"[]float32": "[]float32",
		"[]object":  "[]map[string]any",
	} {
		got, err := generator.fieldGoType(domainField{Type: fieldType}, nil)
		if err != nil {
			t.Fatalf("fieldGoType(%q): %v", fieldType, err)
		}
		if got != want {
			t.Fatalf("fieldGoType(%q) = %q, want %q", fieldType, got, want)
		}
	}
}

func TestFieldGoTypeRequiresTypedEnumReference(t *testing.T) {
	t.Parallel()

	generator := &DomainGenerator{config: domainGeneratorConfig{typedEnums: true}}
	if _, err := generator.fieldGoType(domainField{Type: "enum"}, nil); err == nil ||
		!strings.Contains(err.Error(), "requires enum_ref") {
		t.Fatalf("typed enum without enum_ref error = %v", err)
	}
}

func TestIncludeReferencedValueObjectsOnlyPromotesReachableValues(t *testing.T) {
	t.Parallel()

	fields := fieldsDocument{
		Entities: map[string]domainEntityDocument{
			"Post": {Fields: []domainField{{Name: "source", Type: "SourceAttribution"}}},
		},
		ValueObjects: map[string]domainEntityDocument{
			"SourceAttribution": {Fields: []domainField{{Name: "proof", Type: "RightsProof"}}},
			"RightsProof":       {Fields: []domainField{{Name: "digest", Type: "string"}}},
			"UnrelatedView":     {Fields: []domainField{{Name: "id", Type: "string"}}},
		},
	}

	promoted := includeReferencedValueObjects(&fields)
	for _, name := range []string{"SourceAttribution", "RightsProof"} {
		if _, ok := promoted[name]; !ok {
			t.Fatalf("reachable value object %s was not promoted", name)
		}
		if _, ok := fields.Entities[name]; !ok {
			t.Fatalf("reachable value object %s missing from entity graph", name)
		}
	}
	if _, ok := fields.Entities["UnrelatedView"]; ok {
		t.Fatal("unreferenced value object leaked into generated domain graph")
	}
}
