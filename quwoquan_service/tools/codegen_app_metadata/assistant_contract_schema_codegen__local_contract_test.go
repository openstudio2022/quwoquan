package main

import (
	"strings"
	"testing"
)

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
		Name:    "status",
		Type:    "enum",
		EnumRef: "SkillSubscriptionStatus",
		Default: "active",
		Strict:  true,
	}

	got := assistantRenderFromJsonValue(field, &assistantContractSchema{}, nil)
	if got != "parseSkillSubscriptionStatusStrict((json['status'] as String?)?.trim() ?? '')" {
		t.Fatalf("required lifecycle enum decoder must fail closed, got %q", got)
	}
}
