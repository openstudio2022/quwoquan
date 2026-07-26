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

func TestProductOpsAccountSecurityAuthorityProtectsEndUserRequests(t *testing.T) {
	accessConfig := productOpsAuthorityAccessTokenConfig()
	serviceVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name       string
		status     int
		body       string
		authEpoch  int64
		wantStatus int
		wantNext   bool
	}{
		{
			name:       "active matching epoch passes",
			status:     http.StatusOK,
			body:       `{"accountState":"active","authEpoch":7}`,
			authEpoch:  7,
			wantStatus: http.StatusNoContent,
			wantNext:   true,
		},
		{
			name:       "closed account is rejected",
			status:     http.StatusOK,
			body:       `{"accountState":"closed","authEpoch":7}`,
			authEpoch:  7,
			wantStatus: http.StatusGone,
		},
		{
			name:       "suspended account is rejected",
			status:     http.StatusOK,
			body:       `{"accountState":"suspended","authEpoch":7}`,
			authEpoch:  7,
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "stale epoch is rejected",
			status:     http.StatusOK,
			body:       `{"accountState":"active","authEpoch":8}`,
			authEpoch:  7,
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "authority unavailable is rejected",
			status:     http.StatusServiceUnavailable,
			authEpoch:  7,
			wantStatus: http.StatusServiceUnavailable,
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			calls := 0
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				calls++
				assertProductOpsAuthorityServiceCredential(t, request, serviceVerifier)
				if request.Method != http.MethodGet ||
					request.URL.Path != "/internal/user/accounts/account-1/security" {
					t.Errorf("authority request=%s %s", request.Method, request.URL.Path)
				}
				if request.Header.Get("Cache-Control") != "no-store" {
					t.Errorf("authority Cache-Control=%q, want no-store", request.Header.Get("Cache-Control"))
				}
				writer.Header().Set("Content-Type", "application/json")
				writer.WriteHeader(testCase.status)
				_, _ = writer.Write([]byte(testCase.body))
			}))
			defer server.Close()

			authority := newProductOpsAccountSecurityAuthority(t, server.URL, accessConfig)
			token := signProductOpsAccessToken(t, accessConfig, "account-1", testCase.authEpoch, nil)
			nextCalled := false
			handler := productOpsAuthorityMiddleware(
				t,
				authority,
				accessConfig,
				productOpsAuthorityDeviceTicketConfig(),
				http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
					nextCalled = true
					principal, exists := rtauth.PrincipalFromContext(request.Context())
					if !exists || principal.Actor.AccountID != "account-1" {
						t.Errorf("principal after authority check=%+v exists=%v", principal, exists)
					}
					writer.WriteHeader(http.StatusNoContent)
				}),
			)
			request := httptest.NewRequest(http.MethodPost, "/ops/events", nil)
			request.Header.Set("Authorization", "Bearer "+token)
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
			if !testCase.wantNext && strings.Contains(response.Body.String(), "account-1") {
				t.Fatal("authority denial response leaked account identifier")
			}
		})
	}
}

func TestProductOpsAccountSecurityAuthorityExemptsOperatorServiceAndDevicePrincipals(t *testing.T) {
	accessConfig := productOpsAuthorityAccessTokenConfig()
	deviceConfig := productOpsAuthorityDeviceTicketConfig()
	serverCalls := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		serverCalls++
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	authority := newProductOpsAccountSecurityAuthority(t, server.URL, accessConfig)
	operatorToken := signProductOpsAccessToken(
		t,
		accessConfig,
		"operator-1",
		0,
		[]string{"operator"},
	)
	serviceToken := signProductOpsAccessToken(
		t,
		accessConfig,
		"service:ops-worker",
		0,
		[]string{"service"},
	)
	deviceSigner, err := rtauth.NewHS256Signer(deviceConfig)
	if err != nil {
		t.Fatal(err)
	}
	deviceTicket, err := deviceSigner.Sign(rtauth.TokenSubject{DeviceActorID: "device-1"})
	if err != nil {
		t.Fatal(err)
	}

	for name, request := range map[string]*http.Request{
		"operator access token": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/ops/metrics", nil)
			value.Header.Set("Authorization", "Bearer "+operatorToken)
			return value
		}(),
		"service access token": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/ops/metrics", nil)
			value.Header.Set("Authorization", "Bearer "+serviceToken)
			return value
		}(),
		"device ticket": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/ops/events", nil)
			value.Header.Set(rtauth.DeviceTicketHeader, deviceTicket)
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			handler := productOpsAuthorityMiddleware(
				t,
				authority,
				accessConfig,
				deviceConfig,
				http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
					writer.WriteHeader(http.StatusNoContent)
				}),
			)
			response := httptest.NewRecorder()

			handler.ServeHTTP(response, request)

			if response.Code != http.StatusNoContent {
				t.Fatalf("status=%d, want=%d", response.Code, http.StatusNoContent)
			}
		})
	}
	if serverCalls != 0 {
		t.Fatalf("authority calls=%d, operator/service/device principals must bypass authority", serverCalls)
	}
}

func TestProductOpsAccountSecurityAuthorityFailsClosedDuringConstructionAndHealth(t *testing.T) {
	accessConfig := productOpsAuthorityAccessTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"product-ops-service",
		[]string{"user.account.security.read"},
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
			BaseURL:     "http://user-service/compat",
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: credentials,
			Timeout:     time.Second,
		},
		{
			BaseURL:     "http://user-service:18081",
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: credentials,
		},
	} {
		if _, err := rtauth.NewHTTPAccountSecurityAuthority(testCase); err == nil {
			t.Fatal("missing or invalid authority settings must fail startup construction")
		}
	}

	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.URL.Path != "/internal/user/account-security/health" {
			t.Errorf("health path=%q", request.URL.Path)
		}
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	authority := newProductOpsAccountSecurityAuthority(t, server.URL, accessConfig)
	checker := rthealth.NewChecker()
	checker.Register("account-security-authority", authority.CheckAccountSecurityAuthority)
	result := checker.Check(context.Background())
	if result.Status != "degraded" ||
		result.Checks["account-security-authority"] == "ok" {
		t.Fatalf("readiness result=%+v, want degraded authority dependency", result)
	}

	response := httptest.NewRecorder()
	checker.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("health status=%d, want=%d", response.Code, http.StatusServiceUnavailable)
	}
}

func TestProductOpsAccountSecurityAuthorityConfigurationIsExplicitInEveryEnvironment(t *testing.T) {
	root := productOpsServiceRoot(t)
	schemaPath := filepath.Join(root, "config", "schema.yaml")
	var schema struct {
		Configs []map[string]any `yaml:"configs"`
	}
	readProductOpsAuthorityYAML(t, schemaPath, &schema)

	definitions := make(map[string]map[string]any, len(schema.Configs))
	for _, definition := range schema.Configs {
		key, _ := definition["key"].(string)
		definitions[key] = definition
	}
	for _, key := range []string{
		"sys.product-ops-service.account_security_authority.base_url",
		"sys.product-ops-service.account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is not registered in config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.product-ops-service.account_security_authority.timeout_ms"]["type"] != "int" {
		t.Fatal("authority timeout must be an integer config value")
	}

	wantBaseURLs := map[string]string{
		"alpha": "http://127.0.0.1:18081",
		"beta":  "http://127.0.0.1:18081",
		"gamma": "http://user-service:18081",
		"prod":  "http://user-service:18081",
	}
	for environment, wantBaseURL := range wantBaseURLs {
		t.Run(environment, func(t *testing.T) {
			var environmentConfig struct {
				Overrides map[string]any `yaml:"overrides"`
			}
			readProductOpsAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.product-ops-service.account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.product-ops-service.account_security_authority.timeout_ms"]; got != 300 {
				t.Fatalf("timeout=%#v, want=300ms", got)
			}
		})
	}
}

func TestProductOpsAPIWiresAccountSecurityAuthorityAndNoPIISLO(t *testing.T) {
	root := productOpsServiceRoot(t)
	mainSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "main.go"))
	if err != nil {
		t.Fatalf("read API composition: %v", err)
	}
	source := string(mainSource)
	for _, required := range []string{
		"rtauth.NewHS256ServiceAuthorizationProvider(",
		`"user.account.security.read"`,
		"rtauth.NewHTTPAccountSecurityAuthority(",
		"BaseURL:     cfg.AccountSecurityAuthority.BaseURL",
		"Timeout:     accountSecurityAuthorityTimeout",
		`healthChecker.Register("account-security-authority"`,
		"return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)",
		"AccountSecurityAuthority: accountSecurityAuthority",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("product-ops API composition is missing %q", required)
		}
	}
	if strings.Contains(source, "PRODUCT_OPS_ACCOUNT_SECURITY_AUTHORITY") {
		t.Fatal("account security authority must not use an environment fallback")
	}

	var sloEvidence struct {
		Metrics map[string]string `yaml:"metrics"`
		Privacy struct {
			PermittedLabels  []string `yaml:"permitted_labels"`
			ProhibitedLabels []string `yaml:"prohibited_labels"`
		} `yaml:"privacy"`
	}
	readProductOpsAuthorityYAML(
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
		t.Fatalf("authority SLO labels must remain fixed and non-identifying: %#v", sloEvidence.Privacy.PermittedLabels)
	}
	if strings.Join(sloEvidence.Privacy.ProhibitedLabels, ",") !=
		"account_id,persona_id,token,authorization,request_path" {
		t.Fatalf("authority SLO PII exclusions drift: %#v", sloEvidence.Privacy.ProhibitedLabels)
	}
}

func productOpsAuthorityAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("product-ops-account-security-authority-test-secret"),
		Issuer:       "product-ops-service-test",
		Audience:     "product-ops-service-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func productOpsAuthorityDeviceTicketConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("product-ops-device-ticket-authority-test-secret"),
		Issuer:       "product-ops-service-test",
		Audience:     "product-ops-service-test",
		Type:         rtauth.TokenTypeDevice,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func newProductOpsAccountSecurityAuthority(
	t *testing.T,
	baseURL string,
	accessConfig rtauth.TokenConfig,
) *rtauth.HTTPAccountSecurityAuthority {
	t.Helper()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"product-ops-service",
		[]string{"user.account.security.read"},
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

func productOpsAuthorityMiddleware(
	t *testing.T,
	authority rtauth.AccountSecurityAuthority,
	accessConfig rtauth.TokenConfig,
	deviceConfig rtauth.TokenConfig,
	next http.Handler,
) http.Handler {
	t.Helper()
	accessVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceConfig)
	if err != nil {
		t.Fatal(err)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		DeviceTicketVerifier:     deviceVerifier,
		AccountSecurityAuthority: authority,
	})(next)
}

func signProductOpsAccessToken(
	t *testing.T,
	config rtauth.TokenConfig,
	accountID string,
	authEpoch int64,
	roles []string,
) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		AuthEpoch: authEpoch,
		Roles:     roles,
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func assertProductOpsAuthorityServiceCredential(
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
	if claims.Subject != "service:product-ops-service" ||
		!productOpsAuthorityContains(claims.Roles, "service") ||
		!productOpsAuthorityContains(strings.Fields(claims.Scope), "user.account.security.read") {
		t.Errorf("authority service credential claims=%+v", *claims)
	}
}

func readProductOpsAuthorityYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
}

func productOpsServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate product-ops authority contract test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "main.go")); err != nil {
		t.Fatalf("resolve product-ops-service root: %v", err)
	}
	return root
}

func productOpsAuthorityContains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
