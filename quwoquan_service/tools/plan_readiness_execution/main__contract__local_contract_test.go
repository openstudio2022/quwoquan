package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
)

func TestExecutionPlanProjectsEveryGraphAuthoredSlotDeterministically(t *testing.T) {
	t.Parallel()
	current := testContractGraph()
	path := writeTestGraph(t, current)

	var first bytes.Buffer
	if code := run([]string{"--graph", path}, &first); code != 0 {
		t.Fatalf("run() code=%d output=%s", code, first.String())
	}
	var second bytes.Buffer
	if code := run([]string{"--graph", path}, &second); code != 0 {
		t.Fatalf("second run() code=%d output=%s", code, second.String())
	}
	if first.String() != second.String() {
		t.Fatalf("execution plan is not byte deterministic:\nfirst=%s\nsecond=%s", first.String(), second.String())
	}

	var plan executionPlan
	if err := json.Unmarshal(first.Bytes(), &plan); err != nil {
		t.Fatal(err)
	}
	wantHash, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		t.Fatal(err)
	}
	if plan.Schema != planSchema || plan.ContractGraphSourceHash != wantHash {
		t.Fatalf("plan identity=%+v, want schema=%q sourceHash=%q", plan, planSchema, wantHash)
	}
	if plan.CaseCount != 2 || plan.ExecutionSlotCount != 3 || plan.RunnerSourceCount != 2 {
		t.Fatalf("plan counts=%+v, want cases=2 slots=3 runners=2", plan)
	}
	if got := []string{
		plan.Slots[0].CaseID + "/" + plan.Slots[0].Execution.Environment,
		plan.Slots[1].CaseID + "/" + plan.Slots[1].Execution.Environment,
		plan.Slots[2].CaseID + "/" + plan.Slots[2].Execution.Environment,
	}; strings.Join(got, ",") != "case-a/alpha,case-a/gamma,case-b/beta" {
		t.Fatalf("slot order=%v", got)
	}
	for _, forbidden := range []string{"\"status\"", "\"receipt\"", "\"signature\"", "resultBundle", "commercialReady"} {
		if strings.Contains(first.String(), forbidden) {
			t.Fatalf("execution plan contains forbidden result field %q: %s", forbidden, first.String())
		}
	}
}

func TestExecutionPlanRejectsDuplicateExecutionSlots(t *testing.T) {
	t.Parallel()
	current := testContractGraph()
	current.ReadinessCases[0].Executions = append(
		current.ReadinessCases[0].Executions,
		current.ReadinessCases[0].Executions[0],
	)
	assertPlanFails(t, writeTestGraph(t, current), "duplicate execution requirement")
}

func TestExecutionPlanRejectsDuplicateCaseIdentities(t *testing.T) {
	t.Parallel()
	current := testContractGraph()
	duplicate := current.ReadinessCases[0]
	duplicate.Executions = []ast.ReadinessExecutionRequirement{{
		Environment: "prod", Platform: "android", DeviceClass: "physical",
		Provider: "provider-a", DigestBinding: ast.ReadinessDigestCandidate,
	}}
	current.ReadinessCases = append(current.ReadinessCases, duplicate)
	assertPlanFails(t, writeTestGraph(t, current), "duplicate readiness case identity")
}

func TestExecutionPlanRejectsMalformedGraphJSON(t *testing.T) {
	t.Parallel()
	for name, input := range map[string]string{
		"duplicate key":     `{"sources":[],"sources":[]}`,
		"unknown field":     `{"sources":[],"unexpected":true}`,
		"trailing document": `{"sources":[]} {"sources":[]}`,
	} {
		t.Run(name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "graph.json")
			if err := os.WriteFile(path, []byte(input), 0o600); err != nil {
				t.Fatal(err)
			}
			assertPlanFails(t, path, "decode current ContractGraph")
		})
	}
}

func TestExecutionPlanRejectsSymlinkAndMissingCLIInput(t *testing.T) {
	t.Parallel()
	target := writeTestGraph(t, testContractGraph())
	link := filepath.Join(t.TempDir(), "graph.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	assertPlanFails(t, link, "bounded regular file")

	for _, args := range [][]string{nil, {"positional"}, {"--graph", target, "extra"}} {
		var output bytes.Buffer
		if code := run(args, &output); code != 2 {
			t.Fatalf("run(%v) code=%d output=%s, want 2", args, code, output.String())
		}
		assertSingleErrorJSON(t, output.Bytes(), "")
	}
}

func assertPlanFails(t *testing.T, graphPath, wantError string) {
	t.Helper()
	var output bytes.Buffer
	if code := run([]string{"--graph", graphPath}, &output); code != 2 {
		t.Fatalf("run() code=%d output=%s, want 2", code, output.String())
	}
	assertSingleErrorJSON(t, output.Bytes(), wantError)
}

func assertSingleErrorJSON(t *testing.T, output []byte, wantError string) {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(output))
	var result fatalResult
	if err := decoder.Decode(&result); err != nil {
		t.Fatalf("output=%q is not JSON: %v", output, err)
	}
	if result.Error == "" || (wantError != "" && !strings.Contains(result.Error, wantError)) {
		t.Fatalf("error=%q, want substring %q", result.Error, wantError)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err == nil {
		t.Fatalf("output contains a second JSON document: %s", output)
	}
}

func writeTestGraph(t *testing.T, current *graph.ContractGraph) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "contract_graph.json")
	data, err := json.Marshal(current)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func testContractGraph() *graph.ContractGraph {
	return &graph.ContractGraph{
		Sources: []ast.SourceDigest{
			{Path: "services/chat-service/contracts/chat/conversation/operations.yaml", SHA256: strings.Repeat("b", 64)},
			{Path: "services/user-service/contracts/user/user_settings/operations.yaml", SHA256: strings.Repeat("a", 64)},
		},
		ReadinessCases: []ast.ReadinessCaseContract{
			{
				ObjectID: "user.user_settings", SpecRef: "specs/user/settings/spec.md#gwt-001",
				CaseID: "case-b", Producer: ast.ReadinessProducerApp,
				Layer:            ast.ReadinessLayerAPIIntegration,
				Target:           ast.ReadinessCaseTarget{Kind: ast.ReadinessTargetOperation, ID: "user.user_settings.UpdateSettings"},
				RunnerSourcePath: "quwoquan_app/test/api_integration/service/user_service/user/user_settings/settings__api_integration_test.dart",
				SourcePath:       "user/user_settings/operations.yaml",
				Executions: []ast.ReadinessExecutionRequirement{{
					Environment: "beta", Platform: "android", DeviceClass: "emulator",
					Provider: "provider-b", DigestBinding: ast.ReadinessDigestCandidate,
				}},
			},
			{
				ObjectID: "chat.conversation", SpecRef: "specs/chat/conversation/spec.md#gwt-001",
				CaseID: "case-a", Producer: ast.ReadinessProducerService,
				Layer:            ast.ReadinessLayerLocalContract,
				Target:           ast.ReadinessCaseTarget{Kind: ast.ReadinessTargetObject, ID: "chat.conversation"},
				RunnerSourcePath: "quwoquan_service/services/chat-service/tests/local_contract/chat/conversation/conversation__local_contract_test.go",
				SourcePath:       "chat/conversation/operations.yaml",
				Executions: []ast.ReadinessExecutionRequirement{
					{Environment: "gamma", Platform: "ios", DeviceClass: "physical", Provider: "provider-a", DigestBinding: ast.ReadinessDigestRelease},
					{Environment: "alpha", Platform: "android", DeviceClass: "physical", Provider: "provider-a", DigestBinding: ast.ReadinessDigestRelease},
				},
			},
		},
	}
}
