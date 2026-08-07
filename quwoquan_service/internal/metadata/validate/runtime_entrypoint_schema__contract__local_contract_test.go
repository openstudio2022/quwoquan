// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/domain-service-directory-ownership/spec.md#gwt-001
package validate

import (
	"path/filepath"
	"runtime"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func TestRuntimeEntrypointSchemaRejectsRetiredLifecycleConsumerFacts(t *testing.T) {
	t.Parallel()

	schema := compileOperationsSchema(t)
	validEntrypoint := map[string]any{
		"name":  "ApplySourceEvent",
		"kind":  "subscription",
		"phase": "event_ingest",
		"application": map[string]any{
			"kind": "command", "facet": "SampleHandler",
			"method": "apply", "object_owner": "Sample",
		},
		"telemetry": map[string]any{
			"metric": "sample_event_ingest", "trace": true,
			"attributes": []any{"outcome"},
		},
		"slo": map[string]any{
			"freshness_p95_seconds": 60,
			"backlog_max_events":    1000,
			"failure_ratio_percent": 1,
		},
	}
	if err := schema.Validate(map[string]any{
		"api_routes": []any{}, "runtime_entrypoints": []any{validEntrypoint},
	}); err != nil {
		t.Fatalf("canonical runtime entrypoint rejected: %v", err)
	}

	for _, retired := range []struct {
		key   string
		value any
	}{
		{key: "source_events", value: []any{"content.post.PostPublished"}},
		{key: "checkpoint", value: "aggregate_version"},
		{key: "rebuild", value: "replay_authoritative_events"},
		{key: "tombstone", value: "retain_checkpoint"},
	} {
		t.Run(retired.key, func(t *testing.T) {
			entrypoint := make(map[string]any, len(validEntrypoint)+1)
			for key, value := range validEntrypoint {
				entrypoint[key] = value
			}
			entrypoint[retired.key] = retired.value
			if err := schema.Validate(map[string]any{
				"api_routes": []any{}, "runtime_entrypoints": []any{entrypoint},
			}); err == nil {
				t.Fatalf("operations schema accepted retired runtime entrypoint key %q", retired.key)
			}
		})
	}
}

func TestOperationSchemaAcceptsExactlyOneLifecycleCommandOwner(t *testing.T) {
	t.Parallel()

	schema := compileOperationsSchema(t)
	application := map[string]any{
		"kind": "command", "facet": "SearchRequestAccountClosureRecoveryCommandFacet",
		"method": "recoverDeadLetter", "lifecycle_owner": "SearchRequestFact",
		"mutation_target": "SearchRequestFact", "invariant_target": "SearchRequestFact",
	}
	route := map[string]any{
		"method": "POST", "path": "/internal/search/account-closure/dead-letters:recover",
		"operation": "RecoverSearchAccountClosureDeadLetter", "actor": "none",
		"application": application,
	}
	if err := schema.Validate(map[string]any{"api_routes": []any{route}}); err != nil {
		t.Fatalf("canonical lifecycle-owned command rejected: %v", err)
	}

	application["append_sink"] = "SearchRequestFact"
	if err := schema.Validate(map[string]any{"api_routes": []any{route}}); err == nil {
		t.Fatal("command with lifecycle_owner and append_sink was accepted")
	}
}

func TestOperationSchemaKeepsPermissionsOnlyInTypedAuthorization(t *testing.T) {
	t.Parallel()

	schema := compileOperationsSchema(t)
	route := map[string]any{
		"method": "POST", "path": "/gatherings/{gatheringId}:safety-terminate",
		"operation": "SafetyTerminateGathering", "actor": "persona",
		"request_bindings": map[string]any{
			"path": []any{map[string]any{"name": "gatheringId", "field": "gatheringId"}},
		},
		"application": map[string]any{
			"kind": "command", "facet": "GatheringCommandFacet",
			"method": "safetyTerminateGathering", "aggregate_owner": "Gathering",
			"mutation_target": "Gathering", "invariant_target": "Gathering",
		},
		"security": map[string]any{
			"auth_mode": "required", "principal": "persona",
			"token_transport": "bearer", "anonymous_policy": "deny",
			"visibility": "private",
		},
		"authorization": map[string]any{
			"principal":        "persona",
			"permissions":      []any{"circle.gathering.safety_terminate"},
			"ownership_policy": "trust_and_safety_authority",
		},
	}
	if err := schema.Validate(map[string]any{"api_routes": []any{route}}); err != nil {
		t.Fatalf("typed authorization permissions rejected: %v", err)
	}

	route["security"].(map[string]any)["permissions"] = []any{
		"circle.gathering.safety_terminate",
	}
	if err := schema.Validate(map[string]any{"api_routes": []any{route}}); err == nil {
		t.Fatal("schema accepted duplicate permissions in the scalar security envelope")
	}
}

func compileOperationsSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve operations schema test path")
	}
	schemaPath := filepath.Join(
		filepath.Dir(thisFile), "..", "..", "..",
		"contracts", "metadata", "_schemas", "operations.schema.json",
	)
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile operations schema: %v", err)
	}
	return schema
}
