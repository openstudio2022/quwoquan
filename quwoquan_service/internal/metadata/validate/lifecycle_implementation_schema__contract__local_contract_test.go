// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package validate

import (
	"path/filepath"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func TestContractGraphLifecycleConsumerRequiresDerivedImplementation(t *testing.T) {
	t.Parallel()

	schemaPath := filepath.Join(repositorySchemaRoot(t), "contract_graph.schema.json")
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile ContractGraph schema: %v", err)
	}
	consumer := map[string]any{
		"name": "ProjectDemo", "kind": "projector",
		"facet": "DemoProjector", "method": "apply",
		"idempotency": "aggregate_version",
		"implementation": map[string]any{
			"path":   "quwoquan_service/services/demo-service/internal/demo/demo/adapters/projector.go",
			"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
	}
	document := minimalLifecycleImplementationGraph(consumer)
	if err := schema.Validate(document); err != nil {
		t.Fatalf("ContractGraph schema rejected derived lifecycle implementation: %v", err)
	}

	delete(consumer, "implementation")
	if err := schema.Validate(document); err == nil {
		t.Fatal("ContractGraph schema accepted lifecycle consumer without derived implementation")
	}
}

func minimalLifecycleImplementationGraph(consumer map[string]any) map[string]any {
	return map[string]any{
		"objects": []any{map[string]any{
			"id": "demo.demo", "domain": "demo", "name": "Demo",
			"kind": "projection", "kindExplicit": true,
			"sourcePath": "demo/demo/demo/object.yaml",
			"lifecycle": map[string]any{
				"eventConsumers": []any{consumer},
			},
		}},
		"operations":         []any{},
		"runtimeEntrypoints": []any{},
		"projections":        []any{},
		"businessObjectMaps": []any{},
		"readinessCases":     []any{},
		"readinessEvidence":  []any{},
		"objectReadiness":    []any{},
		"sources":            []any{},
		"documents":          []any{},
	}
}
