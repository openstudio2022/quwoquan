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
	journeyTestID      = "app_root.safe_entry_recovery"
	journeyTestSpecRef = "specs/feature-tree/spec.md#uat-003"
)

type fixedJourneyAuthority struct {
	catalog JourneyCaseCatalog
	err     error
}

func (authority fixedJourneyAuthority) CurrentJourneyCatalog(
	_ context.Context,
	_ *graph.ContractGraph,
) (JourneyCaseCatalog, error) {
	return authority.catalog, authority.err
}

type memoryJourneyReceiptResolver map[string]ResolvedJourneyReceipt

func (resolver memoryJourneyReceiptResolver) ResolveJourney(
	_ context.Context,
	result JourneyReadinessCaseResult,
) (ResolvedJourneyReceipt, error) {
	return resolver[result.ReceiptRef], nil
}

func TestJourneyEvaluatorClosesOnlyTheFullTrustedRemoteMatrix(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	resolver := memoryJourneyReceiptResolver{}
	results := journeyResults(graphValue, catalog.Cases, resolver)
	closure := journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{
			GeneratedAt: journeyTestStart().Add(time.Hour),
			Results:     results,
		},
	)
	if !closure.CommercialReady || len(closure.Violations) != 0 {
		t.Fatalf("closure=%+v, want Journey commercial-ready", closure)
	}
	if len(closure.Journeys) != 1 || !closure.Journeys[0].CommercialReady {
		t.Fatalf("journeys=%+v, want one ready Journey", closure.Journeys)
	}
	if len(graphValue.ObjectReadiness) != 0 || len(graphValue.ReadinessCases) != 0 {
		t.Fatal("Journey evaluation wrote dynamic history into static ContractGraph")
	}
}

func TestJourneyPolicyRequiresFourEnvironmentsBothPhysicalPlatformsAndRecovery(t *testing.T) {
	tests := map[string]struct {
		mutate func(*JourneyCaseCatalog)
		code   string
	}{
		"prod iphone UAT": {
			mutate: func(catalog *JourneyCaseCatalog) {
				catalog.Cases[0].Executions = catalog.Cases[0].Executions[:7]
			},
			code: "JOURNEY_READINESS.CASE_POLICY.PHYSICAL_UAT_MISSING",
		},
		"alpha environment acceptance": {
			mutate: func(catalog *JourneyCaseCatalog) {
				catalog.Cases[1].Executions = catalog.Cases[1].Executions[1:]
			},
			code: "JOURNEY_READINESS.CASE_POLICY.ENVIRONMENT_ACCEPTANCE_MISSING",
		},
		"alpha rollback": {
			mutate: func(catalog *JourneyCaseCatalog) {
				catalog.Cases[2].Executions = catalog.Cases[2].Executions[1:]
			},
			code: "JOURNEY_READINESS.CASE_POLICY.ROLLBACK_MISSING",
		},
		"alpha replay": {
			mutate: func(catalog *JourneyCaseCatalog) {
				catalog.Cases[3].Executions = catalog.Cases[3].Executions[1:]
			},
			code: "JOURNEY_READINESS.CASE_POLICY.REPLAY_MISSING",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			graphValue := journeyTestGraph()
			catalog := completeJourneyCatalog()
			test.mutate(&catalog)
			resolver := memoryJourneyReceiptResolver{}
			results := journeyResults(graphValue, catalog.Cases, resolver)
			closure := journeyEvaluator(catalog, resolver).Evaluate(
				context.Background(), graphValue,
				JourneyReadinessResultBundle{
					GeneratedAt: journeyTestStart(), Results: results,
				},
			)
			requireJourneyViolation(t, closure, test.code)
			if closure.CommercialReady {
				t.Fatal("incomplete Journey matrix became commercial-ready")
			}
		})
	}
}

func TestJourneyPageTargetUsesCurrentPageIdentityWithoutInventedObject(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	pageCase := JourneyCaseContract{
		JourneyID: journeyTestID, SpecRef: journeyTestSpecRef, CaseID: "root-shell-page",
		Producer: ProducerApp, Layer: LayerUserAcceptance,
		Target:           JourneyTarget{Kind: JourneyTargetPage, ID: "app.startup_recovery"},
		RunnerSourcePath: "quwoquan_app/test/user_acceptance/journeys/" + journeyTestID + "/root_shell_page_test.dart",
		Executions: []ExecutionRequirement{
			journeyExecution("gamma", "android", "physical", DigestCandidate),
		},
	}
	catalog.Cases = append(catalog.Cases, pageCase)
	resolver := memoryJourneyReceiptResolver{}
	results := journeyResults(graphValue, catalog.Cases, resolver)
	closure := journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{
			GeneratedAt: journeyTestStart(), Results: results,
		},
	)
	if !closure.CommercialReady {
		t.Fatalf("root shell page with no object participant must remain a valid explicit Journey target: %+v", closure)
	}

	// A page-targeted result is required when declared, but cannot replace the
	// Journey-targeted Android/iPhone matrix.
	catalog = completeJourneyCatalog()
	catalog.Cases[0].Target = pageCase.Target
	resolver = memoryJourneyReceiptResolver{}
	results = journeyResults(graphValue, catalog.Cases, resolver)
	closure = journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{
			GeneratedAt: journeyTestStart(), Results: results,
		},
	)
	requireJourneyViolation(t, closure, "JOURNEY_READINESS.CASE_POLICY.PHYSICAL_UAT_MISSING")

	catalog = completeJourneyCatalog()
	catalog.Cases[0].Target = JourneyTarget{Kind: JourneyTargetPage, ID: "app.missing"}
	resolver = memoryJourneyReceiptResolver{}
	results = journeyResults(graphValue, catalog.Cases, resolver)
	closure = journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{
			GeneratedAt: journeyTestStart(), Results: results,
		},
	)
	requireJourneyViolation(t, closure, "JOURNEY_READINESS.CASE_CONTRACT.TARGET_MISMATCH")
}

func TestJourneyEvaluatorRejectsFalseGreenAndStaleEvidence(t *testing.T) {
	tests := map[string]struct {
		mutate func([]JourneyReadinessCaseResult, memoryJourneyReceiptResolver)
		code   string
	}{
		"failed": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].Status = StatusFailed
			},
			code: "JOURNEY_READINESS.RESULT.NOT_PASSED",
		},
		"blocked": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].Status = StatusBlocked
			},
			code: "JOURNEY_READINESS.RESULT.NOT_PASSED",
		},
		"skipped": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].Status = StatusSkipped
			},
			code: "JOURNEY_READINESS.RESULT.NOT_PASSED",
		},
		"stale commit": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].CommitSHA = strings.Repeat("9", 40)
			},
			code: "JOURNEY_READINESS.RESULT.STALE_IDENTITY",
		},
		"stale graph": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].ContractGraphSourceHash = strings.Repeat("9", 64)
			},
			code: "JOURNEY_READINESS.RESULT.STALE_IDENTITY",
		},
		"stale configuration": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].ConfigurationDigest = "sha256:" + strings.Repeat("9", 64)
			},
			code: "JOURNEY_READINESS.RESULT.STALE_IDENTITY",
		},
		"stale candidate": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].CandidateDigest = "sha256:" + strings.Repeat("9", 64)
			},
			code: "JOURNEY_READINESS.RESULT.STALE_CANDIDATE",
		},
		"stale release": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[6].ReleaseDigest = "sha256:" + strings.Repeat("9", 64)
			},
			code: "JOURNEY_READINESS.RESULT.STALE_RELEASE",
		},
		"Prod release missing": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[6].ReleaseDigest = ""
			},
			code: "JOURNEY_READINESS.RESULT.RELEASE_REQUIRED",
		},
		"execution mismatch": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].Provider = "provider-other"
			},
			code: "JOURNEY_READINESS.RESULT.EXECUTION_MISMATCH",
		},
		"invalid time": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].CompletedAt = results[0].StartedAt
			},
			code: "JOURNEY_READINESS.RESULT.TIME_INVALID",
		},
		"artifact mismatch": {
			mutate: func(results []JourneyReadinessCaseResult, _ memoryJourneyReceiptResolver) {
				results[0].ArtifactSHA256 = strings.Repeat("9", 64)
			},
			code: "JOURNEY_READINESS.RESULT.ARTIFACT_DIGEST_MISMATCH",
		},
		"receipt untrusted": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				receipt := receipts[results[0].ReceiptRef]
				receipt.Trusted = false
				receipts[results[0].ReceiptRef] = receipt
			},
			code: "JOURNEY_READINESS.RESULT.RECEIPT_UNTRUSTED",
		},
		"receipt identity mismatch": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.Provider = "provider-other"
				})
			},
			code: "JOURNEY_READINESS.RESULT.RECEIPT_IDENTITY_MISMATCH",
		},
		"wrong runner root": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.RunnerSourcePath = "quwoquan_app/test/user_acceptance/runtime_shell_test.dart"
				})
			},
			code: "JOURNEY_READINESS.RESULT.RUNNER_SOURCE_INVALID",
		},
		"different canonical runner": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.RunnerSourcePath = "quwoquan_app/test/user_acceptance/journeys/" + journeyTestID + "/different_test.dart"
				})
			},
			code: "JOURNEY_READINESS.RESULT.RUNNER_SOURCE_INVALID",
		},
		"not Remote": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.RemoteComposition = false
				})
			},
			code: "JOURNEY_READINESS.RESULT.REMOTE_COMPOSITION_REQUIRED",
		},
		"fixture": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.FixtureFree = false
				})
			},
			code: "JOURNEY_READINESS.RESULT.FIXTURE_FORBIDDEN",
		},
		"dependency blocked": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.DependenciesReady = false
				})
			},
			code: "JOURNEY_READINESS.RESULT.DEPENDENCY_NOT_READY",
		},
		"Provider unverified": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.ProviderVerified = false
				})
			},
			code: "JOURNEY_READINESS.RESULT.PROVIDER_UNVERIFIED",
		},
		"simulator": {
			mutate: func(results []JourneyReadinessCaseResult, receipts memoryJourneyReceiptResolver) {
				mutateJourneyBinding(receipts, results[0].ReceiptRef, func(binding *JourneyReceiptBinding) {
					binding.PhysicalDevice = false
				})
			},
			code: "JOURNEY_READINESS.RESULT.PHYSICAL_DEVICE_REQUIRED",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			graphValue := journeyTestGraph()
			catalog := completeJourneyCatalog()
			resolver := memoryJourneyReceiptResolver{}
			results := journeyResults(graphValue, catalog.Cases, resolver)
			test.mutate(results, resolver)
			closure := journeyEvaluator(catalog, resolver).Evaluate(
				context.Background(), graphValue,
				JourneyReadinessResultBundle{
					GeneratedAt: journeyTestStart(), Results: results,
				},
			)
			requireJourneyViolation(t, closure, test.code)
			if closure.CommercialReady {
				t.Fatal("false-green Journey evidence became commercial-ready")
			}
		})
	}
}

func TestJourneyEvaluatorRejectsWrongTargetDuplicateAndMissingReceipt(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	resolver := memoryJourneyReceiptResolver{}
	results := journeyResults(graphValue, catalog.Cases, resolver)

	wrong := append([]JourneyReadinessCaseResult(nil), results...)
	wrong[0].Target = JourneyTarget{Kind: JourneyTargetJourney, ID: "app_root.other"}
	closure := journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{GeneratedAt: journeyTestStart(), Results: wrong},
	)
	requireJourneyViolation(t, closure, "JOURNEY_READINESS.RESULT.UNKNOWN_CASE")

	duplicate := append(append([]JourneyReadinessCaseResult(nil), results...), results[0])
	closure = journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{GeneratedAt: journeyTestStart(), Results: duplicate},
	)
	requireJourneyViolation(t, closure, "JOURNEY_READINESS.RESULT.DUPLICATE")

	missing := append([]JourneyReadinessCaseResult(nil), results...)
	missing = missing[1:]
	closure = journeyEvaluator(catalog, resolver).Evaluate(
		context.Background(), graphValue,
		JourneyReadinessResultBundle{GeneratedAt: journeyTestStart(), Results: missing},
	)
	if closure.CommercialReady || len(closure.Journeys) != 1 || len(closure.Journeys[0].Missing) == 0 {
		t.Fatalf("missing result must fail closed: %+v", closure)
	}
}

func journeyEvaluator(
	catalog JourneyCaseCatalog,
	receipts JourneyReceiptResolver,
) *JourneyEvaluator {
	return NewJourneyEvaluator(
		fixedSnapshotProvider{value: journeyTestEvaluationContext()},
		fixedJourneyAuthority{catalog: catalog},
		receipts,
	)
}

func completeJourneyCatalog() JourneyCaseCatalog {
	journey := JourneyTarget{Kind: JourneyTargetJourney, ID: journeyTestID}
	appExecutions := make([]ExecutionRequirement, 0, 8)
	opsExecutions := make([]ExecutionRequirement, 0, 4)
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		binding := DigestCandidate
		if environment == "prod" {
			binding = DigestRelease
		}
		for _, platform := range []string{"android", "ios"} {
			appExecutions = append(appExecutions, journeyExecution(
				environment, platform, "physical", binding,
			))
		}
		opsExecutions = append(opsExecutions, journeyExecution(
			environment, "cloud", "managed", binding,
		))
	}
	return JourneyCaseCatalog{
		Journeys: []JourneyDefinition{{JourneyID: journeyTestID, SpecRef: journeyTestSpecRef}},
		Cases: []JourneyCaseContract{
			{
				JourneyID: journeyTestID, SpecRef: journeyTestSpecRef, CaseID: "remote-physical-uat",
				Producer: ProducerApp, Layer: LayerUserAcceptance, Target: journey,
				RunnerSourcePath: "quwoquan_app/test/user_acceptance/journeys/" + journeyTestID + "/readiness_case_test.dart",
				Executions:       appExecutions,
			},
			{
				JourneyID: journeyTestID, SpecRef: journeyTestSpecRef, CaseID: "four-environment",
				Producer: ProducerOps, Layer: LayerEnvironmentAcceptance, Target: journey,
				RunnerSourcePath: "quwoquan_ops/tests/acceptance/environment_acceptance/journeys/" + journeyTestID + "/readiness_case_test.py",
				Executions:       append([]ExecutionRequirement(nil), opsExecutions...),
			},
			{
				JourneyID: journeyTestID, SpecRef: journeyTestSpecRef, CaseID: "rollback",
				Producer: ProducerOps, Layer: LayerRollback, Target: journey,
				RunnerSourcePath: "quwoquan_ops/tests/acceptance/rollback/journeys/" + journeyTestID + "/readiness_case_test.py",
				Executions:       append([]ExecutionRequirement(nil), opsExecutions...),
			},
			{
				JourneyID: journeyTestID, SpecRef: journeyTestSpecRef, CaseID: "replay",
				Producer: ProducerOps, Layer: LayerReplay, Target: journey,
				RunnerSourcePath: "quwoquan_ops/tests/acceptance/replay/journeys/" + journeyTestID + "/readiness_case_test.py",
				Executions:       append([]ExecutionRequirement(nil), opsExecutions...),
			},
		},
	}
}

func journeyExecution(
	environment, platform, device string,
	binding DigestBinding,
) ExecutionRequirement {
	return ExecutionRequirement{
		Environment: environment, Platform: platform, DeviceClass: device,
		Provider: "provider-live", DigestBinding: binding,
	}
}

func journeyResults(
	current *graph.ContractGraph,
	contracts []JourneyCaseContract,
	resolver memoryJourneyReceiptResolver,
) []JourneyReadinessCaseResult {
	results := make([]JourneyReadinessCaseResult, 0)
	for _, contract := range contracts {
		for index, execution := range contract.Executions {
			ref := strings.Join([]string{
				contract.CaseID, execution.Environment, execution.Platform,
				string(rune('a' + index)),
			}, "/")
			bytes := []byte("journey-receipt:" + ref)
			result := journeyResult(current, contract, execution, ref, bytes)
			binding := journeyReceiptBindingForResult(result)
			binding.RemoteComposition = true
			binding.FixtureFree = true
			binding.DependenciesReady = true
			binding.ProviderVerified = true
			binding.PhysicalDevice = contract.Producer == ProducerApp
			binding.RunnerSourcePath = contract.RunnerSourcePath
			resolver[ref] = ResolvedJourneyReceipt{Bytes: bytes, Binding: binding, Trusted: true}
			results = append(results, result)
		}
	}
	return results
}

func journeyResult(
	current *graph.ContractGraph,
	contract JourneyCaseContract,
	execution ExecutionRequirement,
	receiptRef string,
	receipt []byte,
) JourneyReadinessCaseResult {
	graphHash, err := ContractGraphSourceHash(current)
	if err != nil {
		panic(err)
	}
	digest := sha256.Sum256(receipt)
	result := JourneyReadinessCaseResult{
		JourneyID: contract.JourneyID, SpecRef: contract.SpecRef, CaseID: contract.CaseID,
		Producer: contract.Producer, Layer: contract.Layer, Status: StatusPassed,
		Target: contract.Target, CommitSHA: journeyTestCommit(),
		ContractGraphSourceHash: graphHash,
		DeploymentTarget:        journeyTestDeployment(execution.Environment).DeploymentTarget,
		BaselineID:              journeyTestDeployment(execution.Environment).BaselineID,
		PackageDigest:           journeyTestDeployment(execution.Environment).PackageDigest,
		ConfigurationDigest:     journeyTestDeployment(execution.Environment).ConfigurationDigest,
		CandidateManifestSHA256: journeyTestDeployment(execution.Environment).CandidateManifestSHA256,
		CandidateDigest:         journeyTestCandidate(), Environment: execution.Environment,
		Platform: execution.Platform, DeviceClass: execution.DeviceClass,
		Provider: execution.Provider, StartedAt: journeyTestStart(),
		CompletedAt: journeyTestStart().Add(time.Minute), RunnerIdentity: "runner/live",
		ArtifactSHA256: hex.EncodeToString(digest[:]), ReceiptRef: receiptRef,
	}
	if execution.DigestBinding == DigestRelease {
		result.ReleaseDigest = journeyTestRelease()
	}
	return result
}

func journeyTestGraph() *graph.ContractGraph {
	return &graph.ContractGraph{
		Sources: []ast.SourceDigest{
			{Path: "_shared/page_object_contract.yaml", SHA256: strings.Repeat("8", 64)},
			{Path: "assistant/assistant_run/operations.yaml", SHA256: strings.Repeat("9", 64)},
		},
		Documents: []ast.SourceDocument{{
			Path: "_shared/page_object_contract.yaml", MediaType: "application/yaml",
			SHA256:  strings.Repeat("8", 64),
			Content: json.RawMessage(`{"pages":[{"page_id":"app.startup_recovery","source_path":"lib/runtime/shell/recovery/startup_recovery_page.dart","object_ids":[]}]}`),
		}},
	}
}

func journeyTestEvaluationContext() EvaluationContext {
	return EvaluationContext{
		CommitSHA: journeyTestCommit(),
		Deployments: map[string]DeploymentBinding{
			"alpha": journeyTestDeployment("alpha"), "beta": journeyTestDeployment("beta"),
			"gamma": journeyTestDeployment("gamma"), "prod": journeyTestDeployment("prod"),
		},
		CandidateDigest: journeyTestCandidate(), ReleaseDigest: journeyTestRelease(),
	}
}

func journeyTestDeployment(environment string) DeploymentBinding {
	configurations := map[string]string{
		"alpha": "sha256:" + strings.Repeat("1", 64), "beta": "sha256:" + strings.Repeat("2", 64),
		"gamma": "sha256:" + strings.Repeat("3", 64), "prod": "sha256:" + strings.Repeat("4", 64),
	}
	return DeploymentBinding{
		DeploymentTarget:        "journey-" + environment,
		BaselineID:              "baseline-2026-08-05",
		PackageDigest:           "sha256:" + strings.Repeat("5", 64),
		ConfigurationDigest:     configurations[environment],
		CandidateManifestSHA256: strings.Repeat("6", 64),
	}
}

func journeyTestCommit() string    { return strings.Repeat("a", 40) }
func journeyTestCandidate() string { return "sha256:" + strings.Repeat("b", 64) }
func journeyTestRelease() string   { return "sha256:" + strings.Repeat("c", 64) }
func journeyTestStart() time.Time {
	return time.Date(2026, 8, 5, 2, 0, 0, 0, time.UTC)
}

func mutateJourneyBinding(
	receipts memoryJourneyReceiptResolver,
	ref string,
	mutate func(*JourneyReceiptBinding),
) {
	receipt := receipts[ref]
	mutate(&receipt.Binding)
	receipts[ref] = receipt
}

func requireJourneyViolation(t *testing.T, closure JourneyClosureResult, code string) {
	t.Helper()
	for _, violation := range closure.Violations {
		if violation.Code == code {
			return
		}
	}
	t.Fatalf("violations=%+v, want %s", closure.Violations, code)
}
