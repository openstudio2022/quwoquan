// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-001
package validate

import (
	"path/filepath"
	"runtime"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func TestProjectionLifecycleRequiresConsumerEdgesOnlyWhenEventsAreAuthored(t *testing.T) {
	t.Parallel()

	schema := compileObjectSchema(t)
	base := canonicalProjectionObject()
	if err := schema.Validate(base); err != nil {
		t.Fatalf("callback/import projection without a domain-event edge was rejected: %v", err)
	}

	withSourceOnly := canonicalProjectionObject()
	withSourceOnly["lifecycle"].(map[string]any)["source_events"] = []any{
		"content.post.PostPublished",
	}
	if err := schema.Validate(withSourceOnly); err == nil {
		t.Fatal("projection source_events without an object-local event_consumer was accepted")
	}

	withConsumer := canonicalProjectionObject()
	lifecycle := withConsumer["lifecycle"].(map[string]any)
	lifecycle["source_events"] = []any{"content.post.PostPublished"}
	lifecycle["event_consumers"] = []any{map[string]any{
		"name": "ProjectPublishedPost", "kind": "projector",
		"facet": "PublishedPostProjector", "method": "apply",
		"idempotency": "aggregate_version",
	}}
	if err := schema.Validate(withConsumer); err != nil {
		t.Fatalf("canonical lifecycle event edge was rejected: %v", err)
	}
}

func canonicalProjectionObject() map[string]any {
	return map[string]any{
		"kind":        "projection",
		"description": "A canonical read projection owned by one object.",
		"identity": map[string]any{
			"fields": []any{"id"}, "version_source": "checkpoint",
		},
		"access": map[string]any{
			"commands": "none", "queries": "named_reader",
			"cross_context": "public_contract_only",
		},
		"relationships": []any{},
		"search_policy": map[string]any{
			"exposed":            "none",
			"not_exposed_reason": "Schema fixtures do not participate in production search.",
		},
		"assistant_access": map[string]any{
			"read":  map[string]any{"mode": "none", "scopes": []any{}},
			"cite":  map[string]any{"mode": "none", "scopes": []any{}},
			"write": map[string]any{"mode": "none", "scopes": []any{}},
		},
		"business_rules": []any{
			"Only canonical source callbacks may update the view.",
		},
		"lifecycle": map[string]any{
			"checkpoint": "source_sequence",
			"rebuild":    "replay_authoritative_source",
			"tombstone":  "delete_view_keep_checkpoint",
		},
	}
}

func compileObjectSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve object schema test path")
	}
	schemaPath := filepath.Join(
		filepath.Dir(thisFile), "..", "..", "..",
		"contracts", "metadata", "_schemas", "object.schema.json",
	)
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile object schema: %v", err)
	}
	return schema
}
