package validate

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestObjectSchemaNarrowsStrongRelationshipMeaning(t *testing.T) {
	t.Parallel()

	schemaPath := filepath.Join(repositorySchemaRoot(t), "object.schema.json")
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile object schema: %v", err)
	}
	for _, test := range []struct {
		name         string
		relationship string
		wantValid    bool
	}{
		{"same aggregate strong", "{name: child, kind: owned, consistency: strong}", true},
		{"projection source eventual", "{name: source, kind: projection_source, consistency: eventual}", true},
		{"projection source strong", "{name: source, kind: projection_source, consistency: strong}", false},
	} {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			payload := "kind: aggregate_root\ndescription: canonical consistency schema fixture\nidentity: {fields: [id], version_source: store_commit}\naccess: {commands: aggregate_facade, queries: named_reader, cross_context: public_contract_only}\nrelationships:\n- " + test.relationship + "\nsearch_policy: {exposed: none, not_exposed_reason: canonical test fixture remains outside search}\nassistant_access:\n  read: {mode: none, scopes: []}\n  cite: {mode: none, scopes: []}\n  write: {mode: none, scopes: []}\nbusiness_rules: [identity_is_stable]\nlifecycle: {state_field: status, states: [active]}\n"
			var instance any
			if err := yaml.Unmarshal([]byte(payload), &instance); err != nil {
				t.Fatal(err)
			}
			err := schema.Validate(instance)
			if test.wantValid && err != nil {
				t.Fatalf("schema rejected canonical relationship: %v", err)
			}
			if !test.wantValid && err == nil {
				t.Fatal("schema accepted projection_source + strong")
			}
		})
	}

	data, err := os.ReadFile(schemaPath)
	if err != nil {
		t.Fatal(err)
	}
	if !containsAll(string(data), "同一 aggregate", "线性一致", "read-your-writes", "projection") {
		t.Fatal("object schema does not document the narrow strong consistency semantics")
	}
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
