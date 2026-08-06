package readiness

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

const (
	testObjectID    = "assistant.assistant_run"
	testOperationID = "assistant.assistant_run.ApproveAssistantToolUse"
	testSpecRef     = "specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003"
)

var (
	testCommit    = strings.Repeat("a", 40)
	testConfig    = "sha256:" + strings.Repeat("c", 64)
	testCandidate = "sha256:" + strings.Repeat("d", 64)
	testRelease   = "sha256:" + strings.Repeat("e", 64)
	testStart     = time.Date(2026, 8, 5, 1, 0, 0, 0, time.UTC)
)

type memoryReceiptResolver map[string][]byte

type fixedSnapshotProvider struct {
	value EvaluationContext
}

func (provider fixedSnapshotProvider) CurrentSnapshot(
	_ context.Context,
	_ *graph.ContractGraph,
) (EvaluationContext, error) {
	return provider.value, nil
}

// Evaluate keeps the table tests compact while exercising the production
// Evaluator API whose only per-run inputs are current graph + current bundle.
func Evaluate(
	ctx context.Context,
	current *graph.ContractGraph,
	bundle ReadinessResultBundle,
	caseContracts []ReadinessCaseContract,
	evaluation EvaluationContext,
	receipts ReceiptResolver,
) ClosureResult {
	current.ReadinessCases = make([]ast.ReadinessCaseContract, len(caseContracts))
	for index, contract := range caseContracts {
		if contract.Producer == "" {
			contract.Producer = testProducerForLayer(contract.Layer)
		}
		if contract.SourcePath == "" {
			contract.SourcePath = "assistant/assistant_run/operations.yaml"
		}
		if contract.RunnerSourcePath == "" {
			contract.RunnerSourcePath = testRunnerSourcePath(contract)
		}
		current.ReadinessCases[index] = contract
		current.ReadinessCases[index].Executions = append(
			[]ast.ReadinessExecutionRequirement(nil), contract.Executions...,
		)
	}
	return NewEvaluator(
		fixedSnapshotProvider{value: evaluation}, receipts,
	).Evaluate(ctx, current, bundle)
}

func (resolver memoryReceiptResolver) Resolve(
	_ context.Context,
	result ReadinessCaseResult,
) (ResolvedReceipt, error) {
	return ResolvedReceipt{
		Bytes: resolver[result.ReceiptRef], Binding: receiptBindingForResult(result), Trusted: true,
	}, nil
}

func TestEvaluateRequiresTheExactDynamicCaseMatrixForCommercialClosure(t *testing.T) {
	contracts := completeCaseContracts()
	resolver := memoryReceiptResolver{}
	results := make([]ReadinessCaseResult, 0)
	for _, contract := range contracts {
		for index, execution := range contract.Executions {
			ref := contract.CaseID + "-" + execution.Environment + "-" + string(rune('a'+index))
			bytes := []byte("receipt:" + ref)
			resolver[ref] = bytes
			results = append(results, resultFor(contract, execution, ref, bytes))
		}
	}
	closure := Evaluate(
		context.Background(), implementedGraph(true),
		ReadinessResultBundle{
			GeneratedAt: testStart.Add(time.Hour),
			Results:     results,
		},
		contracts,
		testEvaluationContext(),
		resolver,
	)
	if !closure.CommercialReady || len(closure.Violations) != 0 {
		t.Fatalf("closure=%+v, want commercial-ready with no violations", closure)
	}
	if len(closure.Objects) != 1 || !closure.Objects[0].CommercialReady {
		t.Fatalf("object closure=%+v, want ready", closure.Objects)
	}
}

func TestValidProducerRunnerSourcePathAcceptsCanonicalServiceTestLanguages(t *testing.T) {
	const contractSource = "recommendation/recommendation_model_release/operations.yaml"
	for _, path := range []string{
		"quwoquan_service/services/recommendation-service/tests/local_contract/recommendation/recommendation_model_release/model_release__local_contract_test.go",
		"quwoquan_service/services/recommendation-service/tests/api_integration/recommendation/recommendation_model_release/test_model_release__api_integration_test.py",
	} {
		layer := LayerLocalContract
		if strings.Contains(path, "/api_integration/") {
			layer = LayerAPIIntegration
		}
		if !validProducerRunnerSourcePath(
			path, "recommendation.recommendation_model_release", contractSource,
			ProducerService, layer,
		) {
			t.Fatalf("canonical Service runner rejected: %s", path)
		}
	}
	if validProducerRunnerSourcePath(
		"quwoquan_service/services/recommendation-service/tests/api_integration/recommendation/recommendation_model_release/model_release.py",
		"recommendation.recommendation_model_release", contractSource,
		ProducerService, LayerAPIIntegration,
	) {
		t.Fatal("non-test Python source accepted as a Service runner")
	}
}

func TestValidProducerRunnerSourcePathUsesAppServiceTree(t *testing.T) {
	const contractSource = "assistant/assistant_run/operations.yaml"
	const objectID = "assistant.assistant_run"
	for _, testCase := range []struct {
		path  string
		layer Layer
	}{
		{
			path:  "quwoquan_app/test/local_contract/service/assistant_service/assistant/assistant_run/assistant_run__local_contract_test.dart",
			layer: LayerLocalContract,
		},
		{
			path:  "quwoquan_app/test/api_integration/service/assistant_service/assistant/assistant_run/assistant_run__api_integration_test.dart",
			layer: LayerAPIIntegration,
		},
		{
			path:  "quwoquan_app/test/user_acceptance/service/assistant_service/assistant/assistant_run/assistant_run__user_acceptance_test.dart",
			layer: LayerUserAcceptance,
		},
	} {
		if !validProducerRunnerSourcePath(
			testCase.path, objectID, contractSource, ProducerApp, testCase.layer,
		) {
			t.Fatalf("canonical App service-tree runner rejected: %s", testCase.path)
		}
	}
	if validProducerRunnerSourcePath(
		"quwoquan_app/test/local_contract/service/assistant_service/assistant/assistant_run/assistant_run__local_contract_test.dart",
		objectID, contractSource, ProducerApp, LayerLocalContract,
	) {
		t.Fatal("retired domain-shaped App runner path was accepted")
	}
}

func TestEvaluateFailsClosedWhenCanonicalResponsibilityMatrixIsIncomplete(t *testing.T) {
	tests := map[string]struct {
		mutate func([]ReadinessCaseContract) []ReadinessCaseContract
		code   string
	}{
		"operation local": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				return append([]ReadinessCaseContract(nil), values[1:]...)
			},
			code: "READINESS.CASE_POLICY.SERVICE_LOCAL_CONTRACT_MISSING",
		},
		"operation api": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				return append(values[:1:1], values[2:]...)
			},
			code: "READINESS.CASE_POLICY.SERVICE_API_INTEGRATION_MISSING",
		},
		"physical ios uat": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				values[2].Executions = values[2].Executions[:1]
				return values
			},
			code: "READINESS.CASE_POLICY.PHYSICAL_UAT_MISSING",
		},
		"four environments": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				values[3].Executions = append(values[3].Executions[:1:1], values[3].Executions[2:]...)
				return values
			},
			code: "READINESS.CASE_POLICY.ENVIRONMENT_MISSING",
		},
		"prod rollback": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				values[4].Executions = values[4].Executions[:1]
				return values
			},
			code: "READINESS.CASE_POLICY.ROLLBACK_MISSING",
		},
		"gamma replay": {
			mutate: func(values []ReadinessCaseContract) []ReadinessCaseContract {
				values[5].Executions = values[5].Executions[1:]
				return values
			},
			code: "READINESS.CASE_POLICY.REPLAY_MISSING",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			contracts := test.mutate(completeCaseContracts())
			resolver := memoryReceiptResolver{}
			var results []ReadinessCaseResult
			for _, contract := range contracts {
				for index, execution := range contract.Executions {
					ref := contract.CaseID + execution.Environment + string(rune('a'+index))
					bytes := []byte("receipt:" + ref)
					resolver[ref] = bytes
					results = append(results, resultFor(contract, execution, ref, bytes))
				}
			}
			closure := Evaluate(
				context.Background(), implementedGraph(true),
				ReadinessResultBundle{GeneratedAt: testStart, Results: results},
				contracts, testEvaluationContext(), resolver,
			)
			requireViolation(t, closure, test.code)
		})
	}
}

func TestEvaluateSeparatesServiceAndAppOperationResponsibilities(t *testing.T) {
	current := implementedGraph(true)
	current.Operations[0].ClientContract = &ast.ClientContract{}
	contracts := completeCaseContracts()
	resolver := memoryReceiptResolver{}
	results := resultsForContracts(contracts, resolver)
	closure := Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: results},
		contracts, testEvaluationContext(), resolver,
	)
	requireViolation(t, closure, "READINESS.CASE_POLICY.APP_LOCAL_CONTRACT_MISSING")
	requireViolation(t, closure, "READINESS.CASE_POLICY.APP_API_INTEGRATION_MISSING")

	operation := ReadinessTarget{Kind: TargetOperation, ID: testOperationID}
	contracts = append(contracts,
		ReadinessCaseContract{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "app-local-contract",
			Producer: ProducerApp, Layer: LayerLocalContract, Target: operation,
			Executions: []ExecutionRequirement{
				candidateExecution("alpha", "android", "physical", "provider-stable"),
			},
		},
		ReadinessCaseContract{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "app-api-integration",
			Producer: ProducerApp, Layer: LayerAPIIntegration, Target: operation,
			Executions: []ExecutionRequirement{
				candidateExecution("beta", "android", "physical", "provider-stable"),
			},
		},
	)
	resolver = memoryReceiptResolver{}
	results = resultsForContracts(contracts, resolver)
	closure = Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: results},
		contracts, testEvaluationContext(), resolver,
	)
	if hasViolation(closure, "READINESS.CASE_POLICY.APP_LOCAL_CONTRACT_MISSING") ||
		hasViolation(closure, "READINESS.CASE_POLICY.APP_API_INTEGRATION_MISSING") {
		t.Fatalf("violations=%+v, explicit App cases must close only the App responsibility", closure.Violations)
	}
}

func TestEvaluateRequiresObjectTargetedLifecycleConsumerRunners(t *testing.T) {
	current := implementedGraph(true)
	current.Objects[0].Lifecycle = &ast.LifecycleDefinition{
		SourceEvents: []string{"assistant.assistant_run.AssistantRunCompleted"},
		EventConsumers: []ast.LifecycleEventConsumer{{
			Name: "CompactAssistantRun", Kind: "event_handler",
			Facet: "AssistantRunCompactionHandler", Method: "apply", Idempotency: "event_id",
		}},
	}
	object := ReadinessTarget{Kind: TargetObject, ID: testObjectID}
	contracts := append(completeCaseContracts(),
		ReadinessCaseContract{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "lifecycle-local",
			Producer: ProducerService, Layer: LayerLocalContract, Target: object,
			Executions: []ExecutionRequirement{
				candidateExecution("alpha", "service", "runner", "none"),
			},
		},
		ReadinessCaseContract{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "lifecycle-api",
			Producer: ProducerService, Layer: LayerAPIIntegration, Target: object,
			Executions: []ExecutionRequirement{
				candidateExecution("beta", "service", "runner", "provider-stable"),
			},
		},
	)
	resolver := memoryReceiptResolver{}
	results := resultsForContracts(contracts, resolver)
	closure := Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: results},
		contracts, testEvaluationContext(), resolver,
	)
	if !closure.CommercialReady || len(closure.Violations) != 0 {
		t.Fatalf("lifecycle closure=%+v, want commercial-ready", closure)
	}

	contracts = append(contracts[:len(contracts)-2], contracts[len(contracts)-1])
	resolver = memoryReceiptResolver{}
	closure = Evaluate(
		context.Background(), current,
		ReadinessResultBundle{
			GeneratedAt: testStart,
			Results:     resultsForContracts(contracts, resolver),
		},
		contracts, testEvaluationContext(), resolver,
	)
	requireViolation(t, closure, "READINESS.CASE_POLICY.LIFECYCLE_LOCAL_CONTRACT_MISSING")
}

func TestEvaluateRejectsProducerSubstitutionAndWrongRunnerRoot(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")

	t.Run("result producer cannot substitute", func(t *testing.T) {
		result := resultFor(contract, execution, "receipt", bytes)
		result.Producer = ProducerApp
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.RESULT.UNKNOWN_CASE")
	})

	t.Run("producer layer mismatch", func(t *testing.T) {
		invalid := contract
		invalid.Producer = ProducerOps
		result := resultFor(invalid, execution, "receipt", bytes)
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{invalid}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.CASE_CONTRACT.INVALID")
		requireViolation(t, closure, "READINESS.RESULT.INVALID_ENUM")
	})

	t.Run("service result must attest service test tree", func(t *testing.T) {
		result := resultFor(contract, execution, "receipt", bytes)
		resolver := receiptResolverFunc(func(
			_ context.Context,
			result ReadinessCaseResult,
		) (ResolvedReceipt, error) {
			binding := receiptBindingForResult(result)
			binding.RunnerSourcePath = "quwoquan_app/test/local_contract/service/assistant_service/assistant/assistant_run/case.dart"
			return ResolvedReceipt{Bytes: bytes, Binding: binding, Trusted: true}, nil
		})
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(), resolver,
		)
		requireViolation(t, closure, "READINESS.RESULT.RUNNER_SOURCE_INVALID")
	})

	t.Run("same tree different runner cannot substitute authored case", func(t *testing.T) {
		contract.RunnerSourcePath = testRunnerSourcePath(contract)
		result := resultFor(contract, execution, "receipt", bytes)
		resolver := receiptResolverFunc(func(
			_ context.Context,
			result ReadinessCaseResult,
		) (ResolvedReceipt, error) {
			binding := receiptBindingForResult(result)
			binding.RunnerSourcePath = "quwoquan_service/services/assistant-service/tests/local_contract/assistant/assistant_run/different__local_contract_test.go"
			return ResolvedReceipt{Bytes: bytes, Binding: binding, Trusted: true}, nil
		})
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(), resolver,
		)
		requireViolation(t, closure, "READINESS.RESULT.RUNNER_SOURCE_INVALID")
	})
}

func TestEvaluateRejectsEveryNonPassedStatus(t *testing.T) {
	for _, status := range []Status{StatusFailed, StatusBlocked, StatusSkipped} {
		t.Run(string(status), func(t *testing.T) {
			contract := completeCaseContracts()[0]
			execution := contract.Executions[0]
			bytes := []byte("receipt")
			result := resultFor(contract, execution, "receipt", bytes)
			result.Status = status
			closure := Evaluate(
				context.Background(), implementedGraph(true),
				ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
				[]ReadinessCaseContract{contract}, testEvaluationContext(),
				memoryReceiptResolver{"receipt": bytes},
			)
			requireViolation(t, closure, "READINESS.RESULT.NOT_PASSED")
		})
	}
}

func TestEvaluateRequiresBundleIdentityAndNonSecretExecutionIdentity(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)
	result.Provider = "https://provider.example"

	closure := Evaluate(
		context.Background(), implementedGraph(true),
		ReadinessResultBundle{Results: []ReadinessCaseResult{result}},
		[]ReadinessCaseContract{contract}, testEvaluationContext(),
		memoryReceiptResolver{"receipt": bytes},
	)
	requireViolation(t, closure, "READINESS.BUNDLE.GENERATED_AT_MISSING")
	requireViolation(t, closure, "READINESS.RESULT.EXECUTION_IDENTITY_INVALID")
}

func TestEvaluateRejectsTraversalShapedReceiptReferences(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	for name, mutate := range map[string]func(*ReadinessCaseResult){
		"opaque reference traversal": func(result *ReadinessCaseResult) {
			result.ReceiptRef = "receipts/../secret"
		},
		"artifact path traversal": func(result *ReadinessCaseResult) {
			result.ReceiptRef = ""
			result.ArtifactPath = "receipts/../secret"
		},
	} {
		t.Run(name, func(t *testing.T) {
			result := resultFor(contract, execution, "receipt", bytes)
			mutate(&result)
			closure := Evaluate(
				context.Background(), implementedGraph(true),
				ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
				[]ReadinessCaseContract{contract}, testEvaluationContext(),
				memoryReceiptResolver{"receipt": bytes},
			)
			requireViolation(t, closure, "READINESS.RESULT.RECEIPT_REFERENCE_INVALID")
		})
	}
}

func TestEvaluateRejectsStaleImmutableBindings(t *testing.T) {
	mutations := map[string]func(*ReadinessCaseResult){
		"commit": func(result *ReadinessCaseResult) {
			result.CommitSHA = strings.Repeat("f", 40)
		},
		"graph": func(result *ReadinessCaseResult) {
			result.ContractGraphSourceHash = strings.Repeat("f", 64)
		},
		"config": func(result *ReadinessCaseResult) {
			result.ConfigurationDigest = "sha256:" + strings.Repeat("f", 64)
		},
		"deployment target": func(result *ReadinessCaseResult) {
			result.DeploymentTarget = "assistant-stale"
		},
		"baseline": func(result *ReadinessCaseResult) {
			result.BaselineID = "baseline-stale"
		},
		"package": func(result *ReadinessCaseResult) {
			result.PackageDigest = "sha256:" + strings.Repeat("e", 64)
		},
		"candidate manifest": func(result *ReadinessCaseResult) {
			result.CandidateManifestSHA256 = strings.Repeat("d", 64)
		},
		"candidate": func(result *ReadinessCaseResult) {
			result.CandidateDigest = "sha256:" + strings.Repeat("f", 64)
		},
		"release": func(result *ReadinessCaseResult) {
			result.ReleaseDigest = "sha256:" + strings.Repeat("f", 64)
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			contract := ReadinessCaseContract{
				ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "prod-case",
				Layer:  LayerEnvironmentAcceptance,
				Target: ReadinessTarget{Kind: TargetObject, ID: testObjectID},
				Executions: []ExecutionRequirement{{
					Environment: "prod", Platform: "service", DeviceClass: "runner",
					Provider: "provider-stable", DigestBinding: DigestRelease,
				}},
			}
			bytes := []byte("receipt")
			result := resultFor(contract, contract.Executions[0], "receipt", bytes)
			mutate(&result)
			closure := Evaluate(
				context.Background(), implementedGraph(true),
				ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
				[]ReadinessCaseContract{contract}, testEvaluationContext(),
				memoryReceiptResolver{"receipt": bytes},
			)
			if closure.CommercialReady || len(closure.Violations) == 0 {
				t.Fatalf("closure=%+v, want stale binding failure", closure)
			}
		})
	}
}

func TestEvaluateRejectsHashThatDoesNotIdentifyCurrentGraphSources(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)
	current := implementedGraph(true)
	current.Sources[0].SHA256 = strings.Repeat("f", 64)

	closure := Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
		[]ReadinessCaseContract{contract}, testEvaluationContext(),
		memoryReceiptResolver{"receipt": bytes},
	)
	requireViolation(t, closure, "READINESS.RESULT.STALE_IDENTITY")
}

func TestEvaluateFailsClosedForTargetDuplicateAndReceiptDigest(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	baseline := resultFor(contract, execution, "receipt", bytes)

	t.Run("target mismatch", func(t *testing.T) {
		result := baseline
		result.Target.ID = "assistant.unknown.Operation"
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.RESULT.UNKNOWN_CASE")
	})

	t.Run("duplicate", func(t *testing.T) {
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{baseline, baseline}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.RESULT.DUPLICATE")
	})

	t.Run("artifact digest", func(t *testing.T) {
		result := baseline
		result.ArtifactSHA256 = strings.Repeat("f", 64)
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.RESULT.ARTIFACT_DIGEST_MISMATCH")
	})

	t.Run("receipt identity", func(t *testing.T) {
		resolver := receiptResolverFunc(func(
			_ context.Context,
			result ReadinessCaseResult,
		) (ResolvedReceipt, error) {
			binding := receiptBindingForResult(result)
			binding.Provider = "provider-other"
			return ResolvedReceipt{Bytes: bytes, Binding: binding, Trusted: true}, nil
		})
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{baseline}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(), resolver,
		)
		requireViolation(t, closure, "READINESS.RESULT.RECEIPT_IDENTITY_MISMATCH")
	})

	t.Run("empty receipt", func(t *testing.T) {
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{baseline}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": nil},
		)
		requireViolation(t, closure, "READINESS.RESULT.RECEIPT_EMPTY")
	})
}

type receiptResolverFunc func(context.Context, ReadinessCaseResult) (ResolvedReceipt, error)

func (resolve receiptResolverFunc) Resolve(
	ctx context.Context,
	result ReadinessCaseResult,
) (ResolvedReceipt, error) {
	return resolve(ctx, result)
}

type receiptVerifierFunc func(context.Context, ReadinessCaseResult, ResolvedReceipt) error

func (verify receiptVerifierFunc) Verify(
	ctx context.Context,
	result ReadinessCaseResult,
	receipt ResolvedReceipt,
) error {
	return verify(ctx, result, receipt)
}

func TestVerifiedReceiptResolverSeparatesBytesFromAttestationAuthority(t *testing.T) {
	contract := completeCaseContracts()[0]
	result := resultFor(contract, contract.Executions[0], "receipt", []byte("receipt"))
	verified := false
	resolver := VerifiedReceiptResolver{
		Source: receiptResolverFunc(func(
			_ context.Context,
			result ReadinessCaseResult,
		) (ResolvedReceipt, error) {
			return ResolvedReceipt{
				Bytes: []byte("receipt"), Binding: receiptBindingForResult(result), Trusted: true,
			}, nil
		}),
		Verifier: receiptVerifierFunc(func(
			_ context.Context,
			_ ReadinessCaseResult,
			receipt ResolvedReceipt,
		) error {
			if receipt.Trusted {
				t.Fatal("source resolver self-promoted before independent verification")
			}
			verified = true
			return nil
		}),
	}
	receipt, err := resolver.Resolve(context.Background(), result)
	if err != nil || !verified || !receipt.Trusted {
		t.Fatalf("receipt=%+v verified=%v err=%v", receipt, verified, err)
	}
}

func TestEvaluateRejectsUnknownOrUnrelatedCanonicalPageTarget(t *testing.T) {
	contract := completeCaseContracts()[2]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)
	current := implementedGraph(true)
	current.Documents[0].Content = json.RawMessage(`{"pages":[{"page_id":"assistant.personal_session","object_ids":[]}]}`)

	closure := Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
		[]ReadinessCaseContract{contract}, testEvaluationContext(),
		memoryReceiptResolver{"receipt": bytes},
	)
	requireViolation(t, closure, "READINESS.CASE_CONTRACT.TARGET_MISMATCH")
}

func TestEvaluateDistinguishesPageParticipantFromPhysicalOwner(t *testing.T) {
	contract := completeCaseContracts()[2]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)

	t.Run("physical owner without participant is valid", func(t *testing.T) {
		current := implementedGraph(true)
		current.Documents[0].Content = json.RawMessage(`{
          "pages":[{
            "page_id":"assistant.personal_session",
            "source_path":"lib/service/assistant_service/assistant/assistant_run/presentation/session_page.dart",
            "object_ids":[]
          }]
        }`)
		closure := Evaluate(
			context.Background(), current,
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		if hasViolation(closure, "READINESS.CASE_CONTRACT.TARGET_MISMATCH") {
			t.Fatalf("violations=%+v, physical owner must be a valid page target", closure.Violations)
		}
	})

	t.Run("shell page cannot invent an object owner", func(t *testing.T) {
		current := implementedGraph(true)
		current.Documents[0].Content = json.RawMessage(`{
          "pages":[{
            "page_id":"assistant.personal_session",
            "source_path":"lib/runtime/shell/session_page.dart",
            "object_ids":[]
          }]
        }`)
		closure := Evaluate(
			context.Background(), current,
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		requireViolation(t, closure, "READINESS.CASE_CONTRACT.TARGET_MISMATCH")
	})
}

func TestEvaluateRequiresTrustedReceiptAndRealUserAcceptanceProvenance(t *testing.T) {
	contract := completeCaseContracts()[2]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)

	t.Run("untrusted local manifest", func(t *testing.T) {
		resolver := receiptResolverFunc(func(
			_ context.Context,
			result ReadinessCaseResult,
		) (ResolvedReceipt, error) {
			return ResolvedReceipt{Bytes: bytes, Binding: receiptBindingForResult(result)}, nil
		})
		closure := Evaluate(
			context.Background(), implementedGraph(true),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(), resolver,
		)
		requireViolation(t, closure, "READINESS.RESULT.RECEIPT_UNTRUSTED")
	})

	for name, mutate := range map[string]struct {
		mutate func(*ReceiptBinding)
		code   string
	}{
		"runner path": {
			mutate: func(binding *ReceiptBinding) { binding.RunnerSourcePath = "quwoquan_app/test/patrol/case.dart" },
			code:   "READINESS.RESULT.UAT_RUNNER_SOURCE_INVALID",
		},
		"remote composition": {
			mutate: func(binding *ReceiptBinding) { binding.RemoteComposition = false },
			code:   "READINESS.RESULT.UAT_REMOTE_COMPOSITION_REQUIRED",
		},
		"fixture": {
			mutate: func(binding *ReceiptBinding) { binding.FixtureFree = false },
			code:   "READINESS.RESULT.UAT_FIXTURE_FORBIDDEN",
		},
		"dependency": {
			mutate: func(binding *ReceiptBinding) { binding.DependenciesReady = false },
			code:   "READINESS.RESULT.UAT_DEPENDENCY_NOT_READY",
		},
		"provider not verified": {
			mutate: func(binding *ReceiptBinding) { binding.ProviderVerified = false },
			code:   "READINESS.RESULT.PROVIDER_UNVERIFIED",
		},
		"device not physically attested": {
			mutate: func(binding *ReceiptBinding) { binding.PhysicalDevice = false },
			code:   "READINESS.RESULT.PHYSICAL_DEVICE_REQUIRED",
		},
	} {
		t.Run(name, func(t *testing.T) {
			resolver := receiptResolverFunc(func(
				_ context.Context,
				result ReadinessCaseResult,
			) (ResolvedReceipt, error) {
				binding := receiptBindingForResult(result)
				mutate.mutate(&binding)
				return ResolvedReceipt{Bytes: bytes, Binding: binding, Trusted: true}, nil
			})
			closure := Evaluate(
				context.Background(), implementedGraph(true),
				ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
				[]ReadinessCaseContract{contract}, testEvaluationContext(), resolver,
			)
			requireViolation(t, closure, mutate.code)
		})
	}
}

func TestEvaluatorAcceptsCasePolicyOnlyFromCurrentContractGraph(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)
	current := implementedGraph(true)
	closure := NewEvaluator(
		fixedSnapshotProvider{value: testEvaluationContext()},
		memoryReceiptResolver{"receipt": bytes},
	).Evaluate(
		context.Background(), current,
		ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
	)
	requireViolation(t, closure, "READINESS.RESULT.UNKNOWN_CASE")
}

func TestEvaluateRejectsCaseSourceOutsideCurrentGraph(t *testing.T) {
	contract := completeCaseContracts()[0]
	contract.SourcePath = "assistant/assistant_run/other.yaml"
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)
	closure := Evaluate(
		context.Background(), implementedGraph(true),
		ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
		[]ReadinessCaseContract{contract}, testEvaluationContext(),
		memoryReceiptResolver{"receipt": bytes},
	)
	requireViolation(t, closure, "READINESS.CASE_CONTRACT.UNKNOWN_SOURCE")
}

func TestEvaluateRequiresImplementedAndCommercialOperationPolicy(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	result := resultFor(contract, execution, "receipt", bytes)

	t.Run("not implemented", func(t *testing.T) {
		closure := Evaluate(
			context.Background(), implementedGraph(false),
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		if closure.Objects[0].CommercialReady || !contains(closure.Objects[0].Missing, "commercial.implemented") {
			t.Fatalf("object=%+v, want implemented blocker", closure.Objects[0])
		}
	})

	t.Run("operation blocked", func(t *testing.T) {
		current := implementedGraph(true)
		current.Operations[0].Commercial.Status = "blocked"
		closure := Evaluate(
			context.Background(), current,
			ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}},
			[]ReadinessCaseContract{contract}, testEvaluationContext(),
			memoryReceiptResolver{"receipt": bytes},
		)
		if closure.Objects[0].CommercialReady ||
			!contains(closure.Objects[0].Missing, "commercial.operation.ApproveAssistantToolUse") {
			t.Fatalf("object=%+v, want operation blocker", closure.Objects[0])
		}
	})
}

func completeCaseContracts() []ReadinessCaseContract {
	operation := ReadinessTarget{Kind: TargetOperation, ID: testOperationID}
	page := ReadinessTarget{Kind: TargetPage, ID: "assistant.personal_session"}
	object := ReadinessTarget{Kind: TargetObject, ID: testObjectID}
	return []ReadinessCaseContract{
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "local-contract",
			Producer: ProducerService, Layer: LayerLocalContract, Target: operation,
			Executions: []ExecutionRequirement{candidateExecution("alpha", "service", "runner", "none")},
		},
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "api-integration",
			Producer: ProducerService, Layer: LayerAPIIntegration, Target: operation,
			Executions: []ExecutionRequirement{candidateExecution("beta", "service", "runner", "provider-stable")},
		},
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "device-uat",
			Producer: ProducerApp, Layer: LayerUserAcceptance, Target: page,
			Executions: []ExecutionRequirement{
				candidateExecution("gamma", "android", "physical", "provider-stable"),
				candidateExecution("gamma", "ios", "physical", "provider-stable"),
			},
		},
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "four-environment",
			Producer: ProducerOps, Layer: LayerEnvironmentAcceptance, Target: object,
			Executions: []ExecutionRequirement{
				candidateExecution("alpha", "service", "runner", "provider-stable"),
				candidateExecution("beta", "service", "runner", "provider-stable"),
				candidateExecution("gamma", "service", "runner", "provider-stable"),
				{
					Environment: "prod", Platform: "service", DeviceClass: "runner",
					Provider: "provider-stable", DigestBinding: DigestRelease,
				},
			},
		},
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "rollback",
			Producer: ProducerOps, Layer: LayerRollback, Target: object,
			Executions: []ExecutionRequirement{
				candidateExecution("gamma", "service", "runner", "provider-stable"),
				{
					Environment: "prod", Platform: "service", DeviceClass: "runner",
					Provider: "provider-stable", DigestBinding: DigestRelease,
				},
			},
		},
		{
			ObjectID: testObjectID, SpecRef: testSpecRef, CaseID: "replay",
			Producer: ProducerOps, Layer: LayerReplay, Target: object,
			Executions: []ExecutionRequirement{
				candidateExecution("gamma", "service", "runner", "provider-stable"),
				{
					Environment: "prod", Platform: "service", DeviceClass: "runner",
					Provider: "provider-stable", DigestBinding: DigestRelease,
				},
			},
		},
	}
}

func candidateExecution(environment, platform, device, provider string) ExecutionRequirement {
	return ExecutionRequirement{
		Environment: environment, Platform: platform, DeviceClass: device,
		Provider: provider, DigestBinding: DigestCandidate,
	}
}

func resultsForContracts(
	contracts []ReadinessCaseContract,
	resolver memoryReceiptResolver,
) []ReadinessCaseResult {
	results := make([]ReadinessCaseResult, 0)
	for _, contract := range contracts {
		for index, execution := range contract.Executions {
			ref := contract.CaseID + "-" + execution.Environment + "-" + string(rune('a'+index))
			bytes := []byte("receipt:" + ref)
			resolver[ref] = bytes
			results = append(results, resultFor(contract, execution, ref, bytes))
		}
	}
	return results
}

func resultFor(
	contract ReadinessCaseContract,
	execution ExecutionRequirement,
	receiptRef string,
	receipt []byte,
) ReadinessCaseResult {
	if contract.Producer == "" {
		contract.Producer = testProducerForLayer(contract.Layer)
	}
	digest := sha256.Sum256(receipt)
	graphHash, err := ContractGraphSourceHash(implementedGraph(true))
	if err != nil {
		panic(err)
	}
	result := ReadinessCaseResult{
		ObjectID: contract.ObjectID, SpecRef: contract.SpecRef, CaseID: contract.CaseID,
		Producer: contract.Producer, Layer: contract.Layer,
		Status: StatusPassed, Target: contract.Target,
		CommitSHA: testCommit, ContractGraphSourceHash: graphHash,
		DeploymentTarget:        testDeployment(execution.Environment).DeploymentTarget,
		BaselineID:              testDeployment(execution.Environment).BaselineID,
		PackageDigest:           testDeployment(execution.Environment).PackageDigest,
		ConfigurationDigest:     testDeployment(execution.Environment).ConfigurationDigest,
		CandidateManifestSHA256: testDeployment(execution.Environment).CandidateManifestSHA256,
		CandidateDigest:         testCandidate,
		Environment:             execution.Environment, Platform: execution.Platform,
		DeviceClass: execution.DeviceClass, Provider: execution.Provider,
		StartedAt: testStart, CompletedAt: testStart.Add(time.Minute),
		RunnerIdentity: "runner/stable", ArtifactSHA256: hex.EncodeToString(digest[:]),
		ReceiptRef: receiptRef,
	}
	if execution.DigestBinding == DigestRelease {
		result.ReleaseDigest = testRelease
	}
	return result
}

func testProducerForLayer(layer Layer) Producer {
	switch layer {
	case LayerLocalContract, LayerAPIIntegration:
		return ProducerService
	case LayerUserAcceptance:
		return ProducerApp
	case LayerEnvironmentAcceptance, LayerRollback, LayerReplay:
		return ProducerOps
	default:
		return ""
	}
}

func testRunnerSourcePath(contract ReadinessCaseContract) string {
	return receiptBindingForResult(ReadinessCaseResult{
		ObjectID: contract.ObjectID,
		Producer: contract.Producer,
		Layer:    contract.Layer,
	}).RunnerSourcePath
}

func implementedGraph(implemented bool) *graph.ContractGraph {
	return &graph.ContractGraph{
		Objects: []ast.Object{{ID: testObjectID, Domain: "assistant", Name: "assistant_run"}},
		Sources: []ast.SourceDigest{{
			Path: "assistant/assistant_run/operations.yaml", SHA256: strings.Repeat("b", 64),
		}, {
			Path: "_shared/page_object_contract.yaml", SHA256: strings.Repeat("8", 64),
		}},
		Documents: []ast.SourceDocument{{
			Path: "_shared/page_object_contract.yaml", MediaType: "application/yaml",
			SHA256:  strings.Repeat("8", 64),
			Content: json.RawMessage(`{"pages":[{"page_id":"assistant.personal_session","source_path":"lib/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart","object_ids":["assistant.assistant_run"]}]}`),
		}},
		Operations: []ast.Operation{{
			ID: testOperationID, LocalID: "ApproveAssistantToolUse", ObjectID: testObjectID,
			Commercial: ast.CommercialBinding{Status: "ready"},
		}},
		ObjectReadiness: []graph.ObjectReadiness{{
			ObjectID: testObjectID, Implemented: implemented, CommercialReady: false,
		}},
	}
}

func testEvaluationContext() EvaluationContext {
	return EvaluationContext{
		CommitSHA: testCommit,
		Deployments: map[string]DeploymentBinding{
			"alpha": testDeployment("alpha"), "beta": testDeployment("beta"),
			"gamma": testDeployment("gamma"), "prod": testDeployment("prod"),
		},
		CandidateDigest: testCandidate,
		ReleaseDigest:   testRelease,
	}
}

func testDeployment(environment string) DeploymentBinding {
	configuration := map[string]string{
		"alpha": testConfig, "beta": "sha256:" + strings.Repeat("1", 64),
		"gamma": "sha256:" + strings.Repeat("2", 64), "prod": "sha256:" + strings.Repeat("3", 64),
	}[environment]
	return DeploymentBinding{
		DeploymentTarget:        "assistant-" + environment,
		BaselineID:              "baseline-2026-08-05",
		PackageDigest:           "sha256:" + strings.Repeat("4", 64),
		ConfigurationDigest:     configuration,
		CandidateManifestSHA256: strings.Repeat("5", 64),
	}
}

func requireViolation(t *testing.T, closure ClosureResult, code string) {
	t.Helper()
	for _, item := range closure.Violations {
		if item.Code == code {
			return
		}
	}
	t.Fatalf("violations=%+v, want %s", closure.Violations, code)
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func hasViolation(closure ClosureResult, code string) bool {
	for _, item := range closure.Violations {
		if item.Code == code {
			return true
		}
	}
	return false
}
