package main

import (
	"strings"
	"testing"
)

func TestValidateAssistantEnumDefaultsRejectsMissingParserDefault(t *testing.T) {
	t.Parallel()

	err := validateAssistantEnumDefaults(&assistantEnumCatalog{
		Enums: []assistantEnumDef{
			{
				Name: "AssistantPreferenceScope",
				Values: []assistantEnumValueDef{
					{Name: "session", Wire: "session"},
					{Name: "longTerm", Wire: "long_term"},
				},
			},
		},
	})
	if err == nil {
		t.Fatal("expected missing parser default to be rejected")
	}
	if !strings.Contains(err.Error(), "AssistantPreferenceScope") ||
		!strings.Contains(err.Error(), "unknown") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestValidateAssistantEnumDefaultsAcceptsDeclaredParserDefault(t *testing.T) {
	t.Parallel()

	err := validateAssistantEnumDefaults(&assistantEnumCatalog{
		Enums: []assistantEnumDef{
			{
				Name: "AssistantPreferenceScope",
				Values: []assistantEnumValueDef{
					{Name: "session", Wire: "session"},
					{Name: "longTerm", Wire: "long_term"},
					{Name: "unknown", Wire: ""},
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("expected declared parser default to pass: %v", err)
	}
}
