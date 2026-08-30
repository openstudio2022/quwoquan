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
)

const notificationAccountSecurityAuthorityScope = "user.account.security.read"

func TestNotificationAccountSecurityAuthorityFailsClosedAtConstruction(t *testing.T) {
	accessConfig := notificationAuthorityAccessTokenConfig()
	for _, config := range []struct {
		baseURL   string
		timeoutMS int
	}{
		{},
		{baseURL: "http://user-service:18081"},
		{baseURL: "http://user-service:18081", timeoutMS: 0},
		{baseURL: "http://user-service:18081/path", timeoutMS: 300},
	} {
		if _, err := buildNotificationAccountSecurityAuthority(
			accessConfig, config.baseURL, config.timeoutMS,
		); err == nil {
			t.Fatalf("config=%+v constructed despite missing or invalid authority settings", config)
		}
	}
	if _, err := buildNotificationAccountSecurityAuthority(
		rtauth.TokenConfig{}, "http://user-service:18081", 300,
	); err == nil {
		t.Fatal("missing service credential material must fail authority construction")
	}
}

func TestNotificationAccountSecurityAuthorityUsesLeastPrivilegeRequest(t *testing.T) {
	accessConfig := notificationAuthorityAccessTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodGet ||
			request.URL.Path != "/internal/user/accounts/account-1/security" {
			t.Errorf("authority request=%s %s", request.Method, request.URL.Path)
		}
		assertNotificationAuthorityServiceCredential(t, request, verifier)
		assertNotificationAuthorityHeaders(t, request)
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"accountState":"active","authEpoch":7}`))
	}))
	defer server.Close()

	authority := newNotificationAccountSecurityAuthority(t, server.URL, accessConfig)
	snapshot, err := authority.ReadAccountSecurity(context.Background(), "account-1")
	if err != nil {
		t.Fatalf("read account security: %v", err)
	}
	if snapshot.AccountState != "active" || snapshot.AuthEpoch != 7 {
		t.Fatalf("snapshot=%+v", snapshot)
	}
}

func TestNotificationAccountSecurityAuthorityProtectsEndUserJWTs(t *testing.T) {
	accessConfig := notificationAuthorityAccessTokenConfig()
	for _, testCase := range []struct {
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
	} {
		t.Run(testCase.name, func(t *testing.T) {
			calls := 0
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				calls++
				if request.URL.Path != "/internal/user/accounts/account-1/security" {
					t.Errorf("authority path=%q", request.URL.Path)
				}
				writer.Header().Set("Content-Type", "application/json")
				writer.WriteHeader(testCase.status)
				_, _ = writer.Write([]byte(testCase.body))
			}))
			defer server.Close()

			authority := newNotificationAccountSecurityAuthority(
				t,
				server.URL,
				accessConfig,
			)
			nextCalled := false
			handler := notificationAuthorityMiddleware(
				t,
				authority,
				accessConfig,
				notificationAuthorityDeviceTicketConfig(),
				http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
					nextCalled = true
					writer.WriteHeader(http.StatusNoContent)
				}),
			)
			request := httptest.NewRequest(http.MethodGet, "/notifications", nil)
			request.Header.Set(
				"Authorization",
				"Bearer "+signNotificationAccessToken(
					t,
					accessConfig,
					"account-1",
					testCase.authEpoch,
					nil,
				),
			)
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
			if !testCase.wantNext &&
				strings.Contains(response.Body.String(), "account-1") {
				t.Fatal("authority denial response leaked account identifier")
			}
		})
	}
}

func TestNotificationAccountSecurityAuthorityExemptsServiceAndDevicePrincipals(t *testing.T) {
	accessConfig := notificationAuthorityAccessTokenConfig()
	deviceConfig := notificationAuthorityDeviceTicketConfig()
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		calls++
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()
	authority := newNotificationAccountSecurityAuthority(t, server.URL, accessConfig)
	deviceSigner, err := rtauth.NewHS256Signer(deviceConfig)
	if err != nil {
		t.Fatal(err)
	}
	deviceTicket, err := deviceSigner.Sign(
		rtauth.TokenSubject{DeviceActorID: "device-1"},
	)
	if err != nil {
		t.Fatal(err)
	}

	for name, request := range map[string]*http.Request{
		"service access token": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/notifications", nil)
			value.Header.Set(
				"Authorization",
				"Bearer "+signNotificationAccessToken(
					t,
					accessConfig,
					"service:notification-worker",
					0,
					[]string{"service"},
				),
			)
			return value
		}(),
		"device ticket": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/notifications", nil)
			value.Header.Set(rtauth.DeviceTicketHeader, deviceTicket)
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			handler := notificationAuthorityMiddleware(
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
	if calls != 0 {
		t.Fatalf("authority calls=%d, service/device principals must bypass authority", calls)
	}
}

func TestNotificationAccountSecurityAuthorityReadinessUsesScopedHealthRoute(t *testing.T) {
	accessConfig := notificationAuthorityAccessTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodGet ||
			request.URL.Path != "/internal/user/account-security/health" {
			t.Errorf("health request=%s %s", request.Method, request.URL.Path)
		}
		assertNotificationAuthorityServiceCredential(t, request, verifier)
		assertNotificationAuthorityHeaders(t, request)
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()
	authority := newNotificationAccountSecurityAuthority(t, server.URL, accessConfig)
	if err := authority.CheckAccountSecurityAuthority(context.Background()); err == nil {
		t.Fatal("unavailable authority health route must fail readiness")
	}
}

func TestNotificationAccountSecurityAuthorityConfigurationAndAPIWiring(t *testing.T) {
	root := notificationServiceRoot(t)
	var schema struct {
		Configs []map[string]any `yaml:"configs"`
	}
	readNotificationAuthorityYAML(
		t,
		filepath.Join(root, "config", "schema.yaml"),
		&schema,
	)
	definitions := make(map[string]map[string]any, len(schema.Configs))
	for _, definition := range schema.Configs {
		key, _ := definition["key"].(string)
		definitions[key] = definition
	}
	for _, key := range []string{
		"sys.notification-service.user_account_security_authority.base_url",
		"sys.notification-service.user_account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is absent from config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.notification-service.user_account_security_authority.timeout_ms"]["type"] != "int" {
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
			readNotificationAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.notification-service.user_account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.notification-service.user_account_security_authority.timeout_ms"]; got != 300 {
				t.Fatalf("timeout=%#v, want=300ms", got)
			}
		})
	}

	bootstrapSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatal(err)
	}
	configSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "runtime_config.go"))
	if err != nil {
		t.Fatal(err)
	}
	// 迁移后 authority 客户端、凭据 scope 与 readiness 检查全部由 servicekit
	// 按声明装配，服务侧只声明 scope 与内嵌通用配置段；取证对象随之从服务自建
	// 客户端改为这两处声明。
	source := string(bootstrapSource)
	for _, required := range []string{
		`servicekit.Bootstrap(serviceName`,
		"AuthorityScopes:      []string{accountSecurityReadScope}",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("notification API composition is missing %q", required)
		}
	}
	declaration := string(configSource)
	for _, required := range []string{
		`accountSecurityReadScope = "user.account.security.read"`,
		"servicekit.BaseConfig `yaml:\",inline\"`",
	} {
		if !strings.Contains(declaration, required) {
			t.Fatalf("notification config declaration is missing %q", required)
		}
	}
	if strings.Contains(source, "NOTIFICATION_ACCOUNT_SECURITY") ||
		strings.Contains(declaration, "NOTIFICATION_ACCOUNT_SECURITY") {
		t.Fatal("account security authority must not use an environment fallback")
	}
}

// buildNotificationAccountSecurityAuthority 复刻 servicekit 装配 authority 的
// 输入形状（BaseConfig.user_account_security_authority + AuthorityScopes），
// 让本合约测试与骨架实际走的构造路径同源。
func buildNotificationAccountSecurityAuthority(
	accessConfig rtauth.TokenConfig,
	baseURL string,
	timeoutMS int,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"notification-service",
		[]string{notificationAccountSecurityAuthorityScope},
	)
	if err != nil {
		return nil, err
	}
	timeout := time.Duration(timeoutMS) * time.Millisecond
	return rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     baseURL,
			HTTPClient:  &http.Client{Timeout: timeout},
			Credentials: credentials,
			Timeout:     timeout,
		},
	)
}

func newNotificationAccountSecurityAuthority(
	t *testing.T,
	baseURL string,
	accessConfig rtauth.TokenConfig,
) *rtauth.HTTPAccountSecurityAuthority {
	t.Helper()
	authority, err := buildNotificationAccountSecurityAuthority(accessConfig, baseURL, 300)
	if err != nil {
		t.Fatal(err)
	}
	return authority
}

func notificationAuthorityMiddleware(
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

func notificationAuthorityAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("notification-account-security-authority-contract-secret"),
		Issuer:       "notification-service-contract",
		Audience:     "quwoquan-services",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func notificationAuthorityDeviceTicketConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("notification-device-ticket-authority-contract-secret"),
		Issuer:       "notification-service-contract",
		Audience:     "quwoquan-services",
		Type:         rtauth.TokenTypeDevice,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func signNotificationAccessToken(
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

func assertNotificationAuthorityServiceCredential(
	t *testing.T,
	request *http.Request,
	verifier *rtauth.Verifier,
) {
	t.Helper()
	authorization := strings.TrimSpace(request.Header.Get("Authorization"))
	if !strings.HasPrefix(authorization, "Bearer ") {
		t.Fatalf("authority request has no bearer service credential")
	}
	claims, err := verifier.Verify(strings.TrimPrefix(authorization, "Bearer "))
	if err != nil {
		t.Fatalf("verify authority service credential: %v", err)
	}
	if claims.Subject != "service:notification-service" ||
		claims.Scope != notificationAccountSecurityAuthorityScope ||
		len(claims.Roles) != 1 || claims.Roles[0] != "service" ||
		len(claims.Permissions) != 0 || claims.Persona != "" {
		t.Fatalf("unexpected authority service credential claims=%+v", *claims)
	}
}

func assertNotificationAuthorityHeaders(t *testing.T, request *http.Request) {
	t.Helper()
	if request.Header.Get("Accept") != "application/json" {
		t.Errorf("Accept=%q, want application/json", request.Header.Get("Accept"))
	}
	if request.Header.Get("Cache-Control") != "no-store" {
		t.Errorf("Cache-Control=%q, want no-store", request.Header.Get("Cache-Control"))
	}
	for header := range request.Header {
		switch header {
		case "Authorization", "Accept", "Cache-Control", "User-Agent", "Accept-Encoding":
		default:
			t.Errorf("authority request forwarded unauthorized header %q", header)
		}
	}
}

func readNotificationAuthorityYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatal(err)
	}
}

func notificationServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate notification authority contract test")
	}
	root := filepath.Clean(
		filepath.Join(filepath.Dir(file), "..", "..", "..", ".."),
	)
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatal(err)
	}
	return root
}
