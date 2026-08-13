package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-005
func TestAssistantSearchAccessIsGeneratedFromObjectContracts(t *testing.T) {
	registry := searchRegistryDocument{ObjectTypes: []searchObjectType{
		{ID: "content.post", Domain: "content", OwnerObject: "content.post", ExecutionStrategy: "remote_only"},
		{ID: "user.profile", Domain: "user", OwnerObject: "user.user_account", ExecutionStrategy: "remote_only"},
		{ID: "tag", Domain: "tag", OwnerObject: "tag.tag_node_view", ExecutionStrategy: "filter_only"},
		{ID: "web.document", Domain: "external", OwnerObject: "assistant.assistant_run", ExecutionStrategy: "remote_only"},
	}}
	objects := map[string]assistantSearchObjectDocument{
		"content.post": {
			AssistantAccess: assistantAccessDocument{
				Read: assistantAccessMode{Mode: "public"},
				Cite: assistantAccessMode{Mode: "public_citation"},
			},
		},
		"user.user_account": {
			AssistantAccess: assistantAccessDocument{
				Read: assistantAccessMode{Mode: "owner_scoped"},
				Cite: assistantAccessMode{Mode: "none"},
			},
		},
		"tag.tag_node_view": {},
		"assistant.assistant_run": {
			SearchPolicy: searchPolicyDocument{Exposed: "remote_provider"},
		},
	}

	rendered, err := renderAssistantSearchAccess(registry, objects)
	if err != nil {
		t.Fatalf("render assistant search access: %v", err)
	}
	for _, expected := range []string{
		`"content.post"`, `"web.document"`, `AssistantSearchAccessPolicyDigest`,
	} {
		if !bytes.Contains(rendered, []byte(expected)) {
			t.Fatalf("generated access is missing %s:\n%s", expected, rendered)
		}
	}
	for _, forbidden := range []string{`"user.profile"`, `"tag"`} {
		if bytes.Contains(rendered, []byte(forbidden)) {
			t.Fatalf("generated access unexpectedly includes %s:\n%s", forbidden, rendered)
		}
	}
}

func TestAssistantSearchAccessDiscoversObjectsOnlyFromContractGraphSource(t *testing.T) {
	source := contractcodegen.NewSourceFromGraph(
		"/path/that/must/not/be-scanned",
		&graph.ContractGraph{Documents: []ast.SourceDocument{
			jsonSourceDocument("_shared/search_objects.yaml", `{
				"object_types":[
					{"id":"content.post","domain":"content","owner_object":"content.post","execution_strategy":"remote_only"},
					{"id":"web.document","domain":"external","owner_object":"assistant.assistant_run","execution_strategy":"remote_only"}
				]
			}`),
			jsonSourceDocument("content/content/post/object.yaml", `{
				"assistant_access":{"read":{"mode":"public"},"cite":{"mode":"public_citation"}}
			}`),
			jsonSourceDocument("assistant/assistant/assistant_run/object.yaml", `{
				"search_policy":{"exposed":"remote_provider"}
			}`),
		}},
	)
	rendered, err := generateAssistantSearchAccess(source)
	if err != nil {
		t.Fatalf("generate from ContractGraph Source: %v", err)
	}
	for _, expected := range []string{`"content.post"`, `"web.document"`} {
		if !bytes.Contains(rendered, []byte(expected)) {
			t.Fatalf("generated access is missing %s:\n%s", expected, rendered)
		}
	}
}

func jsonSourceDocument(path, content string) ast.SourceDocument {
	return ast.SourceDocument{Path: path, Content: json.RawMessage(content)}
}

func TestMutatingToolRequiresCapabilityIntersectionPolicy(t *testing.T) {
	valid := map[string]any{
		"capability": map[string]any{
			"capabilityKey":        "calendar.event.create",
			"connectorRequirement": "required",
			"consentScopes":        []any{"calendar.event.create"},
			"allowedSurfaceKinds":  []any{"personal"},
			"recheckAtExecution":   true,
		},
	}
	if err := validateMutatingCapabilityPolicy("calendar_create_reminder", valid); err != nil {
		t.Fatalf("valid capability policy rejected: %v", err)
	}

	for name, mutate := range map[string]func(map[string]any){
		"missing capability": func(tool map[string]any) { delete(tool, "capability") },
		"no consent": func(tool map[string]any) {
			tool["capability"].(map[string]any)["consentScopes"] = []any{}
		},
		"no execution recheck": func(tool map[string]any) {
			tool["capability"].(map[string]any)["recheckAtExecution"] = false
		},
	} {
		t.Run(name, func(t *testing.T) {
			tool := map[string]any{
				"capability": map[string]any{
					"capabilityKey":        "calendar.event.create",
					"connectorRequirement": "required",
					"consentScopes":        []any{"calendar.event.create"},
					"allowedSurfaceKinds":  []any{"personal"},
					"recheckAtExecution":   true,
				},
			}
			mutate(tool)
			err := validateMutatingCapabilityPolicy("calendar_create_reminder", tool)
			if err == nil || !strings.Contains(err.Error(), "capability") &&
				!strings.Contains(err.Error(), "consent") {
				t.Fatalf("invalid capability policy was not rejected: %v", err)
			}
		})
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
func TestResearchPolicyUsesCanonicalInputBindings(t *testing.T) {
	navigate := map[string]any{
		"readOnly": true,
		"inputSchema": map[string]any{
			"properties": map[string]any{
				"target": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"kind": map[string]any{
							"type": "string",
							"enum": []any{"source", "document_link"},
						},
						"value": map[string]any{"type": "string"},
					},
				},
			},
		},
		"research": map[string]any{
			"operation":                 "navigate",
			"targetInputField":          "target",
			"targetKindField":           "kind",
			"targetValueField":          "value",
			"reusableSourceTargetKinds": []any{"source"},
			"childTargetKinds":          []any{"document_link"},
		},
	}
	if err := validateResearchPolicy("public_reader", navigate); err != nil {
		t.Fatalf("valid navigate policy rejected: %v", err)
	}

	navigate["research"].(map[string]any)["targetValueField"] = "url"
	if err := validateResearchPolicy("public_reader", navigate); err == nil ||
		!strings.Contains(err.Error(), "value binding") {
		t.Fatalf("invalid navigate binding was not rejected: %v", err)
	}

	discover := map[string]any{
		"readOnly": true,
		"inputSchema": map[string]any{
			"properties": map[string]any{
				"queries": map[string]any{"type": "string"},
			},
		},
		"research": map[string]any{
			"operation":          "discover",
			"parallelInputField": "queries",
		},
	}
	if err := validateResearchPolicy("search", discover); err == nil ||
		!strings.Contains(err.Error(), "array input") {
		t.Fatalf("invalid parallel binding was not rejected: %v", err)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
func TestFailurePolicyRequiresCanonicalAssistantError(t *testing.T) {
	valid := map[string]any{
		"failure": map[string]any{
			"providerFailureCode": "ASSISTANT.MIDDLEWARE.vertical_provider_unavailable",
		},
	}
	canonical := map[string]bool{
		"ASSISTANT.MIDDLEWARE.vertical_provider_unavailable": true,
	}
	if err := validateFailurePolicy("vertical_reader", valid, canonical); err != nil {
		t.Fatalf("valid failure policy rejected: %v", err)
	}

	invalid := map[string]any{
		"failure": map[string]any{
			"providerFailureCode": "VERTICAL.provider_unavailable",
		},
	}
	if err := validateFailurePolicy("vertical_reader", invalid, canonical); err == nil {
		t.Fatal("non-Assistant failure code was accepted")
	}

	missing := map[string]any{
		"failure": map[string]any{
			"providerFailureCode": "ASSISTANT.MIDDLEWARE.missing_error",
		},
	}
	if err := validateFailurePolicy("vertical_reader", missing, canonical); err == nil {
		t.Fatal("failure code absent from AssistantRun errors was accepted")
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
func TestResearchToolRequiresCompleteEvidenceAssessment(t *testing.T) {
	fields := []any{
		"status", "evidenceSufficient", "replanRequired", "reason",
		"targetIds", "documentIds", "artifactRefs", "sourceIds",
	}
	tool := map[string]any{
		"research": map[string]any{"operation": "discover"},
		"outputSchema": map[string]any{
			"required": []any{"evidenceAssessment"},
			"properties": map[string]any{
				"evidenceAssessment": map[string]any{
					"type":                 "object",
					"additionalProperties": false,
					"required":             fields,
				},
			},
		},
	}
	if err := validateResearchOutput("vertical_reader", tool); err != nil {
		t.Fatalf("complete evidence output rejected: %v", err)
	}

	tool["outputSchema"].(map[string]any)["required"] = []any{}
	if err := validateResearchOutput("vertical_reader", tool); err == nil {
		t.Fatal("optional evidenceAssessment was accepted")
	}
}

func TestEmergentTagProjectionUsesStandardOutputContract(t *testing.T) {
	valid := map[string]any{
		"outputSchema": map[string]any{
			"required": []any{"emergedTagRefs"},
			"properties": map[string]any{
				"emergedTagRefs": map[string]any{
					"type":  "array",
					"items": map[string]any{"type": "string"},
				},
			},
		},
	}
	if err := validateEmergentTagProjection("vertical_search", valid); err != nil {
		t.Fatalf("valid emergedTagRefs output rejected: %v", err)
	}

	invalid := map[string]any{
		"outputSchema": map[string]any{
			"required": []any{},
			"properties": map[string]any{
				"emergedTagRefs": map[string]any{
					"type":  "array",
					"items": map[string]any{"type": "string"},
				},
			},
		},
	}
	if err := validateEmergentTagProjection("vertical_search", invalid); err == nil {
		t.Fatal("optional emergedTagRefs output was accepted")
	}
}
