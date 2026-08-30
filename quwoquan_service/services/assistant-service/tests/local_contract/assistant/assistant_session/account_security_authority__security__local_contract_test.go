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

	"gopkg.in/yaml.v3"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
)

const assistantAccountSecurityAuthorityScope = "user.account.security.read"

func TestAssistantAccountSecurityAuthorityConfigurationFailsClosed(t *testing.T) {
	accessConfig := assistantAccountSecurityAuthorityTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"assistant-service",
		[]string{assistantAccountSecurityAuthorityScope},
	)
	if err != nil {
		t.Fatal(err)
	}

	for _, testCase := range []rtauth.HTTPAccountSecurityAuthorityConfig{
		{
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: credentials,
			Timeout:     time.Second,
		},
		{
			BaseURL:     "https://user-service.internal/not-an-origin",
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: credentials,
			Timeout:     time.Second,
		},
		{
			BaseURL:     "https://user-service.internal",
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: credentials,
		},
	} {
		if _, err := rtauth.NewHTTPAccountSecurityAuthority(testCase); err == nil {
			t.Fatal("missing or invalid authority config must fail startup construction")
		}
	}

	invalidAccessConfig := accessConfig
	invalidAccessConfig.Secret = nil
	if _, err := rtauth.NewHS256ServiceAuthorizationProvider(
		invalidAccessConfig,
		"assistant-service",
		[]string{assistantAccountSecurityAuthorityScope},
	); err == nil {
		t.Fatal("invalid authority service credential config must fail startup construction")
	}
}

func TestAssistantAccountSecurityAuthorityConfigIsExplicitInEveryEnvironment(t *testing.T) {
	root := assistantServiceRoot(t)
	var schema struct {
		Configs []map[string]any `yaml:"configs"`
	}
	readAssistantAuthorityYAML(t, filepath.Join(root, "config", "schema.yaml"), &schema)

	definitions := make(map[string]map[string]any, len(schema.Configs))
	for _, definition := range schema.Configs {
		key, _ := definition["key"].(string)
		definitions[key] = definition
	}
	for _, key := range []string{
		"sys.assistant-service.user_account_security_authority.base_url",
		"sys.assistant-service.user_account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is missing from config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.assistant-service.user_account_security_authority.timeout_ms"]["type"] != "int" {
		t.Fatal("authority timeout must be an integer config value")
	}

	wantBaseURLs := map[string]string{
		"alpha": "http://user-service:18081",
		"beta":  "http://user-service:18081",
		"gamma": "http://user-service:18081",
		"prod":  "http://user-service:18081",
	}
	for environment, wantBaseURL := range wantBaseURLs {
		t.Run(environment, func(t *testing.T) {
			var environmentConfig struct {
				Overrides map[string]any `yaml:"overrides"`
			}
			readAssistantAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.assistant-service.user_account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.assistant-service.user_account_security_authority.timeout_ms"]; got != 300 {
				t.Fatalf("timeout=%#v, want=300ms", got)
			}
		})
	}
}

func TestAssistantMiddlewareSynchronouslyEnforcesAccountSecurityAuthority(t *testing.T) {
	accessConfig := assistantAccountSecurityAuthorityTokenConfig()
	accessVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}
	accessToken := signAssistantAccessToken(t, accessConfig, "account-1", 7)

	for _, testCase := range []struct {
		name       string
		status     int
		body       string
		wantStatus int
		wantNext   bool
	}{
		{
			name:       "active matching epoch passes",
			status:     http.StatusOK,
			body:       `{"accountState":"active","authEpoch":7}`,
			wantStatus: http.StatusNoContent,
			wantNext:   true,
		},
		{
			name:       "closed account fails closed",
			status:     http.StatusOK,
			body:       `{"accountState":"closed","authEpoch":7}`,
			wantStatus: http.StatusGone,
		},
		{
			name:       "suspended account fails closed",
			status:     http.StatusOK,
			body:       `{"accountState":"suspended","authEpoch":7}`,
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "stale epoch fails closed",
			status:     http.StatusOK,
			body:       `{"accountState":"active","authEpoch":8}`,
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "unavailable authority fails closed",
			status:     http.StatusServiceUnavailable,
			wantStatus: http.StatusServiceUnavailable,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			calls := 0
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				calls++
				assertAssistantAuthorityServiceCredential(t, request, accessVerifier)
				if request.Method != http.MethodGet ||
					request.URL.Path != "/internal/user/accounts/account-1/security" {
					http.Error(writer, "unexpected authority request", http.StatusUnauthorized)
					return
				}
				writer.Header().Set("Content-Type", "application/json")
				writer.WriteHeader(testCase.status)
				_, _ = writer.Write([]byte(testCase.body))
			}))
			defer server.Close()

			authority := newAssistantAccountSecurityAuthority(t, server.URL, accessConfig)
			nextCalled := false
			handler := rtauth.Middleware(rtauth.MiddlewareConfig{
				AccessTokenVerifier:      accessVerifier,
				AccountSecurityAuthority: authority,
			})(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				nextCalled = true
				principal, exists := rtauth.PrincipalFromContext(request.Context())
				if !exists || principal.Actor.AccountID != "account-1" {
					t.Errorf("principal injected before authority result=%+v exists=%v", principal, exists)
				}
				writer.WriteHeader(http.StatusNoContent)
			}))

			request := httptest.NewRequest(http.MethodGet, "/assistant/sessions", nil)
			request.Header.Set("Authorization", "Bearer "+accessToken)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)

			if response.Code != testCase.wantStatus {
				t.Fatalf("status=%d, want=%d", response.Code, testCase.wantStatus)
			}
			if nextCalled != testCase.wantNext {
				t.Fatalf("nextCalled=%v, want=%v", nextCalled, testCase.wantNext)
			}
			if calls != 1 {
				t.Fatalf("authority calls=%d, want=1", calls)
			}
		})
	}
}

func TestAssistantAccountSecurityAuthorityReadinessUsesScopedHealthRoute(t *testing.T) {
	accessConfig := assistantAccountSecurityAuthorityTokenConfig()
	accessVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		assertAssistantAuthorityServiceCredential(t, request, accessVerifier)
		if request.Method != http.MethodGet ||
			request.URL.Path != "/internal/user/account-security/health" {
			http.Error(writer, "unexpected authority readiness request", http.StatusUnauthorized)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"status":"ok"}`))
	}))
	defer server.Close()

	authority := newAssistantAccountSecurityAuthority(t, server.URL, accessConfig)
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", authority.CheckAccountSecurityAuthority)
	result := healthChecker.Check(context.Background())
	if result.Status != "ok" || result.Checks["account_security_authority"] != "ok" {
		t.Fatalf("readiness result=%+v", result)
	}
}

func TestAssistantAPIWiresAccountSecurityAuthorityWithoutPIILabels(t *testing.T) {
	root := assistantServiceRoot(t)
	source, err := os.ReadFile(filepath.Join(root, "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatal(err)
	}
	// authority 客户端与其 readiness 检查已上收到 servicekit（DEC-028）：
	// 服务侧只声明所需 scope，装配与健康注册在骨架一处成立。
	for _, required := range []string{
		"AuthorityScopes:",
		`"user.account.security.read"`,
		"accountSecurityAuthority: asm.Auth.AccountSecurityAuthority",
	} {
		if !strings.Contains(string(source), required) {
			t.Fatalf("assistant API composition is missing %q", required)
		}
	}
	if strings.Contains(string(source), "ASSISTANT_ACCOUNT_SECURITY_AUTHORITY") {
		t.Fatal("account security authority must not use an environment fallback")
	}
	kitAuth, err := os.ReadFile(
		filepath.Join(root, "..", "..", "runtime", "servicekit", "auth.go"),
	)
	if err != nil {
		t.Fatal(err)
	}
	kitBootstrap, err := os.ReadFile(
		filepath.Join(root, "..", "..", "runtime", "servicekit", "bootstrap.go"),
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, required := range []string{
		"rtauth.NewHS256ServiceAuthorizationProvider(",
		"rtauth.NewHTTPAccountSecurityAuthority(",
		"BaseURL:     spec.AccountSecurityAuthority.BaseURL",
	} {
		if !strings.Contains(string(kitAuth), required) {
			t.Fatalf("servicekit auth stack is missing %q", required)
		}
	}
	for _, required := range []string{
		`health.Register("account_security_authority"`,
		"CheckAccountSecurityAuthority(hctx)",
		`yaml:"user_account_security_authority"`,
	} {
		if !strings.Contains(string(kitBootstrap), required) {
			t.Fatalf("servicekit bootstrap is missing %q", required)
		}
	}

	var sloEvidence struct {
		Metrics map[string]string `yaml:"metrics"`
		Privacy struct {
			PermittedLabels  []string `yaml:"permitted_labels"`
			ProhibitedLabels []string `yaml:"prohibited_labels"`
		} `yaml:"privacy"`
	}
	readAssistantAuthorityYAML(
		t,
		filepath.Join(root, "observability", "slo", "account_security_authority_slo.yaml"),
		&sloEvidence,
	)
	if sloEvidence.Metrics["authority_checks_total"] !=
		"runtime_auth_account_security_authority_checks_total" ||
		sloEvidence.Metrics["readiness_status"] != "runtime_health_check_status" {
		t.Fatalf("authority SLO metrics drift: %#v", sloEvidence.Metrics)
	}
	if strings.Join(sloEvidence.Privacy.PermittedLabels, ",") != "outcome,check" {
		t.Fatalf("authority SLO labels must remain non-identifying: %#v", sloEvidence.Privacy.PermittedLabels)
	}
	if strings.Join(sloEvidence.Privacy.ProhibitedLabels, ",") !=
		"account_id,persona_id,token,authorization,request_path" {
		t.Fatalf("authority SLO PII exclusions drift: %#v", sloEvidence.Privacy.ProhibitedLabels)
	}
}

func assistantAccountSecurityAuthorityTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("assistant-account-security-authority-test-secret"),
		Issuer:       "assistant-service-test",
		Audience:     "assistant-service-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func signAssistantAccessToken(
	t *testing.T,
	config rtauth.TokenConfig,
	accountID string,
	authEpoch int64,
) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		AuthEpoch: authEpoch,
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func newAssistantAccountSecurityAuthority(
	t *testing.T,
	baseURL string,
	accessConfig rtauth.TokenConfig,
) *rtauth.HTTPAccountSecurityAuthority {
	t.Helper()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"assistant-service",
		[]string{assistantAccountSecurityAuthorityScope},
	)
	if err != nil {
		t.Fatal(err)
	}
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     baseURL,
			HTTPClient:  &http.Client{Timeout: 300 * time.Millisecond},
			Credentials: credentials,
			Timeout:     300 * time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return authority
}

func assertAssistantAuthorityServiceCredential(
	t *testing.T,
	request *http.Request,
	verifier *rtauth.Verifier,
) {
	t.Helper()
	header := strings.TrimSpace(request.Header.Get("Authorization"))
	if !strings.HasPrefix(header, "Bearer ") {
		t.Errorf("authority request has no bearer service credential")
		return
	}
	claims, err := verifier.Verify(strings.TrimPrefix(header, "Bearer "))
	if err != nil {
		t.Errorf("verify authority service credential: %v", err)
		return
	}
	if claims.Subject != "service:assistant-service" ||
		!containsAssistantAuthorityString(claims.Roles, "service") ||
		claims.Scope != assistantAccountSecurityAuthorityScope {
		t.Errorf("authority service credential claims=%+v", *claims)
	}
}

func readAssistantAuthorityYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
}

func assistantServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate assistant authority contract test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatalf("resolve assistant-service root: %v", err)
	}
	return root
}

func containsAssistantAuthorityString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
