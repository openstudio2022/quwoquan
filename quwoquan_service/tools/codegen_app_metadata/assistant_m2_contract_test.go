package main

import (
	"path/filepath"
	"testing"
)

func TestAssistantM2ContractSchemasGovernance(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	cases := []struct {
		domain string
		name   string
	}{
		{domain: "assistant", name: "runtime_failure"},
		{domain: "assistant", name: "assistant_conversation"},
		{domain: "assistant", name: "assistant_turn_envelope"},
		{domain: "assistant", name: "skill_subscription"},
		{domain: "assistant", name: "device_context"},
		{domain: "assistant", name: "tool_use"},
		{domain: "assistant", name: "assistant_stream_event"},
		{domain: "notification", name: "app_message"},
	}
	allowedMapFields := map[string]bool{
		"runtime_failure.context":                            true,
		"assistant_turn_envelope.input":                      true,
		"assistant_turn_envelope.trigger":                    true,
		"device_context.device_context_facts.coarseLocation": true,
		"tool_use.input":                                     true,
		"tool_use.result":                                    true,
		"assistant_stream_event.payload":                     true,
	}

	for _, tc := range cases {
		t.Run(tc.domain+"/"+tc.name, func(t *testing.T) {
			schemaPath := filepath.Join(metadataDir, tc.domain, tc.name, "schema.yaml")
			schema, err := readAssistantContractSchema(schemaPath)
			if err != nil {
				t.Fatalf("read schema: %v", err)
			}
			assertM2FieldsGovernance(t, tc.name, tc.name, schema.Fields, allowedMapFields)
			for subName, sub := range schema.Subcontracts {
				assertM2FieldsGovernance(t, tc.name, tc.name+"."+subName, sub.Fields, allowedMapFields)
			}
		})
	}
}

func assertM2FieldsGovernance(t *testing.T, schemaName, owner string, fields []assistantContractField, allowedMapFields map[string]bool) {
	t.Helper()
	for _, field := range fields {
		key := owner + "." + field.Name
		if field.Name == "errorMessage" || field.Name == "debugMessage" {
			t.Fatalf("%s uses naked error message field %q", schemaName, field.Name)
		}
		if field.Name == "failure" || field.Name == "runtimeFailure" {
			if field.Ref != "RuntimeFailureWire" {
				t.Fatalf("%s.%s must ref RuntimeFailureWire, got %q", schemaName, field.Name, field.Ref)
			}
		}
		switch field.Type {
		case "map", "any", "list<map>":
			if !allowedMapFields[key] {
				t.Fatalf("%s has weak boundary field %s of type %s", schemaName, key, field.Type)
			}
		}
	}
}
