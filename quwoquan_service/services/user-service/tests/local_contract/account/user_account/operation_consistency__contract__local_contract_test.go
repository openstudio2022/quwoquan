// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

type userAccountOperationConsistency struct {
	AtomicCommit *bool  `yaml:"atomic_commit"`
	Arbitration  string `yaml:"arbitration"`
	Source       string `yaml:"source"`
	Freshness    string `yaml:"freshness"`
	StaleResult  string `yaml:"stale_result"`
}

func TestUserAccountSecurityOperationsDeclareImplementedConsistency(t *testing.T) {
	operations := loadUserAccountOperationConsistency(t)
	for _, operation := range []string{"CloseAccount", "SuspendAccount", "RestoreAccount"} {
		consistency := operations[operation]
		if consistency.AtomicCommit == nil || !*consistency.AtomicCommit {
			t.Fatalf("%s atomic_commit=%v, want true", operation, consistency.AtomicCommit)
		}
		if consistency.Arbitration != "" {
			t.Fatalf("%s arbitration=%q, row-lock serialization is not version CAS", operation, consistency.Arbitration)
		}
	}
	for _, operation := range []string{"ReadAccountSecurity", "CheckAccountSecurityAuthority"} {
		consistency := operations[operation]
		if consistency.Source != "authority" ||
			consistency.Freshness != "read_your_writes" ||
			consistency.StaleResult != "fail_closed" {
			t.Fatalf("%s consistency=%+v", operation, consistency)
		}
	}
}

func loadUserAccountOperationConsistency(t *testing.T) map[string]userAccountOperationConsistency {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve UserAccount consistency contract test")
	}
	path := filepath.Join(filepath.Dir(source), "..", "..", "..", "..", "contracts", "account", "user_account", "operations.yaml")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Routes []struct {
			Operation   string                          `yaml:"operation"`
			Consistency userAccountOperationConsistency `yaml:"consistency"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	operations := make(map[string]userAccountOperationConsistency, len(document.Routes))
	for _, route := range document.Routes {
		operations[route.Operation] = route.Consistency
	}
	return operations
}
