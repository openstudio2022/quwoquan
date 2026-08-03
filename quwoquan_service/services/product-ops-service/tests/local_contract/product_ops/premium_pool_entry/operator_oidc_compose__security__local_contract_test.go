// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPremiumPoolOperatorOIDCIsPassedThroughWithoutLocalFallback(t *testing.T) {
	composePath := filepath.Join("..", "..", "..", "..", "deploy", "compose.yaml")
	payload, err := os.ReadFile(composePath)
	if err != nil {
		t.Fatalf("read Product Ops compose: %v", err)
	}
	compose := string(payload)
	for _, required := range []string{
		`OPS_OIDC_ISSUER: "${OPS_OIDC_ISSUER:-}"`,
		`OPS_OIDC_AUDIENCE: "${OPS_OIDC_AUDIENCE:-}"`,
		`OPS_OIDC_JWKS_URL: "${OPS_OIDC_JWKS_URL:-}"`,
	} {
		if !strings.Contains(compose, required) {
			t.Fatalf("Product Ops compose is missing exact protected OIDC passthrough %q", required)
		}
	}
	for _, forbidden := range []string{
		"OPS_OIDC_SECRET",
		"OPS_OIDC_HS256",
		"LOCAL_OPERATOR_TOKEN",
		"operator-token",
	} {
		if strings.Contains(compose, forbidden) {
			t.Fatalf("Product Ops compose contains forbidden local operator fallback %q", forbidden)
		}
	}
}
