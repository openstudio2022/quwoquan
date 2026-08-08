package codegen

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
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

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestDomainEventWireValueUsesAuthoredOutboxWireIdentity(t *testing.T) {
	t.Parallel()

	got, err := domainEventWireValue(domainEvent{
		Name:              "ReportCreated",
		DeliverySemantics: "transactional_outbox",
		WireEventType:     "content.report.ReportCreated",
	})
	if err != nil {
		t.Fatal(err)
	}
	if got != "content.report.ReportCreated" {
		t.Fatalf("wire value = %q, want authored wire_event_type", got)
	}
}

func TestDomainEventWireValueFailsClosedForMissingOutboxWireIdentity(t *testing.T) {
	t.Parallel()

	if _, err := domainEventWireValue(domainEvent{
		Name:              "ReportCreated",
		DeliverySemantics: "transactional_outbox",
	}); err == nil || !strings.Contains(err.Error(), "requires wire_event_type") {
		t.Fatalf("missing wire_event_type error = %v", err)
	}
	got, err := domainEventWireValue(domainEvent{
		Name:              "LocalAuditRecorded",
		DeliverySemantics: "transactional_event_log",
	})
	if err != nil || got != "LocalAuditRecorded" {
		t.Fatalf("non-outbox wire value = %q, err=%v", got, err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestGenerateDomainEventsEmitsAuthoredWireIdentity(t *testing.T) {
	t.Parallel()

	const objectDir = "content/trust_safety/report"
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "content.report", Name: "Report",
			SourcePath: objectDir + "/object.yaml",
		}},
		Documents: []ast.SourceDocument{
			{
				Path: objectDir + "/fields.yaml",
				Content: json.RawMessage(`{
					"entity":"Report",
					"fields":[{"name":"reportId","type":"string"}]
				}`),
			},
			{
				Path: objectDir + "/events.yaml",
				Content: json.RawMessage(`{
					"events":[{
						"name":"ReportCreated",
						"delivery_semantics":"transactional_outbox",
						"wire_event_type":"content.report.ReportCreated"
					}]
				}`),
			},
		},
	}
	outputDir := t.TempDir()
	generator := NewDomainGenerator(
		NewSourceFromGraph("metadata", contractGraph),
		outputDir,
	)
	if err := generator.GenerateDomainEvents("Report"); err != nil {
		t.Fatal(err)
	}
	generated, err := os.ReadFile(filepath.Join(
		outputDir,
		"domain",
		"report",
		"event",
		"events.go",
	))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(
		string(generated),
		`ReportCreated = "content.report.ReportCreated"`,
	) {
		t.Fatalf("generated event constant did not preserve wire_event_type:\n%s", generated)
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
