// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"context"
	"testing"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

func TestToolRegistryFreezesMetadataAtRegistrationAndReadBoundaries(t *testing.T) {
	metadata := toolpkg.DefaultMetadata("isolated_reader")
	registry := toolpkg.NewRegistry()
	registry.Register(metadata, func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{Output: map[string]any{"summary": "ok"}}, nil
	})

	originalProperties := metadata.InputSchema["properties"].(map[string]any)
	originalProperties["injected_after_registration"] = toolpkg.StringProperty("invalid")

	first, found := registry.Metadata("isolated_reader")
	if !found {
		t.Fatal("registered tool metadata is missing")
	}
	firstProperties := first.InputSchema["properties"].(map[string]any)
	if _, leaked := firstProperties["injected_after_registration"]; leaked {
		t.Fatal("registry retained the caller-owned metadata map")
	}
	firstProperties["injected_after_read"] = toolpkg.StringProperty("invalid")

	second, found := registry.Metadata("isolated_reader")
	if !found {
		t.Fatal("registered tool metadata disappeared")
	}
	secondProperties := second.InputSchema["properties"].(map[string]any)
	if _, leaked := secondProperties["injected_after_read"]; leaked {
		t.Fatal("Metadata returned a mutable registry-owned schema")
	}

	declaration := registry.ModelDeclarations([]string{"isolated_reader"})[0]
	declaration.Parameters["properties"].(map[string]any)["model_mutation"] =
		toolpkg.StringProperty("invalid")
	declarationAgain := registry.ModelDeclarations([]string{"isolated_reader"})[0]
	if _, leaked := declarationAgain.Parameters["properties"].(map[string]any)["model_mutation"]; leaked {
		t.Fatal("model tool declaration leaked mutable schema across calls")
	}
}
