package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
	readinesstrust "quwoquan_service/internal/metadata/readiness/trust"
)

const (
	cliObjectID    = "assistant.assistant_run"
	cliOperationID = "assistant.assistant_run.ApproveAssistantToolUse"
	cliPageID      = "assistant.personal_session"
	cliSpecRef     = "specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003"
	cliSourcePath  = "assistant/assistant/assistant_run/operations.yaml"
)

func TestCLIRequiresTheSignedSnapshotReceiptAndEvidenceChain(t *testing.T) {
	fixture := newCLIFixture(t)
	var output bytes.Buffer
	if code := run(context.Background(), fixture.args, &output); code != 0 {
		t.Fatalf("run() code=%d output=%s", code, output.String())
	}
	var closure readiness.ClosureResult
	if err := json.Unmarshal(output.Bytes(), &closure); err != nil {
		t.Fatal(err)
	}
	if !closure.CommercialReady || len(closure.Violations) != 0 {
		t.Fatalf("closure=%+v, want commercial-ready", closure)
	}

	// File presence is insufficient: modifying even whitespace changes the
	// exact signed receipt bytes and makes the complete closure fail.
	file, err := os.OpenFile(fixture.receiptPaths[0], os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := file.Write([]byte("\n")); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	output.Reset()
	if code := run(context.Background(), fixture.args, &output); code != 1 {
		t.Fatalf("tampered run() code=%d output=%s, want non-ready exit 1", code, output.String())
	}
	if err := json.Unmarshal(output.Bytes(), &closure); err != nil {
		t.Fatal(err)
	}
	if closure.CommercialReady || !containsViolation(closure, "READINESS.RESULT.RECEIPT_UNAVAILABLE") {
		t.Fatalf("closure=%+v, tampered receipt must fail closed", closure)
	}
}

func TestCLIEmitsJSONAndExitTwoForMissingTrustInput(t *testing.T) {
	var output bytes.Buffer
	if code := run(context.Background(), nil, &output); code != 2 {
		t.Fatalf("run() code=%d, want 2", code)
	}
	var result fatalResult
	if err := json.Unmarshal(output.Bytes(), &result); err != nil {
		t.Fatalf("output=%q is not JSON: %v", output.String(), err)
	}
	if result.CommercialReady || result.Error == "" {
		t.Fatalf("result=%+v, want explicit fail-closed JSON", result)
	}
}

func TestDecodeGraphRejectsDuplicateJSONKeys(t *testing.T) {
	t.Parallel()
	if _, err := decodeGraph([]byte(`{"sources":[],"sources":[]}`)); err == nil {
		t.Fatal("ContractGraph decoder accepted duplicate JSON keys")
	}
}

type cliFixture struct {
	args         []string
	receiptPaths []string
}

func newCLIFixture(t *testing.T) cliFixture {
	t.Helper()
	root := t.TempDir()
	receiptRoot := filepath.Join(root, "receipts")
	evidenceRoot := filepath.Join(root, "evidence")
	if err := os.MkdirAll(receiptRoot, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(evidenceRoot, "sha256"), 0o700); err != nil {
		t.Fatal(err)
	}
	graphValue := cliGraph()
	sourceHash, err := readiness.ContractGraphSourceHash(graphValue)
	if err != nil {
		t.Fatal(err)
	}
	commitSHA := strings.Repeat("a", 40)
	configurationDigests := map[string]string{
		"alpha": "sha256:" + strings.Repeat("1", 64), "beta": "sha256:" + strings.Repeat("2", 64),
		"gamma": "sha256:" + strings.Repeat("3", 64), "prod": "sha256:" + strings.Repeat("4", 64),
	}
	deployments := map[string]readiness.DeploymentBinding{}
	for environment, configurationDigest := range configurationDigests {
		deployments[environment] = readiness.DeploymentBinding{
			DeploymentTarget:        "assistant-" + environment,
			BaselineID:              "baseline-2026-08-05",
			PackageDigest:           "sha256:" + strings.Repeat("7", 64),
			ConfigurationDigest:     configurationDigest,
			CandidateManifestSHA256: strings.Repeat("8", 64),
		}
	}
	candidateDigest := "sha256:" + strings.Repeat("5", 64)
	releaseDigest := "sha256:" + strings.Repeat("6", 64)
	startedAt := time.Date(2026, 8, 5, 3, 0, 0, 0, time.UTC)
	runnerPublic, runnerPrivate := deterministicCLIKey(7)
	snapshotPublic, snapshotPrivate := deterministicCLIKey(8)
	results := make([]readiness.ReadinessCaseResult, 0)
	receiptPaths := make([]string, 0)
	receiptIndex := 0
	for _, contract := range graphValue.ReadinessCases {
		for _, execution := range contract.Executions {
			receiptIndex++
			relative := filepath.ToSlash(filepath.Join("cases", contract.CaseID+"-"+execution.Environment+"-"+execution.Platform+".json"))
			result := readiness.ReadinessCaseResult{
				ObjectID: contract.ObjectID, SpecRef: contract.SpecRef, CaseID: contract.CaseID,
				Producer: contract.Producer, Layer: contract.Layer, Status: readiness.StatusPassed,
				Target: contract.Target, CommitSHA: commitSHA,
				ContractGraphSourceHash: sourceHash,
				DeploymentTarget:        deployments[execution.Environment].DeploymentTarget,
				BaselineID:              deployments[execution.Environment].BaselineID,
				PackageDigest:           deployments[execution.Environment].PackageDigest,
				ConfigurationDigest:     deployments[execution.Environment].ConfigurationDigest,
				CandidateManifestSHA256: deployments[execution.Environment].CandidateManifestSHA256,
				CandidateDigest:         candidateDigest, Environment: execution.Environment,
				Platform: execution.Platform, DeviceClass: execution.DeviceClass,
				Provider: execution.Provider, StartedAt: startedAt.Add(time.Duration(receiptIndex) * time.Minute),
				CompletedAt:    startedAt.Add(time.Duration(receiptIndex)*time.Minute + time.Second),
				RunnerIdentity: "runner.acceptance", ArtifactPath: relative,
			}
			if execution.DigestBinding == readiness.DigestRelease {
				result.ReleaseDigest = releaseDigest
			}
			evidence := []byte("proof:" + relative)
			evidenceDigest := sha256.Sum256(evidence)
			evidenceSHA := hex.EncodeToString(evidenceDigest[:])
			if err := os.WriteFile(filepath.Join(evidenceRoot, "sha256", evidenceSHA), evidence, 0o600); err != nil {
				t.Fatal(err)
			}
			receipt := readiness.ReadinessReceipt{
				Binding: receiptBinding(result, contract), EvidenceSHA256: evidenceSHA,
			}
			receiptBytes, err := json.Marshal(receipt)
			if err != nil {
				t.Fatal(err)
			}
			receiptDigest := sha256.Sum256(receiptBytes)
			result.ArtifactSHA256 = hex.EncodeToString(receiptDigest[:])
			receiptPath := filepath.Join(receiptRoot, filepath.FromSlash(relative))
			if err := os.MkdirAll(filepath.Dir(receiptPath), 0o700); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(receiptPath, receiptBytes, 0o600); err != nil {
				t.Fatal(err)
			}
			signature := readinesstrust.DetachedReceiptSignature{
				KeyID: "runner-key-1",
				Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
					runnerPrivate, readinesstrust.ReceiptSigningMessage(receiptBytes),
				)),
			}
			writeCLIJSON(t, receiptPath+".sig.json", signature)
			results = append(results, result)
			receiptPaths = append(receiptPaths, receiptPath)
		}
	}

	graphPath := filepath.Join(root, "contract_graph.json")
	bundlePath := filepath.Join(root, "bundle.json")
	snapshotPath := filepath.Join(root, "snapshot.json")
	snapshotKeyringPath := filepath.Join(root, "snapshot_keyring.json")
	runnerKeyringPath := filepath.Join(root, "runner_keyring.json")
	writeCLIJSON(t, graphPath, graphValue)
	writeCLIJSON(t, bundlePath, readiness.ReadinessResultBundle{
		GeneratedAt: startedAt, Results: results,
	})
	snapshotPayload, err := json.Marshal(readinesstrust.CurrentSnapshot{
		CommitSHA: commitSHA, ContractGraphSourceHash: sourceHash,
		Deployments: readinesstrust.EnvironmentDeployments{
			Alpha: deployments["alpha"], Beta: deployments["beta"],
			Gamma: deployments["gamma"], Prod: deployments["prod"],
		},
		CandidateDigest: candidateDigest, ReleaseDigest: releaseDigest,
	})
	if err != nil {
		t.Fatal(err)
	}
	writeCLIJSON(t, snapshotPath, readinesstrust.SignedCurrentSnapshot{
		KeyID: "snapshot-key-1", Payload: base64.StdEncoding.EncodeToString(snapshotPayload),
		Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
			snapshotPrivate, readinesstrust.SnapshotSigningMessage(snapshotPayload),
		)),
	})
	writeCLIJSON(t, snapshotKeyringPath, readinesstrust.SnapshotKeyring{
		Authorities: []readinesstrust.SnapshotAuthority{{
			KeyID: "snapshot-key-1", PublicKey: base64.StdEncoding.EncodeToString(snapshotPublic),
		}},
	})
	writeCLIJSON(t, runnerKeyringPath, readinesstrust.RunnerKeyring{
		Runners: []readinesstrust.RunnerAuthority{{
			RunnerIdentity: "runner.acceptance", KeyID: "runner-key-1",
			PublicKey: base64.StdEncoding.EncodeToString(runnerPublic),
		}},
	})
	_, currentFile, _, _ := runtime.Caller(0)
	metadataDir := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "contracts", "metadata"))
	return cliFixture{
		receiptPaths: receiptPaths,
		args: []string{
			"--graph", graphPath, "--bundle", bundlePath, "--snapshot", snapshotPath,
			"--snapshot-keyring", snapshotKeyringPath, "--runner-keyring", runnerKeyringPath,
			"--receipt-root", receiptRoot, "--evidence-root", evidenceRoot,
			"--metadata-dir", metadataDir,
		},
	}
}

func cliGraph() *graph.ContractGraph {
	operationTarget := ast.ReadinessCaseTarget{Kind: ast.ReadinessTargetOperation, ID: cliOperationID}
	pageTarget := ast.ReadinessCaseTarget{Kind: ast.ReadinessTargetPage, ID: cliPageID}
	objectTarget := ast.ReadinessCaseTarget{Kind: ast.ReadinessTargetObject, ID: cliObjectID}
	execution := func(environment, platform, device, provider string, digest ast.ReadinessDigestBinding) ast.ReadinessExecutionRequirement {
		return ast.ReadinessExecutionRequirement{
			Environment: environment, Platform: platform, DeviceClass: device,
			Provider: provider, DigestBinding: digest,
		}
	}
	cases := []ast.ReadinessCaseContract{
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "service-local", Producer: ast.ReadinessProducerService, Layer: ast.ReadinessLayerLocalContract, Target: operationTarget, RunnerSourcePath: "quwoquan_service/services/assistant-service/tests/local_contract/assistant/assistant_run/readiness_case_test.go", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("alpha", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate)}},
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "service-api", Producer: ast.ReadinessProducerService, Layer: ast.ReadinessLayerAPIIntegration, Target: operationTarget, RunnerSourcePath: "quwoquan_service/services/assistant-service/tests/api_integration/assistant/assistant_run/readiness_case_test.go", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("beta", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate)}},
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "physical-uat", Producer: ast.ReadinessProducerApp, Layer: ast.ReadinessLayerUserAcceptance, Target: pageTarget, RunnerSourcePath: "quwoquan_app/test/user_acceptance/service/assistant_service/assistant/assistant_run/readiness_case_test.dart", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("alpha", "android", "physical", "provider-live", ast.ReadinessDigestCandidate), execution("beta", "ios", "physical", "provider-live", ast.ReadinessDigestCandidate)}},
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "environment", Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerEnvironmentAcceptance, Target: objectTarget, RunnerSourcePath: "quwoquan_ops/tests/acceptance/environment_acceptance/assistant/assistant/assistant_run/readiness_case_test.py", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("alpha", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate), execution("beta", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate), execution("gamma", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate), execution("prod", "linux", "managed-runner", "provider-live", ast.ReadinessDigestRelease)}},
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "rollback", Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerRollback, Target: objectTarget, RunnerSourcePath: "quwoquan_ops/tests/acceptance/rollback/assistant/assistant/assistant_run/readiness_case_test.py", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("gamma", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate), execution("prod", "linux", "managed-runner", "provider-live", ast.ReadinessDigestRelease)}},
		{ObjectID: cliObjectID, SpecRef: cliSpecRef, CaseID: "replay", Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerReplay, Target: objectTarget, RunnerSourcePath: "quwoquan_ops/tests/acceptance/replay/assistant/assistant/assistant_run/readiness_case_test.py", SourcePath: cliSourcePath, Executions: []ast.ReadinessExecutionRequirement{execution("gamma", "linux", "managed-runner", "provider-live", ast.ReadinessDigestCandidate), execution("prod", "linux", "managed-runner", "provider-live", ast.ReadinessDigestRelease)}},
	}
	return &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: cliObjectID, Domain: "assistant", Name: "assistant_run",
			SourcePath: "assistant/assistant/assistant_run/object.yaml",
		}},
		Operations: []ast.Operation{{
			ID: cliOperationID, LocalID: "ApproveAssistantToolUse", ObjectID: cliObjectID,
			Commercial: ast.CommercialBinding{Status: "ready"},
		}},
		ReadinessCases:  cases,
		ObjectReadiness: []graph.ObjectReadiness{{ObjectID: cliObjectID, Implemented: true}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{{
			ObjectID:   cliObjectID,
			SourcePath: "quwoquan_service/services/assistant-service/internal/assistant/assistant_run",
		}},
		Sources: []ast.SourceDigest{{Path: cliSourcePath, SHA256: strings.Repeat("b", 64)}, {Path: "_shared/page_object_contract.yaml", SHA256: strings.Repeat("8", 64)}},
		Documents: []ast.SourceDocument{{
			Path: "_shared/page_object_contract.yaml", MediaType: "application/yaml",
			SHA256:  strings.Repeat("8", 64),
			Content: json.RawMessage(`{"pages":[{"page_id":"assistant.personal_session","source_path":"lib/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart","object_ids":["assistant.assistant_run"]}]}`),
		}},
	}
}

func receiptBinding(
	result readiness.ReadinessCaseResult,
	contract ast.ReadinessCaseContract,
) readiness.ReceiptBinding {
	return readiness.ReceiptBinding{
		ObjectID: result.ObjectID, SpecRef: result.SpecRef, CaseID: result.CaseID,
		Producer: result.Producer, Layer: result.Layer, Status: result.Status,
		Target: result.Target, CommitSHA: result.CommitSHA,
		ContractGraphSourceHash: result.ContractGraphSourceHash,
		DeploymentTarget:        result.DeploymentTarget, BaselineID: result.BaselineID,
		PackageDigest:           result.PackageDigest,
		ConfigurationDigest:     result.ConfigurationDigest,
		CandidateManifestSHA256: result.CandidateManifestSHA256,
		CandidateDigest:         result.CandidateDigest, ReleaseDigest: result.ReleaseDigest,
		Environment: result.Environment, Platform: result.Platform,
		DeviceClass: result.DeviceClass, Provider: result.Provider,
		StartedAt: result.StartedAt, CompletedAt: result.CompletedAt,
		RunnerIdentity: result.RunnerIdentity, RunnerSourcePath: contract.RunnerSourcePath,
		RemoteComposition: result.Layer == readiness.LayerUserAcceptance,
		FixtureFree:       true, DependenciesReady: true, ProviderVerified: true,
		PhysicalDevice: result.Layer == readiness.LayerUserAcceptance &&
			result.DeviceClass == "physical",
	}
}

func deterministicCLIKey(value byte) (ed25519.PublicKey, ed25519.PrivateKey) {
	seed := bytes.Repeat([]byte{value}, ed25519.SeedSize)
	privateKey := ed25519.NewKeyFromSeed(seed)
	return privateKey.Public().(ed25519.PublicKey), privateKey
}

func writeCLIJSON(t *testing.T, path string, value any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func containsViolation(closure readiness.ClosureResult, code string) bool {
	for _, violation := range closure.Violations {
		if violation.Code == code {
			return true
		}
	}
	return false
}
