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

func TestIncludeReferencedOwnedTypesOnlyPromotesReachableValues(t *testing.T) {
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

	promoted := includeReferencedOwnedTypes(&fields, nil)
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

func TestIncludeReferencedOwnedTypesResolvesObjectRefAndTypes(t *testing.T) {
	t.Parallel()

	fields := fieldsDocument{
		Entities: map[string]domainEntityDocument{
			"Gathering": {Fields: []domainField{
				{Name: "targetRef", Type: "object", ObjectRef: "GatheringTargetRef"},
				{Name: "participants", Type: "[]GatheringParticipant"},
			}},
		},
		Types: map[string]domainEntityDocument{
			"GatheringTargetRef":     {Fields: []domainField{{Name: "objectId", Type: "string"}}},
			"GatheringParticipant":   {Fields: []domainField{{Name: "personaId", Type: "string"}}},
			"CreateGatheringCommand": {Fields: []domainField{{Name: "title", Type: "string"}}},
		},
	}

	promoted := includeReferencedOwnedTypes(&fields, nil)
	for _, name := range []string{"GatheringTargetRef", "GatheringParticipant"} {
		if _, ok := promoted[name]; !ok {
			t.Fatalf("reachable owned type %s was not promoted", name)
		}
	}
	if _, ok := promoted["CreateGatheringCommand"]; ok {
		t.Fatal("unreferenced command DTO leaked into generated domain graph")
	}
}

func TestIncludeReferencedOwnedTypesPromotesSharedGeoPointOnce(t *testing.T) {
	t.Parallel()

	fields := fieldsDocument{
		Entities: map[string]domainEntityDocument{
			"Post": {Fields: []domainField{{Name: "location", Type: "GeoPoint"}}},
		},
	}
	sharedTypes := map[string]domainEntityDocument{
		"GeoPoint": {Fields: []domainField{
			{Name: "latitude", Type: "float64"},
			{Name: "longitude", Type: "float64"},
		}},
	}

	promoted := includeReferencedOwnedTypes(&fields, sharedTypes)
	if _, ok := promoted["GeoPoint"]; !ok {
		t.Fatal("shared GeoPoint was not promoted from _shared/types.yaml")
	}
	if _, ok := fields.Entities["GeoPoint"]; !ok {
		t.Fatal("shared GeoPoint missing from entity graph")
	}
	if strings.Contains(goModelTemplate, "type GeoPoint struct") {
		t.Fatal("goModelTemplate must not hardcode GeoPoint; shared types own the wire shape")
	}
}

func TestCollectEnumTypesPrefersObjectLocalEnum(t *testing.T) {
	t.Parallel()

	generator := &DomainGenerator{}
	fields := fieldsDocument{
		Entities: map[string]domainEntityDocument{
			"Gathering": {Fields: []domainField{{Name: "status", Type: "enum", EnumRef: "GatheringStatus"}}},
		},
		Enums: map[string]localEnumDocument{
			"GatheringStatus": {Values: []string{"draft", "open"}},
		},
	}
	types, err := generator.collectEnumTypes(fields, []string{"Gathering"})
	if err != nil {
		t.Fatalf("collectEnumTypes: %v", err)
	}
	if len(types) != 1 || len(types[0].Values) != 2 || types[0].Values[0].WireValue != "draft" {
		t.Fatalf("local enum values = %#v", types)
	}
}
