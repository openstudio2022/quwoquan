package controlplane

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestHydrateOperationReferencesUsesContractGraphTransportAndScopes(t *testing.T) {
	document := map[string]any{
		"object_types": []any{map[string]any{
			"object_type": "experiment",
			"operation_refs": []any{map[string]any{
				"operation_id":  "ops.experiment.UpdateExperimentRollout",
				"danger_level":  "high",
				"approval_mode": "single",
			}},
		}},
	}
	contractGraph := &graph.ContractGraph{Operations: []ast.Operation{{
		ID: "ops.experiment.UpdateExperimentRollout", LocalID: "UpdateExperimentRollout",
		Method: "POST", PathTemplate: "/control-plane/product/experiments/{experimentId}:rollout",
		Scopes: []string{"ops.experiment.write"},
	}}}

	if err := HydrateOperationReferences(document, contractGraph); err != nil {
		t.Fatalf("hydrate operation refs: %v", err)
	}
	object := document["object_types"].([]any)[0].(map[string]any)
	if _, exists := object["operation_refs"]; exists {
		t.Fatal("resolved document must not retain operation_refs")
	}
	operation := object["operations"].([]any)[0].(map[string]any)
	if operation["method"] != "POST" || operation["path"] != contractGraph.Operations[0].PathTemplate {
		t.Fatalf("operation transport was not sourced from ContractGraph: %#v", operation)
	}
	if operation["contract_operation_id"] != contractGraph.Operations[0].ID {
		t.Fatalf("missing canonical operation identity: %#v", operation)
	}
}

func TestHydrateOperationReferencesRejectsUnknownOrDuplicateTruth(t *testing.T) {
	contractGraph := &graph.ContractGraph{}
	unknown := map[string]any{"object_types": []any{map[string]any{
		"object_type":    "experiment",
		"operation_refs": []any{map[string]any{"operation_id": "ops.experiment.Missing"}},
	}}}
	if err := HydrateOperationReferences(unknown, contractGraph); err == nil {
		t.Fatal("unknown ContractGraph operation reference must fail")
	}

	duplicate := map[string]any{"object_types": []any{map[string]any{
		"object_type":    "experiment",
		"operations":     []any{map[string]any{"operation": "InlineParallelTruth"}},
		"operation_refs": []any{},
	}}}
	if err := HydrateOperationReferences(duplicate, contractGraph); err == nil {
		t.Fatal("parallel operation truth sources must fail")
	}
}
