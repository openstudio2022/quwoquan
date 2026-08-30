package artifactidentity

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeIdentity(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "artifact-identity.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadAndValidateRequiresExactEnvironmentAssertion(t *testing.T) {
	path := writeIdentity(t, `{"schema":"qwq.environment-artifact-identity","environment":"gamma","configDigest":"sha256:`+strings.Repeat("a", 64)+`"}`)
	identity, err := LoadAndValidate(path, "gamma")
	if err != nil {
		t.Fatal(err)
	}
	if identity.Environment != "gamma" {
		t.Fatalf("unexpected environment: %s", identity.Environment)
	}
	for name, assertion := range map[string]string{
		"missing":           "",
		"cross_environment": "prod",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := LoadAndValidate(path, assertion); err == nil {
				t.Fatal("expected artifact identity assertion failure")
			}
		})
	}
}

func TestLoadAndValidateRejectsUnknownFieldsAndInvalidDigest(t *testing.T) {
	for name, content := range map[string]string{
		"unknown": `{"schema":"qwq.environment-artifact-identity","environment":"alpha","configDigest":"sha256:` + strings.Repeat("b", 64) + `","selector":"prod"}`,
		"digest":  `{"schema":"qwq.environment-artifact-identity","environment":"alpha","configDigest":"not-a-digest"}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := LoadAndValidate(writeIdentity(t, content), "alpha"); err == nil {
				t.Fatal("expected malformed artifact identity rejection")
			}
		})
	}
}
