package graph_test

import (
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

func TestContractGraphCarriesCanonicalReadinessCasesDeterministically(t *testing.T) {
	t.Parallel()

	firstExecution := ast.ReadinessExecutionRequirement{
		Environment: "prod", Platform: "service", DeviceClass: "runner",
		Provider: "provider-stable", DigestBinding: ast.ReadinessDigestRelease,
	}
	secondExecution := ast.ReadinessExecutionRequirement{
		Environment: "gamma", Platform: "service", DeviceClass: "runner",
		Provider: "provider-stable", DigestBinding: ast.ReadinessDigestCandidate,
	}
	catalog := &ast.Catalog{
		ReadinessCases: []ast.ReadinessCaseContract{
			{
				ObjectID: "user.account_session", CaseID: "z-case",
				SpecRef:  "specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001",
				Producer: ast.ReadinessProducerOps,
				Layer:    ast.ReadinessLayerEnvironmentAcceptance,
				Target: ast.ReadinessCaseTarget{
					Kind: ast.ReadinessTargetObject, ID: "user.account_session",
				},
				RunnerSourcePath: "quwoquan_ops/tests/acceptance/environment_acceptance/user/account/account_session/readiness_case_test.py",
				Executions:       []ast.ReadinessExecutionRequirement{firstExecution, secondExecution},
				SourcePath:       "account/account_session/operations.yaml",
			},
			{
				ObjectID: "assistant.assistant_run", CaseID: "a-case",
				SpecRef:  "specs/feature-tree/assistant-run-learning/spec.md#dom-001",
				Producer: ast.ReadinessProducerService,
				Layer:    ast.ReadinessLayerLocalContract,
				Target: ast.ReadinessCaseTarget{
					Kind: ast.ReadinessTargetOperation,
					ID:   "assistant.assistant_run.StartAssistantRun",
				},
				RunnerSourcePath: "quwoquan_service/services/assistant-service/tests/local_contract/assistant/assistant_run/readiness_case_test.go",
				Executions:       []ast.ReadinessExecutionRequirement{secondExecution},
				SourcePath:       "assistant/assistant_run/operations.yaml",
			},
		},
	}

	contractGraph := graph.Build(catalog)
	if len(contractGraph.ReadinessCases) != 2 ||
		contractGraph.ReadinessCases[0].ObjectID != "assistant.assistant_run" {
		t.Fatalf("readinessCases=%+v, want canonical object/case order", contractGraph.ReadinessCases)
	}
	gotExecutions := contractGraph.ReadinessCases[1].Executions
	if len(gotExecutions) != 2 || gotExecutions[0].Environment != "gamma" ||
		gotExecutions[1].Environment != "prod" {
		t.Fatalf("executions=%+v, want deterministic execution order", gotExecutions)
	}
	if catalog.ReadinessCases[0].Executions[0].Environment != "prod" {
		t.Fatal("graph.Build mutated the loader AST execution order")
	}
	if contractGraph.Coverage().ReadinessCases != 2 {
		t.Fatalf("coverage=%+v, want two readiness cases", contractGraph.Coverage())
	}
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("validate ContractGraph schema: %v", err)
	}
}
