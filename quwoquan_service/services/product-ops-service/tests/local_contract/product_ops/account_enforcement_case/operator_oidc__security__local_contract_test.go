package local_contract

import (
	"testing"

	rtauth "quwoquan_service/runtime/auth"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
func TestOperatorOIDCIsMandatoryForProductionAndNonLocalEnvironments(t *testing.T) {
	tests := []struct {
		environment string
		required    bool
	}{
		{environment: "alpha", required: false},
		{environment: "beta", required: false},
		{environment: "gamma", required: false},
		{environment: "prod", required: true},
		{environment: "release", required: true},
		{environment: "", required: true},
		{environment: "unknown", required: true},
	}
	for _, test := range tests {
		t.Run(test.environment, func(t *testing.T) {
			actual := rtauth.OperatorOIDCRequiredForEnvironment(
				test.environment,
			)
			if actual != test.required {
				t.Fatalf(
					"OperatorOIDCRequiredForEnvironment(%q)=%t want %t",
					test.environment,
					actual,
					test.required,
				)
			}
		})
	}
}
