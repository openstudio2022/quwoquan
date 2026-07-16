package auth

import (
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
)

func TestTokenAuthorityConfigRequiresSecretIssuerAudienceAndVersion(t *testing.T) {
	t.Parallel()

	valid := map[string]string{
		"AUTH_JWT_SECRET":        "0123456789abcdef0123456789abcdef",
		"AUTH_JWT_ISSUER":        "https://auth.quwoquan.test",
		"AUTH_JWT_AUDIENCE":      "quwoquan-api",
		"AUTH_JWT_TOKEN_VERSION": "1",
	}
	for _, missing := range []string{
		"AUTH_JWT_SECRET",
		"AUTH_JWT_ISSUER",
		"AUTH_JWT_AUDIENCE",
		"AUTH_JWT_TOKEN_VERSION",
	} {
		values := make(map[string]string, len(valid))
		for key, value := range valid {
			values[key] = value
		}
		delete(values, missing)
		if _, err := LoadAccessTokenConfig(
			runtimeconfig.MapRuntimeConfigProvider{Values: values},
		); err == nil {
			t.Fatalf("missing %s must fail", missing)
		}
	}

	config, err := LoadAccessTokenConfig(
		runtimeconfig.MapRuntimeConfigProvider{Values: valid},
	)
	if err != nil {
		t.Fatalf("load access config: %v", err)
	}
	if config.Type != TokenTypeAccess ||
		config.TokenVersion != 1 ||
		config.Issuer != valid["AUTH_JWT_ISSUER"] ||
		config.Audience != valid["AUTH_JWT_AUDIENCE"] {
		t.Fatalf("unexpected config: %+v", config)
	}
}

func TestDeviceTicketConfigUsesIndependentTrustRoot(t *testing.T) {
	t.Parallel()

	config, err := LoadDeviceTicketConfig(
		runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
			"AUTH_DEVICE_TICKET_SECRET":        "abcdef0123456789abcdef0123456789",
			"AUTH_DEVICE_TICKET_ISSUER":        "https://device.quwoquan.test",
			"AUTH_DEVICE_TICKET_AUDIENCE":      "quwoquan-api",
			"AUTH_DEVICE_TICKET_TOKEN_VERSION": "2",
		}},
	)
	if err != nil {
		t.Fatalf("load device ticket config: %v", err)
	}
	if config.Type != TokenTypeDevice || config.TokenVersion != 2 {
		t.Fatalf("unexpected config: %+v", config)
	}
}
