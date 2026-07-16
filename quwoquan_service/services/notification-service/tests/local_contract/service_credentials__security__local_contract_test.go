package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func TestNotificationIntegrationCredentialCarriesOnlyServiceGrant(t *testing.T) {
	config := rtauth.TokenConfig{
		Secret:       []byte("notification-service-contract-secret-32-bytes-minimum"),
		Issuer:       "quwoquan.contract",
		Audience:     "quwoquan-services",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
	provider, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		"notification-service",
		[]string{"integration.external_interaction.submit"},
	)
	if err != nil {
		t.Fatalf("construct service credential provider: %v", err)
	}
	header, err := provider.AuthorizationHeader(context.Background())
	if err != nil {
		t.Fatalf("issue service credential: %v", err)
	}
	if !strings.HasPrefix(header, "Bearer ") {
		t.Fatalf("authorization scheme = %q", header)
	}
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatalf("construct verifier: %v", err)
	}
	claims, err := verifier.Verify(strings.TrimPrefix(header, "Bearer "))
	if err != nil {
		t.Fatalf("verify service credential: %v", err)
	}
	if claims.Subject != "service:notification-service" ||
		claims.Scope != "integration.external_interaction.submit" ||
		len(claims.Roles) != 1 || claims.Roles[0] != "service" ||
		len(claims.Permissions) != 0 || claims.Persona != "" {
		t.Fatalf("unexpected least-privilege claims: %+v", claims)
	}
}
