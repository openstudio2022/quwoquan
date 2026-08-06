package readiness

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadinessResultBundleSchemaAcceptsCanonicalWire(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	bundle := ReadinessResultBundle{
		GeneratedAt: testStart,
		Results: []ReadinessCaseResult{
			resultFor(contract, execution, "receipt/stable", bytes),
		},
	}
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	if err := ValidateBundleSchema(metadataDir, bundle); err != nil {
		t.Fatalf("ValidateBundleSchema: %v", err)
	}
}

func TestReadinessDigestWireSeparatesDigestFromSHA256Fields(t *testing.T) {
	contract := completeCaseContracts()[0]
	canonical := resultFor(
		contract, contract.Executions[0], "receipt/stable", []byte("receipt"),
	)
	canonical.ReleaseDigest = "sha256:" + strings.Repeat("e", 64)
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	mutations := map[string]func(*ReadinessCaseResult){
		"bare package digest": func(result *ReadinessCaseResult) {
			result.PackageDigest = strings.Repeat("4", 64)
		},
		"bare configuration digest": func(result *ReadinessCaseResult) {
			result.ConfigurationDigest = strings.Repeat("c", 64)
		},
		"bare candidate digest": func(result *ReadinessCaseResult) {
			result.CandidateDigest = strings.Repeat("d", 64)
		},
		"bare release digest": func(result *ReadinessCaseResult) {
			result.ReleaseDigest = strings.Repeat("e", 64)
		},
		"prefixed graph hash": func(result *ReadinessCaseResult) {
			result.ContractGraphSourceHash = "sha256:" + result.ContractGraphSourceHash
		},
		"prefixed candidate manifest sha256": func(result *ReadinessCaseResult) {
			result.CandidateManifestSHA256 = "sha256:" + result.CandidateManifestSHA256
		},
		"prefixed artifact sha256": func(result *ReadinessCaseResult) {
			result.ArtifactSHA256 = "sha256:" + result.ArtifactSHA256
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			result := canonical
			mutate(&result)
			bundle := ReadinessResultBundle{
				GeneratedAt: testStart, Results: []ReadinessCaseResult{result},
			}
			if err := ValidateBundleSchema(metadataDir, bundle); err == nil {
				t.Fatal("non-canonical digest/hash representation entered readiness wire")
			}
		})
	}
}

func TestDecodeBundleRejectsUnknownSecretAndTrailingDocuments(t *testing.T) {
	unknownSecret := `{
      "generatedAt":"2026-08-05T01:00:00Z",
      "results":[],
      "token":"must-not-enter-the-wire"
    }`
	if _, err := DecodeBundle(strings.NewReader(unknownSecret)); err == nil {
		t.Fatal("DecodeBundle accepted an unknown secret field")
	}
	if _, err := DecodeBundle(strings.NewReader(`{"generatedAt":"2026-08-05T01:00:00Z","results":[]} {}`)); err == nil {
		t.Fatal("DecodeBundle accepted a trailing JSON document")
	}
}

func TestWireSchemaAuthorityRejectsDuplicateKeysAndMissingDeploymentBinding(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	schemas, err := LoadWireSchemas(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	duplicate := `{"generatedAt":"2026-08-05T01:00:00Z","generatedAt":"2026-08-05T02:00:00Z","results":[]}`
	if _, err := schemas.DecodeBundle(strings.NewReader(duplicate)); err == nil {
		t.Fatal("schema authority accepted duplicate signed identity key")
	}

	contract := completeCaseContracts()[0]
	result := resultFor(contract, contract.Executions[0], "receipt/stable", []byte("receipt"))
	bundle := ReadinessResultBundle{GeneratedAt: testStart, Results: []ReadinessCaseResult{result}}
	data, err := json.Marshal(bundle)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	results := document["results"].([]any)
	delete(results[0].(map[string]any), "packageDigest")
	data, err = json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := schemas.DecodeBundle(bytes.NewReader(data)); err == nil {
		t.Fatal("schema authority accepted result without packageDigest")
	}
}

func TestWireSchemaAuthorityRejectsSymlinkedSchemaRoot(t *testing.T) {
	canonical, err := filepath.Abs(
		filepath.Join("..", "..", "..", "contracts", "metadata"),
	)
	if err != nil {
		t.Fatal(err)
	}
	symlink := filepath.Join(t.TempDir(), "metadata")
	if err := os.Symlink(canonical, symlink); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadWireSchemas(symlink); err == nil {
		t.Fatal("symlinked metadata schema authority unexpectedly accepted")
	}

	root := t.TempDir()
	metadata := filepath.Join(root, "metadata")
	if err := os.Mkdir(metadata, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(canonical, "_schemas"), filepath.Join(metadata, "_schemas")); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadWireSchemas(metadata); err == nil {
		t.Fatal("symlinked canonical _schemas authority unexpectedly accepted")
	}
}

func TestWireSchemaAuthorityRejectsDirectoryReplacement(t *testing.T) {
	metadata := filepath.Join(t.TempDir(), "metadata")
	schemas := filepath.Join(metadata, "_schemas")
	if err := os.MkdirAll(schemas, 0o700); err != nil {
		t.Fatal(err)
	}
	metadataRoot, metadataInfo, schemaRoot, schemaInfo, err := stableSchemaRoots(metadata)
	if err != nil {
		t.Fatal(err)
	}
	retired := schemaRoot + ".retired"
	if err := os.Rename(schemaRoot, retired); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(schemaRoot, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := verifyStableSchemaRoots(
		metadataRoot, metadataInfo, schemaRoot, schemaInfo,
	); err == nil {
		t.Fatal("replaced canonical _schemas directory unexpectedly remained trusted")
	}
}

func TestDecodeReceiptRejectsUnknownSecretAndTrailingDocuments(t *testing.T) {
	unknownSecret := `{
      "binding":{},
      "evidenceSha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "credential":"must-not-enter-the-receipt"
    }`
	if _, err := DecodeReceipt(strings.NewReader(unknownSecret)); err == nil {
		t.Fatal("DecodeReceipt accepted an unknown secret field")
	}
	if _, err := DecodeReceipt(strings.NewReader(`{"binding":{},"evidenceSha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"} {}`)); err == nil {
		t.Fatal("DecodeReceipt accepted a trailing JSON document")
	}
}

func TestReceiptSchemaRequiresCompleteDeploymentAndRejectsUnknownProofFields(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	schemas, err := LoadWireSchemas(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	contract := completeCaseContracts()[0]
	result := resultFor(contract, contract.Executions[0], "receipt/stable", []byte("receipt"))
	receipt := ReadinessReceipt{
		Binding: receiptBindingForResult(result), EvidenceSHA256: strings.Repeat("f", 64),
	}
	data, err := json.Marshal(receipt)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := schemas.DecodeReceipt(bytes.NewReader(data)); err != nil {
		t.Fatalf("canonical receipt rejected: %v", err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	binding := document["binding"].(map[string]any)
	delete(binding, "candidateManifestSha256")
	binding["credential"] = "must-not-enter-receipt"
	data, err = json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := schemas.DecodeReceipt(bytes.NewReader(data)); err == nil {
		t.Fatal("receipt schema accepted missing deployment identity and unknown secret")
	}
}

func TestReadinessResultBundleSchemaRejectsEndpointShapedIdentities(t *testing.T) {
	contract := completeCaseContracts()[0]
	execution := contract.Executions[0]
	bytes := []byte("receipt")
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	for name, mutate := range map[string]func(*ReadinessCaseResult){
		"producer layer mismatch": func(result *ReadinessCaseResult) {
			result.Producer = ProducerOps
		},
		"provider endpoint": func(result *ReadinessCaseResult) {
			result.Provider = "https://provider.example"
		},
		"receipt endpoint": func(result *ReadinessCaseResult) {
			result.ReceiptRef = "https://receipt.example/proof"
		},
		"absolute artifact path": func(result *ReadinessCaseResult) {
			result.ReceiptRef = ""
			result.ArtifactPath = "/private/runner/receipt.json"
		},
	} {
		t.Run(name, func(t *testing.T) {
			result := resultFor(contract, execution, "receipt/stable", bytes)
			mutate(&result)
			bundle := ReadinessResultBundle{
				GeneratedAt: testStart,
				Results:     []ReadinessCaseResult{result},
			}
			if err := ValidateBundleSchema(metadataDir, bundle); err == nil {
				t.Fatal("endpoint-shaped identity entered the canonical readiness wire")
			}
		})
	}
}

func TestFileReceiptResolverRejectsPathAndSymlinkEscape(t *testing.T) {
	root := t.TempDir()
	inside := filepath.Join(root, "receipt.json")
	contract := completeCaseContracts()[0]
	result := resultFor(contract, contract.Executions[0], "", []byte("unused"))
	result.ReceiptRef = ""
	result.ArtifactPath = "receipt.json"
	receiptBytes, err := json.Marshal(ReadinessReceipt{
		Binding:        receiptBindingForResult(result),
		EvidenceSHA256: strings.Repeat("f", 64),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(inside, receiptBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	resolver := FileReceiptResolver{Root: root}
	resolved, err := resolver.Resolve(context.Background(), result)
	if err != nil || string(resolved.Bytes) != string(receiptBytes) ||
		resolved.Binding != receiptBindingForResult(result) {
		t.Fatalf("inside receipt=%+v err=%v", resolved, err)
	}

	outsideRoot := t.TempDir()
	outside := filepath.Join(outsideRoot, "secret")
	if err := os.WriteFile(outside, []byte("secret"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := resolver.Resolve(context.Background(), ReadinessCaseResult{ArtifactPath: outside}); err == nil {
		t.Fatal("absolute path escape was accepted")
	}
	link := filepath.Join(root, "linked-receipt")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	if _, err := resolver.Resolve(context.Background(), ReadinessCaseResult{ArtifactPath: "linked-receipt"}); err == nil {
		t.Fatal("symlink escape was accepted")
	}
}
