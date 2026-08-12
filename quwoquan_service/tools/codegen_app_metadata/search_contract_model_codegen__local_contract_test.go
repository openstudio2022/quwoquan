package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestCanonicalSearchProjectionFollowsReadModelIdentity(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	path, err := projectionPathByReadModel(metadataDir, "CanonicalSearchHit")
	if err != nil {
		t.Fatal(err)
	}
	relative, err := filepath.Rel(metadataDir, path)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := filepath.ToSlash(relative),
		"search/search/search_index_view/projections/canonical_search_hit.yaml"; got != want {
		t.Fatalf("projection path=%q want %q", got, want)
	}
}

func TestCanonicalSearchClientFieldsPreserveNestedTypesAndWireNames(t *testing.T) {
	fields, err := canonicalSearchEntityFields([]fieldDef{
		{
			Name:           "class",
			Type:           "string",
			ClientDartName: "intersectionClass",
			ClientWireName: "class",
			Constraints:    []string{"NULLABLE"},
		},
		{
			Name:        "contentType",
			Type:        "enum",
			EnumRef:     "ContentType",
			Constraints: []string{"NOT_NULL"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if fields[0].Name != "intersectionClass" || projectionWireKey(fields[0]) != "class" {
		t.Fatalf("reserved wire name drifted: %#v", fields[0])
	}
	if fields[1].DartType != "ContentType" || fields[1].EnumRef != "ContentType" {
		t.Fatalf("canonical enum degraded: %#v", fields[1])
	}
	if !fields[1].DartEnumDecoderWithPath || fields[1].DartEnumWireGetter != "wireName" {
		t.Fatalf("canonical enum owner ABI degraded: %#v", fields[1])
	}

	hitField, err := canonicalSearchClientField(
		"evidence",
		"evidence",
		"[]CanonicalSearchEvidence",
		"",
		false,
	)
	if err != nil {
		t.Fatal(err)
	}
	if hitField.DartType != "List<CanonicalSearchEvidence>" ||
		hitField.ListElementDartClass != "CanonicalSearchEvidence" {
		t.Fatalf("nested list degraded: %#v", hitField)
	}
}

func TestCanonicalSearchGeneratedModelIsStrictAndUsesCanonicalNestedDecoder(t *testing.T) {
	content := renderStandaloneDtoDart(clientProjection{
		DartClass: "CanonicalSearchHit",
		Strict:    true,
		Fields: []projectionFieldDef{
			{Name: "target", WireName: "target", DartType: "String", WireType: "string"},
			{
				Name:                  "content",
				WireName:              "content",
				DartType:              "CanonicalSearchContentHit",
				WireType:              "CanonicalSearchContentHit",
				Nullable:              true,
				MapFromStringKeyClass: "CanonicalSearchContentHit",
			},
		},
	}, "canonical_search_hit.yaml")
	for _, expected := range []string{
		"_validateCanonicalSearchHitWire(m)",
		"CanonicalSearchContentHit.fromMap(_parseStringKeyMap(m['content'])!)",
		"'target': target",
		"'content': content?.toMap()",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated canonical Search model missing %q:\n%s", expected, content)
		}
	}
}

func TestCanonicalSearchContentEnumsUseContentOperationOwner(t *testing.T) {
	field, err := canonicalSearchClientField(
		"contentType",
		"contentType",
		"enum",
		"ContentType",
		false,
	)
	if err != nil {
		t.Fatal(err)
	}
	model := canonicalSearchClientModel{
		className: "CanonicalSearchContentHit",
		fields:    []projectionFieldDef{field},
	}
	imports, err := canonicalSearchModelImports(model, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(imports) != 1 || imports[0] != "../../content/content_operation_contracts.g.dart" {
		t.Fatalf("canonical enum import=%v", imports)
	}
	content := renderStandaloneDtoDart(clientProjection{
		DartClass: "CanonicalSearchContentHit",
		Strict:    true,
		Fields:    []projectionFieldDef{field},
	}, "search/search/search_index_view/fields.yaml#types.CanonicalSearchContentHit")
	for _, expected := range []string{
		"ContentType.fromWire(m['contentType'], 'CanonicalSearchContentHit.contentType')",
		"'contentType': contentType.wireName",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated Search model missing canonical Content enum ABI %q:\n%s", expected, content)
		}
	}
}

func TestCanonicalSearchNestedOwnerTypesUseSchemaOwnedGeneratedClosure(t *testing.T) {
	t.Parallel()
	models := []canonicalSearchClientModel{{
		className: "SearchResponseView",
		fileName:  "search_response_view.g.dart",
		fields: []projectionFieldDef{{
			Name: "interpretedQuery", WireName: "interpretedQuery",
			WireType: "OwnerSearchInterpretedQuery", DartType: "OwnerSearchInterpretedQuery",
			MapFromStringKeyClass: "OwnerSearchInterpretedQuery",
		}},
	}}
	fields := &fieldsFile{Types: map[string]entityDef{
		"OwnerSearchInterpretedQuery": {Fields: []fieldDef{
			{Name: "normalized", Type: "string", Constraints: []string{"NOT_NULL"}},
			{Name: "tokens", Type: "[]string", Constraints: []string{"NOT_NULL"}},
		}},
	}}
	closed, err := canonicalSearchModelClosure(models, fields)
	if err != nil {
		t.Fatal(err)
	}
	if len(closed) != 2 || closed[1].className != "OwnerSearchInterpretedQuery" ||
		closed[1].fileName != "owner_search_interpreted_query.g.dart" {
		t.Fatalf("closed models=%+v", closed)
	}
	files := map[string]string{}
	for _, model := range closed {
		files[model.className] = model.fileName
	}
	imports, err := canonicalSearchModelImports(closed[0], files)
	if err != nil {
		t.Fatal(err)
	}
	if len(imports) != 1 || imports[0] != "owner_search_interpreted_query.g.dart" {
		t.Fatalf("nested owner imports=%v", imports)
	}
}

func TestCanonicalSearchNestedTypeClosureRejectsUnknownAndRecursiveTypes(t *testing.T) {
	t.Parallel()
	base := func(typeName string) []canonicalSearchClientModel {
		return []canonicalSearchClientModel{{
			className: "SearchResponseView",
			fields: []projectionFieldDef{{
				Name: "nested", WireName: "nested", WireType: typeName,
				DartType: typeName, MapFromStringKeyClass: typeName,
			}},
		}}
	}
	if _, err := canonicalSearchModelClosure(base("ForeignModel"), &fieldsFile{}); err == nil ||
		!strings.Contains(err.Error(), "schema-owned") {
		t.Fatalf("unknown nested type error=%v", err)
	}
	recursive := &fieldsFile{Types: map[string]entityDef{
		"OwnerSearchRecursive": {Fields: []fieldDef{{Name: "child", Type: "OwnerSearchRecursive"}}},
	}}
	if _, err := canonicalSearchModelClosure(base("OwnerSearchRecursive"), recursive); err == nil ||
		!strings.Contains(err.Error(), "recursive") {
		t.Fatalf("recursive nested type error=%v", err)
	}
}

func TestCanonicalSearchSchemaEntityAcceptsLoaderAliasButRejectsConflict(t *testing.T) {
	t.Parallel()
	definition := entityDef{Fields: []fieldDef{{Name: "normalized", Type: "string"}}}
	fields := &fieldsFile{
		Types:    map[string]entityDef{"OwnerSearchInterpretedQuery": definition},
		Entities: map[string]entityDef{"OwnerSearchInterpretedQuery": definition},
	}
	entity, section, err := canonicalSearchSchemaEntity(fields, "OwnerSearchInterpretedQuery")
	if err != nil {
		t.Fatalf("projected loader alias must remain one schema definition: %v", err)
	}
	if section != "types" || len(entity.Fields) != 1 {
		t.Fatalf("unexpected canonical entity section=%q fields=%#v", section, entity.Fields)
	}

	fields.Entities["OwnerSearchInterpretedQuery"] = entityDef{
		Fields: []fieldDef{{Name: "raw", Type: "string"}},
	}
	if _, _, err := canonicalSearchSchemaEntity(fields, "OwnerSearchInterpretedQuery"); err == nil ||
		!strings.Contains(err.Error(), "conflicting schema-owned definitions") {
		t.Fatalf("conflicting loader definitions must fail closed, got %v", err)
	}
}
