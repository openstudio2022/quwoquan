package main

import (
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
func TestAssistantSkillManifestCodegenIncludesCanonicalPackageProfiles(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	schema, err := readAssistantContractSchema(filepath.Join(
		metadataDir,
		"assistant",
		"assistant_skill_manifest",
		"schema.yaml",
	))
	if err != nil {
		t.Fatalf("read canonical SkillManifest schema: %v", err)
	}
	index, err := loadAssistantContractIndex(metadataDir)
	if err != nil {
		t.Fatalf("load Assistant contract index: %v", err)
	}
	rendered := renderAssistantSchemaDrivenContract(
		schema,
		index,
		"assistant/assistant_skill_manifest/schema.yaml",
	)
	for _, field := range []string{
		"catalogProfileRef",
		"activationProfileRef",
		"inputProfileRef",
		"contextProfileRef",
		"capabilityProfileRef",
		"orchestrationProfileRef",
		"triggerProfileRef",
		"memoryProfileRef",
		"presentationProfileRef",
		"evaluationProfileRef",
		"replayAssetRef",
	} {
		if !strings.Contains(rendered, "required this."+field+",") ||
			!strings.Contains(rendered, "final String "+field+";") {
			t.Fatalf("generated SkillManifest misses required field %q", field)
		}
	}
}

func TestAssistantRequiredObjectDecoderFailsClosedWhenMissing(t *testing.T) {
	field := assistantContractField{
		Name:     "destination",
		Type:     "object",
		Ref:      "CitationDestination",
		Required: true,
	}
	schema := &assistantContractSchema{DartClass: "AnswerEvidenceBinding"}
	index := &assistantContractIndex{
		fieldsByClass: map[string][]assistantContractField{},
	}

	got := assistantRenderFromJsonValue(field, schema, index)
	if !strings.Contains(got, "throw FormatException('required object field destination is missing')") {
		t.Fatalf("required object decoder must fail closed, got %q", got)
	}
	if strings.Contains(got, ": null") {
		t.Fatalf("required object decoder must not yield null, got %q", got)
	}
}

func TestAssistantRequiredEnumDecoderUsesStrictParser(t *testing.T) {
	field := assistantContractField{
		Name:     "status",
		Type:     "enum",
		EnumRef:  "SkillSubscriptionStatus",
		Default:  "active",
		Required: true,
		Strict:   true,
	}

	got := assistantRenderFromJsonValue(field, &assistantContractSchema{}, nil)
	if got != "parseSkillSubscriptionStatusStrict((json['status'] as String?)?.trim() ?? '')" {
		t.Fatalf("required lifecycle enum decoder must fail closed, got %q", got)
	}
}

func TestAssistantWireSchemaCodecOwnsStrictNestedWireABI(t *testing.T) {
	schema := &assistantContractSchema{
		DartClass: "ExampleEnvelopeWire",
		Fields: []assistantContractField{
			{
				Name:     "destination",
				Type:     "object",
				Ref:      "destination",
				Required: true,
			},
			{
				Name:    "destinations",
				Type:    "list<object>",
				Ref:     "destination",
				Default: []interface{}{},
			},
		},
		Subcontracts: map[string]assistantSubcontractSchema{
			"destination": {
				ClassName: "ExampleDestinationWire",
				Fields: []assistantContractField{
					{Name: "destinationId", Type: "string", Required: true},
				},
			},
		},
	}
	rendered := renderAssistantSchemaDrivenWireContract(
		schema,
		&assistantContractIndex{},
		"assistant/example/schema.yaml",
	)
	for _, expected := range []string{
		"Map<String, Object?> toWire()",
		"factory ExampleEnvelopeWire.fromWire(Map<String, Object?> map, [String path = \"ExampleEnvelopeWire\"])",
		"factory ExampleDestinationWire.fromWire(Map<String, Object?> map, [String path = \"ExampleDestinationWire\"])",
		"'destination': destination.toWire()",
		"ExampleDestinationWire.fromWire((map['destination'] as Map).cast<String, Object?>(), '$path.destination')",
		"ExampleDestinationWire.fromWire((entry.value as Map).cast<String, Object?>(), '$path.destinations[${entry.key}]')",
		"ExampleEnvelopeWire response contains unknown fields",
		"ExampleDestinationWire field destinationId has an invalid wire value",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("wire schema output misses %q:\n%s", expected, rendered)
		}
	}
	for _, forbidden := range []string{"toJson()", ".fromJson("} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("wire schema output retained JSON codec %q:\n%s", forbidden, rendered)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
func TestAssistantPreferenceSnapshotCodegenHasOneCanonicalIdentity(t *testing.T) {
	rendered := renderAssistantPreferenceSnapshotDart(&assistantSimpleSchema{})
	for _, expected := range []string{
		"class AssistantPreferenceSnapshot",
		"required this.preferenceId",
		"required this.kind",
		"final String sourceType",
		"final int version",
		"factory AssistantPreferenceSnapshot.fromJson",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated AssistantPreferenceSnapshot misses %q", expected)
		}
	}
	for _, retired := range []string{
		"Preference" + "Fact",
		"factId",
		"required this.key",
		"final bool revoked",
	} {
		if strings.Contains(rendered, retired) {
			t.Fatalf("generated AssistantPreferenceSnapshot retained retired contract %q", retired)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
func TestAssistantTurnImportsCanonicalPreferenceSnapshot(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	schema, err := readAssistantContractSchema(filepath.Join(
		metadataDir,
		"assistant",
		"assistant_turn",
		"schema.yaml",
	))
	if err != nil {
		t.Fatalf("read canonical AssistantTurn schema: %v", err)
	}
	index, err := loadAssistantContractIndex(metadataDir)
	if err != nil {
		t.Fatalf("load Assistant contract index: %v", err)
	}
	rendered := renderAssistantSchemaDrivenContract(
		schema,
		index,
		"assistant/assistant_turn/schema.yaml",
	)
	for _, expected := range []string{
		"import 'package:quwoquan_app/assistant/contracts/assistant_preference_snapshot.dart';",
		"this.sessionPreferences = const <AssistantPreferenceSnapshot>[]",
		"this.longTermPreferences = const <AssistantPreferenceSnapshot>[]",
		"final List<AssistantPreferenceSnapshot> sessionPreferences",
		"final List<AssistantPreferenceSnapshot> longTermPreferences",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated AssistantTurn misses canonical preference snapshot binding %q", expected)
		}
	}
	for _, retired := range []string{
		"preference_" + "fact.dart",
		"sessionPreference" + "Facts",
		"longTermPreference" + "Facts",
	} {
		if strings.Contains(rendered, retired) {
			t.Fatalf("generated AssistantTurn retained retired preference binding %q", retired)
		}
	}
}
