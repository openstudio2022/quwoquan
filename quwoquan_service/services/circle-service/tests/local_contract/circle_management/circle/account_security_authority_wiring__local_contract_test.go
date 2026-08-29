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

func TestCircleAccountSecurityAuthorityRejectsEndUserStates(t *testing.T) {
	accessConfig := circleAuthorityAccessTokenConfig()
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
				assertCircleAuthorityServiceCredential(t, request, serviceVerifier)
				if request.Method != http.MethodGet ||
					request.URL.Path != "/internal/user/accounts/account-1/security" {
					t.Errorf("authority request=%s %s", request.Method, request.URL.Path)
				}
				writer.Header().Set("Content-Type", "application/json")
				writer.WriteHeader(testCase.status)
				_, _ = writer.Write([]byte(testCase.body))
			}))
			defer server.Close()

			authority := newCircleAccountSecurityAuthority(t, server.URL, accessConfig)
			token := signCircleAccessToken(t, accessConfig, "account-1", testCase.authEpoch, nil)
			nextCalled := false
			handler := circleAuthorityMiddleware(
				t,
				authority,
				accessConfig,
				circleAuthorityDeviceTicketConfig(),
				http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
					nextCalled = true
					principal, exists := rtauth.PrincipalFromContext(request.Context())
					if !exists || principal.Actor.AccountID != "account-1" {
						t.Errorf("principal after successful authority check=%+v exists=%v", principal, exists)
					}
					writer.WriteHeader(http.StatusNoContent)
				}),
			)
			request := httptest.NewRequest(http.MethodGet, "/circles", nil)
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

func TestCircleAccountSecurityAuthoritySkipsServiceAndDevicePrincipals(t *testing.T) {
	accessConfig := circleAuthorityAccessTokenConfig()
	deviceConfig := circleAuthorityDeviceTicketConfig()
	serverCalls := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		serverCalls++
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	authority := newCircleAccountSecurityAuthority(t, server.URL, accessConfig)
	serviceToken := signCircleAccessToken(
		t,
		accessConfig,
		"service:circle-worker",
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
		"service access token": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/internal/circle", nil)
			value.Header.Set("Authorization", "Bearer "+serviceToken)
			return value
		}(),
		"device ticket": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/device/circle", nil)
			value.Header.Set(rtauth.DeviceTicketHeader, deviceTicket)
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			handler := circleAuthorityMiddleware(
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
		t.Fatalf("authority calls=%d, service/device principals must bypass authority", serverCalls)
	}
}

func TestCircleAccountSecurityAuthorityConfigurationAndHealthFailClosed(t *testing.T) {
	accessConfig := circleAuthorityAccessTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"circle-service",
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

	authority := newCircleAccountSecurityAuthority(t, server.URL, accessConfig)
	checker := rthealth.NewChecker()
	checker.Register("account_security_authority", authority.CheckAccountSecurityAuthority)
	result := checker.Check(context.Background())
	if result.Status != "degraded" ||
		result.Checks["account_security_authority"] == "ok" {
		t.Fatalf("readiness result=%+v, want degraded authority dependency", result)
	}

	response := httptest.NewRecorder()
	checker.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("health status=%d, want=%d", response.Code, http.StatusServiceUnavailable)
	}
}

func TestCircleAccountSecurityAuthorityConfigurationIsExplicitInEveryEnvironment(t *testing.T) {
	root := circleServiceRoot(t)
	schemaPath := filepath.Join(root, "config", "schema.yaml")
	var schema struct {
		Configs []map[string]any `yaml:"configs"`
	}
	readCircleAuthorityYAML(t, schemaPath, &schema)

	definitions := make(map[string]map[string]any, len(schema.Configs))
	for _, definition := range schema.Configs {
		key, _ := definition["key"].(string)
		definitions[key] = definition
	}
	for _, key := range []string{
		"sys.circle-service.user_account_security_authority.base_url",
		"sys.circle-service.user_account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is not registered in config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.circle-service.user_account_security_authority.timeout_ms"]["type"] != "int" {
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
			readCircleAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.circle-service.user_account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.circle-service.user_account_security_authority.timeout_ms"]; got != 300 {
				t.Fatalf("timeout=%#v, want=300ms", got)
			}
		})
	}
}

func TestCircleAPIWiresAccountSecurityAuthorityAndNoPIISLO(t *testing.T) {
	root := circleServiceRoot(t)
	mainSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatalf("read API composition: %v", err)
	}
	source := string(mainSource)
	// 迁移到声明式 servicekit.Bootstrap 后（DEC-028），authority spec 的装配、
	// 健康检查接线与认证中间件包裹全部由骨架承担，其必然性由 servicekit 同包
	// 白盒测试锁定（TestBootstrapAssemblesFullChain 断言 account_security_authority
	// 健康检查注册；NewAuthStack 用例锁定凭据与 authority 客户端 fail-closed）。
	// composition 侧断言收敛为：走声明式骨架、authority 配置段来自内嵌
	// BaseConfig、最小授权范围显式声明。
	for _, required := range []string{
		`servicekit.Bootstrap("circle-service"`,
		"servicekit.BaseConfig",
		"AuthorityScopes:",
		`"user.account.security.read"`,
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("circle API composition is missing %q", required)
		}
	}
	if strings.Contains(source, "CIRCLE_ACCOUNT_SECURITY_AUTHORITY") {
		t.Fatal("account security authority must not use an environment fallback")
	}

	var sloEvidence struct {
		Metrics map[string]string `yaml:"metrics"`
		Privacy struct {
			PermittedLabels  []string `yaml:"permitted_labels"`
			ProhibitedLabels []string `yaml:"prohibited_labels"`
		} `yaml:"privacy"`
	}
	readCircleAuthorityYAML(
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

func circleAuthorityAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("circle-account-security-authority-test-secret"),
		Issuer:       "circle-service-test",
		Audience:     "circle-service-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func circleAuthorityDeviceTicketConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("circle-device-ticket-authority-test-secret"),
		Issuer:       "circle-service-test",
		Audience:     "circle-service-test",
		Type:         rtauth.TokenTypeDevice,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func newCircleAccountSecurityAuthority(
	t *testing.T,
	baseURL string,
	accessConfig rtauth.TokenConfig,
) *rtauth.HTTPAccountSecurityAuthority {
	t.Helper()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"circle-service",
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

func circleAuthorityMiddleware(
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

func signCircleAccessToken(
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

func assertCircleAuthorityServiceCredential(
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
	if claims.Subject != "service:circle-service" ||
		!containsString(claims.Roles, "service") ||
		!containsString(strings.Fields(claims.Scope), "user.account.security.read") {
		t.Errorf("authority service credential claims=%+v", *claims)
	}
}

func readCircleAuthorityYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
}

func circleServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate circle authority contract test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatalf("resolve circle-service root: %v", err)
	}
	return root
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
