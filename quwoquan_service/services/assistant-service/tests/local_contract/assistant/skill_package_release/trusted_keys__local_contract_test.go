// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package skill_package_release_test

import (
	"crypto/ed25519"
	"encoding/base64"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
)

func TestTrustedSkillPackageKeysAreStrictlyDecoded(t *testing.T) {
	publicKey, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	raw := `{"quwoquan.official.2026-01":"` +
		base64.StdEncoding.EncodeToString(publicKey) + `"}`
	keys, err := application.DecodeTrustedPublicKeys(raw)
	if err != nil {
		t.Fatalf("DecodeTrustedPublicKeys() error = %v", err)
	}
	if len(keys) != 1 || len(keys["quwoquan.official.2026-01"]) != ed25519.PublicKeySize {
		t.Fatalf("decoded keys = %#v", keys)
	}
	for _, invalid := range []string{"", `{}`, `{"":"invalid"}`, `{"key":"invalid"}`} {
		if _, err := application.DecodeTrustedPublicKeys(invalid); err == nil {
			t.Fatalf("DecodeTrustedPublicKeys(%q) succeeded", invalid)
		}
	}
}
