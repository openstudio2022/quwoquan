// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

type credentialOperationConsistency struct {
	AtomicCommit *bool  `yaml:"atomic_commit"`
	Arbitration  string `yaml:"arbitration"`
	Source       string `yaml:"source"`
	StaleResult  string `yaml:"stale_result"`
}

func TestCredentialBindingOperationsDeclareImplementedConsistency(t *testing.T) {
	operations := loadCredentialOperationConsistency(t)
	list := operations["ListCredentials"]
	if list.Source != "authority" || list.StaleResult != "fail_closed" {
		t.Fatalf("ListCredentials consistency=%+v", list)
	}
	for _, operation := range []string{
		"BindPhoneCredential",
		"CompleteFederatedPhoneBinding",
		"BindCarrierPhoneCredential",
	} {
		consistency := operations[operation]
		if consistency.AtomicCommit == nil || !*consistency.AtomicCommit ||
			consistency.Arbitration != "unique_winner" {
			t.Fatalf("%s consistency=%+v", operation, consistency)
		}
	}
	unbind := operations["UnbindCredential"]
	if unbind.AtomicCommit == nil || !*unbind.AtomicCommit ||
		unbind.Arbitration != "version_cas" {
		t.Fatalf("UnbindCredential consistency=%+v", unbind)
	}
}

func loadCredentialOperationConsistency(t *testing.T) map[string]credentialOperationConsistency {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve CredentialBinding consistency contract test")
	}
	path := filepath.Join(filepath.Dir(source), "..", "..", "..", "..", "contracts", "account", "credential_binding", "operations.yaml")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Routes []struct {
			Operation   string                         `yaml:"operation"`
			Consistency credentialOperationConsistency `yaml:"consistency"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	operations := make(map[string]credentialOperationConsistency, len(document.Routes))
	for _, route := range document.Routes {
		operations[route.Operation] = route.Consistency
	}
	return operations
}
