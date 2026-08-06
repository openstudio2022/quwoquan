// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-001
package load_test

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/load"
)

const syntheticReadinessSpecRef = "specs/feature-tree/runtime/" + "demo/spec.md#gwt-001"

const (
	syntheticServiceRunner       = "quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/operation_alpha__api_integration_test.go"
	syntheticPythonServiceRunner = "quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/test_operation_alpha__api_integration_test.py"
	syntheticAppRunner           = "quwoquan_app/test/user_acceptance/service/demo_service/demo_context/demo_object/page_uat_test.dart"
	syntheticOpsRunner           = "quwoquan_ops/tests/acceptance/replay/demo/demo_context/demo_object/object_replay_test.py"
)

type readinessCaseRepo struct {
	root           string
	metadataDir    string
	operationsPath string
}

func newReadinessCaseRepo(t *testing.T, readinessCases string) readinessCaseRepo {
	t.Helper()
	root := t.TempDir()
	repo := readinessCaseRepo{
		root: root,
		metadataDir: filepath.Join(
			root, "quwoquan_service", "services", "demo-service", "contracts",
		),
	}
	objectDir := filepath.Join(repo.metadataDir, "demo", "demo_context", "demo_object")
	repo.operationsPath = filepath.Join(objectDir, "operations.yaml")
	repo.write(
		t,
		filepath.Join(repo.metadataDir, "demo", "demo_context", "context.yaml"),
		"role: core\n",
	)
	repo.write(t, filepath.Join(objectDir, "object.yaml"), "kind: aggregate_root\n")
	repo.write(t, repo.operationsPath, syntheticOperations(readinessCases))
	repo.write(
		t,
		filepath.Join(repo.root, "specs", "feature-tree", "runtime", "demo", "spec.md"),
		"# Demo\n\n<a id=\"gwt-001\"></a>\n### GWT-001 readiness case\n",
	)
	repo.write(t, filepath.Join(repo.root, syntheticServiceRunner),
		"// spec_ref: "+syntheticReadinessSpecRef+"\n// readiness_case: operation-alpha\npackage demo_object_test\n")
	repo.write(t, filepath.Join(repo.root, syntheticPythonServiceRunner),
		"# spec_ref: "+syntheticReadinessSpecRef+"\n# readiness_case: operation-alpha\n")
	repo.write(t, filepath.Join(repo.root, syntheticAppRunner),
		"// spec_ref: "+syntheticReadinessSpecRef+"\n// readiness_case: page-uat\n")
	repo.write(t, filepath.Join(repo.root, syntheticOpsRunner),
		"# spec_ref: "+syntheticReadinessSpecRef+"\n# readiness_case: object-replay\n")
	return repo
}

func TestLoadReadinessCasesAcceptsCanonicalPythonServiceRunner(t *testing.T) {
	repo := newReadinessCaseRepo(t, strings.Replace(
		validSyntheticReadinessCase(), syntheticServiceRunner, syntheticPythonServiceRunner, 1,
	))

	catalog, err := load.Load(repo.metadataDir, load.WithRepoRoot(repo.root))
	if err != nil {
		t.Fatalf("Load Python service runner: %v", err)
	}
	if len(catalog.ReadinessCases) != 1 ||
		catalog.ReadinessCases[0].RunnerSourcePath != syntheticPythonServiceRunner {
		t.Fatalf("readiness cases=%+v, want canonical Python service runner", catalog.ReadinessCases)
	}
}

func (repo readinessCaseRepo) write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", path, err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func syntheticOperations(readinessCases string) string {
	return `api_routes:
  - method: POST
    path: /demo/run
    operation: RunDemo
    actor: none
    application:
      kind: command
      facet: DemoFacade
      method: runDemo
      aggregate_owner: DemoObject
      mutation_target: DemoObject
      invariant_target: DemoObject
runtime_entrypoints:
  - name: AppendDemoProjection
    kind: internal_port
    phase: transactional_append
    application:
      kind: command
      facet: DemoProjectionAppender
      method: append
      object_owner: DemoObject
` + readinessCases
}

func TestLoadReadinessCasesNormalizesObjectLocalOperationTarget(t *testing.T) {
	repo := newReadinessCaseRepo(t, `readiness_cases:
  - case_id: operation-alpha
    spec_ref: `+syntheticReadinessSpecRef+`
    producer: service
    layer: api_integration
    target:
      kind: operation
      id: RunDemo
    runner_source_path: `+syntheticServiceRunner+`
    executions:
      - env: alpha
        platform: service
        device: runner
        provider: provider-stable
        digest_binding: candidate
      - env: prod
        platform: service
        device: runner
        provider: provider-stable
        digest_binding: release
  - case_id: page-uat
    spec_ref: `+syntheticReadinessSpecRef+`
    producer: app
    layer: user_acceptance
    target:
      kind: page
      id: demo.main
    runner_source_path: `+syntheticAppRunner+`
    executions:
      - env: gamma
        platform: android
        device: physical
        provider: provider-stable
        digest_binding: candidate
  - case_id: object-replay
    spec_ref: `+syntheticReadinessSpecRef+`
    producer: ops
    layer: replay
    target:
      kind: object
      id: demo.demo_object
    runner_source_path: `+syntheticOpsRunner+`
    executions:
      - env: gamma
        platform: service
        device: runner
        provider: provider-stable
        digest_binding: candidate
`)

	catalog, err := load.Load(repo.metadataDir, load.WithRepoRoot(repo.root))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(catalog.ReadinessCases) != 3 {
		t.Fatalf("readiness cases=%+v, want 3", catalog.ReadinessCases)
	}
	operation := catalog.ReadinessCases[0]
	if operation.ObjectID != "demo.demo_object" ||
		operation.Target.Kind != ast.ReadinessTargetOperation ||
		operation.Target.ID != "demo.demo_object.RunDemo" {
		t.Fatalf("operation case=%+v, want fully-qualified local target", operation)
	}
	if operation.SourcePath != "demo/demo_context/demo_object/operations.yaml" {
		t.Fatalf("sourcePath=%q", operation.SourcePath)
	}
	if operation.RunnerSourcePath != syntheticServiceRunner {
		t.Fatalf("runnerSourcePath=%q", operation.RunnerSourcePath)
	}
	if len(operation.Executions) != 2 ||
		operation.Executions[1].DigestBinding != ast.ReadinessDigestRelease {
		t.Fatalf("executions=%+v", operation.Executions)
	}
	if catalog.ReadinessCases[1].Target.ID != "demo.main" ||
		catalog.ReadinessCases[2].Target.ID != "demo.demo_object" {
		t.Fatalf("non-operation targets changed: %+v", catalog.ReadinessCases)
	}
}

func TestLoadReadinessCasesInfersRepositoryRootFromOwningContract(t *testing.T) {
	repo := newReadinessCaseRepo(t, validSyntheticReadinessCase())

	catalog, err := load.Load(repo.metadataDir)
	if err != nil {
		t.Fatalf("Load without physical evidence derivation: %v", err)
	}
	if len(catalog.ReadinessCases) != 1 {
		t.Fatalf("readiness cases=%+v, want one verified authored runner", catalog.ReadinessCases)
	}
	if len(catalog.ReadinessEvidence) != 0 {
		t.Fatalf("readiness evidence=%+v, want none without WithRepoRoot", catalog.ReadinessEvidence)
	}
}

func TestLoadReadinessCasesNormalizesRuntimeEntrypointTarget(t *testing.T) {
	for _, targetID := range []string{
		"AppendDemoProjection",
		"demo.demo_object.AppendDemoProjection",
	} {
		t.Run(targetID, func(t *testing.T) {
			repo := newReadinessCaseRepo(t, strings.Replace(
				validSyntheticReadinessCase(),
				"id: RunDemo",
				"id: "+targetID,
				1,
			))

			catalog, err := load.Load(repo.metadataDir, load.WithRepoRoot(repo.root))
			if err != nil {
				t.Fatalf("Load: %v", err)
			}
			if len(catalog.ReadinessCases) != 1 {
				t.Fatalf("readiness cases=%+v, want 1", catalog.ReadinessCases)
			}
			if got := catalog.ReadinessCases[0].Target; got.Kind != ast.ReadinessTargetOperation ||
				got.ID != "demo.demo_object.AppendDemoProjection" {
				t.Fatalf("runtime entrypoint target=%+v, want fully-qualified operation target", got)
			}
		})
	}
}

func TestLoadReadinessCasesAreOptional(t *testing.T) {
	repo := newReadinessCaseRepo(t, "")
	catalog, err := load.Load(repo.metadataDir)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(catalog.ReadinessCases) != 0 {
		t.Fatalf("readiness cases=%+v, want empty", catalog.ReadinessCases)
	}
}

func TestLoadReadinessCasesFailsClosed(t *testing.T) {
	tests := map[string]struct {
		cases      string
		mutateRepo func(*testing.T, readinessCaseRepo)
		want       string
	}{
		"unknown case field": {
			cases: validSyntheticReadinessCase() + "    status: passed\n",
			want:  "unknown fields: status",
		},
		"missing runner source": {
			cases: strings.Replace(
				validSyntheticReadinessCase(),
				"    runner_source_path: "+syntheticServiceRunner+"\n", "", 1,
			),
			want: "runner_source_path must be a non-empty string",
		},
		"runner source unavailable": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), syntheticServiceRunner,
				"quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/missing__api_integration_test.go", 1,
			),
			want: "runner file is unavailable",
		},
		"service runner is not a test file": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), syntheticServiceRunner,
				"quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/operation_alpha.py", 1,
			),
			mutateRepo: func(t *testing.T, repo readinessCaseRepo) {
				repo.write(t,
					filepath.Join(repo.root, "quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/operation_alpha.py"),
					"# spec_ref: "+syntheticReadinessSpecRef+"\n# readiness_case: operation-alpha\n",
				)
			},
			want: "runner path is not canonical",
		},
		"runner source does not attest case": {
			cases: strings.Replace(validSyntheticReadinessCase(), "operation-alpha", "operation-other", 1),
			want:  "runner does not declare exact readiness_case",
		},
		"runner string literal cannot spoof source markers": {
			cases: validSyntheticReadinessCase(),
			mutateRepo: func(t *testing.T, repo readinessCaseRepo) {
				repo.write(t, filepath.Join(repo.root, syntheticServiceRunner),
					"package demo_object_test\nvar fake = `spec_ref: "+syntheticReadinessSpecRef+
						"\\nreadiness_case: operation-alpha`\n")
			},
			want: "runner does not declare exact spec_ref",
		},
		"unknown target field": {
			cases: strings.Replace(validSyntheticReadinessCase(), "      id: RunDemo\n", "      id: RunDemo\n      operation_id: RunDemo\n", 1),
			want:  "unknown fields: operation_id",
		},
		"unknown execution field": {
			cases: validSyntheticReadinessCase() + "        token: forbidden\n",
			want:  "unknown fields: token",
		},
		"unknown operation": {
			cases: strings.Replace(validSyntheticReadinessCase(), "id: RunDemo", "id: MissingDemo", 1),
			want:  "is not declared by this object's api_routes or runtime_entrypoints",
		},
		"duplicate operation and runtime entrypoint": {
			cases: validSyntheticReadinessCase(),
			mutateRepo: func(t *testing.T, repo readinessCaseRepo) {
				repo.write(t, repo.operationsPath, strings.Replace(
					syntheticOperations(validSyntheticReadinessCase()),
					"name: AppendDemoProjection",
					"name: RunDemo",
					1,
				))
			},
			want: "declared more than once across api_routes and runtime_entrypoints",
		},
		"foreign operation": {
			cases: strings.Replace(validSyntheticReadinessCase(), "id: RunDemo", "id: other.object.RunDemo", 1),
			want:  "is not owned by demo.demo_object",
		},
		"producer layer mismatch": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), "producer: service", "producer: ops", 1,
			),
			want: "producer \"ops\" cannot own layer \"api_integration\"",
		},
		"app local contract cannot own page target": {
			cases: strings.NewReplacer(
				"producer: service", "producer: app",
				"layer: api_integration", "layer: local_contract",
				"kind: operation", "kind: page",
				"id: RunDemo", "id: demo.main",
			).Replace(validSyntheticReadinessCase()),
			want: "producer \"app\" layer \"local_contract\" cannot own target kind \"page\"",
		},
		"app user acceptance cannot own operation target": {
			cases: strings.NewReplacer(
				"producer: service", "producer: app",
				"layer: api_integration", "layer: user_acceptance",
			).Replace(validSyntheticReadinessCase()),
			want: "producer \"app\" layer \"user_acceptance\" cannot own target kind \"operation\"",
		},
		"ops replay cannot own operation target": {
			cases: strings.NewReplacer(
				"producer: service", "producer: ops",
				"layer: api_integration", "layer: replay",
			).Replace(validSyntheticReadinessCase()),
			want: "producer \"ops\" layer \"replay\" cannot own target kind \"operation\"",
		},
		"unknown producer": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), "producer: service", "producer: fixture", 1,
			),
			want: "producer \"fixture\" is unknown",
		},
		"duplicate case": {
			cases: validSyntheticReadinessCase() + strings.TrimPrefix(validSyntheticReadinessCase(), "readiness_cases:\n"),
			want:  "duplicate readiness case_id",
		},
		"duplicate execution": {
			cases: validSyntheticReadinessCase() + `      - env: alpha
        platform: service
        device: runner
        provider: provider-stable
        digest_binding: candidate
`,
			want: "duplicate execution requirement",
		},
		"prod candidate": {
			cases: strings.Replace(
				strings.Replace(validSyntheticReadinessCase(), "env: alpha", "env: prod", 1),
				"digest_binding: candidate", "digest_binding: candidate_or_release", 1,
			),
			want: "Prod execution must bind release",
		},
		"missing spec": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), syntheticReadinessSpecRef,
				"specs/feature-tree/runtime/"+"missing/spec.md#gwt-001", 1,
			),
			want: "target does not exist",
		},
		"missing acceptance anchor": {
			cases: strings.Replace(
				validSyntheticReadinessCase(), "#gwt-001", "#gwt-002", 1,
			),
			want: "acceptance anchor does not exist",
		},
	}

	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			repo := newReadinessCaseRepo(t, test.cases)
			if test.mutateRepo != nil {
				test.mutateRepo(t, repo)
			}
			_, err := load.Load(repo.metadataDir, load.WithRepoRoot(repo.root))
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("Load error=%v, want substring %q", err, test.want)
			}
		})
	}
}

func validSyntheticReadinessCase() string {
	return `readiness_cases:
  - case_id: operation-alpha
    spec_ref: ` + syntheticReadinessSpecRef + `
    producer: service
    layer: api_integration
    target:
      kind: operation
      id: RunDemo
    runner_source_path: ` + syntheticServiceRunner + `
    executions:
      - env: alpha
        platform: service
        device: runner
        provider: provider-stable
        digest_binding: candidate
`
}

func TestOperationsSchemaStrictlyDefinesReadinessCases(t *testing.T) {
	schema := compileOperationsSchema(t)
	valid := func() map[string]any {
		return map[string]any{
			"api_routes": []any{},
			"readiness_cases": []any{map[string]any{
				"case_id":            "operation-alpha",
				"spec_ref":           syntheticReadinessSpecRef,
				"producer":           "service",
				"layer":              "api_integration",
				"runner_source_path": syntheticServiceRunner,
				"target": map[string]any{
					"kind": "operation",
					"id":   "RunDemo",
				},
				"executions": []any{map[string]any{
					"env":            "alpha",
					"platform":       "service",
					"device":         "runner",
					"provider":       "provider-stable",
					"digest_binding": "candidate",
				}},
			}},
		}
	}
	if err := schema.Validate(valid()); err != nil {
		t.Fatalf("valid readiness case rejected: %v", err)
	}

	for name, mutate := range map[string]func(map[string]any){
		"unknown case field": func(instance map[string]any) {
			firstReadinessCase(instance)["status"] = "passed"
		},
		"unknown target field": func(instance map[string]any) {
			firstReadinessCase(instance)["target"].(map[string]any)["operation_id"] = "RunDemo"
		},
		"unknown execution field": func(instance map[string]any) {
			firstExecution(instance)["credential"] = "forbidden"
		},
		"missing target": func(instance map[string]any) {
			delete(firstReadinessCase(instance), "target")
		},
		"missing runner source": func(instance map[string]any) {
			delete(firstReadinessCase(instance), "runner_source_path")
		},
		"unknown layer": func(instance map[string]any) {
			firstReadinessCase(instance)["layer"] = "smoke"
		},
		"producer layer mismatch": func(instance map[string]any) {
			firstReadinessCase(instance)["producer"] = "ops"
		},
		"prod must bind release": func(instance map[string]any) {
			firstExecution(instance)["env"] = "prod"
		},
	} {
		t.Run(name, func(t *testing.T) {
			instance := valid()
			mutate(instance)
			if err := schema.Validate(instance); err == nil {
				t.Fatalf("operations schema accepted invalid readiness case: %+v", instance)
			}
		})
	}
}

func firstReadinessCase(instance map[string]any) map[string]any {
	return instance["readiness_cases"].([]any)[0].(map[string]any)
}

func firstExecution(instance map[string]any) map[string]any {
	return firstReadinessCase(instance)["executions"].([]any)[0].(map[string]any)
}

func compileOperationsSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
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
