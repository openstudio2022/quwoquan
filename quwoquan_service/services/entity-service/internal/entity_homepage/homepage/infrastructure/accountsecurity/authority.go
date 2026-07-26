// Package accountsecurity binds entity-service to the public UserAccount
// security-authority contract. It owns no account state and never caches a
// successful decision.
package accountsecurity

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

const readScope = "user.account.security.read"

type Config struct {
	BaseURL   string
	TimeoutMS int
}

func NewAuthority(
	accessTokenConfig rtauth.TokenConfig,
	config Config,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	baseURL := strings.TrimSpace(config.BaseURL)
	if baseURL == "" {
		return nil, fmt.Errorf("entity-service account security authority base URL is required")
	}
	if config.TimeoutMS <= 0 {
		return nil, fmt.Errorf("entity-service account security authority timeout must be positive")
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"entity-service",
		[]string{readScope},
	)
	if err != nil {
		return nil, fmt.Errorf("entity-service account security authority credentials: %w", err)
	}
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     baseURL,
			HTTPClient:  &http.Client{Timeout: time.Duration(config.TimeoutMS) * time.Millisecond},
			Credentials: credentials,
			Timeout:     time.Duration(config.TimeoutMS) * time.Millisecond,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("entity-service account security authority: %w", err)
	}
	return authority, nil
}
