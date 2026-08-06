// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
package assistant_run_test

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestAssistantAppWireSchemasHaveOnePackageCanonicalDestination(t *testing.T) {
	t.Parallel()

	root := deviceActionAssistantServiceRoot(t)
	packagePrefix := "packages/quwoquan_cloud_contracts/lib/src/generated/assistant/"
	libraryPrefix := "package:quwoquan_cloud_contracts/src/generated/assistant/"
	for source, fileName := range map[string]string{
		"contracts/assistant/assistant_run/schema.yaml":        "assistant_run.g.dart",
		"contracts/assistant/assistant_session/schema.yaml":    "assistant_session.g.dart",
		"contracts/assistant/skill_subscription/schema.yaml":   "skill_subscription.g.dart",
		"contracts/_shared/assistant_stream_event/schema.yaml": "assistant_stream_event.g.dart",
		"contracts/_shared/runtime_failure/schema.yaml":        "assistant_runtime_failure.g.dart",
		"resources/skill_packages/official/schema.yaml":        "assistant_skill_manifest_registry.g.dart",
	} {
		t.Run(fileName, func(t *testing.T) {
			var schema struct {
				LibraryPath string `yaml:"library_path"`
				OutputPath  string `yaml:"output_path"`
			}
			data, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(source)))
			if err != nil {
				t.Fatal(err)
			}
			if err := yaml.Unmarshal(data, &schema); err != nil {
				t.Fatal(err)
			}
			if schema.LibraryPath != libraryPrefix+fileName ||
				schema.OutputPath != packagePrefix+fileName {
				t.Fatalf("schema=%+v, want one package canonical destination", schema)
			}
		})
	}
}

func TestRetiredSessionStateDecisionSchemaCannotReenterGeneration(t *testing.T) {
	t.Parallel()

	path := filepath.Join(
		deviceActionAssistantServiceRoot(t),
		"contracts", "_shared", "session_state_decision", "schema.yaml",
	)
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("retired App-owned policy schema still exists: %s err=%v", path, err)
	}
}
