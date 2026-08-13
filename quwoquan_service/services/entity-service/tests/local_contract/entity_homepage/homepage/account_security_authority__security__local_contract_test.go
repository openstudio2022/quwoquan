// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	accountsecurity "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/accountsecurity"
)

func TestEntityAccountSecurityAuthorityUsesScopedServiceCredential(t *testing.T) {
	tokenConfig := entityAccountSecurityTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/user/accounts/entity-owner/security" {
			t.Fatalf("path=%q", r.URL.Path)
		}
		token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		claims, err := verifier.Verify(token)
		if err != nil {
			t.Fatalf("verify service credential: %v", err)
		}
		if claims.Subject != "service:entity-service" ||
			!hasScope(strings.Fields(claims.Scope), "user.account.security.read") {
			t.Fatalf("claims=%+v", claims)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"accountState":"active","authEpoch":4}`))
	}))
	defer server.Close()

	authority, err := accountsecurity.NewAuthority(
		tokenConfig,
		accountsecurity.Config{BaseURL: server.URL, TimeoutMS: 250},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := authority.ReadAccountSecurity(context.Background(), "entity-owner"); err != nil {
		t.Fatal(err)
	}
}

func TestEntityAccountSecurityAuthorityFailsStartupForInvalidConfig(t *testing.T) {
	tokenConfig := entityAccountSecurityTokenConfig()
	for _, config := range []accountsecurity.Config{
		{TimeoutMS: 250},
		{BaseURL: "https://user-service.internal/path", TimeoutMS: 250},
		{BaseURL: "https://user-service.internal", TimeoutMS: 0},
	} {
		if _, err := accountsecurity.NewAuthority(tokenConfig, config); err == nil {
			t.Fatalf("invalid authority config=%+v must fail", config)
		}
	}
}

func TestEntityAccountSecurityAuthorityUsesDeploymentOriginForHostedEnvironments(
	t *testing.T,
) {
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve entity-service test source")
	}
	serviceRoot := filepath.Clean(
		filepath.Join(filepath.Dir(source), "../../../../"),
	)
	expectedOrigins := map[string]string{
		"gamma": "http://user-service:18081",
		"prod":  "http://user-service:18081",
	}
	for environment, origin := range expectedOrigins {
		t.Run(environment, func(t *testing.T) {
			configPath := filepath.Join(
				serviceRoot,
				"environments",
				environment,
				"config.yaml",
			)
			raw, err := os.ReadFile(configPath)
			if err != nil {
				t.Fatalf("read %s: %v", configPath, err)
			}
			expected := "sys.entity-service.user_account_security_authority.base_url: " +
				origin
			if !strings.Contains(string(raw), expected) {
				t.Fatalf(
					"%s authority endpoint must target actual user-service origin %q",
					environment,
					origin,
				)
			}
		})
	}
}

func TestEntityAccountSecurityAuthorityUsesTargetTopologyForLocalEnvironments(
	t *testing.T,
) {
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve entity-service test source")
	}
	serviceRoot := filepath.Clean(
		filepath.Join(filepath.Dir(source), "../../../../"),
	)
	for _, environment := range []string{"alpha", "beta"} {
		configPath := filepath.Join(
			serviceRoot,
			"environments",
			environment,
			"config.yaml",
		)
		raw, err := os.ReadFile(configPath)
		if err != nil {
			t.Fatalf("read %s: %v", configPath, err)
		}
		if strings.Contains(
			string(raw),
			"sys.entity-service.user_account_security_authority.base_url",
		) {
			t.Fatalf(
				"%s config duplicates target-local user-service port instead of using topology injection",
				environment,
			)
		}
	}

	repoRoot := filepath.Clean(filepath.Join(serviceRoot, "../../.."))
	expectedBindings := map[string]string{
		filepath.Join(
			repoRoot,
			"quwoquan_app/scripts/tools/device/beta_manual_app.sh",
		): `ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL="http://127.0.0.1:${USER_PORT}"`,
		filepath.Join(
			repoRoot,
			"quwoquan_ops/cli/alpha/content_release_runtime.py",
		): `f"http://127.0.0.1:{ports['user-service']}"`,
	}
	for path, expected := range expectedBindings {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if !strings.Contains(string(raw), expected) {
			t.Fatalf("%s does not derive account authority from target topology", path)
		}
	}
}

func entityAccountSecurityTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("entity-account-security-test-secret-at-least-32-bytes"),
		Issuer:       "quwoquan-test",
		Audience:     "quwoquan-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
}

func hasScope(scopes []string, expected string) bool {
	for _, scope := range scopes {
		if scope == expected {
			return true
		}
	}
	return false
}
