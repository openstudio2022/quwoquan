package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDiscoverContractInputsDerivesObjectPaths(t *testing.T) {
	t.Parallel()

	contractsDir := t.TempDir()
	writeTestFile(t, filepath.Join(contractsDir, "domain.yaml"), "domain: chat\n")
	writeTestFile(t, filepath.Join(contractsDir, "chat", "message", "operations.yaml"), "api_routes: []\n")
	writeTestFile(t, filepath.Join(contractsDir, "chat", "conversation", "operations.yaml"), "api_routes: []\n")
	writeTestFile(t, filepath.Join(contractsDir, "chat", "conversation", "errors.yaml"), "errors: []\n")

	inputs, err := discoverContractInputs(contractsDir)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(inputs.Objects), 2; got != want {
		t.Fatalf("object inputs = %d, want %d", got, want)
	}
	conversation := inputs.Objects[0]
	if got, want := conversation.Context+"/"+conversation.Object, "chat/conversation"; got != want {
		t.Fatalf("first owner = %q, want %q", got, want)
	}
	if got, want := conversation.OperationGraphPath, "chat/chat/conversation/operations.yaml"; got != want {
		t.Fatalf("operation graph path = %q, want %q", got, want)
	}
	if got, want := conversation.OperationSourcePath, "contracts/chat/conversation/operations.yaml"; got != want {
		t.Fatalf("operation source path = %q, want %q", got, want)
	}
	if got, want := conversation.ErrorsGraphPath, "chat/chat/conversation/errors.yaml"; got != want {
		t.Fatalf("errors graph path = %q, want %q", got, want)
	}
	if got, want := conversation.ErrorsSourcePath, "chat/chat/conversation/errors.yaml"; got != want {
		t.Fatalf("errors source path = %q, want %q", got, want)
	}
}

func TestDiscoverContractInputsRejectsServiceLevelObjectCatalog(t *testing.T) {
	t.Parallel()

	contractsDir := t.TempDir()
	writeTestFile(t, filepath.Join(contractsDir, "domain.yaml"), "domain: chat\n")
	writeTestFile(t, filepath.Join(contractsDir, "operations.yaml"), "api_routes: []\n")
	writeTestFile(t, filepath.Join(contractsDir, "chat", "conversation", "errors.yaml"), "errors: []\n")

	if _, err := discoverContractInputs(contractsDir); err == nil {
		t.Fatal("service-level operations.yaml must not replace object-owned contracts")
	}
}

func writeTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}
