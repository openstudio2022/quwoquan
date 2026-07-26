package runtimeconfig

import (
	"fmt"
	"net/url"
	"strings"
)

// RequireInternalServiceBaseURL validates a service dependency as one explicit
// HTTP(S) origin. Paths, credentials and query material are rejected so the
// configured dependency boundary cannot be widened implicitly.
func RequireInternalServiceBaseURL(name, raw string) (string, error) {
	value := strings.TrimRight(strings.TrimSpace(raw), "/")
	if value == "" {
		return "", fmt.Errorf("%s is required", name)
	}
	parsed, err := url.Parse(value)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", fmt.Errorf("%s must be an absolute http(s) origin without credentials, query, or fragment", name)
	}
	if parsed.Path != "" {
		return "", fmt.Errorf("%s must not contain a path", name)
	}
	return value, nil
}
