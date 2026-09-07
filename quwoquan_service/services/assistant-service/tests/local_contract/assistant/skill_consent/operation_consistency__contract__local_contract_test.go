// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

type skillConsentOperationConsistency struct {
	AtomicCommit *bool  `yaml:"atomic_commit"`
	Arbitration  string `yaml:"arbitration"`
	Source       string `yaml:"source"`
	StaleResult  string `yaml:"stale_result"`
}

func TestSkillConsentOperationsDeclareImplementedConsistency(t *testing.T) {
	operations := loadSkillConsentOperationConsistency(t)
	grant := operations["GrantSkillConsent"]
	if grant.AtomicCommit == nil || !*grant.AtomicCommit ||
		grant.Arbitration != "unique_winner" {
		t.Fatalf("GrantSkillConsent consistency=%+v", grant)
	}
	revoke := operations["RevokeSkillConsent"]
	if revoke.AtomicCommit == nil || !*revoke.AtomicCommit ||
		revoke.Arbitration != "conditional_admission" {
		t.Fatalf("RevokeSkillConsent consistency=%+v", revoke)
	}
	list := operations["ListConsents"]
	if list.Source != "authority" || list.StaleResult != "fail_closed" {
		t.Fatalf("ListConsents consistency=%+v", list)
	}
}

func loadSkillConsentOperationConsistency(t *testing.T) map[string]skillConsentOperationConsistency {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve SkillConsent consistency contract test")
	}
	path := filepath.Join(filepath.Dir(source), "..", "..", "..", "..", "contracts", "assistant", "skill_consent", "operations.yaml")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Routes []struct {
			Operation   string                           `yaml:"operation"`
			Consistency skillConsentOperationConsistency `yaml:"consistency"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	operations := make(map[string]skillConsentOperationConsistency, len(document.Routes))
	for _, route := range document.Routes {
		operations[route.Operation] = route.Consistency
	}
	return operations
}
