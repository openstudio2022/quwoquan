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

func TestDelegatedPersonaCompatibilityAllowlistCannotExpand(t *testing.T) {
	t.Parallel()
	for _, scope := range []string{
		"circle.gathering.write",
		"travel.trip.read",
	} {
		_, err := NewHS256DelegatedPersonaAuthorizationProvider(
			TokenConfig{
				Secret:       []byte("delegated-persona-test-secret-at-least-32-bytes"),
				Issuer:       "quwoquan-test",
				Audience:     "quwoquan-test",
				Type:         TokenTypeAccess,
				TokenVersion: 1,
				TTL:          time.Minute,
			},
			"assistant-service",
			[]string{scope},
		)
		if err == nil {
			t.Fatalf("legacy delegated persona scope %q must fail", scope)
		}
	}
}

func TestServiceAccountAuthorizationPreservesDistinctAccountAndServiceActors(
	t *testing.T,
) {
	config := TokenConfig{
		Secret:       []byte("service-account-test-secret-at-least-32-bytes"),
		Issuer:       "quwoquan-test",
		Audience:     "quwoquan-test",
		Type:         TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
	provider, err := NewHS256ServiceAccountAuthorizationProvider(
		config,
		"assistant-service",
		[]string{"integration.connector_grant.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	header, err := provider.AuthorizationHeaderForAccount(
		context.Background(),
		"account-123",
	)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	claims, err := verifier.Verify(strings.TrimPrefix(header, "Bearer "))
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != "account-123" ||
		claims.ServiceActorID != "assistant-service" ||
		!containsGrant(claims.Roles, "service") ||
		!strings.Contains(claims.Scope, "integration.connector_grant.read") {
		t.Fatalf("claims=%+v", claims)
	}
}

func TestServiceAccountAuthorizationRejectsMissingOrServiceAccountSubject(
	t *testing.T,
) {
	provider, err := NewHS256ServiceAccountAuthorizationProvider(
		TokenConfig{
			Secret:       []byte("service-account-test-secret-at-least-32-bytes"),
			Issuer:       "quwoquan-test",
			Audience:     "quwoquan-test",
			Type:         TokenTypeAccess,
			TokenVersion: 1,
			TTL:          time.Minute,
		},
		"assistant-service",
		[]string{"integration.connector_grant.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, accountID := range []string{"", " ", "service:assistant-service"} {
		if _, err := provider.AuthorizationHeaderForAccount(
			context.Background(), accountID,
		); err == nil {
			t.Fatalf("account subject %q must fail closed", accountID)
		}
	}
}
