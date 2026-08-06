package validate

import (
	"path/filepath"
	"runtime"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// spec_ref: specs/feature-tree/runtime/runtime-errors/spec.md#sit-001
func TestRepositoryErrorsConformToCanonicalSchema(t *testing.T) {
	t.Parallel()

	schema := compileErrorsSchema(t)
	serviceRoot := serviceRootFromErrorsSchemaTest(t)
	paths, err := filepath.Glob(filepath.Join(
		serviceRoot, "services", "*", "contracts", "*", "*", "errors.yaml",
	))
	if err != nil {
		t.Fatalf("glob repository errors: %v", err)
	}
	if len(paths) == 0 {
		t.Fatal("no repository errors.yaml files found")
	}
	for _, path := range paths {
		instance, decodeErr := decodeYAMLAsJSON(path)
		if decodeErr != nil {
			t.Errorf("decode %s: %v", path, decodeErr)
			continue
		}
		if validateErr := schema.Validate(instance); validateErr != nil {
			t.Errorf("validate %s: %v", path, validateErr)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-errors/spec.md#sit-001
func TestErrorsSchemaAcceptsOnlyCanonicalRecoveryContract(t *testing.T) {
	t.Parallel()

	schema := compileErrorsSchema(t)
	actions := []string{
		"absorb", "retry", "fallback", "surface", "escalate", "compensate",
	}
	disruptions := []string{
		"silent", "passiveIndicator", "snackbar", "inlineCard", "permissionCard",
	}
	for _, action := range actions {
		action := action
		for _, disruption := range disruptions {
			disruption := disruption
			t.Run(action+"_"+disruption, func(t *testing.T) {
				t.Parallel()
				entry := canonicalHTTPErrorEntry()
				entry["recovery_action"] = action
				entry["disruption_level"] = disruption
				if err := schema.Validate(map[string]any{"errors": []any{entry}}); err != nil {
					t.Fatalf("canonical recovery contract rejected: %v", err)
				}
			})
		}
	}

	if err := schema.Validate(map[string]any{"errors": []any{}}); err != nil {
		t.Fatalf("explicit empty error set rejected: %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-errors/spec.md#sit-001
func TestErrorsSchemaRejectsSecondTruthAndIncompleteHTTPContract(t *testing.T) {
	t.Parallel()

	schema := compileErrorsSchema(t)
	for _, action := range []string{
		"none", "refresh", "reload", "reauth", "reauthenticate",
		"request_permission", "configure", "resubmit",
	} {
		action := action
		t.Run("legacy_action_"+action, func(t *testing.T) {
			t.Parallel()
			entry := canonicalHTTPErrorEntry()
			entry["recovery_action"] = action
			if err := schema.Validate(map[string]any{"errors": []any{entry}}); err == nil {
				t.Fatalf("errors schema accepted legacy recovery action %q", action)
			}
		})
	}

	for name, mutate := range map[string]func(map[string]any, map[string]any){
		"top-level domain identity": func(document, _ map[string]any) {
			document["domain"] = "RUNTIME"
		},
		"top-level aggregate identity": func(document, _ map[string]any) {
			document["aggregate"] = "Fixture"
		},
		"unknown recovery action": func(_, entry map[string]any) {
			entry["recovery_action"] = "restart_everything"
		},
		"missing disruption level": func(_, entry map[string]any) {
			delete(entry, "disruption_level")
		},
		"unknown disruption level": func(_, entry map[string]any) {
			entry["disruption_level"] = "modalDialog"
		},
		"authored l10n key": func(_, entry map[string]any) {
			entry["l10n_key"] = "runtime.error.fixture_unavailable"
		},
		"Dart code without English message": func(_, entry map[string]any) {
			entry["dart_const"] = "fixtureUnavailable"
			delete(entry["user_message"].(map[string]any), "en")
		},
		"unknown item key": func(_, entry map[string]any) {
			entry["debug_hint"] = "retry later"
		},
		"HTTP without status": func(_, entry map[string]any) {
			delete(entry, "http_status")
		},
		"scalar HTTP without status": func(_, entry map[string]any) {
			entry["emitted_by"] = []any{"http"}
			delete(entry, "http_status")
		},
		"gateway without status": func(_, entry map[string]any) {
			entry["emitted_by"] = []any{map[string]any{"surface": "gateway"}}
			delete(entry, "http_status")
		},
		"non-HTTP with status": func(_, entry map[string]any) {
			entry["emitted_by"] = []any{map[string]any{"surface": "worker"}}
		},
	} {
		name := name
		mutate := mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			entry := canonicalHTTPErrorEntry()
			document := map[string]any{"errors": []any{entry}}
			mutate(document, entry)
			if err := schema.Validate(document); err == nil {
				t.Fatalf("errors schema accepted invalid document: %#v", document)
			}
		})
	}
}

func canonicalHTTPErrorEntry() map[string]any {
	return map[string]any{
		"code":             "RUNTIME.SYSTEM.fixture_unavailable",
		"reason":           "fixture_unavailable",
		"http_status":      503,
		"emitted_by":       []any{map[string]any{"surface": "http", "operations": []any{"GetFixture"}}},
		"recovery_action":  "retry",
		"disruption_level": "snackbar",
		"user_message":     map[string]any{"zh": "暂时不可用", "en": "Temporarily unavailable"},
	}
}

func compileErrorsSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	serviceRoot := serviceRootFromErrorsSchemaTest(t)
	schemaPath := filepath.Join(
		serviceRoot, "contracts", "metadata", "_schemas", "errors.schema.json",
	)
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile errors schema: %v", err)
	}
	return schema
}

func serviceRootFromErrorsSchemaTest(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
}
