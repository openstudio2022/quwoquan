package auth

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestDelegatedPersonaAuthorizationPreservesServiceAndPersonaActors(
	t *testing.T,
) {
	config := TokenConfig{
		Secret:       []byte("delegated-persona-test-secret-at-least-32-bytes"),
		Issuer:       "quwoquan-test",
		Audience:     "quwoquan-test",
		Type:         TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
	provider, err := NewHS256DelegatedPersonaAuthorizationProvider(
		config,
		"entity-service",
		[]string{"content.object_intersections.read"},
	)
	if err != nil {
		t.Fatalf("new delegated provider: %v", err)
	}
	header, err := provider.AuthorizationHeaderForPersona(
		context.Background(),
		"persona-123",
	)
	if err != nil {
		t.Fatalf("authorization header: %v", err)
	}
	token := strings.TrimPrefix(header, "Bearer ")
	verifier, err := NewHS256Verifier(config)
	if err != nil {
		t.Fatalf("new verifier: %v", err)
	}
	claims, err := verifier.Verify(token)
	if err != nil {
		t.Fatalf("verify delegated token: %v", err)
	}
	if claims.Subject != "service:entity-service" {
		t.Fatalf("service subject mismatch: %q", claims.Subject)
	}
	if claims.Persona != "persona-123" {
		t.Fatalf("persona actor mismatch: %q", claims.Persona)
	}
	if !strings.Contains(claims.Scope, "content.object_intersections.read") {
		t.Fatalf("scope mismatch: %q", claims.Scope)
	}
}

func TestDelegatedPersonaAuthorizationRejectsMissingPersona(t *testing.T) {
	provider, err := NewHS256DelegatedPersonaAuthorizationProvider(
		TokenConfig{
			Secret:       []byte("delegated-persona-test-secret-at-least-32-bytes"),
			Issuer:       "quwoquan-test",
			Audience:     "quwoquan-test",
			Type:         TokenTypeAccess,
			TokenVersion: 1,
			TTL:          time.Minute,
		},
		"entity-service",
		[]string{"content.object_intersections.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := provider.AuthorizationHeaderForPersona(
		context.Background(),
		" ",
	); err == nil {
		t.Fatal("missing delegated persona must fail closed")
	}
}
