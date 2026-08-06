package auth

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// operationAdmissionErrorsContract is the declaring authority for the gateway
// admission rejection copy. runtime/auth is mounted by every service and must
// not import one service's generated error package, so the guard keeps a local
// mirror; this test is what makes the mirror non-authoritative.
const operationAdmissionErrorsContract = "../../services/api-edge/contracts/edge_security/operation_admission_decision/errors.yaml"

func TestOperationGuardUserMessagesMatchContract(t *testing.T) {
	raw, err := os.ReadFile(filepath.Clean(operationAdmissionErrorsContract))
	if err != nil {
		t.Fatalf("read %s: %v", operationAdmissionErrorsContract, err)
	}
	var contract struct {
		Errors []struct {
			Code        string `yaml:"code"`
			Reason      string `yaml:"reason"`
			UserMessage struct {
				ZH string `yaml:"zh"`
			} `yaml:"user_message"`
		} `yaml:"errors"`
	}
	if err := yaml.Unmarshal(raw, &contract); err != nil {
		t.Fatalf("parse %s: %v", operationAdmissionErrorsContract, err)
	}

	declared := map[string]string{}
	for _, entry := range contract.Errors {
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
