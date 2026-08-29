// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
)

const (
	accountSecurityAuthorityBaseURLConfigKey = "sys.chat-service.user_account_security_authority.base_url"
	accountSecurityAuthorityTimeoutConfigKey = "sys.chat-service.user_account_security_authority.timeout_ms"
)

// newChatAccountSecurityAuthority 复刻 servicekit.NewAuthStack 对 chat 的装配
// 路径：base_url + timeout_ms + BootstrapSpec 声明的服务间 scope。测试与
// 运行时共用同一构造契约，authority 请求形态漂移即在此暴露。
func newChatAccountSecurityAuthority(
	tokenConfig rtauth.TokenConfig,
	baseURL string,
	timeoutMilliseconds int,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"chat-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, err
	}
	timeout := time.Duration(timeoutMilliseconds) * time.Millisecond
	return rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     baseURL,
			HTTPClient:  &http.Client{Timeout: timeout},
			Credentials: credentials,
			Timeout:     timeout,
		},
	)
}

// TestChatAccountSecurityAuthorityConstructionRejectsMissingOrInvalidRuntimeConfig
// 覆盖装配期拒收。50ms~5s 的超时档位由 chat 的 ValidateConfig 钩子把守，
// 断言在 cmd/api 的 bootstrap_env_keys__local_contract_test.go。
func TestChatAccountSecurityAuthorityConstructionRejectsMissingOrInvalidRuntimeConfig(t *testing.T) {
	validTokenConfig := chatAccountSecurityTokenConfig()
	invalidTokenConfig := validTokenConfig
	invalidTokenConfig.Secret = nil

	for _, testCase := range []struct {
		name    string
		token   rtauth.TokenConfig
		baseURL string
		timeout int
	}{
		{
			name:    "missing user service URL",
			token:   validTokenConfig,
			timeout: 500,
		},
		{
			name:    "non origin user service URL",
			token:   validTokenConfig,
			baseURL: "https://user-service.internal/internal/user",
			timeout: 500,
		},
		{
			name:    "missing timeout",
			token:   validTokenConfig,
			baseURL: "https://user-service.internal",
		},
		{
			name:    "invalid signing configuration",
			token:   invalidTokenConfig,
			baseURL: "https://user-service.internal",
			timeout: 500,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			if _, err := newChatAccountSecurityAuthority(
				testCase.token,
				testCase.baseURL,
				testCase.timeout,
			); err == nil {
				t.Fatal("account security authority construction must fail closed")
			}
		})
	}
}

func TestChatAccountSecurityAuthorityTimeoutConfiguredForEveryEnvironment(t *testing.T) {
	root := chatServiceRepositoryRoot(t)
	type configDefinition struct {
		Key     string `yaml:"key"`
		Type    string `yaml:"type"`
		Default any    `yaml:"default"`
	}
	var schema struct {
		Configs []configDefinition `yaml:"configs"`
	}
	schemaBytes, err := os.ReadFile(filepath.Join(
		root,
		"quwoquan_service/services/chat-service/config/schema.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(schemaBytes, &schema); err != nil {
		t.Fatal(err)
	}

	definitions := map[string]configDefinition{}
	for _, definition := range schema.Configs {
		definitions[definition.Key] = definition
	}
	timeoutDefinition, found := definitions[accountSecurityAuthorityTimeoutConfigKey]
	if !found || timeoutDefinition.Type != "int" {
		t.Fatalf("missing integer timeout config definition: %#v", timeoutDefinition)
	}
	if timeoutDefinition.Default != nil {
		t.Fatal("account security authority timeout must not have a silent default")
	}
	baseURLDefinition, found := definitions[accountSecurityAuthorityBaseURLConfigKey]
	if !found || baseURLDefinition.Type != "string" {
		t.Fatalf("missing string base URL config definition: %#v", baseURLDefinition)
	}
	if baseURLDefinition.Default != nil {
		t.Fatal("account security authority base URL must not have a silent default")
	}
	if _, retired := definitions["sys.chat-service.runtime.auth.account_security_authority.timeout_ms"]; retired {
		t.Fatal("runtime.auth is retired; the authority segment now lives in user_account_security_authority")
	}

	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			var environmentConfig struct {
				Overrides map[string]any `yaml:"overrides"`
			}
			configBytes, readErr := os.ReadFile(filepath.Join(
				root,
				"quwoquan_service/services/chat-service/environments",
				environment,
				"config.yaml",
			))
			if readErr != nil {
				t.Fatal(readErr)
			}
			if unmarshalErr := yaml.Unmarshal(configBytes, &environmentConfig); unmarshalErr != nil {
				t.Fatal(unmarshalErr)
			}
			timeout, ok := environmentConfig.Overrides[accountSecurityAuthorityTimeoutConfigKey].(int)
			if !ok || timeout <= 0 {
				t.Fatal("environment must declare an integer authority timeout")
			}
			baseURL, ok := environmentConfig.Overrides[accountSecurityAuthorityBaseURLConfigKey].(string)
			if !ok || baseURL != "http://user-service:18081" {
				t.Fatalf(
					"environment must target the actual user-service origin, got %q",
					baseURL,
				)
			}
		})
	}
}

func TestChatMiddlewareSynchronouslyEnforcesAccountSecurityAuthority(t *testing.T) {
	tokenConfig := chatAccountSecurityTokenConfig()
	accessVerifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	deviceTokenConfig := tokenConfig
	deviceTokenConfig.Type = rtauth.TokenTypeDevice
	signer, err := rtauth.NewHS256Signer(tokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	accessToken, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "account-1",
		AuthEpoch: 7,
	})
	if err != nil {
		t.Fatal(err)
	}

	type authorityResponse struct {
		status       int
		accountState string
		authEpoch    int64
	}
	var (
		responseMu sync.RWMutex
		response   = authorityResponse{
			status:       http.StatusOK,
			accountState: "active",
			authEpoch:    7,
		}
		requestMu sync.Mutex
		requests  []chatAccountSecurityAuthorityRequest
	)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		claims, verifyErr := accessVerifier.Verify(strings.TrimPrefix(
			request.Header.Get("Authorization"),
			"Bearer ",
		))
		observed := chatAccountSecurityAuthorityRequest{
			path:        request.URL.Path,
			subject:     "",
			scope:       "",
			roles:       nil,
			verifyError: verifyErr,
		}
		if claims != nil {
			observed.subject = claims.Subject
			observed.scope = claims.Scope
			observed.roles = claims.Roles
		}
		requestMu.Lock()
		requests = append(requests, observed)
		requestMu.Unlock()

		if request.URL.Path != "/internal/user/accounts/account-1/security" ||
			verifyErr != nil ||
			claims == nil ||
			claims.Subject != "service:chat-service" ||
			claims.Scope != "user.account.security.read" ||
			len(claims.Roles) != 1 || claims.Roles[0] != "service" {
			http.Error(w, "authority request contract mismatch", http.StatusUnauthorized)
			return
		}

		responseMu.RLock()
		current := response
		responseMu.RUnlock()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(current.status)
		if current.status == http.StatusOK {
			_, _ = w.Write([]byte(
				`{"accountState":"` + current.accountState + `","authEpoch":` +
					strconv.FormatInt(current.authEpoch, 10) + `}`,
			))
		}
	}))
	defer server.Close()

	authority, err := newChatAccountSecurityAuthority(tokenConfig, server.URL, 500)
	if err != nil {
		t.Fatal(err)
	}
	businessCalls := 0
	// chat 的 BootstrapSpec 声明 SkipDeviceTicketAuth，装配出的中间件没有
	// 设备票据 verifier：这里按同一形状构造，才不会用一份服务不具备的
	// 认证能力取证。
	handler := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		AccountSecurityAuthority: authority,
	})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		businessCalls++
		w.WriteHeader(http.StatusNoContent)
	}))

	for _, testCase := range []struct {
		name       string
		response   authorityResponse
		wantStatus int
		wantCode   string
		wantCalls  int
	}{
		{
			name: "closed account rejects a previously issued token",
			response: authorityResponse{
				status: http.StatusOK, accountState: "closed", authEpoch: 7,
			},
			wantStatus: http.StatusGone,
			wantCode:   "USER.AUTH.account_deleted",
		},
		{
			name: "suspended account rejects a previously issued token",
			response: authorityResponse{
				status: http.StatusOK, accountState: "suspended", authEpoch: 7,
			},
			wantStatus: http.StatusForbidden,
			wantCode:   "USER.AUTH.account_suspended",
		},
		{
			name: "stale account epoch rejects a previously issued token",
			response: authorityResponse{
				status: http.StatusOK, accountState: "active", authEpoch: 8,
			},
			wantStatus: http.StatusUnauthorized,
			wantCode:   "USER.AUTH.token_stale",
		},
		{
			name: "unavailable authority denies access",
			response: authorityResponse{
				status: http.StatusServiceUnavailable,
			},
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "USER.AUTH.account_security_unavailable",
		},
		{
			name: "active matching account passes",
			response: authorityResponse{
				status: http.StatusOK, accountState: "active", authEpoch: 7,
			},
			wantStatus: http.StatusNoContent,
			wantCalls:  1,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			responseMu.Lock()
			response = testCase.response
			responseMu.Unlock()

			before := businessCalls
			request := httptest.NewRequest(http.MethodGet, "/chat/conversations", nil)
			request.Header.Set("Authorization", "Bearer "+accessToken)
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)

			if recorder.Code != testCase.wantStatus {
				t.Fatalf("status=%d want=%d", recorder.Code, testCase.wantStatus)
			}
			if businessCalls-before != testCase.wantCalls {
				t.Fatalf(
					"business handler calls=%d want=%d",
					businessCalls-before,
					testCase.wantCalls,
				)
			}
			if testCase.wantCode != "" {
				var payload struct {
					Code string `json:"code"`
				}
				if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
					t.Fatal(err)
				}
				if payload.Code != testCase.wantCode {
					t.Fatalf("code=%q want=%q", payload.Code, testCase.wantCode)
				}
			}
		})
	}

	serviceToken, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "service:chat-worker",
		Roles:     []string{"service"},
	})
	if err != nil {
		t.Fatal(err)
	}
	deviceSigner, err := rtauth.NewHS256Signer(deviceTokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	deviceTicket, err := deviceSigner.Sign(rtauth.TokenSubject{
		DeviceActorID: "device-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	for name, testCase := range map[string]struct {
		request    *http.Request
		wantStatus int
	}{
		"service access token": {
			request: func() *http.Request {
				request := httptest.NewRequest(http.MethodGet, "/internal/chat", nil)
				request.Header.Set("Authorization", "Bearer "+serviceToken)
				return request
			}(),
			wantStatus: http.StatusNoContent,
		},
		// chat 不提供设备票据认证能力：没有 verifier 即拒绝，而不是放行。
		"device ticket": {
			request: func() *http.Request {
				request := httptest.NewRequest(http.MethodGet, "/device/chat", nil)
				request.Header.Set(rtauth.DeviceTicketHeader, deviceTicket)
				return request
			}(),
			wantStatus: http.StatusUnauthorized,
		},
	} {
		t.Run(name, func(t *testing.T) {
			requestMu.Lock()
			before := len(requests)
			requestMu.Unlock()

			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, testCase.request)

			if recorder.Code != testCase.wantStatus {
				t.Fatalf("status=%d want=%d", recorder.Code, testCase.wantStatus)
			}
			requestMu.Lock()
			after := len(requests)
			requestMu.Unlock()
			if after != before {
				t.Fatal("service and device credentials must skip account security authority")
			}
		})
	}

	requestMu.Lock()
	defer requestMu.Unlock()
	if len(requests) != 5 {
		t.Fatalf("authority request count=%d want=5", len(requests))
	}
	for _, request := range requests {
		if request.path != "/internal/user/accounts/account-1/security" ||
			request.verifyError != nil ||
			request.subject != "service:chat-service" ||
			request.scope != "user.account.security.read" ||
			len(request.roles) != 1 || request.roles[0] != "service" {
			t.Fatalf("authority request drift: %#v", request)
		}
	}
}

func TestChatAccountSecurityAuthorityReadinessUsesScopedHealthRoute(t *testing.T) {
	tokenConfig := chatAccountSecurityTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	var (
		requestMu sync.Mutex
		requests  []chatAccountSecurityAuthorityRequest
	)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		claims, verifyErr := verifier.Verify(strings.TrimPrefix(
			request.Header.Get("Authorization"),
			"Bearer ",
		))
		observed := chatAccountSecurityAuthorityRequest{
			path:        request.URL.Path,
			verifyError: verifyErr,
		}
		if claims != nil {
			observed.subject = claims.Subject
			observed.scope = claims.Scope
			observed.roles = claims.Roles
		}
		requestMu.Lock()
		requests = append(requests, observed)
		requestMu.Unlock()

		if request.URL.Path != "/internal/user/account-security/health" ||
			verifyErr != nil ||
			claims == nil ||
			claims.Subject != "service:chat-service" ||
			claims.Scope != "user.account.security.read" ||
			len(claims.Roles) != 1 || claims.Roles[0] != "service" {
			http.Error(w, "authority readiness contract mismatch", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer server.Close()

	authority, err := newChatAccountSecurityAuthority(tokenConfig, server.URL, 500)
	if err != nil {
		t.Fatal(err)
	}
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", authority.CheckAccountSecurityAuthority)
	result := healthChecker.Check(context.Background())
	if result.Status != "ok" || result.Checks["account_security_authority"] != "ok" {
		t.Fatalf("readiness result=%+v", result)
	}

	requestMu.Lock()
	defer requestMu.Unlock()
	if len(requests) != 1 {
		t.Fatalf("readiness request count=%d want=1", len(requests))
	}
	request := requests[0]
	if request.path != "/internal/user/account-security/health" ||
		request.verifyError != nil ||
		request.subject != "service:chat-service" ||
		request.scope != "user.account.security.read" ||
		len(request.roles) != 1 || request.roles[0] != "service" {
		t.Fatalf("readiness request drift: %#v", request)
	}
}

type chatAccountSecurityAuthorityRequest struct {
	path        string
	subject     string
	scope       string
	roles       []string
	verifyError error
}

func chatAccountSecurityTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          5 * time.Minute,
		ClockSkew:    5 * time.Second,
	}
}

func chatServiceRepositoryRoot(t *testing.T) string {
	t.Helper()
	_, sourceFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve chat-service test source path")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(sourceFile),
		"../../../../../../../",
	))
}
