package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

func validContract(t *testing.T) contract {
	t.Helper()
	metadataRoot := filepath.Join("..", "..", "contracts", "metadata")
	source, err := contractcodegen.NewDocumentSource(
		metadataRoot,
		[]string{"_shared/semantic_document.yaml"},
	)
	if err != nil {
		t.Fatal(err)
	}
	c, err := loadContract(source, "_shared/semantic_document.yaml")
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func TestContractValidationFailsClosed(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*contract)
		want   string
	}{
		{"version triplet", func(c *contract) { c.SchemaVersion = "1.0" }, "exact major.minor.patch"},
		{"unknown disposition", func(c *contract) { c.ClosedSets.ProcessingDispositions[0] = "invented" }, "missing required value"},
		{"unknown capability", func(c *contract) {
			c.NodeRegistry["paragraph"] = nodeSpec{Status: "formal", RequiredCapabilities: []string{"parse.unknown"}}
		}, "unknown capability"},
		{"missing registry", func(c *contract) { c.InlineRegistry.Kinds = nil }, "registries must be non-empty"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := validContract(t)
			tc.mutate(&c)
			if err := validateContract(c); err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("validateContract() error = %v, want containing %q", err, tc.want)
			}
		})
	}
}

func TestCheckOutputsDetectsMissingStaleAndUnexpectedGeneratedFiles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "semantic_document.g.go")
	outputs := []output{{path: path, data: []byte("wanted")}}
	if err := checkOutputs(outputs); err == nil || !strings.Contains(err.Error(), "missing") {
		t.Fatalf("missing error = %v", err)
	}
	if err := os.WriteFile(path, []byte("stale"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := checkOutputs(outputs); err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("stale error = %v", err)
	}
	if err := os.WriteFile(path, []byte("wanted"), 0o644); err != nil {
		t.Fatal(err)
	}
	extra := filepath.Join(dir, "old.g.go")
	if err := os.WriteFile(extra, []byte("// "+generatedMarker), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := checkOutputs(outputs); err == nil || !strings.Contains(err.Error(), "unexpected") {
		t.Fatalf("unexpected output error = %v", err)
	}
}

func TestRenderAllCarriesSameVersionsAndTypedValidation(t *testing.T) {
	c := validContract(t)
	outputs, err := renderAll(c, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if len(outputs) != 7 {
		t.Fatalf("got %d outputs, want 7", len(outputs))
	}
	for _, out := range outputs {
		if strings.HasSuffix(out.path, "validator__local_contract_test.go") {
			continue
		}
		text := string(out.data)
		for _, token := range []string{"1.0.0", "requiredCapabilities", "DocumentEnvelope", "SemanticNode", "SemanticInline", "SourceAnchor", "SemanticLoss", "SemanticDiagnostic", "SemanticAsset"} {
			if !strings.Contains(text, token) {
				t.Errorf("%s missing %q", out.path, token)
			}
		}
	}
}

func TestWriteOutputAtomicallyReplacesTargetWithoutResidue(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "semantic_document.g.go")
	if err := os.WriteFile(path, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := writeOutputAtomically(output{path: path, data: []byte("new")}); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil || string(data) != "new" {
		t.Fatalf("output = %q, err = %v", data, err)
	}
	matches, err := filepath.Glob(filepath.Join(dir, ".semantic-document-*.tmp"))
	if err != nil || len(matches) != 0 {
		t.Fatalf("temporary residue = %v, err = %v", matches, err)
	}
}

func TestWriteOutputAtomicallyCleansTemporaryOnRenameFailure(t *testing.T) {
	dir := t.TempDir()
	targetDirectory := filepath.Join(dir, "target")
	if err := os.Mkdir(targetDirectory, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := writeOutputAtomically(output{path: targetDirectory, data: []byte("new")}); err == nil {
		t.Fatal("expected rename failure")
	}
	matches, err := filepath.Glob(filepath.Join(dir, ".semantic-document-*.tmp"))
	if err != nil || len(matches) != 0 {
		t.Fatalf("temporary residue = %v, err = %v", matches, err)
	}
}
