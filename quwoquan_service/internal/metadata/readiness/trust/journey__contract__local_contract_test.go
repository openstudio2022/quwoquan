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
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/readiness"
)

func TestSignedJourneyCaseAuthorityBindsCompleteCatalogToCurrentGraph(t *testing.T) {
	current := trustTestGraph()
	sourceHash, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		t.Fatal(err)
	}
	publicKey, privateKey := deterministicKey(21)
	catalog := readiness.JourneyCaseCatalog{
		Journeys: []readiness.JourneyDefinition{{
			JourneyID: "startup_recovery",
			SpecRef:   "specs/feature-tree/spec.md#uat-001",
		}},
		Cases: []readiness.JourneyCaseContract{{
			JourneyID: "startup_recovery",
			SpecRef:   "specs/feature-tree/spec.md#uat-001",
			CaseID:    "physical-uat",
			Producer:  readiness.ProducerApp,
			Layer:     readiness.LayerUserAcceptance,
			Target: readiness.JourneyTarget{
				Kind: readiness.JourneyTargetJourney, ID: "startup_recovery",
			},
			RunnerSourcePath: "quwoquan_app/test/user_acceptance/journeys/startup_recovery/case_test.dart",
			Executions: []readiness.ExecutionRequirement{{
				Environment: "alpha", Platform: "android", DeviceClass: "physical",
				Provider: "provider-live", DigestBinding: readiness.DigestCandidate,
			}},
		}},
	}
	payloadBytes, err := json.Marshal(CurrentJourneyCatalog{
		ContractGraphSourceHash: sourceHash,
		Catalog:                 catalog,
	})
	if err != nil {
		t.Fatal(err)
	}
	envelopeBytes, err := json.Marshal(SignedCurrentJourneyCatalog{
		KeyID:   "journey-authority-1",
		Payload: base64.StdEncoding.EncodeToString(payloadBytes),
		Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(
			privateKey, JourneyCatalogSigningMessage(payloadBytes),
		)),
	})
	if err != nil {
		t.Fatal(err)
	}
	keyringBytes, err := json.Marshal(JourneyCatalogKeyring{
		Authorities: []JourneyCatalogAuthority{{
			KeyID:     "journey-authority-1",
			PublicKey: base64.StdEncoding.EncodeToString(publicKey),
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	authority, err := NewSignedJourneyCaseAuthority(envelopeBytes, keyringBytes)
	if err != nil {
		t.Fatalf("NewSignedJourneyCaseAuthority() error = %v", err)
	}
	resolved, err := authority.CurrentJourneyCatalog(context.Background(), current)
	if err != nil {
		t.Fatalf("CurrentJourneyCatalog() error = %v", err)
	}
	if len(resolved.Journeys) != 1 || len(resolved.Cases) != 1 {
		t.Fatalf("resolved catalog = %+v", resolved)
	}
	resolved.Cases[0].Executions[0].Provider = "mutated"
	again, err := authority.CurrentJourneyCatalog(context.Background(), current)
	if err != nil || again.Cases[0].Executions[0].Provider != "provider-live" {
		t.Fatalf("authority leaked mutable catalog: catalog=%+v err=%v", again, err)
	}
	stale := trustTestGraph()
	stale.Sources = append(stale.Sources, ast.SourceDigest{
		Path: "specs/feature-tree/spec.md", SHA256: strings.Repeat("c", 64),
	})
	if _, err := authority.CurrentJourneyCatalog(context.Background(), stale); err == nil {
		t.Fatal("stale ContractGraph accepted by signed Journey case authority")
	}
}

func TestSignedJourneyReceiptResolverUsesDistinctSignatureAndEvidence(t *testing.T) {
	root := t.TempDir()
	receiptRoot := filepath.Join(root, "receipts")
	evidenceRoot := filepath.Join(root, "evidence")
	if err := os.MkdirAll(filepath.Join(receiptRoot, "cases"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(evidenceRoot, "sha256"), 0o700); err != nil {
		t.Fatal(err)
	}
	publicKey, privateKey := deterministicKey(22)
	keyringBytes, err := json.Marshal(RunnerKeyring{
		Runners: []RunnerAuthority{{
			RunnerIdentity: "runner.journey-uat", KeyID: "journey-runner-key-1",
			PublicKey: base64.StdEncoding.EncodeToString(publicKey),
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	resolver, err := NewSignedJourneyReceiptResolver(
		receiptRoot, evidenceRoot, keyringBytes, testWireSchemas(t),
	)
	if err != nil {
		t.Fatal(err)
	}
	startedAt := time.Date(2026, 8, 5, 4, 0, 0, 0, time.UTC)
	result := readiness.JourneyReadinessCaseResult{
		JourneyID: "startup_recovery", SpecRef: "specs/feature-tree/spec.md#uat-001",
		CaseID: "physical-uat", Producer: readiness.ProducerApp,
		Layer: readiness.LayerUserAcceptance, Status: readiness.StatusPassed,
		Target: readiness.JourneyTarget{
			Kind: readiness.JourneyTargetJourney, ID: "startup_recovery",
		},
		CommitSHA:               strings.Repeat("a", 40),
		ContractGraphSourceHash: strings.Repeat("b", 64),
		DeploymentTarget:        "journey-alpha",
		BaselineID:              "baseline-2026-08-05",
		PackageDigest:           "sha256:" + strings.Repeat("3", 64),
		ConfigurationDigest:     "sha256:" + strings.Repeat("1", 64),
		CandidateManifestSHA256: strings.Repeat("4", 64),
		CandidateDigest:         "sha256:" + strings.Repeat("2", 64),
		Environment:             "alpha", Platform: "android", DeviceClass: "physical",
		Provider: "provider-live", StartedAt: startedAt,
		CompletedAt: startedAt.Add(time.Second), RunnerIdentity: "runner.journey-uat",
		ArtifactPath: "cases/startup-recovery-alpha-android.json",
	}
	evidence := []byte("physical-device-provider-receipt")
	evidenceDigest := sha256.Sum256(evidence)
	evidenceSHA := hex.EncodeToString(evidenceDigest[:])
	if err := os.WriteFile(
		filepath.Join(evidenceRoot, "sha256", evidenceSHA), evidence, 0o600,
	); err != nil {
		t.Fatal(err)
	}
	receipt := readiness.JourneyReadinessReceipt{
		Binding: readiness.JourneyReceiptBinding{
			JourneyID: result.JourneyID, SpecRef: result.SpecRef, CaseID: result.CaseID,
			Producer: result.Producer, Layer: result.Layer, Status: result.Status,
			Target: result.Target, CommitSHA: result.CommitSHA,
			ContractGraphSourceHash: result.ContractGraphSourceHash,
			DeploymentTarget:        result.DeploymentTarget,
			BaselineID:              result.BaselineID,
			PackageDigest:           result.PackageDigest,
			ConfigurationDigest:     result.ConfigurationDigest,
			CandidateManifestSHA256: result.CandidateManifestSHA256,
			CandidateDigest:         result.CandidateDigest, ReleaseDigest: result.ReleaseDigest,
			Environment: result.Environment, Platform: result.Platform,
			DeviceClass: result.DeviceClass, Provider: result.Provider,
			StartedAt: result.StartedAt, CompletedAt: result.CompletedAt,
			RunnerIdentity:    result.RunnerIdentity,
			RunnerSourcePath:  "quwoquan_app/test/user_acceptance/journeys/startup_recovery/case_test.dart",
			RemoteComposition: true, FixtureFree: true, DependenciesReady: true,
			ProviderVerified: true, PhysicalDevice: true,
		},
		EvidenceSHA256: evidenceSHA,
	}
	receiptBytes, err := json.Marshal(receipt)
	if err != nil {
		t.Fatal(err)
	}
	receiptDigest := sha256.Sum256(receiptBytes)
	result.ArtifactSHA256 = hex.EncodeToString(receiptDigest[:])
	receiptPath := filepath.Join(receiptRoot, filepath.FromSlash(result.ArtifactPath))
	if err := os.WriteFile(receiptPath, receiptBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	writeSignature := func(message []byte) {
		t.Helper()
		writeJSONFile(t, receiptPath+".sig.json", DetachedReceiptSignature{
			KeyID: "journey-runner-key-1",
			Signature: base64.StdEncoding.EncodeToString(
				ed25519.Sign(privateKey, message),
			),
		})
	}
	writeSignature(JourneyReceiptSigningMessage(receiptBytes))
	resolved, err := resolver.ResolveJourney(context.Background(), result)
	if err != nil || !resolved.Trusted {
		t.Fatalf("ResolveJourney() = %+v, %v", resolved, err)
	}

	// A valid object-readiness signature is not valid in the Journey domain.
	writeSignature(ReceiptSigningMessage(receiptBytes))
	if _, err := resolver.ResolveJourney(context.Background(), result); err == nil {
		t.Fatal("object receipt signature substituted for Journey receipt signature")
	}
}

var _ readiness.JourneyCaseAuthority = (*SignedJourneyCaseAuthority)(nil)
var _ readiness.JourneyReceiptResolver = (*SignedJourneyReceiptResolver)(nil)
