package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestGenerateErrorsCarriesHomepageTransportMetadata(t *testing.T) {
	source, err := contractcodegen.NewSource(contractsview.Build(t), validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	outDir := t.TempDir()
	if err := generateErrors(source, outDir, false); err != nil {
		t.Fatalf("generate errors: %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(outDir, "entity_homepage", "homepage", "errors.go"))
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
	if strings.Contains(string(generated), "AppErrorFromClaimNotFound") {
		t.Fatalf("homepage errors must not aggregate homepage_claim_request errors:\n%s", generated)
	}
	claimGenerated, err := os.ReadFile(filepath.Join(
		outDir,
		"entity_homepage",
		"homepage_claim_request",
		"errors.go",
	))
	if err != nil {
		t.Fatalf("read generated claim errors: %v", err)
	}
	for _, want := range []string{
		"from entity/entity_homepage/homepage_claim_request/errors.yaml",
		"AppErrorFromClaimNotFound",
	} {
		if !strings.Contains(string(claimGenerated), want) {
			t.Fatalf("generated claim errors missing %q:\n%s", want, claimGenerated)
		}
	}
	if err := generateErrors(source, outDir, true); err != nil {
		t.Fatalf("check generated errors: %v", err)
	}
}
