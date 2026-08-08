package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
)

type fakeSignedResolver struct {
	root   string
	error  error
	mutate func()
	once   sync.Once
}

func (resolver *fakeSignedResolver) Resolve(
	_ context.Context,
	result readiness.ReadinessCaseResult,
) (readiness.ResolvedReceipt, error) {
	if resolver.error != nil {
		return readiness.ResolvedReceipt{}, resolver.error
	}
	data, err := os.ReadFile(filepath.Join(resolver.root, filepath.FromSlash(result.ArtifactPath)))
	if err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	receipt, err := readiness.DecodeReceipt(bytes.NewReader(data))
	if err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	resolver.once.Do(func() {
		if resolver.mutate != nil {
			resolver.mutate()
		}
	})
	return readiness.ResolvedReceipt{
		Bytes: data, Binding: receipt.Binding, Trusted: true,
	}, nil
}

type collectorFixture struct {
	root         string
	graphPath    string
	metadataDir  string
	keyringPath  string
	receiptRoot  string
	evidenceRoot string
	graph        graph.ContractGraph
	sourceHash   string
}

func TestCollectorBuildsDeterministicTrustedBundle(t *testing.T) {
	fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
		testCase("case_b", "beta", "ios", "ios_simulator", "substitute"),
		testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
	})
	completedA := time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC)
	completedB := completedA.Add(5 * time.Minute)
	fixture.writeReceipt(t, "nested/b.json", testBinding(
		fixture.sourceHash, fixture.graph.ReadinessCases[0], completedB, readiness.StatusPassed,
	))
	fixture.writeReceipt(t, "a.json", testBinding(
		fixture.sourceHash, fixture.graph.ReadinessCases[1], completedA, readiness.StatusPassed,
	))

	var stdout bytes.Buffer
	exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, nil))
	if exitCode != 0 {
		t.Fatalf("collector exit=%d output=%s", exitCode, stdout.String())
	}
	var bundle readiness.ReadinessResultBundle
	if err := json.Unmarshal(stdout.Bytes(), &bundle); err != nil {
		t.Fatalf("decode bundle: %v", err)
	}
	if !bundle.GeneratedAt.Equal(completedB) {
		t.Fatalf("generatedAt=%s want max completedAt=%s", bundle.GeneratedAt, completedB)
	}
	if len(bundle.Results) != 2 || bundle.Results[0].CaseID != "case_a" ||
		bundle.Results[1].CaseID != "case_b" {
		t.Fatalf("results are not deterministically ordered: %#v", bundle.Results)
	}
	for _, result := range bundle.Results {
		data, err := os.ReadFile(filepath.Join(fixture.receiptRoot, result.ArtifactPath))
		if err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(data)
		if result.ArtifactSHA256 != hex.EncodeToString(digest[:]) {
			t.Fatalf("artifact digest does not bind exact receipt bytes: %#v", result)
		}
		if result.ReceiptRef != "" {
			t.Fatalf("collector invented receiptRef: %#v", result)
		}
	}
}

func TestCollectorReturnsOneForMissingOrNonPassedTrustedResults(t *testing.T) {
	t.Run("all receipts missing", func(t *testing.T) {
		fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
			testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
		})
		var stdout bytes.Buffer
		if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, nil)); exitCode != 1 {
			t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
		}
		var incomplete incompleteResult
		if err := json.Unmarshal(stdout.Bytes(), &incomplete); err != nil || incomplete.MissingSlots != 1 || incomplete.Complete {
			t.Fatalf("unexpected incomplete result: %#v err=%v", incomplete, err)
		}
	})

	t.Run("partial bundle", func(t *testing.T) {
		fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
			testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
			testCase("case_b", "beta", "ios", "ios_simulator", "substitute"),
		})
		completed := time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC)
		fixture.writeReceipt(t, "a.json", testBinding(
			fixture.sourceHash, fixture.graph.ReadinessCases[0], completed, readiness.StatusPassed,
		))
		var stdout bytes.Buffer
		if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, nil)); exitCode != 1 {
			t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
		}
		var bundle readiness.ReadinessResultBundle
		if err := json.Unmarshal(stdout.Bytes(), &bundle); err != nil || len(bundle.Results) != 1 ||
			!bundle.GeneratedAt.Equal(completed) {
			t.Fatalf("unexpected partial bundle: %#v err=%v", bundle, err)
		}
	})

	t.Run("trusted failed receipt", func(t *testing.T) {
		fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
			testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
		})
		fixture.writeReceipt(t, "a.json", testBinding(
			fixture.sourceHash, fixture.graph.ReadinessCases[0],
			time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusFailed,
		))
		var stdout bytes.Buffer
		if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, nil)); exitCode != 1 {
			t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
		}
		var bundle readiness.ReadinessResultBundle
		if err := json.Unmarshal(stdout.Bytes(), &bundle); err != nil ||
			len(bundle.Results) != 1 || bundle.Results[0].Status != readiness.StatusFailed {
			t.Fatalf("non-passed receipt was not preserved: %#v err=%v", bundle, err)
		}
	})
}

func TestCollectorRejectsReceiptProtocolAndTrustViolations(t *testing.T) {
	tests := []struct {
		name   string
		setup  func(*testing.T, *collectorFixture)
		trust  error
		needle string
	}{
		{
			name: "extra receipt",
			setup: func(t *testing.T, fixture *collectorFixture) {
				contract := testCase("unknown_case", "alpha", "android", "android_emulator", "substitute")
				fixture.writeReceipt(t, "extra.json", testBinding(
					fixture.sourceHash, contract,
					time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
				))
			},
			needle: "does not match a graph-authored execution slot",
		},
		{
			name: "duplicate receipt",
			setup: func(t *testing.T, fixture *collectorFixture) {
				binding := testBinding(
					fixture.sourceHash, fixture.graph.ReadinessCases[0],
					time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
				)
				fixture.writeReceipt(t, "a.json", binding)
				fixture.writeReceipt(t, "b.json", binding)
			},
			needle: "duplicate one execution slot",
		},
		{
			name: "unsigned receipt",
			setup: func(t *testing.T, fixture *collectorFixture) {
				fixture.writeReceiptWithoutSignature(t, "a.json", testBinding(
					fixture.sourceHash, fixture.graph.ReadinessCases[0],
					time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
				))
			},
			needle: "is unsigned",
		},
		{
			name: "unknown field",
			setup: func(t *testing.T, fixture *collectorFixture) {
				writeTestFile(t, filepath.Join(fixture.receiptRoot, "a.json"), []byte(`{"binding":{},"evidenceSha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff","unknown":true}`))
				writeTestFile(t, filepath.Join(fixture.receiptRoot, "a.json.sig.json"), []byte(`{}`))
			},
			needle: "decode receipt",
		},
		{
			name: "signed trust rejection",
			setup: func(t *testing.T, fixture *collectorFixture) {
				fixture.writeReceipt(t, "a.json", testBinding(
					fixture.sourceHash, fixture.graph.ReadinessCases[0],
					time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
				))
			},
			trust:  errors.New("detached receipt signature is invalid"),
			needle: "detached receipt signature is invalid",
		},
		{
			name: "evidence digest drift",
			setup: func(t *testing.T, fixture *collectorFixture) {
				fixture.writeReceipt(t, "a.json", testBinding(
					fixture.sourceHash, fixture.graph.ReadinessCases[0],
					time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
				))
			},
			trust:  errors.New("content-addressed evidence digest mismatch"),
			needle: "content-addressed evidence digest mismatch",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
				testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
			})
			test.setup(t, fixture)
			var stdout bytes.Buffer
			if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(test.trust, nil)); exitCode != 2 {
				t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
			}
			if !strings.Contains(stdout.String(), test.needle) {
				t.Fatalf("output %q does not contain %q", stdout.String(), test.needle)
			}
		})
	}
}

func TestCollectorRejectsSymlinkAndReceiptTreeTOCTOU(t *testing.T) {
	t.Run("symlink", func(t *testing.T) {
		fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
			testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
		})
		outside := filepath.Join(fixture.root, "outside.json")
		writeTestFile(t, outside, []byte(`{}`))
		if err := os.Symlink(outside, filepath.Join(fixture.receiptRoot, "linked.json")); err != nil {
			t.Fatal(err)
		}
		var stdout bytes.Buffer
		if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, nil)); exitCode != 2 ||
			!strings.Contains(stdout.String(), "contains symlink") {
			t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
		}
	})

	t.Run("receipt tree changes after trust resolution", func(t *testing.T) {
		fixture := newCollectorFixture(t, []ast.ReadinessCaseContract{
			testCase("case_a", "alpha", "android", "android_emulator", "substitute"),
		})
		fixture.writeReceipt(t, "a.json", testBinding(
			fixture.sourceHash, fixture.graph.ReadinessCases[0],
			time.Date(2026, 8, 8, 1, 2, 3, 0, time.UTC), readiness.StatusPassed,
		))
		mutate := func() {
			writeTestFile(t, filepath.Join(fixture.receiptRoot, "a.json.sig.json"), []byte(`{"changed":true}`))
		}
		var stdout bytes.Buffer
		if exitCode := run(context.Background(), fixture.args(), &stdout, fixture.factory(nil, mutate)); exitCode != 2 ||
			!strings.Contains(stdout.String(), "receipt tree changed") {
			t.Fatalf("exit=%d output=%s", exitCode, stdout.String())
		}
	})
}

func newCollectorFixture(
	t *testing.T,
	cases []ast.ReadinessCaseContract,
) *collectorFixture {
	t.Helper()
	root := t.TempDir()
	receiptRoot := filepath.Join(root, "receipts")
	evidenceRoot := filepath.Join(root, "evidence")
	for _, directory := range []string{
		receiptRoot,
		filepath.Join(evidenceRoot, "sha256"),
	} {
		if err := os.MkdirAll(directory, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	current := graph.ContractGraph{
		ReadinessCases: cases,
		Sources: []ast.SourceDigest{{
			Path:   "services/example-service/contracts/example/context/operations.yaml",
			SHA256: strings.Repeat("a", 64),
		}},
	}
	sourceHash, err := readiness.ContractGraphSourceHash(&current)
	if err != nil {
		t.Fatal(err)
	}
	graphBytes, err := json.Marshal(current)
	if err != nil {
		t.Fatal(err)
	}
	graphPath := filepath.Join(root, "contract_graph.json")
	keyringPath := filepath.Join(root, "runner-keyring.json")
	writeTestFile(t, graphPath, graphBytes)
	writeTestFile(t, keyringPath, []byte(`{}`))
	return &collectorFixture{
		root: root, graphPath: graphPath,
		metadataDir: filepath.Clean(filepath.Join("..", "..", "contracts", "metadata")),
		keyringPath: keyringPath, receiptRoot: receiptRoot,
		evidenceRoot: evidenceRoot, graph: current, sourceHash: sourceHash,
	}
}

func (fixture *collectorFixture) args() []string {
	return []string{
		"--graph", fixture.graphPath,
		"--metadata-dir", fixture.metadataDir,
		"--runner-keyring", fixture.keyringPath,
		"--receipt-root", fixture.receiptRoot,
		"--evidence-root", fixture.evidenceRoot,
	}
}

func (fixture *collectorFixture) factory(
	resolverError error,
	mutate func(),
) resolverFactory {
	return func(
		receiptRoot string,
		_ string,
		_ []byte,
		_ *readiness.WireSchemas,
	) (readiness.ReceiptResolver, error) {
		return &fakeSignedResolver{
			root: receiptRoot, error: resolverError, mutate: mutate,
		}, nil
	}
}

func (fixture *collectorFixture) writeReceipt(
	t *testing.T,
	relative string,
	binding readiness.ReceiptBinding,
) {
	t.Helper()
	fixture.writeReceiptWithoutSignature(t, relative, binding)
	writeTestFile(t, filepath.Join(fixture.receiptRoot, filepath.FromSlash(relative)+".sig.json"), []byte(`{}`))
}

func (fixture *collectorFixture) writeReceiptWithoutSignature(
	t *testing.T,
	relative string,
	binding readiness.ReceiptBinding,
) {
	t.Helper()
	evidence := []byte("evidence:" + relative)
	evidenceDigest := sha256.Sum256(evidence)
	evidenceSHA256 := hex.EncodeToString(evidenceDigest[:])
	writeTestFile(
		t,
		filepath.Join(fixture.evidenceRoot, "sha256", evidenceSHA256),
		evidence,
	)
	data, err := json.Marshal(readiness.ReadinessReceipt{
		Binding: binding, EvidenceSHA256: evidenceSHA256,
	})
	if err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, filepath.Join(fixture.receiptRoot, filepath.FromSlash(relative)), data)
}

func testCase(
	caseID string,
	environment string,
	platform string,
	deviceClass string,
	provider string,
) ast.ReadinessCaseContract {
	return ast.ReadinessCaseContract{
		ObjectID: "example.example_context.example_object",
		SpecRef:  "specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001",
		CaseID:   caseID, Producer: ast.ReadinessProducerService,
		Layer: ast.ReadinessLayerLocalContract,
		Target: ast.ReadinessCaseTarget{
			Kind: ast.ReadinessTargetOperation,
			ID:   "example.example_object.GetExample",
		},
		RunnerSourcePath: "services/example-service/tests/local_contract/example/example_object/example__local_contract_test.go",
		SourcePath:       "services/example-service/contracts/example/example_object/operations.yaml",
		Executions: []ast.ReadinessExecutionRequirement{{
			Environment: environment, Platform: platform,
			DeviceClass: deviceClass, Provider: provider,
			DigestBinding: ast.ReadinessDigestCandidate,
		}},
	}
}

func testBinding(
	sourceHash string,
	contract ast.ReadinessCaseContract,
	completed time.Time,
	status readiness.Status,
) readiness.ReceiptBinding {
	execution := contract.Executions[0]
	return readiness.ReceiptBinding{
		ObjectID: contract.ObjectID, SpecRef: contract.SpecRef,
		CaseID: contract.CaseID, Producer: contract.Producer,
		Layer: contract.Layer, Status: status, Target: contract.Target,
		CommitSHA: strings.Repeat("b", 40), ContractGraphSourceHash: sourceHash,
		DeploymentTarget: execution.Environment + "-local", BaselineID: "baseline-current",
		PackageDigest:           "sha256:" + strings.Repeat("c", 64),
		ConfigurationDigest:     "sha256:" + strings.Repeat("d", 64),
		CandidateManifestSHA256: strings.Repeat("e", 64),
		CandidateDigest:         "sha256:" + strings.Repeat("1", 64),
		ReleaseDigest:           "sha256:" + strings.Repeat("2", 64),
		Environment:             execution.Environment, Platform: execution.Platform,
		DeviceClass: execution.DeviceClass, Provider: execution.Provider,
		StartedAt: completed.Add(-time.Minute), CompletedAt: completed,
		RunnerIdentity: "runner.current", RunnerSourcePath: contract.RunnerSourcePath,
		RemoteComposition: true, FixtureFree: true, DependenciesReady: true,
		ProviderVerified: true, PhysicalDevice: true,
	}
}

func writeTestFile(t *testing.T, path string, data []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}
