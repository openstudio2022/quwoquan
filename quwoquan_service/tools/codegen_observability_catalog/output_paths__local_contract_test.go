package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestRuntimeLogCatalogKeepsIndependentCanonicalAppOwner(t *testing.T) {
	repoRoot := t.TempDir()
	want := filepath.Join(
		repoRoot,
		"quwoquan_app",
		"lib",
		"runtime",
		"observability",
		"generated",
		"runtime_log_catalog.g.dart",
	)
	if got := appRuntimeLogCatalogOutputPath(repoRoot); got != want {
		t.Fatalf("App runtime log catalog target = %q, want %q", got, want)
	}

	source, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	text := string(source)
	if !strings.Contains(text, "appRuntimeLogCatalogOutputPath(root)") {
		t.Fatal("observability generator does not use the canonical App target")
	}
	for _, retirementCall := range []string{
		"exitIf(checkRetiredAppRuntimeLogCatalogOutput(root))",
		"exitIf(removeRetiredAppRuntimeLogCatalogOutput(root))",
	} {
		if !strings.Contains(text, retirementCall) {
			t.Fatalf("observability generator does not enforce retirement through %s", retirementCall)
		}
	}
	if strings.Contains(
		text,
		`"core", "observability", "generated", "runtime_log_catalog.g.dart"`,
	) {
		t.Fatal("observability generator still emits the retired App target")
	}
	for _, manifestToken := range []string{"generated-manifest", "generated_manifest"} {
		if strings.Contains(text, manifestToken) {
			t.Fatalf(
				"independent observability generator must not participate in the App manifest: found %q",
				manifestToken,
			)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestRuntimeLogCatalogCheckFailsClosedForRetiredAppOwner(t *testing.T) {
	repoRoot := t.TempDir()
	retired := retiredAppRuntimeLogCatalogOutputPath(repoRoot)
	if err := os.MkdirAll(filepath.Dir(retired), 0o755); err != nil {
		t.Fatal(err)
	}
	want := []byte("retired catalog must remain for check diagnostics\n")
	if err := os.WriteFile(retired, want, 0o644); err != nil {
		t.Fatal(err)
	}

	err := checkRetiredAppRuntimeLogCatalogOutput(repoRoot)
	if err == nil || !strings.Contains(err.Error(), "retired generated observability catalog still exists") {
		t.Fatalf("retired output check error = %v, want fail-closed diagnostic", err)
	}
	got, readErr := os.ReadFile(retired)
	if readErr != nil {
		t.Fatalf("check mode mutated the retired output: %v", readErr)
	}
	if string(got) != string(want) {
		t.Fatalf("check mode changed retired output = %q, want %q", got, want)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestRuntimeLogCatalogGenerateRetiresOnlyExactLegacyAppOwner(t *testing.T) {
	repoRoot := t.TempDir()
	retired := retiredAppRuntimeLogCatalogOutputPath(repoRoot)
	canonical := appRuntimeLogCatalogOutputPath(repoRoot)
	sibling := retired + ".keep"
	for path, content := range map[string]string{
		retired:   "retired\n",
		canonical: "canonical\n",
		sibling:   "sibling\n",
	} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	if err := removeRetiredAppRuntimeLogCatalogOutput(repoRoot); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(retired); !os.IsNotExist(err) {
		t.Fatalf("retired App catalog still exists after generate retirement: %v", err)
	}
	for path, want := range map[string]string{
		canonical: "canonical\n",
		sibling:   "sibling\n",
	} {
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("non-retired output %s was removed: %v", path, err)
		}
		if string(got) != want {
			t.Fatalf("non-retired output %s = %q, want %q", path, got, want)
		}
	}
	if err := removeRetiredAppRuntimeLogCatalogOutput(repoRoot); err != nil {
		t.Fatalf("repeated retirement must be deterministic and idempotent: %v", err)
	}
	if err := checkRetiredAppRuntimeLogCatalogOutput(repoRoot); err != nil {
		t.Fatalf("check must pass after exact retirement: %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestRuntimeLogCatalogGenerateRejectsDirectoryAtRetiredFilePath(t *testing.T) {
	repoRoot := t.TempDir()
	retired := retiredAppRuntimeLogCatalogOutputPath(repoRoot)
	if err := os.MkdirAll(retired, 0o755); err != nil {
		t.Fatal(err)
	}

	err := removeRetiredAppRuntimeLogCatalogOutput(repoRoot)
	if err == nil || !strings.Contains(err.Error(), "path is a directory") {
		t.Fatalf("directory retirement error = %v, want fail-closed diagnostic", err)
	}
	if info, statErr := os.Stat(retired); statErr != nil || !info.IsDir() {
		t.Fatalf("directory at retired file path was mutated: info=%v err=%v", info, statErr)
	}
}
