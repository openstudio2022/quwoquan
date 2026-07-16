package auth

import (
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
)

const (
	accessTokenTTL  = 30 * time.Minute
	deviceTicketTTL = 15 * time.Minute
	tokenClockSkew  = 30 * time.Second
)

func LoadAccessTokenConfig(
	provider runtimeconfig.RuntimeConfigProvider,
) (TokenConfig, error) {
	return loadTokenConfig(
		provider,
		"AUTH_JWT",
		TokenTypeAccess,
		accessTokenTTL,
	)
}

func LoadDeviceTicketConfig(
	provider runtimeconfig.RuntimeConfigProvider,
) (TokenConfig, error) {
	return loadTokenConfig(
		provider,
		"AUTH_DEVICE_TICKET",
		TokenTypeDevice,
		deviceTicketTTL,
	)
}

func loadTokenConfig(
	provider runtimeconfig.RuntimeConfigProvider,
	prefix string,
	tokenType TokenType,
	ttl time.Duration,
) (TokenConfig, error) {
	if provider == nil {
		return TokenConfig{}, fmt.Errorf("auth: %s provider is required", prefix)
	}
	secret, secretOK := provider.GetString(prefix + "_SECRET")
	issuer, issuerOK := provider.GetString(prefix + "_ISSUER")
	audience, audienceOK := provider.GetString(prefix + "_AUDIENCE")
	version, versionOK := provider.GetInt(prefix + "_TOKEN_VERSION")
	missing := make([]string, 0, 4)
	if !secretOK {
		missing = append(missing, prefix+"_SECRET")
	}
	if !issuerOK {
		missing = append(missing, prefix+"_ISSUER")
	}
	if !audienceOK {
		missing = append(missing, prefix+"_AUDIENCE")
	}
	if !versionOK {
		missing = append(missing, prefix+"_TOKEN_VERSION")
	}
	if len(missing) > 0 {
		return TokenConfig{}, fmt.Errorf(
			"auth: required config missing or invalid: %s",
			strings.Join(missing, ","),
		)
	}
	config := TokenConfig{
		Secret:       []byte(secret),
		Issuer:       issuer,
		Audience:     audience,
		Type:         tokenType,
		TokenVersion: version,
		TTL:          ttl,
		ClockSkew:    tokenClockSkew,
	}
	if err := config.validate(); err != nil {
		return TokenConfig{}, err
	}
	return config, nil
}
