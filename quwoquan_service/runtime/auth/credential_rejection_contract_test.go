package auth

import (
	"os"
	"path/filepath"
	"testing"

	rterr "quwoquan_service/runtime/errors"

	"gopkg.in/yaml.v3"
)

// runtime/auth is linked into every service binary and must not import one
// service's generated error package, so writeCredentialError keeps a local copy
// of the declared credential-boundary copy. These contracts stay the declaring
// authority and this test fails as soon as the copy drifts.
var credentialRejectionContracts = []string{
	"../../services/user-service/contracts/account/account_session/errors.yaml",
	"../../services/user-service/contracts/account/user_account/errors.yaml",
}

func loadDeclaredErrors(t *testing.T) map[string]string {
	t.Helper()
	declared := map[string]string{}
	for _, relative := range credentialRejectionContracts {
		raw, err := os.ReadFile(filepath.Clean(relative))
		if err != nil {
			t.Fatalf("read %s: %v", relative, err)
		}
		var contract struct {
			Errors []struct {
				Code        string `yaml:"code"`
				UserMessage struct {
					ZH string `yaml:"zh"`
				} `yaml:"user_message"`
			} `yaml:"errors"`
		}
		if err := yaml.Unmarshal(raw, &contract); err != nil {
			t.Fatalf("parse %s: %v", relative, err)
		}
		for _, entry := range contract.Errors {
			declared[entry.Code] = entry.UserMessage.ZH
		}
	}
	return declared
}

func TestCredentialRejectionsMatchContract(t *testing.T) {
	declared := loadDeclaredErrors(t)
	for _, rejection := range []credentialRejection{
		credentialUnauthorized,
		credentialTokenExpired,
		credentialMFARequired,
	} {
		code := rterr.NewCode(rterr.ModuleUser, rejection.kind, rejection.reason).String()
		message, ok := declared[code]
		if !ok {
			t.Errorf("credential boundary emits %s but no errors.yaml declares it", code)
			continue
		}
		if message != rejection.userMessage {
			t.Errorf("%s user message drifted: runtime %q, contract %q", code, rejection.userMessage, message)
		}
	}
}
