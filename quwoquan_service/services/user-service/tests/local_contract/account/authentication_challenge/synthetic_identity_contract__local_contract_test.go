package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-013
// 仅authoring闭包证据，不模拟生成validator或声称运行时/设备已隔离。
func TestSyntheticIdentityAuthoringDoesNotReusePhoneOrExposeCredentials(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "contracts", "account")
	for _, owner := range []string{"authentication_challenge", "account_session"} {
		raw, err := os.ReadFile(filepath.Join(root, owner, "fields.yaml"))
		if err != nil {
			t.Fatal(err)
		}
		var doc struct {
			Types map[string]struct {
				Description string `yaml:"description"`
				Fields      []struct {
					Name           string `yaml:"name"`
					Classification string `yaml:"classification"`
					LogPolicy      string `yaml:"log_policy"`
					Exposure       string `yaml:"api_exposure"`
				} `yaml:"fields"`
			} `yaml:"types"`
		}
		if err := yaml.Unmarshal(raw, &doc); err != nil {
			t.Fatal(err)
		}
		expected := []string{"SyntheticIdentityLabel", "BeginSyntheticChallenge", "SyntheticChallengeView", "SyntheticLoginEvidence"}
		if owner == "account_session" {
			expected = []string{"CompleteSyntheticChallenge", "SyntheticSessionResult", "SyntheticLoginFailure"}
		}
		for _, name := range expected {
			value, ok := doc.Types[name]
			if !ok {
				t.Fatalf("missing %s", name)
			}
			if value.Description == "" || len(value.Fields) == 0 {
				t.Fatalf("empty contract %s", name)
			}
			for _, field := range value.Fields {
				for _, forbidden := range []string{"phone", "otpCode", "accessToken", "refreshToken", "credential"} {
					if field.Name == forbidden {
						t.Fatalf("%s reuses %s", name, forbidden)
					}
				}
				if field.LogPolicy != "drop" || field.Exposure != "none" {
					t.Fatalf("%s.%s broadens logging/HTTP", name, field.Name)
				}
				if field.Classification != "PUBLIC" && field.Classification != "INTERNAL" {
					t.Fatalf("unknown synthetic classification %s", field.Classification)
				}
			}
		}
		if owner == "authentication_challenge" {
			if !strings.Contains(doc.Types["SyntheticIdentityLabel"].Description, "^alpha-synthetic:[a-f0-9]{32}$") {
				t.Fatal("missing non-phone grammar")
			}
			if !strings.Contains(doc.Types["SyntheticLoginEvidence"].Description, "unknown") {
				t.Fatal("unknown evidence must reject")
			}
			if doc.Types["SendOtpCommand"].Fields[0].Name != "phone" {
				t.Fatal("real SendOtp changed")
			}
		} else if doc.Types["LoginWithPhoneCommand"].Fields[0].Name != "phone" {
			t.Fatal("real LoginWithPhone changed")
		}
		operations, err := os.ReadFile(filepath.Join(root, owner, "operations.yaml"))
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(operations), "Synthetic") {
			t.Fatal("synthetic declarations must not become fake HTTP operations")
		}
	}
}
