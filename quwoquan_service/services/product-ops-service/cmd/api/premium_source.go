package main

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"quwoquan_service/runtime/auth"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/contentsource"
	"strings"
	"time"
)

// newPremiumSourceReader与真实bootstrap共用，credential来自servicekit Auth，禁止静态bearer配置。
func newPremiumSourceReader(endpoint string, credentials auth.ServiceAuthorizationProvider) (*contentsource.Reader, error) {
	parsed, err := url.Parse(strings.TrimSpace(endpoint))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "https" && parsed.Scheme != "http") || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || credentials == nil {
		return nil, fmt.Errorf("premium Content source configuration incomplete")
	}
	return &contentsource.Reader{Endpoint: strings.TrimRight(endpoint, "/"), Client: &http.Client{Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}, Credential: func(ctx context.Context) (string, error) {
		header, err := credentials.AuthorizationHeader(ctx)
		if err != nil {
			return "", err
		}
		if !strings.HasPrefix(header, "Bearer ") {
			return "", fmt.Errorf("invalid service credential header")
		}
		return strings.TrimPrefix(header, "Bearer "), nil
	}}, nil
}
