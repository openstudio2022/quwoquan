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

const journeySpecRef = "specs/feature-tree/spec.md#uat-001"

func TestCLIRequiresSignedCatalogSnapshotReceiptsAndEvidence(t *testing.T) {
	fixture := newJourneyCLIFixture(t)
	var output bytes.Buffer
	if code := run(context.Background(), fixture.args, &output); code != 0 {
		t.Fatalf("run() code=%d output=%s", code, output.String())
	}
	var closure readiness.JourneyClosureResult
	if err := json.Unmarshal(output.Bytes(), &closure); err != nil {
		t.Fatal(err)
	}
	if !closure.CommercialReady || len(closure.Journeys) != 1 ||
		!closure.Journeys[0].CommercialReady || len(closure.Violations) != 0 {
		t.Fatalf("closure=%+v, want one commercial-ready AppRoot Journey", closure)
	}

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
		t.Fatalf("tampered run() code=%d output=%s, want blocked exit 1", code, output.String())
	}
	if err := json.Unmarshal(output.Bytes(), &closure); err != nil {
		t.Fatal(err)
	}
	if closure.CommercialReady || !containsJourneyViolation(
		closure, "JOURNEY_READINESS.RESULT.RECEIPT_UNAVAILABLE",
	) {
		t.Fatalf("tampered receipt did not fail closed: %+v", closure)
	}
}

func TestCLIEmitsJSONAndExitTwoForMissingJourneyTrustInput(t *testing.T) {
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

type journeyCLIFixture struct {
	args         []string
	receiptPaths []string
}

func newJourneyCLIFixture(t *testing.T) journeyCLIFixture {
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
	current := &graph.ContractGraph{Sources: []ast.SourceDigest{{
		Path: "specs/feature-tree/spec.md", SHA256: strings.Repeat("b", 64),
	}}}
	sourceHash, err := readiness.ContractGraphSourceHash(current)
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
			DeploymentTarget:        "journey-" + environment,
			BaselineID:              "baseline-2026-08-05",
			PackageDigest:           "sha256:" + strings.Repeat("7", 64),
			ConfigurationDigest:     configurationDigest,
			CandidateManifestSHA256: strings.Repeat("8", 64),
		}
	}
	candidateDigest := "sha256:" + strings.Repeat("5", 64)
	releaseDigest := "sha256:" + strings.Repeat("6", 64)
	startedAt := time.Date(2026, 8, 5, 5, 0, 0, 0, time.UTC)
	runnerPublic, runnerPrivate := deterministicKey(31)
	snapshotPublic, snapshotPrivate := deterministicKey(32)
	catalogPublic, catalogPrivate := deterministicKey(33)
	catalog := completeJourneyCatalog()

	results := make([]readiness.JourneyReadinessCaseResult, 0, 20)
	receiptPaths := make([]string, 0, 20)
	receiptIndex := 0
	for _, contract := range catalog.Cases {
		for _, execution := range contract.Executions {
			receiptIndex++
			relative := filepath.ToSlash(filepath.Join(
				"cases", contract.CaseID+"-"+execution.Environment+"-"+
					execution.Platform+".json",
			))
			result := readiness.JourneyReadinessCaseResult{
				JourneyID: contract.JourneyID, SpecRef: contract.SpecRef,
				CaseID: contract.CaseID, Producer: contract.Producer,
				Layer: contract.Layer, Status: readiness.StatusPassed,
				Target: contract.Target, CommitSHA: commitSHA,
				ContractGraphSourceHash: sourceHash,
				DeploymentTarget:        deployments[execution.Environment].DeploymentTarget,
				BaselineID:              deployments[execution.Environment].BaselineID,
				PackageDigest:           deployments[execution.Environment].PackageDigest,
				ConfigurationDigest:     deployments[execution.Environment].ConfigurationDigest,
				CandidateManifestSHA256: deployments[execution.Environment].CandidateManifestSHA256,
				CandidateDigest:         candidateDigest, Environment: execution.Environment,
				Platform: execution.Platform, DeviceClass: execution.DeviceClass,
				Provider:  execution.Provider,
				StartedAt: startedAt.Add(time.Duration(receiptIndex) * time.Minute),
				CompletedAt: startedAt.Add(
					time.Duration(receiptIndex)*time.Minute + time.Second,
				),
				RunnerIdentity: "runner.journey-acceptance", ArtifactPath: relative,
			}
			if execution.DigestBinding == readiness.DigestRelease {
				result.ReleaseDigest = releaseDigest
			}
			evidence := []byte("journey-proof:" + relative)
			evidenceDigest := sha256.Sum256(evidence)
			evidenceSHA := hex.EncodeToString(evidenceDigest[:])
			if err := os.WriteFile(
				filepath.Join(evidenceRoot, "sha256", evidenceSHA), evidence, 0o600,
			); err != nil {
				t.Fatal(err)
			}
			receipt := readiness.JourneyReadinessReceipt{
				Binding:        journeyReceiptBinding(result),
				EvidenceSHA256: evidenceSHA,
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
			writeFileJSON(t, receiptPath+".sig.json", readinesstrust.DetachedReceiptSignature{
				KeyID: "journey-runner-key-1",
				Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
					runnerPrivate,
					readinesstrust.JourneyReceiptSigningMessage(receiptBytes),
				)),
			})
			results = append(results, result)
			receiptPaths = append(receiptPaths, receiptPath)
		}
	}

	graphPath := filepath.Join(root, "contract_graph.json")
	bundlePath := filepath.Join(root, "bundle.json")
	snapshotPath := filepath.Join(root, "snapshot.json")
	snapshotKeyringPath := filepath.Join(root, "snapshot_keyring.json")
	catalogPath := filepath.Join(root, "journey_catalog.json")
	catalogKeyringPath := filepath.Join(root, "journey_catalog_keyring.json")
	runnerKeyringPath := filepath.Join(root, "runner_keyring.json")
	writeFileJSON(t, graphPath, current)
	writeFileJSON(t, bundlePath, readiness.JourneyReadinessResultBundle{
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
	writeFileJSON(t, snapshotPath, readinesstrust.SignedCurrentSnapshot{
		KeyID:   "snapshot-authority-1",
		Payload: base64.StdEncoding.EncodeToString(snapshotPayload),
		Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
			snapshotPrivate,
			readinesstrust.SnapshotSigningMessage(snapshotPayload),
		)),
	})
	writeFileJSON(t, snapshotKeyringPath, readinesstrust.SnapshotKeyring{
		Authorities: []readinesstrust.SnapshotAuthority{{
			KeyID:     "snapshot-authority-1",
			PublicKey: base64.StdEncoding.EncodeToString(snapshotPublic),
		}},
	})

	catalogPayload, err := json.Marshal(readinesstrust.CurrentJourneyCatalog{
		ContractGraphSourceHash: sourceHash, Catalog: catalog,
	})
	if err != nil {
		t.Fatal(err)
	}
	writeFileJSON(t, catalogPath, readinesstrust.SignedCurrentJourneyCatalog{
		KeyID:   "journey-authority-1",
		Payload: base64.StdEncoding.EncodeToString(catalogPayload),
		Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
			catalogPrivate,
			readinesstrust.JourneyCatalogSigningMessage(catalogPayload),
		)),
	})
	writeFileJSON(t, catalogKeyringPath, readinesstrust.JourneyCatalogKeyring{
		Authorities: []readinesstrust.JourneyCatalogAuthority{{
			KeyID:     "journey-authority-1",
			PublicKey: base64.StdEncoding.EncodeToString(catalogPublic),
		}},
	})
	writeFileJSON(t, runnerKeyringPath, readinesstrust.RunnerKeyring{
		Runners: []readinesstrust.RunnerAuthority{{
			RunnerIdentity: "runner.journey-acceptance",
			KeyID:          "journey-runner-key-1",
			PublicKey:      base64.StdEncoding.EncodeToString(runnerPublic),
		}},
	})

	_, currentFile, _, _ := runtime.Caller(0)
	metadataDir := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "contracts", "metadata"))
	return journeyCLIFixture{
		receiptPaths: receiptPaths,
		args: []string{
			"--graph", graphPath, "--bundle", bundlePath,
			"--snapshot", snapshotPath, "--snapshot-keyring", snapshotKeyringPath,
			"--journey-catalog", catalogPath,
			"--journey-catalog-keyring", catalogKeyringPath,
			"--runner-keyring", runnerKeyringPath,
			"--receipt-root", receiptRoot, "--evidence-root", evidenceRoot,
			"--metadata-dir", metadataDir,
		},
	}
}

func completeJourneyCatalog() readiness.JourneyCaseCatalog {
	journey := readiness.JourneyTarget{
		Kind: readiness.JourneyTargetJourney, ID: "startup_recovery",
	}
	execution := func(
		environment, platform, device string,
	) readiness.ExecutionRequirement {
		binding := readiness.DigestCandidate
		if environment == "prod" {
			binding = readiness.DigestRelease
		}
		return readiness.ExecutionRequirement{
			Environment: environment, Platform: platform, DeviceClass: device,
			Provider: "provider-live", DigestBinding: binding,
		}
	}
	physical := make([]readiness.ExecutionRequirement, 0, 8)
	server := make([]readiness.ExecutionRequirement, 0, 4)
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		for _, platform := range []string{"android", "ios"} {
			physical = append(physical, execution(environment, platform, "physical"))
		}
		server = append(server, execution(environment, "linux", "managed-runner"))
	}
	caseContract := func(
		caseID string,
		producer readiness.Producer,
		layer readiness.Layer,
		executions []readiness.ExecutionRequirement,
	) readiness.JourneyCaseContract {
		runnerSourcePath := "quwoquan_app/test/user_acceptance/journeys/startup_recovery/case_test.dart"
		if producer == readiness.ProducerOps {
			runnerSourcePath = "quwoquan_ops/tests/acceptance/" + string(layer) +
				"/journeys/startup_recovery/case_test.py"
		}
		return readiness.JourneyCaseContract{
			JourneyID: "startup_recovery", SpecRef: journeySpecRef,
			CaseID: caseID, Producer: producer, Layer: layer, Target: journey,
			RunnerSourcePath: runnerSourcePath,
			Executions:       append([]readiness.ExecutionRequirement(nil), executions...),
		}
	}
	return readiness.JourneyCaseCatalog{
		Journeys: []readiness.JourneyDefinition{{
			JourneyID: "startup_recovery", SpecRef: journeySpecRef,
		}},
		Cases: []readiness.JourneyCaseContract{
			caseContract("physical-uat", readiness.ProducerApp, readiness.LayerUserAcceptance, physical),
			caseContract("environment", readiness.ProducerOps, readiness.LayerEnvironmentAcceptance, server),
			caseContract("rollback", readiness.ProducerOps, readiness.LayerRollback, server),
			caseContract("replay", readiness.ProducerOps, readiness.LayerReplay, server),
		},
	}
}

func journeyReceiptBinding(
	result readiness.JourneyReadinessCaseResult,
) readiness.JourneyReceiptBinding {
	runnerSourcePath := "quwoquan_app/test/user_acceptance/journeys/startup_recovery/case_test.dart"
	physical := result.Producer == readiness.ProducerApp
	if result.Producer == readiness.ProducerOps {
		runnerSourcePath = "quwoquan_ops/tests/acceptance/" + string(result.Layer) +
			"/journeys/startup_recovery/case_test.py"
	}
	return readiness.JourneyReceiptBinding{
		JourneyID: result.JourneyID, SpecRef: result.SpecRef, CaseID: result.CaseID,
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
		RunnerIdentity: result.RunnerIdentity, RunnerSourcePath: runnerSourcePath,
		RemoteComposition: true, FixtureFree: true, DependenciesReady: true,
		ProviderVerified: true, PhysicalDevice: physical,
	}
}

func deterministicKey(value byte) (ed25519.PublicKey, ed25519.PrivateKey) {
	seed := bytes.Repeat([]byte{value}, ed25519.SeedSize)
	privateKey := ed25519.NewKeyFromSeed(seed)
	return privateKey.Public().(ed25519.PublicKey), privateKey
}

func writeFileJSON(t *testing.T, path string, value any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func containsJourneyViolation(
	closure readiness.JourneyClosureResult,
	code string,
) bool {
	for _, violation := range closure.Violations {
		if violation.Code == code {
			return true
		}
	}
	return false
}
