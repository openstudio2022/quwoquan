package readiness

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestJourneyBundleSchemaAcceptsCanonicalWireAndRejectsObjectIdentity(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	resolver := memoryJourneyReceiptResolver{}
	results := journeyResults(graphValue, catalog.Cases, resolver)
	bundle := JourneyReadinessResultBundle{
		GeneratedAt: journeyTestStart(), Results: results,
	}
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	if err := ValidateJourneyBundleSchema(metadataDir, bundle); err != nil {
		t.Fatalf("ValidateJourneyBundleSchema: %v", err)
	}

	withObjectID := `{
      "generatedAt":"2026-08-05T02:00:00Z",
      "results":[{"objectId":"runtime.shell"}]
    }`
	if _, err := DecodeJourneyBundle(strings.NewReader(withObjectID)); err == nil {
		t.Fatal("Journey bundle accepted invented objectId")
	}
	withSecret := `{
      "generatedAt":"2026-08-05T02:00:00Z",
      "results":[],
      "token":"must-not-enter-the-wire"
    }`
	if _, err := DecodeJourneyBundle(strings.NewReader(withSecret)); err == nil {
		t.Fatal("Journey bundle accepted unknown secret field")
	}
	if _, err := DecodeJourneyBundle(strings.NewReader(
		`{"generatedAt":"2026-08-05T02:00:00Z","results":[]} {}`,
	)); err == nil {
		t.Fatal("Journey bundle accepted trailing JSON document")
	}
}

func TestJourneyBundleSchemaRejectsProducerLayerAndEndpointIdentity(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	for name, mutate := range map[string]func(*JourneyReadinessCaseResult){
		"service producer": func(result *JourneyReadinessCaseResult) {
			result.Producer = ProducerService
		},
		"app environment layer": func(result *JourneyReadinessCaseResult) {
			result.Producer = ProducerApp
			result.Layer = LayerEnvironmentAcceptance
		},
		"provider endpoint": func(result *JourneyReadinessCaseResult) {
			result.Provider = "https://provider.example"
		},
		"receipt endpoint": func(result *JourneyReadinessCaseResult) {
			result.ReceiptRef = "https://receipt.example/proof"
		},
	} {
		t.Run(name, func(t *testing.T) {
			resolver := memoryJourneyReceiptResolver{}
			results := journeyResults(graphValue, catalog.Cases, resolver)
			mutate(&results[0])
			bundle := JourneyReadinessResultBundle{
				GeneratedAt: journeyTestStart(), Results: results,
			}
			if err := ValidateJourneyBundleSchema(metadataDir, bundle); err == nil {
				t.Fatal("invalid Journey wire passed schema validation")
			}
		})
	}
}

func TestJourneyReceiptDecoderAndFileResolverRemainUntrusted(t *testing.T) {
	graphValue := journeyTestGraph()
	catalog := completeJourneyCatalog()
	resolved := memoryJourneyReceiptResolver{}
	result := journeyResults(graphValue, catalog.Cases[:1], resolved)[0]
	receipt := JourneyReadinessReceipt{
		Binding:        resolved[result.ReceiptRef].Binding,
		EvidenceSHA256: strings.Repeat("f", 64),
	}
	data, err := json.Marshal(receipt)
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	path := filepath.Join(root, "receipt.json")
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	result.ReceiptRef = ""
	result.ArtifactPath = "receipt.json"
	fileReceipt, err := (FileJourneyReceiptResolver{Root: root}).ResolveJourney(
		context.Background(), result,
	)
	if err != nil {
		t.Fatalf("ResolveJourney: %v", err)
	}
	if fileReceipt.Trusted {
		t.Fatal("local Journey receipt file self-promoted to trusted evidence")
	}

	unknownSecret := strings.TrimSuffix(string(data), "}") + `,"credential":"secret"}`
	if _, err := DecodeJourneyReceipt(strings.NewReader(unknownSecret)); err == nil {
		t.Fatal("Journey receipt accepted an unknown secret field")
	}
	if _, err := DecodeJourneyReceipt(strings.NewReader(string(data) + ` {}`)); err == nil {
		t.Fatal("Journey receipt accepted a trailing JSON document")
	}
}
