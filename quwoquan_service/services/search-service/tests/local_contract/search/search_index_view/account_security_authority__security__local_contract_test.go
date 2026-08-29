// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
)

func TestSearchAccountSecurityAuthorityProtectsEndUserRequests(t *testing.T) {
	accessConfig := searchAuthorityAccessTokenConfig()
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
				assertSearchAuthorityServiceCredential(t, request, serviceVerifier)
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

			authority := newSearchAccountSecurityAuthority(t, server.URL, accessConfig)
			token := signSearchAccessToken(t, accessConfig, "account-1", testCase.authEpoch, nil)
			nextCalled := false
			handler := searchAuthorityMiddleware(
				t,
				authority,
				accessConfig,
				searchAuthorityDeviceTicketConfig(),
				http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
					nextCalled = true
					principal, exists := rtauth.PrincipalFromContext(request.Context())
					if !exists || principal.Actor.AccountID != "account-1" {
						t.Errorf("principal after authority check=%+v exists=%v", principal, exists)
					}
					writer.WriteHeader(http.StatusNoContent)
				}),
			)
			request := httptest.NewRequest(http.MethodGet, "/search", nil)
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

func TestSearchAccountSecurityAuthorityExemptsServiceAndDevicePrincipals(t *testing.T) {
	accessConfig := searchAuthorityAccessTokenConfig()
	deviceConfig := searchAuthorityDeviceTicketConfig()
	serverCalls := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		serverCalls++
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	authority := newSearchAccountSecurityAuthority(t, server.URL, accessConfig)
	serviceToken := signSearchAccessToken(
		t,
		accessConfig,
		"service:search-worker",
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
			value := httptest.NewRequest(http.MethodGet, "/search", nil)
			value.Header.Set("Authorization", "Bearer "+serviceToken)
			return value
		}(),
		"device ticket": func() *http.Request {
			value := httptest.NewRequest(http.MethodGet, "/search", nil)
			value.Header.Set(rtauth.DeviceTicketHeader, deviceTicket)
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			handler := searchAuthorityMiddleware(
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

func TestSearchAccountSecurityAuthorityFailsClosedDuringConstructionAndHealth(t *testing.T) {
	accessConfig := searchAuthorityAccessTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"search-service",
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

	authority := newSearchAccountSecurityAuthority(t, server.URL, accessConfig)
	checker := rthealth.NewChecker()
	// 检查名与 servicekit 注册的名字保持一致：它是 /readyz 的可观测键，也是
	// observability/slo 里 runtime_health_check_status 的 check 标签值。
	checker.Register(searchAuthorityHealthCheckName, authority.CheckAccountSecurityAuthority)
	result := checker.Check(context.Background())
	if result.Status != "degraded" ||
		result.Checks[searchAuthorityHealthCheckName] == "ok" {
		t.Fatalf("readiness result=%+v, want degraded authority dependency", result)
	}

	response := httptest.NewRecorder()
	checker.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("health status=%d, want=%d", response.Code, http.StatusServiceUnavailable)
	}
}

func TestSearchAccountSecurityAuthorityConfigurationIsExplicitInEveryEnvironment(t *testing.T) {
	root := searchServiceRoot(t)
	schemaPath := filepath.Join(root, "config", "schema.yaml")
	var schema struct {
		Configs []map[string]any `yaml:"configs"`
	}
	readSearchAuthorityYAML(t, schemaPath, &schema)

	definitions := make(map[string]map[string]any, len(schema.Configs))
	for _, definition := range schema.Configs {
		key, _ := definition["key"].(string)
		definitions[key] = definition
	}
	// 键名跟随 servicekit.BaseConfig 的 user_account_security_authority 标准段：
	// 配置快照的路径就是 Go 侧读取的路径，不存在第二套映射。
	for _, key := range []string{
		"sys.search-service.user_account_security_authority.base_url",
		"sys.search-service.user_account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is not registered in config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.search-service.user_account_security_authority.timeout_ms"]["type"] != "int" {
		t.Fatal("authority timeout must be an integer config value")
	}
	esTimeoutDefinition, exists := definitions["sys.search-service.es.requestTimeoutMs"]
	if !exists {
		t.Fatal("Elasticsearch request timeout must be registered in config/schema.yaml")
	}
	if got := esTimeoutDefinition["default"]; got != 800 {
		t.Fatalf("Elasticsearch request timeout default=%#v, want=800ms", got)
	}
	if _, retired := definitions["sys.search-service.accountSecurityAuthority.baseUrl"]; retired {
		t.Fatal("retired accountSecurityAuthority keys must not coexist with the standard section")
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
			readSearchAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.search-service.user_account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.search-service.user_account_security_authority.timeout_ms"]; got != 300 {
				t.Fatalf("timeout=%#v, want=300ms", got)
			}
			if got, overridden := environmentConfig.Overrides["sys.search-service.es.requestTimeoutMs"]; overridden {
				t.Fatalf(
					"Elasticsearch request timeout must use canonical 800ms default, got overlay=%#v",
					got,
				)
			}

			repositoryRoot := filepath.Dir(filepath.Dir(filepath.Dir(root)))
			renderedPath := filepath.Join(t.TempDir(), "search-service.yaml")
			command := exec.Command(
				"python3",
				filepath.Join(repositoryRoot, "quwoquan_ops", "cli", "render_runtime_config.py"),
				"--env", environment,
				"--workload", "search-service",
				"--output", renderedPath,
			)
			command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
			if combined, err := command.CombinedOutput(); err != nil {
				t.Fatalf("render %s Search config: %v\n%s", environment, err, combined)
			}
			var effectiveConfig struct {
				ES struct {
					RequestTimeoutMs int `yaml:"requestTimeoutMs"`
				} `yaml:"es"`
			}
			readSearchAuthorityYAML(t, renderedPath, &effectiveConfig)
			if got := effectiveConfig.ES.RequestTimeoutMs; got != 800 {
				t.Fatalf("rendered Elasticsearch request timeout=%dms, want=800ms", got)
			}
		})
	}
}

func TestSearchAPIWiresAccountSecurityAuthorityAndNoPIISLO(t *testing.T) {
	root := searchServiceRoot(t)
	bootstrapSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatalf("read API composition: %v", err)
	}
	runtimeConfigSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "runtime_config.go"))
	if err != nil {
		t.Fatalf("read API runtime config: %v", err)
	}
	// 去空白后比对：断言的是装配契约，不是 gofmt 对对齐与换行的选择。
	source := stripSearchProbeWhitespace(
		string(bootstrapSource) + "\n" + string(runtimeConfigSource),
	)
	// authority 客户端、凭据与 readiness 检查由 servicekit 统一装配；服务侧的
	// 责任是声明最小 scope 并从 BaseConfig 标准段拿地址/超时，而不是自建第二套
	// authority 客户端。
	for _, required := range []string{
		"servicekit.Bootstrap(serviceName",
		"AuthorityScopes:[]string{\"user.account.security.read\"}",
		"servicekit.BaseConfig`yaml:\",inline\"`",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("search API composition is missing %q", required)
		}
	}
	for _, forbidden := range []string{
		"SEARCH_ACCOUNT_SECURITY_AUTHORITY",
		"rtauth.NewHTTPAccountSecurityAuthority(",
	} {
		if strings.Contains(source, forbidden) {
			t.Fatalf("account security authority must stay servicekit-owned, found %q", forbidden)
		}
	}

	var sloEvidence struct {
		Metrics map[string]string `yaml:"metrics"`
		Privacy struct {
			PermittedLabels  []string `yaml:"permitted_labels"`
			ProhibitedLabels []string `yaml:"prohibited_labels"`
		} `yaml:"privacy"`
		SLIs []struct {
			ID  string `yaml:"id"`
			SLI string `yaml:"sli"`
		} `yaml:"slis"`
	}
	readSearchAuthorityYAML(
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
	// readiness SLI 的 check 标签必须等于 servicekit 注册的检查名；写错不会报错，
	// 只会让这条 SLI 永远匹配空序列。
	readinessSLI := ""
	for _, sli := range sloEvidence.SLIs {
		if sli.ID == "account_security_authority_readiness" {
			readinessSLI = sli.SLI
		}
	}
	wantReadinessSLI := `runtime_health_check_status{check="` +
		searchAuthorityHealthCheckName + `"}`
	if readinessSLI != wantReadinessSLI {
		t.Fatalf("authority readiness SLI=%q, want=%q", readinessSLI, wantReadinessSLI)
	}
}

// searchAuthorityHealthCheckName 是 servicekit 为账号安全 authority 注册的健康
// 检查名，同时是 /readyz 与 runtime_health_check_status 的 check 标签值。
const searchAuthorityHealthCheckName = "account_security_authority"

func searchAuthorityAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("search-account-security-authority-test-secret"),
		Issuer:       "search-service-test",
		Audience:     "search-service-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func searchAuthorityDeviceTicketConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("search-device-ticket-authority-test-secret"),
		Issuer:       "search-service-test",
		Audience:     "search-service-test",
		Type:         rtauth.TokenTypeDevice,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func newSearchAccountSecurityAuthority(
	t *testing.T,
	baseURL string,
	accessConfig rtauth.TokenConfig,
) *rtauth.HTTPAccountSecurityAuthority {
	t.Helper()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"search-service",
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

func searchAuthorityMiddleware(
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

func signSearchAccessToken(
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

func assertSearchAuthorityServiceCredential(
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
	if claims.Subject != "service:search-service" ||
		!searchAuthorityContains(claims.Roles, "service") ||
		!searchAuthorityContains(strings.Fields(claims.Scope), "user.account.security.read") {
		t.Errorf("authority service credential claims=%+v", *claims)
	}
}

func readSearchAuthorityYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
}

func searchServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate search authority contract test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatalf("resolve search-service root: %v", err)
	}
	return root
}

func searchAuthorityContains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
