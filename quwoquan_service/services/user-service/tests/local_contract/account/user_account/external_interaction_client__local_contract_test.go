// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-003
package local_contract

import (
	"net/http"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestNewExternalInteractionClientAcceptsOnlyCanonicalNonprodTopology(t *testing.T) {
	signer := &rtauth.Signer{}
	if _, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"alpha",
		&http.Client{},
		signer,
	); err != nil {
		t.Fatalf("canonical Alpha substitute must be accepted: %v", err)
	}

	for _, baseURL := range []string{
		"https://integration-service:18086",
		"http://127.0.0.1:18086",
		"http://integration-service:18089",
	} {
		if _, err := userintegration.NewExternalInteractionClient(baseURL, "alpha", &http.Client{}, signer); err == nil {
			t.Fatalf("non-canonical Alpha URL must be rejected: %s", baseURL)
		}
	}
}

func TestNewExternalInteractionClientKeepsProdOnHTTPS(t *testing.T) {
	t.Setenv("QWQ_RUNTIME_TARGET", "")
	signer := &rtauth.Signer{}
	if _, err := userintegration.NewExternalInteractionClient(
		"https://integration-service.prod",
		"prod",
		&http.Client{},
		signer,
	); err != nil {
		t.Fatalf("canonical Prod HTTPS URL must be accepted: %v", err)
	}
	if _, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"prod",
		&http.Client{},
		signer,
	); err == nil {
		t.Fatal("Prod HTTP URL must be rejected")
	}
}

func TestNewExternalInteractionClientRejectsProdHostedHTTP(t *testing.T) {
	t.Setenv("QWQ_RUNTIME_TARGET", "prod-hosted")
	signer := &rtauth.Signer{}
	if _, err := userintegration.NewExternalInteractionClient(
		"https://integration-service.prod",
		"prod",
		&http.Client{},
		signer,
	); err != nil {
		t.Fatalf("prod-hosted HTTPS URL must be accepted: %v", err)
	}
	if _, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"prod",
		&http.Client{},
		signer,
	); err == nil {
		t.Fatal("prod-hosted HTTP URL must be rejected")
	}
}

func TestNewExternalInteractionClientAcceptsProdSimCanonicalHTTP(t *testing.T) {
	t.Setenv("QWQ_RUNTIME_TARGET", "prod-sim")
	signer := &rtauth.Signer{}
	if _, err := userintegration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"prod",
		&http.Client{},
		signer,
	); err != nil {
		t.Fatalf("prod-sim canonical mesh URL must be accepted: %v", err)
	}
	for _, baseURL := range []string{
		"https://integration-service.prod",
		"https://integration-service:18086",
		"http://127.0.0.1:18086",
	} {
		if _, err := userintegration.NewExternalInteractionClient(
			baseURL,
			"prod",
			&http.Client{},
			signer,
		); err == nil {
			t.Fatalf("prod-sim non-canonical URL must be rejected: %s", baseURL)
		}
	}
}
