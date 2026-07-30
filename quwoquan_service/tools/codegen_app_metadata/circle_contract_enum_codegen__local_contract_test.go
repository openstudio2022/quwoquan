package main

import (
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
func TestCircleContractEnumsAreGeneratedAsStrictCanonicalWireTypes(t *testing.T) {
	enums := map[string][]string{
		"CircleStatus":             {"active", "archived", "deleted"},
		"CircleVisibility":         {"public", "private", "invite_only"},
		"CircleJoinPolicy":         {"open", "approval", "invite_only"},
		"CircleKind":               {"interest", "organization"},
		"CircleDisplaySubjectType": {"circle", "school"},
		"HomepageType":             {"vehicle", "travel_photo"},
	}
	fields := &fieldsFile{Entities: map[string]entityDef{
		"PersonaCircleSlice": {Fields: []fieldDef{
			{Name: "status", Type: "enum", EnumRef: "CircleStatus"},
			{Name: "visibility", Type: "enum", EnumRef: "CircleVisibility"},
			{Name: "joinPolicy", Type: "enum", EnumRef: "CircleJoinPolicy"},
			{Name: "kind", Type: "enum", EnumRef: "CircleKind"},
			{Name: "displaySubjectType", Type: "enum", EnumRef: "CircleDisplaySubjectType"},
			{Name: "linkedHomepageType", Type: "enum", EnumRef: "HomepageType"},
		}},
	}}
	circleFields := &fieldsFile{Entities: map[string]entityDef{
		"Circle": {Fields: []fieldDef{
			{Name: "status", Type: "enum", EnumRef: "CircleStatus"},
			{Name: "visibility", Type: "enum", EnumRef: "CircleVisibility"},
			{Name: "joinPolicy", Type: "enum", EnumRef: "CircleJoinPolicy"},
			{Name: "kind", Type: "enum", EnumRef: "CircleKind"},
			{Name: "displaySubjectType", Type: "enum", EnumRef: "CircleDisplaySubjectType"},
			{Name: "linkedHomepageType", Type: "enum", EnumRef: "HomepageType"},
		}},
	}}
	refs, err := personaCircleSliceEnumRefs(circleFields, fields)
	if err != nil {
		t.Fatal(err)
	}
	content, err := renderCircleContractEnumsDart(enums, refs)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"enum CircleStatus",
		"inviteOnly(\"invite_only\")",
		"travelPhoto(\"travel_photo\")",
		"static CircleVisibility fromWire(Object? raw)",
		"throw FormatException('invalid HomepageType: $raw')",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated Circle enums missing %q:\n%s", expected, content)
		}
	}
}

func TestCircleContractEnumGenerationRejectsMissingCanonicalEnum(t *testing.T) {
	_, err := renderCircleContractEnumsDart(
		map[string][]string{},
		[]string{"CircleStatus"},
	)
	if err == nil || !strings.Contains(err.Error(), "CircleStatus") {
		t.Fatalf("missing canonical enum accepted: %v", err)
	}
}

func TestUserContractEnumGenerationUsesSharedFollowSubjectKind(t *testing.T) {
	content, err := renderSharedContractEnumsDart(
		map[string][]string{
			"FollowSubjectKind": {"persona", "homepage", "circle", "location"},
		},
		[]string{"FollowSubjectKind"},
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"enum FollowSubjectKind",
		"location(\"location\")",
		"final String wireValue",
		"static FollowSubjectKind fromWire(Object? raw)",
		"throw FormatException('invalid FollowSubjectKind: $raw')",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated User enum missing %q:\n%s", expected, content)
		}
	}
}

func TestCircleContractEnumGenerationRejectsUnownedProjectionEnum(t *testing.T) {
	_, err := personaCircleSliceEnumRefs(
		&fieldsFile{Entities: map[string]entityDef{
			"Circle": {Fields: []fieldDef{{Name: "status", Type: "enum", EnumRef: "CircleStatus"}}},
		}},
		&fieldsFile{Entities: map[string]entityDef{
			"PersonaCircleSlice": {Fields: []fieldDef{{Name: "status", Type: "enum"}}},
		}},
	)
	if err == nil || !strings.Contains(err.Error(), "status") {
		t.Fatalf("enum without enum_ref accepted: %v", err)
	}
}

func TestPersonaCircleSliceCannotDowngradeCanonicalCircleEnumToString(t *testing.T) {
	_, err := personaCircleSliceEnumRefs(
		&fieldsFile{Entities: map[string]entityDef{
			"Circle": {Fields: []fieldDef{{Name: "status", Type: "enum", EnumRef: "CircleStatus"}}},
		}},
		&fieldsFile{Entities: map[string]entityDef{
			"PersonaCircleSlice": {Fields: []fieldDef{{Name: "status", Type: "string"}}},
		}},
	)
	if err == nil || !strings.Contains(err.Error(), "CircleStatus") {
		t.Fatalf("canonical Circle enum downgrade accepted: %v", err)
	}
}
