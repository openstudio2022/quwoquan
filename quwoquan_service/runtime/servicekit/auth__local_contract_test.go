package servicekit

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
)

func authTestEnvironment(t *testing.T) {
	t.Helper()
	secret := strings.Repeat("s", 64)
	t.Setenv("AUTH_JWT_SECRET", secret)
	t.Setenv("AUTH_JWT_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-app")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
	t.Setenv("AUTH_DEVICE_TICKET_SECRET", strings.Repeat("d", 64))
	t.Setenv("AUTH_DEVICE_TICKET_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_DEVICE_TICKET_AUDIENCE", "quwoquan-device")
	t.Setenv("AUTH_DEVICE_TICKET_TOKEN_VERSION", "1")
}

func authTestSpec() AuthStackSpec {
	return AuthStackSpec{
		OperationDescriptors: []rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.get",
			ContractGraphSHA256:  strings.Repeat("a", 64),
			Transport:            "http",
			Method:               http.MethodGet,
			PathTemplate:         "/circles/{circleId}",
			OperationKind:        "query",
			TimeoutMilliseconds:  2000,
		}},
		AccountSecurityAuthority: AccountSecurityAuthoritySpec{
			BaseURL:   "http://user.internal:18081",
			TimeoutMs: 800,
			Scopes:    []string{"user.account.security.read"},
		},
	}
}

// TestNewAuthStackSkipsDeviceTicketWhenCapabilityIsNotDeclared 锁定按能力
// 声明装配：未声明设备票据认证的服务不要求其配置在场，但带设备票据的请求
// 仍被 nil verifier fail-closed 拒绝，不是放行。
func TestNewAuthStackSkipsDeviceTicketWhenCapabilityIsNotDeclared(t *testing.T) {
	authTestEnvironment(t)
	t.Setenv("AUTH_DEVICE_TICKET_SECRET", "")
	t.Setenv("AUTH_DEVICE_TICKET_ISSUER", "")
	t.Setenv("AUTH_DEVICE_TICKET_AUDIENCE", "")
	t.Setenv("AUTH_DEVICE_TICKET_TOKEN_VERSION", "")

	spec := authTestSpec()
	if _, err := NewAuthStack(Identity{ServiceName: "entity-service"}, spec); err == nil {
		t.Fatal("declaring device ticket auth without its config must fail closed")
	}

	spec.SkipDeviceTicketAuth = true
	stack, err := NewAuthStack(Identity{ServiceName: "entity-service"}, spec)
	if err != nil {
		t.Fatalf("undeclared device ticket capability must not require its config: %v", err)
	}
	if stack.DeviceTicketVerifier != nil {
		t.Fatal("device ticket verifier must stay unassembled when undeclared")
	}

	handler := stack.WrapHTTPHandler(http.HandlerFunc(
		func(http.ResponseWriter, *http.Request) {
			t.Fatal("device ticket credential must not reach the inner handler")
		},
	))
	request := httptest.NewRequest(http.MethodGet, "/homepages/h1", nil)
	request.Header.Set("X-Device-Ticket", "any-ticket")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for device ticket without verifier, got %d", recorder.Code)
	}
}

// TestNewAuthStackAccountSecurityAuthorityAbsenceIsDeclared 锁定账号安全
// authority 的「声明缺席」形态：不声明就必须有 base_url（缺失即 fail-closed），
// 声明缺席后不装配客户端也不登记就绪依赖，但终端用户账号 principal 仍被拒，
// 而不是绕过账号状态检查放行。声明缺席同时给出 base_url/scopes 是矛盾声明。
func TestNewAuthStackAccountSecurityAuthorityAbsenceIsDeclared(t *testing.T) {
	authTestEnvironment(t)

	spec := authTestSpec()
	spec.AccountSecurityAuthority = AccountSecurityAuthoritySpec{}
	if _, err := NewAuthStack(Identity{ServiceName: "circle-service"}, spec); err == nil ||
		!strings.Contains(err.Error(), "account security authority") {
		t.Fatalf("undeclared absence with no base URL must fail closed, got %v", err)
	}

	spec.SkipAccountSecurityAuthority = true
	stack, err := NewAuthStack(Identity{ServiceName: "platform-ops-service"}, spec)
	if err != nil {
		t.Fatalf("declared absence must assemble: %v", err)
	}
	if stack.AccountSecurityAuthority != nil {
		t.Fatal("declared absence must not assemble an authority client")
	}
	if _, ok := stack.accountSecurityGate.(deniedAccountSecurityAuthority); !ok {
		t.Fatalf(
			"declared absence must install the deny-all gate, got %T",
			stack.accountSecurityGate,
		)
	}

	contradicting := authTestSpec()
	contradicting.SkipAccountSecurityAuthority = true
	if _, err := NewAuthStack(
		Identity{ServiceName: "platform-ops-service"}, contradicting,
	); err == nil || !strings.Contains(err.Error(), "SkipAccountSecurityAuthority") {
		t.Fatalf("contradicting absence declaration must fail closed, got %v", err)
	}
}

// TestDeclaredAccountSecurityAbsenceDeniesEndUserPrincipal 锁定声明缺席不是
// 放行：一个签名有效的终端用户 access token 必须被账号安全裁决面拒绝。
func TestDeclaredAccountSecurityAbsenceDeniesEndUserPrincipal(t *testing.T) {
	authTestEnvironment(t)
	spec := authTestSpec()
	spec.AccountSecurityAuthority = AccountSecurityAuthoritySpec{}
	spec.SkipAccountSecurityAuthority = true
	stack, err := NewAuthStack(Identity{ServiceName: "platform-ops-service"}, spec)
	if err != nil {
		t.Fatalf("declared absence must assemble: %v", err)
	}

	signer, err := rtauth.NewHS256Signer(stack.AccessTokenConfig)
	if err != nil {
		t.Fatalf("access token signer: %v", err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "acct-1",
		AuthEpoch: 1,
	})
	if err != nil {
		t.Fatalf("sign end-user access token: %v", err)
	}

	handler := stack.WrapHTTPHandler(http.HandlerFunc(
		func(http.ResponseWriter, *http.Request) {
			t.Fatal("end-user account principal must not reach the inner handler")
		},
	))
	request := httptest.NewRequest(http.MethodGet, "/circles/c1", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf(
			"expected account security unavailable rejection, got %d: %s",
			recorder.Code, recorder.Body.String(),
		)
	}
}

func TestNewAuthStackRequiresOperationDescriptors(t *testing.T) {
	authTestEnvironment(t)
	spec := authTestSpec()
	spec.OperationDescriptors = nil
	_, err := NewAuthStack(Identity{ServiceName: "circle-service"}, spec)
	if err == nil || !strings.Contains(err.Error(), "operation descriptors") {
		t.Fatalf("expected descriptor requirement, got %v", err)
	}
}

func TestNewAuthStackFailsClosedWithoutTokenConfig(t *testing.T) {
	authTestEnvironment(t)
	t.Setenv("AUTH_JWT_SECRET", "")
	_, err := NewAuthStack(Identity{ServiceName: "circle-service"}, authTestSpec())
	if err == nil || !strings.Contains(err.Error(), "access token config") {
		t.Fatalf("expected access token fail-closed, got %v", err)
	}
}

func TestNewAuthStackAssemblesVerifiersAndTimeouts(t *testing.T) {
	authTestEnvironment(t)
	stack, err := NewAuthStack(Identity{ServiceName: "circle-service"}, authTestSpec())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if stack.AccessVerifier == nil || stack.DeviceTicketVerifier == nil {
		t.Fatal("expected both verifiers to be constructed")
	}
	if stack.AccountSecurityAuthority == nil {
		t.Fatal("expected account security authority client")
	}
	if stack.Timeouts.ReadHeader <= 0 || stack.Timeouts.Write <= 0 || stack.Timeouts.Idle <= 0 {
		t.Fatalf("expected contract-derived timeouts, got %+v", stack.Timeouts)
	}
}

func TestAuthStackMiddlewareRejectsInvalidCredential(t *testing.T) {
	authTestEnvironment(t)
	stack, err := NewAuthStack(Identity{ServiceName: "circle-service"}, authTestSpec())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	handler := stack.WrapHTTPHandler(http.HandlerFunc(
		func(http.ResponseWriter, *http.Request) {
			t.Fatal("invalid credential must not reach the inner handler")
		},
	))
	request := httptest.NewRequest(http.MethodGet, "/circles/c1", nil)
	request.Header.Set("Authorization", "Bearer not-a-real-token")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for invalid credential, got %d", recorder.Code)
	}
}

func TestAuthStackGuardRejectsUndeclaredOperation(t *testing.T) {
	authTestEnvironment(t)
	stack, err := NewAuthStack(Identity{ServiceName: "circle-service"}, authTestSpec())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	guarded := stack.GuardOperations(http.HandlerFunc(
		func(http.ResponseWriter, *http.Request) {
			t.Fatal("undeclared operation must not reach the inner handler")
		},
	))
	recorder := httptest.NewRecorder()
	guarded.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/undeclared/route", nil))
	if recorder.Code < 400 {
		t.Fatalf("expected fail-closed rejection for undeclared route, got %d", recorder.Code)
	}
}
