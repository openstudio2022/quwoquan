package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func TestGenerateErrorsCarriesHomepageTransportMetadata(t *testing.T) {
	source, err := contractcodegen.NewSource(filepath.Join("..", "..", "contracts", "metadata"), validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	outDir := t.TempDir()
	if err := generateErrors(source, outDir); err != nil {
		t.Fatalf("generate errors: %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(outDir, "generated", "errors.go"))
	if err != nil {
		t.Fatalf("read generated errors: %v", err)
	}
	for _, want := range []string{
		"AppErrorFromHomepageOffline",
		"WithMetadata(\"gone\", 410)",
		"AppErrorFromInvalidArgument",
		"WithMetadata(\"invalid_argument\", 400)",
	} {
		if !strings.Contains(string(generated), want) {
			t.Fatalf("generated entity errors missing %q:\n%s", want, generated)
		}
	}
}
