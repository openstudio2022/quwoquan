// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t5
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

	"github.com/prometheus/client_golang/prometheus"
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

func TestProductOpsAccountSecurityAuthorityChargesSlowSuccessToLatencyBudget(t *testing.T) {
	accessConfig := productOpsAuthorityAccessTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		"product-ops-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		time.Sleep(200 * time.Millisecond)
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"accountState":"active","authEpoch":7}`))
	}))
	defer server.Close()
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     server.URL,
			HTTPClient:  &http.Client{Timeout: 1500 * time.Millisecond},
			Credentials: credentials,
			Timeout:     1500 * time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	beforeTotal, beforeWithinSLO := productOpsAuthorityAllowedHistogram(t)
	handler := productOpsAuthorityMiddleware(
		t,
		authority,
		accessConfig,
		productOpsAuthorityDeviceTicketConfig(),
		http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusNoContent)
		}),
	)
	request := httptest.NewRequest(http.MethodPost, "/ops/events", nil)
	request.Header.Set(
		"Authorization",
		"Bearer "+signProductOpsAccessToken(t, accessConfig, "account-1", 7, nil),
	)
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusNoContent {
		t.Fatalf("200ms authority read under 1500ms deadline status=%d, want=204", response.Code)
	}
	afterTotal, afterWithinSLO := productOpsAuthorityAllowedHistogram(t)
	if afterTotal != beforeTotal+1 {
		t.Fatalf("authority histogram count=%d, want=%d", afterTotal, beforeTotal+1)
	}
	if afterWithinSLO != beforeWithinSLO {
		t.Fatalf(
			"200ms authority read must exceed the 150ms SLO bucket: before=%d after=%d",
			beforeWithinSLO,
			afterWithinSLO,
		)
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
		"sys.product-ops-service.user_account_security_authority.base_url",
		"sys.product-ops-service.user_account_security_authority.timeout_ms",
	} {
		definition, exists := definitions[key]
		if !exists {
			t.Fatalf("authority setting %q is not registered in config/schema.yaml", key)
		}
		if _, hasDefault := definition["default"]; hasDefault {
			t.Fatalf("authority setting %q must not have a fallback default", key)
		}
	}
	if definitions["sys.product-ops-service.user_account_security_authority.timeout_ms"]["type"] != "int" {
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
			readProductOpsAuthorityYAML(
				t,
				filepath.Join(root, "environments", environment, "config.yaml"),
				&environmentConfig,
			)
			if got := environmentConfig.Overrides["sys.product-ops-service.user_account_security_authority.base_url"]; got != wantBaseURL {
				t.Fatalf("base URL=%#v, want=%q", got, wantBaseURL)
			}
			if got := environmentConfig.Overrides["sys.product-ops-service.user_account_security_authority.timeout_ms"]; got != 1500 {
				t.Fatalf("timeout=%#v, want=1500ms (hot-swap persist; thrash-tolerant authority probe)", got)
			}
		})
	}
}

func TestProductOpsAPIWiresAccountSecurityAuthorityAndNoPIISLO(t *testing.T) {
	root := productOpsServiceRoot(t)
	bootstrapSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatalf("read API composition: %v", err)
	}
	source := string(bootstrapSource)
	// authority 客户端、凭据与健康检查由 servicekit.Bootstrap 统一装配
	// （DEC-028）；本服务只声明最小 scope 与配置来源，装配语义由
	// runtime/servicekit 的白盒测试锁定。
	for _, required := range []string{
		"servicekit.Bootstrap(serviceName",
		"AuthorityScopes:",
		`"user.account.security.read"`,
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("product-ops API composition is missing %q", required)
		}
	}
	configSource, err := os.ReadFile(filepath.Join(root, "cmd", "api", "runtime_config.go"))
	if err != nil {
		t.Fatalf("read runtime config: %v", err)
	}
	for _, required := range []string{
		"servicekit.BaseConfig",
		"user_account_security_authority.timeout_ms must be within 1..5000",
	} {
		if !strings.Contains(string(configSource), required) {
			t.Fatalf("product-ops runtime config is missing %q", required)
		}
	}
	if strings.Contains(source, "PRODUCT_OPS_ACCOUNT_SECURITY_AUTHORITY") ||
		strings.Contains(string(configSource), "PRODUCT_OPS_ACCOUNT_SECURITY_AUTHORITY") {
		t.Fatal("account security authority must not use an environment fallback")
	}

	var sloEvidence struct {
		Metrics        map[string]string `yaml:"metrics"`
		DeadlinePolicy struct {
			LatencySLOMS               int     `yaml:"latency_slo_ms"`
			RequestDeadlineMS          int     `yaml:"request_deadline_ms"`
			SlowSuccess                string  `yaml:"slow_success"`
			DeadlineExceeded           string  `yaml:"deadline_exceeded"`
			LatencyErrorBudgetFraction float64 `yaml:"latency_error_budget_fraction"`
		} `yaml:"deadline_policy"`
		Alerts []struct {
			ID                string  `yaml:"id"`
			Signal            string  `yaml:"signal"`
			ShortWindow       string  `yaml:"short_window"`
			LongWindow        string  `yaml:"long_window"`
			BurnRateThreshold float64 `yaml:"burn_rate_threshold"`
			Response          string  `yaml:"response"`
		} `yaml:"alerts"`
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
	if sloEvidence.DeadlinePolicy.LatencySLOMS != 150 ||
		sloEvidence.DeadlinePolicy.RequestDeadlineMS != 1500 ||
		sloEvidence.DeadlinePolicy.SlowSuccess !=
			"allow_before_deadline_and_charge_latency_error_budget" ||
		sloEvidence.DeadlinePolicy.DeadlineExceeded !=
			"fail_closed_and_degrade_readiness" ||
		sloEvidence.DeadlinePolicy.LatencyErrorBudgetFraction != 0.05 {
		t.Fatalf("authority deadline/SLO policy drift: %+v", sloEvidence.DeadlinePolicy)
	}
	if len(sloEvidence.Alerts) != 1 ||
		sloEvidence.Alerts[0].ID !=
			"account_security_authority_latency_error_budget_burn" ||
		sloEvidence.Alerts[0].Signal !=
			"AccountSecurityAuthorityLatencyErrorBudgetBurn" ||
		sloEvidence.Alerts[0].ShortWindow != "5m" ||
		sloEvidence.Alerts[0].LongWindow != "1h" ||
		sloEvidence.Alerts[0].BurnRateThreshold != 14.4 ||
		sloEvidence.Alerts[0].Response != "page_owner_and_halt_rollout" {
		t.Fatalf("authority latency burn-rate contract drift: %+v", sloEvidence.Alerts)
	}
	var alertCatalog struct {
		Groups []struct {
			Rules []struct {
				Alert string `yaml:"alert"`
				Expr  string `yaml:"expr"`
			} `yaml:"rules"`
		} `yaml:"groups"`
	}
	readProductOpsAuthorityYAML(
		t,
		filepath.Join(
			root,
			"..",
			"..",
			"..",
			"quwoquan_ops",
			"observability",
			"monitoring",
			"alerts",
			"quwoquan_alerts.yaml",
		),
		&alertCatalog,
	)
	var burnRateExpr string
	for _, group := range alertCatalog.Groups {
		for _, rule := range group.Rules {
			if rule.Alert == "AccountSecurityAuthorityLatencyErrorBudgetBurn" {
				burnRateExpr = rule.Expr
			}
		}
	}
	for _, required := range []string{
		`le="0.15"`,
		"[5m]",
		"[1h]",
		"/ 0.05",
		"> 14.4",
	} {
		if !strings.Contains(burnRateExpr, required) {
			t.Fatalf("authority burn-rate alert missing %q: %s", required, burnRateExpr)
		}
	}
}

func TestProductOpsComposeStartsAccountSecurityAuthorityBeforeHealthGate(t *testing.T) {
	root := productOpsServiceRoot(t)
	var compose struct {
		Services map[string]struct {
			DependsOn map[string]struct {
				Condition string `yaml:"condition"`
			} `yaml:"depends_on"`
		} `yaml:"services"`
	}
	readProductOpsAuthorityYAML(
		t,
		filepath.Join(root, "deploy", "compose.yaml"),
		&compose,
	)
	productOps, ok := compose.Services["product-ops-service"]
	if !ok {
		t.Fatal("product-ops-service Compose workload is missing")
	}
	dependency, ok := productOps.DependsOn["user-service"]
	if !ok {
		t.Fatal("Product Ops must start the public AccountSecurityAuthority owner")
	}
	if dependency.Condition != "service_healthy" {
		t.Fatalf(
			"user-service dependency condition=%q, want service_healthy",
			dependency.Condition,
		)
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

func productOpsAuthorityAllowedHistogram(t *testing.T) (uint64, uint64) {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather authority metrics: %v", err)
	}
	var total uint64
	var withinSLO uint64
	for _, family := range families {
		if family.GetName() !=
			"runtime_auth_account_security_authority_check_duration_seconds" {
			continue
		}
		for _, metric := range family.GetMetric() {
			isAllowed := false
			for _, label := range metric.GetLabel() {
				if label.GetName() == "outcome" && label.GetValue() == "allowed" {
					isAllowed = true
				}
			}
			if !isAllowed || metric.GetHistogram() == nil {
				continue
			}
			total += metric.GetHistogram().GetSampleCount()
			for _, bucket := range metric.GetHistogram().GetBucket() {
				if bucket.GetUpperBound() == 0.15 {
					withinSLO += bucket.GetCumulativeCount()
				}
			}
		}
	}
	return total, withinSLO
}
