package runtimeconfig

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

const (
	minAccountSecurityAuthorityTimeout = 50 * time.Millisecond
	maxAccountSecurityAuthorityTimeout = 5 * time.Second
)

// NewAccountSecurityAuthority composes the same fail-closed authority used by
// RTC HTTP middleware and direct media-access issuance. The internal origin and
// timeout are explicit deployment configuration; neither has a fallback.
func NewAccountSecurityAuthority(
	accessTokenConfig rtauth.TokenConfig,
	userServiceBaseURL string,
	timeoutMilliseconds int,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	if strings.TrimSpace(userServiceBaseURL) == "" {
		return nil, fmt.Errorf("account security authority user-service URL is required")
	}
	timeout, err := accountSecurityAuthorityTimeout(timeoutMilliseconds)
	if err != nil {
		return nil, err
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"rtc-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority service credential: %w", err)
	}
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     strings.TrimSpace(userServiceBaseURL),
			HTTPClient:  &http.Client{Timeout: timeout},
			Credentials: credentials,
			Timeout:     timeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority: %w", err)
	}
	return authority, nil
}

func accountSecurityAuthorityTimeout(
	timeoutMilliseconds int,
) (time.Duration, error) {
	timeout := time.Duration(timeoutMilliseconds) * time.Millisecond
	if timeout < minAccountSecurityAuthorityTimeout ||
		timeout > maxAccountSecurityAuthorityTimeout {
		return 0, fmt.Errorf(
			"account security authority timeout must be between %s and %s",
			minAccountSecurityAuthorityTimeout,
			maxAccountSecurityAuthorityTimeout,
		)
	}
	return timeout, nil
}
