package auth

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// operationAdmissionErrorsContract is the declaring authority for the gateway
// admission rejection copy. These codes are produced before any owner handler by
// a guard that every service links, so they belong to no single service object
// and are declared in the runtime failure code contract. runtime/auth still keeps
// a local mirror because it must not import a service's generated error package;
// this test is what makes the mirror non-authoritative.
const operationAdmissionErrorsContract = "../../contracts/runtime_errors/errors/runtime_failure_codes.yaml"

func TestOperationGuardUserMessagesMatchContract(t *testing.T) {
	raw, err := os.ReadFile(filepath.Clean(operationAdmissionErrorsContract))
	if err != nil {
		t.Fatalf("read %s: %v", operationAdmissionErrorsContract, err)
	}
	var contract struct {
		Codes []struct {
			Code        string `yaml:"code"`
			Reason      string `yaml:"reason"`
			UserMessage struct {
				ZH string `yaml:"zh"`
			} `yaml:"userMessage"`
		} `yaml:"codes"`
	}
	if err := yaml.Unmarshal(raw, &contract); err != nil {
		t.Fatalf("parse %s: %v", operationAdmissionErrorsContract, err)
	}

	declared := map[string]string{}
	for _, entry := range contract.Codes {
		if !strings.HasPrefix(entry.Code, "GATEWAY.USER.") {
			continue
		}
		declared[entry.Reason] = entry.UserMessage.ZH
	}
	if len(declared) == 0 {
		t.Fatalf("no GATEWAY.USER.* rejection declared in %s", operationAdmissionErrorsContract)
	}

	for reason, message := range operationGuardUserMessages {
		want, ok := declared[reason]
		if !ok {
			t.Errorf("guard emits GATEWAY.USER.%s but the contract declares no such error", reason)
			continue
		}
		if message != want {
			t.Errorf("GATEWAY.USER.%s user message drifted: guard %q, contract %q", reason, message, want)
		}
	}
	for reason := range declared {
		if _, ok := operationGuardUserMessages[reason]; !ok {
			t.Errorf("contract declares GATEWAY.USER.%s but the guard has no message for it", reason)
		}
	}
}
