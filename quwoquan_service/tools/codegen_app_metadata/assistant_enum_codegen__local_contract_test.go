package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestStrictOnlyAssistantEnumDoesNotRequireParserFallback(t *testing.T) {
	t.Parallel()

	catalog := &assistantEnumCatalog{
		Enums: []assistantEnumDef{
			{
				Name: "AssistantPreferenceScope",
				Values: []assistantEnumValueDef{
					{Name: "session", Wire: "session"},
					{Name: "longTerm", Wire: "long_term"},
				},
			},
		},
	}
	if err := validateAssistantEnumDefaults(catalog); err != nil {
		t.Fatalf("strict-only enum rejected: %v", err)
	}
	rendered := renderAssistantRuntimeEnumsDart(catalog)
	if !strings.Contains(rendered, "parseAssistantPreferenceScopeStrict") {
		t.Fatalf("strict parser missing:\n%s", rendered)
	}
	if strings.Contains(rendered, "AssistantPreferenceScope parseAssistantPreferenceScope(") {
		t.Fatalf("strict-only enum must not generate a fallback parser:\n%s", rendered)
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

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
func TestGenerateAssistantRuntimeEnumsGoWritesAndChecksExplicitServiceOutput(
	t *testing.T,
) {
	output := filepath.Join(t.TempDir(), "assistant_runtime_enums.g.go")
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize ContractGraph metadata source: %v", err)
	}
	if err := generateAssistantRuntimeEnumsGo(metadataDir, output, false); err != nil {
		t.Fatalf("generate Assistant runtime Go enums: %v", err)
	}
	if err := generateAssistantRuntimeEnumsGo(metadataDir, output, true); err != nil {
		t.Fatalf("check generated Assistant runtime Go enums: %v", err)
	}

	if err := os.WriteFile(output, []byte("stale"), 0o600); err != nil {
		t.Fatalf("write stale generated output: %v", err)
	}
	err := generateAssistantRuntimeEnumsGo(metadataDir, output, true)
	if err == nil || !strings.Contains(err.Error(), "are stale") {
		t.Fatalf("stale generated output error = %v, want stale diagnostic", err)
	}
}
