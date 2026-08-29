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

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/servicekit"
)

// authority 客户端的构造轨只有一条：servicekit 骨架按服务声明的
// AuthorityScopes 装配（DEC-028）。本文件因此直接对骨架装配取证，而不是对
// 服务内的等价构造器——后者没有生产读取点，对它取证证明不了生产行为。
func entityAuthStack(t *testing.T, baseURL string, timeoutMs int) (*servicekit.AuthStack, error) {
	t.Helper()
	t.Setenv("AUTH_JWT_SECRET", strings.Repeat("s", 64))
	t.Setenv("AUTH_JWT_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-app")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
	t.Setenv("APP_ENV", "alpha")
	t.Setenv("SERVICE_NAME", "entity-service")

	identity, err := servicekit.ResolveIdentity("entity-service")
	if err != nil {
		t.Fatalf("resolve identity: %v", err)
	}
	return servicekit.NewAuthStack(identity, servicekit.AuthStackSpec{
		OperationDescriptors: []rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "entity.homepage.get",
			ContractGraphSHA256:  strings.Repeat("a", 64),
			Transport:            "http",
			Method:               http.MethodGet,
			PathTemplate:         "/entity/homepages/{homepageId}",
			OperationKind:        "query",
			TimeoutMilliseconds:  2000,
		}},
		AccountSecurityAuthority: servicekit.AccountSecurityAuthoritySpec{
			BaseURL:   baseURL,
			TimeoutMs: timeoutMs,
			Scopes:    entityDeclaredAuthorityScopes(t),
		},
		// entity-service 不提供设备票据认证能力，与 bootstrap.go 的声明一致。
		SkipDeviceTicketAuth: true,
	})
}

// entityDeclaredAuthorityScopes 从 bootstrap.go 读取本服务声明的 scope，
// 使凭据取证绑定真实声明而不是测试里重抄一份常量——重抄会让声明改动后
// 测试仍然通过。
func entityDeclaredAuthorityScopes(t *testing.T) []string {
	t.Helper()
	source := readEntityBootstrapSource(t)
	const marker = "AuthorityScopes:"
	index := strings.Index(source, marker)
	if index < 0 {
		t.Fatal("bootstrap.go must declare AuthorityScopes")
	}
	line := source[index:]
	if end := strings.Index(line, "\n"); end >= 0 {
		line = line[:end]
	}
	open := strings.Index(line, "{")
	close := strings.LastIndex(line, "}")
	if open < 0 || close <= open {
		t.Fatalf("AuthorityScopes declaration is not a literal slice: %q", line)
	}
	var scopes []string
	for _, raw := range strings.Split(line[open+1:close], ",") {
		if scope := strings.Trim(strings.TrimSpace(raw), `"`); scope != "" {
			scopes = append(scopes, scope)
		}
	}
	if len(scopes) == 0 {
		t.Fatalf("AuthorityScopes declaration is empty: %q", line)
	}
	return scopes
}

func readEntityBootstrapSource(t *testing.T) string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join(entityServiceRoot(t), "cmd", "api", "bootstrap.go"))
	if err != nil {
		t.Fatalf("read entity bootstrap: %v", err)
	}
	return string(raw)
}

func entityServiceRoot(t *testing.T) string {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve entity-service test source")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(source), "../../../../"))
}

func TestEntityAccountSecurityAuthorityUsesScopedServiceCredential(t *testing.T) {
	var verifier *rtauth.Verifier
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/user/accounts/entity-owner/security" {
			t.Errorf("path=%q", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		claims, err := verifier.Verify(token)
		if err != nil {
			t.Errorf("verify service credential: %v", err)
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if claims.Subject != "service:entity-service" ||
			!hasScope(strings.Fields(claims.Scope), "user.account.security.read") {
			t.Errorf("claims=%+v", claims)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"accountState":"active","authEpoch":4}`))
	}))
	defer server.Close()

	stack, err := entityAuthStack(t, server.URL, 250)
	if err != nil {
		t.Fatalf("auth stack: %v", err)
	}
	verifier = stack.AccessVerifier
	if stack.AccountSecurityAuthority == nil {
		t.Fatal("骨架必须为 entity-service 装配 authority 客户端")
	}
	if _, err := stack.AccountSecurityAuthority.ReadAccountSecurity(
		context.Background(), "entity-owner",
	); err != nil {
		t.Fatal(err)
	}
}

func TestEntityAccountSecurityAuthorityFailsStartupForInvalidConfig(t *testing.T) {
	cases := map[string]struct {
		baseURL   string
		timeoutMs int
	}{
		"missing base url": {baseURL: "", timeoutMs: 250},
		"base url carries a path": {
			baseURL: "https://user-service.internal/path", timeoutMs: 250,
		},
		"non-positive timeout": {baseURL: "https://user-service.internal", timeoutMs: 0},
	}
	for name, testCase := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := entityAuthStack(t, testCase.baseURL, testCase.timeoutMs); err == nil {
				t.Fatal("非法 authority 配置必须让装配失败")
			}
		})
	}
}

func TestEntityAccountSecurityAuthorityUsesDeploymentOriginForHostedEnvironments(
	t *testing.T,
) {
	serviceRoot := entityServiceRoot(t)
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
	serviceRoot := entityServiceRoot(t)
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

func hasScope(scopes []string, expected string) bool {
	for _, scope := range scopes {
		if scope == expected {
			return true
		}
	}
	return false
}
