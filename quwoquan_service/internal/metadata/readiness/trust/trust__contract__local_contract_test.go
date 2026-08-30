package trust

import (
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
)

const (
	testRunnerIdentity = "runner.release-acceptance"
	testSnapshotKeyID  = "snapshot-authority-1"
	testRunnerKeyID    = "runner-key-1"
)

var testStartedAt = time.Date(2026, 8, 5, 2, 0, 0, 0, time.UTC)

func TestSignedSnapshotProviderVerifiesSignatureAndCurrentGraphBinding(t *testing.T) {
	graphValue := trustTestGraph()
	sourceHash, err := readiness.ContractGraphSourceHash(graphValue)
	if err != nil {
		t.Fatal(err)
	}
	publicKey, privateKey := deterministicKey(1)
	keyring := snapshotKeyringBytes(publicKey)
	payload := CurrentSnapshot{
		CommitSHA: strings.Repeat("a", 40), ContractGraphSourceHash: sourceHash,
		Deployments: EnvironmentDeployments{
			Alpha: trustDeployment("alpha", strings.Repeat("1", 64)),
			Beta:  trustDeployment("beta", strings.Repeat("2", 64)),
			Gamma: trustDeployment("gamma", strings.Repeat("3", 64)),
			Prod:  trustDeployment("prod", strings.Repeat("4", 64)),
		},
		CandidateDigest: "sha256:" + strings.Repeat("5", 64),
		ReleaseDigest:   "sha256:" + strings.Repeat("6", 64),
	}
	envelope := signedSnapshotBytes(t, payload, privateKey, testSnapshotKeyID)

	provider, err := NewSignedSnapshotProvider(envelope, keyring, testWireSchemas(t))
	if err != nil {
		t.Fatalf("NewSignedSnapshotProvider() error = %v", err)
	}
	resolved, err := provider.CurrentSnapshot(context.Background(), graphValue)
	if err != nil {
		t.Fatalf("CurrentSnapshot() error = %v", err)
	}
	if resolved.CommitSHA != payload.CommitSHA ||
		resolved.Deployments["prod"] != payload.Deployments.Prod {
		t.Fatalf("resolved=%+v, want exact signed snapshot", resolved)
	}

	t.Run("tampered payload", func(t *testing.T) {
		var current SignedCurrentSnapshot
		if err := json.Unmarshal(envelope, &current); err != nil {
			t.Fatal(err)
		}
		decoded, err := base64.StdEncoding.DecodeString(current.Payload)
		if err != nil {
			t.Fatal(err)
		}
		decoded[20] ^= 1
		current.Payload = base64.StdEncoding.EncodeToString(decoded)
		tampered, _ := json.Marshal(current)
		if _, err := NewSignedSnapshotProvider(tampered, keyring, testWireSchemas(t)); err == nil {
			t.Fatal("tampered snapshot unexpectedly trusted")
		}
	})

	t.Run("unknown key", func(t *testing.T) {
		_, unknownPrivate := deterministicKey(2)
		unknownEnvelope := signedSnapshotBytes(t, payload, unknownPrivate, "unknown-key")
		if _, err := NewSignedSnapshotProvider(unknownEnvelope, keyring, testWireSchemas(t)); err == nil {
			t.Fatal("unknown snapshot key unexpectedly trusted")
		}
	})

	t.Run("duplicate envelope identity", func(t *testing.T) {
		duplicate := strings.TrimSuffix(string(envelope), "}") +
			`,"keyId":"snapshot-authority-1"}`
		if _, err := NewSignedSnapshotProvider(
			[]byte(duplicate), keyring, testWireSchemas(t),
		); err == nil {
			t.Fatal("duplicate signed snapshot key unexpectedly accepted")
		}
	})

	t.Run("stale graph source hash", func(t *testing.T) {
		stale := trustTestGraph()
		stale.Sources[0].SHA256 = strings.Repeat("f", 64)
		if _, err := provider.CurrentSnapshot(context.Background(), stale); err == nil {
			t.Fatal("snapshot signed for another graph unexpectedly trusted")
		}
	})

	t.Run("mixed candidate packages", func(t *testing.T) {
		mixed := payload
		mixed.Deployments.Prod.PackageDigest = "sha256:" + strings.Repeat("f", 64)
		mixedEnvelope := signedSnapshotBytes(t, mixed, privateKey, testSnapshotKeyID)
		if _, err := NewSignedSnapshotProvider(
			mixedEnvelope, keyring, testWireSchemas(t),
		); err == nil {
			t.Fatal("four environments with mixed package digests unexpectedly trusted")
		}
	})

	t.Run("digest and sha256 wire formats are not interchangeable", func(t *testing.T) {
		bareDigest := payload
		bareDigest.CandidateDigest = strings.Repeat("5", 64)
		if _, err := NewSignedSnapshotProvider(
			signedSnapshotBytes(t, bareDigest, privateKey, testSnapshotKeyID),
			keyring, testWireSchemas(t),
		); err == nil {
			t.Fatal("bare candidateDigest unexpectedly trusted")
		}

		prefixedHash := payload
		prefixedHash.Deployments.Alpha.CandidateManifestSHA256 =
			"sha256:" + prefixedHash.Deployments.Alpha.CandidateManifestSHA256
		if _, err := NewSignedSnapshotProvider(
			signedSnapshotBytes(t, prefixedHash, privateKey, testSnapshotKeyID),
			keyring, testWireSchemas(t),
		); err == nil {
			t.Fatal("prefixed candidateManifestSha256 unexpectedly trusted")
		}
	})
}

func TestSignedReceiptResolverVerifiesExactReceiptAndEvidenceBytes(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		resolved, err := fixture.resolver.Resolve(context.Background(), fixture.result)
		if err != nil {
			t.Fatalf("Resolve() error = %v", err)
		}
		if !resolved.Trusted || resolved.Binding.Provider != "provider-live" ||
			resolved.Binding.DeviceClass != "physical" {
			t.Fatalf("resolved=%+v, want signed physical Provider binding", resolved)
		}
	})

	t.Run("content release UAT binding drift", func(t *testing.T) {
		mutations := map[string]func(*readiness.ReadinessCaseResult){
			"releaseId": func(result *readiness.ReadinessCaseResult) {
				result.ReleaseID = "content-release-drifted"
			},
			"targetUatBindingDigest": func(result *readiness.ReadinessCaseResult) {
				result.TargetUATBindingDigest = "sha256:" + strings.Repeat("f", 64)
			},
			"entrySurface": func(result *readiness.ReadinessCaseResult) {
				result.EntrySurface = "search"
			},
			"carrier": func(result *readiness.ReadinessCaseResult) {
				result.Carrier = "video"
			},
			"deviceIdentity": func(result *readiness.ReadinessCaseResult) {
				result.DeviceIdentity = "device.drifted"
			},
			"uatProfile": func(result *readiness.ReadinessCaseResult) {
				result.UATProfile = "production"
			},
			"nonPromotable": func(result *readiness.ReadinessCaseResult) {
				result.NonPromotable = !result.NonPromotable
			},
			"artifactClass": func(result *readiness.ReadinessCaseResult) {
				result.ArtifactClass = "production"
			},
			"physicalDevice": func(result *readiness.ReadinessCaseResult) {
				result.PhysicalDevice = !result.PhysicalDevice
			},
			"observedOutcome": func(result *readiness.ReadinessCaseResult) {
				result.ObservedOutcome = "empty"
			},
			"observedReleaseId": func(result *readiness.ReadinessCaseResult) {
				result.ObservedReleaseID = "content-release-drifted"
			},
			"previousReleaseId": func(result *readiness.ReadinessCaseResult) {
				result.PreviousReleaseID = "content-release-previous"
			},
			"reasonCode": func(result *readiness.ReadinessCaseResult) {
				result.ReasonCode = "stale_failure"
			},
		}
		for name, mutate := range mutations {
			t.Run(name, func(t *testing.T) {
				fixture := newReceiptFixture(t)
				drifted := fixture.result
				mutate(&drifted)
				if _, err := fixture.resolver.Resolve(context.Background(), drifted); err == nil {
					t.Fatalf("signed receipt with drifted %s unexpectedly trusted", name)
				}
			})
		}
	})

	t.Run("receipt tamper", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		appendFile(t, fixture.receiptPath, []byte("\n"))
		if _, err := fixture.resolver.Resolve(context.Background(), fixture.result); err == nil {
			t.Fatal("tampered exact receipt bytes unexpectedly trusted")
		}
	})

	t.Run("signature tamper", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		var signature DetachedReceiptSignature
		readJSONFile(t, fixture.receiptPath+".sig.json", &signature)
		decoded, _ := base64.StdEncoding.DecodeString(signature.Signature)
		decoded[0] ^= 1
		signature.Signature = base64.StdEncoding.EncodeToString(decoded)
		writeJSONFile(t, fixture.receiptPath+".sig.json", signature)
		if _, err := fixture.resolver.Resolve(context.Background(), fixture.result); err == nil {
			t.Fatal("tampered receipt signature unexpectedly trusted")
		}
	})

	t.Run("duplicate detached signature identity", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		var signature DetachedReceiptSignature
		readJSONFile(t, fixture.receiptPath+".sig.json", &signature)
		duplicate := []byte(`{"keyId":"` + signature.KeyID +
			`","keyId":"` + signature.KeyID + `","signature":"` +
			signature.Signature + `"}`)
		if err := os.WriteFile(fixture.receiptPath+".sig.json", duplicate, 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := fixture.resolver.Resolve(
			context.Background(), fixture.result,
		); err == nil {
			t.Fatal("duplicate detached signature key unexpectedly accepted")
		}
	})

	t.Run("unknown runner key", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		otherPublic, _ := deterministicKey(9)
		keyring := RunnerKeyring{
			Runners: []RunnerAuthority{{
				RunnerIdentity: "another-runner", KeyID: "another-key",
				PublicKey: base64.StdEncoding.EncodeToString(otherPublic),
			}},
		}
		keyringBytes, _ := json.Marshal(keyring)
		resolver, err := NewSignedReceiptResolver(
			fixture.receiptRoot, fixture.evidenceRoot, keyringBytes, testWireSchemas(t),
		)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := resolver.Resolve(context.Background(), fixture.result); err == nil {
			t.Fatal("receipt from unknown runner unexpectedly trusted")
		}
	})

	t.Run("evidence tamper", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		if err := os.WriteFile(fixture.evidencePath, []byte("tampered evidence"), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := fixture.resolver.Resolve(context.Background(), fixture.result); err == nil {
			t.Fatal("tampered evidence unexpectedly trusted")
		}
	})

	t.Run("evidence symlink", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		original, err := os.ReadFile(fixture.evidencePath)
		if err != nil {
			t.Fatal(err)
		}
		outside := filepath.Join(t.TempDir(), "outside-proof")
		if err := os.WriteFile(outside, original, 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.Remove(fixture.evidencePath); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(outside, fixture.evidencePath); err != nil {
			t.Fatal(err)
		}
		if _, err := fixture.resolver.Resolve(context.Background(), fixture.result); err == nil {
			t.Fatal("symlink evidence unexpectedly allowed")
		}
	})

	t.Run("path escape", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		result := fixture.result
		result.ArtifactPath = "../receipt.json"
		if _, err := fixture.resolver.Resolve(context.Background(), result); err == nil {
			t.Fatal("parent path escape unexpectedly allowed")
		}
	})

	t.Run("symlink", func(t *testing.T) {
		fixture := newReceiptFixture(t)
		outside := filepath.Join(t.TempDir(), "outside.json")
		if err := os.WriteFile(outside, []byte("{}"), 0o600); err != nil {
			t.Fatal(err)
		}
		link := filepath.Join(fixture.receiptRoot, "linked.json")
		if err := os.Symlink(outside, link); err != nil {
			t.Fatal(err)
		}
		result := fixture.result
		result.ArtifactPath = "linked.json"
		if _, err := fixture.resolver.Resolve(context.Background(), result); err == nil {
			t.Fatal("symlink receipt unexpectedly allowed")
		}
	})
}

type receiptFixture struct {
	resolver     *SignedReceiptResolver
	result       readiness.ReadinessCaseResult
	receiptRoot  string
	evidenceRoot string
	receiptPath  string
	evidencePath string
}

func newReceiptFixture(t *testing.T) receiptFixture {
	t.Helper()
	receiptRoot := filepath.Join(t.TempDir(), "receipts")
	evidenceRoot := filepath.Join(t.TempDir(), "evidence")
	if err := os.MkdirAll(receiptRoot, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(evidenceRoot, "sha256"), 0o700); err != nil {
		t.Fatal(err)
	}
	publicKey, privateKey := deterministicKey(3)
	keyring := RunnerKeyring{
		Runners: []RunnerAuthority{{
			RunnerIdentity: testRunnerIdentity, KeyID: testRunnerKeyID,
			PublicKey: base64.StdEncoding.EncodeToString(publicKey),
		}},
	}
	keyringBytes, _ := json.Marshal(keyring)
	resolver, err := NewSignedReceiptResolver(
		receiptRoot, evidenceRoot, keyringBytes, testWireSchemas(t),
	)
	if err != nil {
		t.Fatal(err)
	}
	evidence := []byte("external provider and physical-device proof")
	evidenceDigest := sha256.Sum256(evidence)
	evidenceSHA := hex.EncodeToString(evidenceDigest[:])
	evidencePath := filepath.Join(evidenceRoot, "sha256", evidenceSHA)
	if err := os.WriteFile(evidencePath, evidence, 0o600); err != nil {
		t.Fatal(err)
	}
	result := readiness.ReadinessCaseResult{
		ObjectID: "assistant.assistant_run",
		SpecRef:  "specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003",
		CaseID:   "physical-uat", Producer: readiness.ProducerApp,
		Layer: readiness.LayerUserAcceptance, Status: readiness.StatusPassed,
		Target:    readiness.ReadinessTarget{Kind: readiness.TargetPage, ID: "assistant.personal_session"},
		CommitSHA: strings.Repeat("a", 40), ContractGraphSourceHash: strings.Repeat("b", 64),
		DeploymentTarget: "assistant-alpha", BaselineID: "baseline-2026-08-05",
		PackageDigest: "sha256:" + strings.Repeat("9", 64), ConfigurationDigest: "sha256:" + strings.Repeat("c", 64),
		CandidateManifestSHA256: strings.Repeat("8", 64), CandidateDigest: "sha256:" + strings.Repeat("d", 64),
		ReleaseDigest:          "sha256:" + strings.Repeat("e", 64),
		ReleaseID:              "content-release-2026-08-29",
		TargetUATBindingDigest: "sha256:" + strings.Repeat("7", 64),
		EntrySurface:           "feed", Carrier: "article",
		DeviceIdentity:    "device.pixel-9.fixture",
		UATProfile:        "rehearsal",
		NonPromotable:     true,
		ArtifactClass:     "production_behavior",
		PhysicalDevice:    false,
		ObservedOutcome:   "content",
		ObservedReleaseID: "content-release-2026-08-29",
		Environment:       "alpha", Platform: "android", DeviceClass: "physical",
		Provider: "provider-live", StartedAt: testStartedAt,
		CompletedAt: testStartedAt.Add(time.Minute), RunnerIdentity: testRunnerIdentity,
		ArtifactPath: "physical-uat.json",
	}
	receipt := readiness.ReadinessReceipt{
		Binding: readiness.ReceiptBinding{
			ObjectID: result.ObjectID, SpecRef: result.SpecRef, CaseID: result.CaseID,
			Producer: result.Producer, Layer: result.Layer, Status: result.Status,
			Target: result.Target, CommitSHA: result.CommitSHA,
			ContractGraphSourceHash: result.ContractGraphSourceHash,
			DeploymentTarget:        result.DeploymentTarget, BaselineID: result.BaselineID,
			PackageDigest: result.PackageDigest, ConfigurationDigest: result.ConfigurationDigest,
			CandidateManifestSHA256: result.CandidateManifestSHA256,
			CandidateDigest:         result.CandidateDigest,
			ReleaseDigest:           result.ReleaseDigest,
			ReleaseID:               result.ReleaseID,
			TargetUATBindingDigest:  result.TargetUATBindingDigest,
			EntrySurface:            result.EntrySurface,
			Carrier:                 result.Carrier,
			DeviceIdentity:          result.DeviceIdentity,
			UATProfile:              result.UATProfile,
			NonPromotable:           result.NonPromotable,
			ArtifactClass:           result.ArtifactClass,
			PhysicalDevice:          result.PhysicalDevice,
			ObservedOutcome:         result.ObservedOutcome,
			ObservedReleaseID:       result.ObservedReleaseID,
			Environment:             result.Environment, Platform: result.Platform,
			DeviceClass: result.DeviceClass, Provider: result.Provider,
			StartedAt: result.StartedAt, CompletedAt: result.CompletedAt,
			RunnerIdentity:    result.RunnerIdentity,
			RunnerSourcePath:  "quwoquan_app/test/user_acceptance/service/assistant_service/assistant/assistant_run/readiness_case_test.dart",
			RemoteComposition: true, FixtureFree: true, DependenciesReady: true,
		},
		EvidenceSHA256: evidenceSHA,
	}
	receiptBytes, _ := json.Marshal(receipt)
	receiptDigest := sha256.Sum256(receiptBytes)
	result.ArtifactSHA256 = hex.EncodeToString(receiptDigest[:])
	receiptPath := filepath.Join(receiptRoot, result.ArtifactPath)
	if err := os.WriteFile(receiptPath, receiptBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	signature := DetachedReceiptSignature{
		KeyID: testRunnerKeyID,
		Signature: base64.StdEncoding.EncodeToString(
			ed25519.Sign(privateKey, ReceiptSigningMessage(receiptBytes)),
		),
	}
	writeJSONFile(t, receiptPath+".sig.json", signature)
	return receiptFixture{
		resolver: resolver, result: result, receiptRoot: receiptRoot,
		evidenceRoot: evidenceRoot, receiptPath: receiptPath, evidencePath: evidencePath,
	}
}

func trustDeployment(environment, configurationDigest string) readiness.DeploymentBinding {
	return readiness.DeploymentBinding{
		DeploymentTarget:        "assistant-" + environment,
		BaselineID:              "baseline-2026-08-05",
		PackageDigest:           "sha256:" + strings.Repeat("7", 64),
		ConfigurationDigest:     "sha256:" + configurationDigest,
		CandidateManifestSHA256: strings.Repeat("8", 64),
	}
}

func trustTestGraph() *graph.ContractGraph {
	return &graph.ContractGraph{Sources: []ast.SourceDigest{{
		Path: "assistant/assistant_run/operations.yaml", SHA256: strings.Repeat("b", 64),
	}}}
}

func deterministicKey(seedByte byte) (ed25519.PublicKey, ed25519.PrivateKey) {
	seed := bytesOf(seedByte, ed25519.SeedSize)
	privateKey := ed25519.NewKeyFromSeed(seed)
	return privateKey.Public().(ed25519.PublicKey), privateKey
}

func bytesOf(value byte, size int) []byte {
	result := make([]byte, size)
	for index := range result {
		result[index] = value
	}
	return result
}

func snapshotKeyringBytes(publicKey ed25519.PublicKey) []byte {
	data, _ := json.Marshal(SnapshotKeyring{
		Authorities: []SnapshotAuthority{{
			KeyID:     testSnapshotKeyID,
			PublicKey: base64.StdEncoding.EncodeToString(publicKey),
		}},
	})
	return data
}

func signedSnapshotBytes(
	t *testing.T,
	payload CurrentSnapshot,
	privateKey ed25519.PrivateKey,
	keyID string,
) []byte {
	t.Helper()
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := json.Marshal(SignedCurrentSnapshot{
		KeyID:   keyID,
		Payload: base64.StdEncoding.EncodeToString(payloadBytes),
		Signature: base64.StdEncoding.EncodeToString(
			ed25519.Sign(privateKey, SnapshotSigningMessage(payloadBytes)),
		),
	})
	if err != nil {
		t.Fatal(err)
	}
	return envelope
}

func appendFile(t *testing.T, path string, data []byte) {
	t.Helper()
	file, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if _, err := file.Write(data); err != nil {
		t.Fatal(err)
	}
}

func readJSONFile(t *testing.T, path string, target any) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatal(err)
	}
}

func writeJSONFile(t *testing.T, path string, value any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func testWireSchemas(t *testing.T) *readiness.WireSchemas {
	t.Helper()
	_, currentFile, _, _ := runtime.Caller(0)
	metadataDir := filepath.Clean(filepath.Join(
		filepath.Dir(currentFile), "..", "..", "..", "..", "contracts", "metadata",
	))
	schemas, err := readiness.LoadWireSchemas(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	return schemas
}
