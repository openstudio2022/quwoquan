package integration

import (
	"net/http"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
)

func TestNewExternalInteractionClientAcceptsOnlyCanonicalNonprodTopology(t *testing.T) {
	signer := &rtauth.Signer{}
	if _, err := NewExternalInteractionClient(
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
		if _, err := NewExternalInteractionClient(baseURL, "alpha", &http.Client{}, signer); err == nil {
			t.Fatalf("non-canonical Alpha URL must be rejected: %s", baseURL)
		}
	}
}

func TestNewExternalInteractionClientKeepsProdOnHTTPS(t *testing.T) {
	signer := &rtauth.Signer{}
	if _, err := NewExternalInteractionClient(
		"https://integration-service.prod",
		"prod",
		&http.Client{},
		signer,
	); err != nil {
		t.Fatalf("canonical Prod HTTPS URL must be accepted: %v", err)
	}
	if _, err := NewExternalInteractionClient(
		"http://integration-service:18086",
		"prod",
		&http.Client{},
		signer,
	); err == nil {
		t.Fatal("Prod HTTP URL must be rejected")
	}
}
