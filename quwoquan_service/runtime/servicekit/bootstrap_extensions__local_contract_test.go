package servicekit

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	rthttp "quwoquan_service/runtime/http"
)

// 本文件锁定为 user-service（自托管 authority、admission 前置放行）与
// api-edge（认证外层中间件、按环境分档的 operation guard、显式 CORS）补的
// 骨架能力。每一项都取证「缺声明即 fail-closed」，而不只是「有声明能跑通」。

// selfHostedFixtureEnvironment 换掉快照里的 authority 段：authority 的提供方
// 不该在自己的配置里声明一个指向自己的 base_url，所以自托管取证必须用不含
// 该段的快照，而不是靠 env 覆盖把它清空。
func selfHostedFixtureEnvironment(t *testing.T) {
	t.Helper()
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	root := t.TempDir()
	snapshot := strings.Join([]string{
		"config:",
		"  version: sha256:cfg-fixture",
		"service:",
		"  http:",
		"    addr: \":19082\"",
		"greeting:",
		"  label: from-snapshot",
		"redis:",
		"  general:",
		"    mode: memory",
		"",
	}, "\n")
	if err := os.WriteFile(
		filepath.Join(root, "bootstrap-fixture.yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CONFIG_ROOT", root)
}

func passthroughGate(next http.Handler) http.Handler { return next }

// 发布身份校验必须早于任何领域构件被构造。api-edge 迁移前用一条源码文本位置
// 断言守着这个相对顺序（`StartReleaseConfigAttestation` 出现在
// `OperationAuthorizationForRuntime` 之前），骨架接手后那条判据的字面量不再
// 共存于服务源码，顺序只剩 Bootstrap 实现本身保证。这里改用行为取证把它锁回
// 来：判据不是文本位置而是「身份不可信时领域构件一次都没被构造」，因此重排
// Bootstrap 内部相位会直接让它失败。
func TestReleaseIdentityIsValidatedBeforeDomainConstructsAreBuilt(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	// latest 是可变引用：这个进程跑的是哪份产物无法回答。
	t.Setenv("IMAGE_VERSION", "latest")

	guardConstructed := false
	assembleRan := false
	spec := bootstrapFixtureSpec()
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		guardConstructed = true
		return passthroughGate, nil
	}
	spec.Assemble = func(*Assembly, *bootstrapFixtureConfig) error {
		assembleRan = true
		return nil
	}

	_, err := Bootstrap("bootstrap-fixture", spec)
	if err == nil {
		t.Fatal("expected a mutable IMAGE_VERSION to be rejected")
	}
	// 断言失败原因就是发布身份，否则「工厂没被调用」可能只是因为装配在更早
	// 的某一步因无关原因就断了。
	if !strings.Contains(err.Error(), "IMAGE_VERSION is not immutable") {
		t.Fatalf("expected release identity rejection, got %v", err)
	}
	if guardConstructed {
		t.Fatal("operation guard was constructed before the release identity was validated")
	}
	if assembleRan {
		t.Fatal("domain assembly ran before the release identity was validated")
	}
}

// 反例的对照：身份可信时两者都会被构造。缺了它，上一条测试无法区分「顺序
// 正确」与「这两个钩子根本不会被调用」。
func TestDomainConstructsAreBuiltOnceTheReleaseIdentityIsTrusted(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	guardConstructed := false
	assembleRan := false
	spec := bootstrapFixtureSpec()
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		guardConstructed = true
		return passthroughGate, nil
	}
	spec.Assemble = func(*Assembly, *bootstrapFixtureConfig) error {
		assembleRan = true
		return nil
	}

	if _, err := Bootstrap("bootstrap-fixture", spec); err != nil {
		t.Fatalf("expected bootstrap to succeed, got %v", err)
	}
	if !guardConstructed || !assembleRan {
		t.Fatalf(
			"expected both constructs to be built, guard=%v assemble=%v",
			guardConstructed, assembleRan,
		)
	}
}

func TestSelfHostedAuthorityRequiresInProcessGate(t *testing.T) {
	selfHostedFixtureEnvironment(t)

	spec := bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	// Assemble 不交出 gate：自托管形态下认证层的 authority 面是 nil，若领域
	// gate 也缺席，账号安全就静默失效，因此必须在装配阶段失败。
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "provided no in-process gate") {
		t.Fatalf("expected missing in-process gate rejection, got %v", err)
	}

	spec = bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		return asm.Auth.ProvideInProcessAccountSecurityGate(passthroughGate)
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err != nil {
		t.Fatalf("expected self-hosted authority bootstrap to succeed, got %v", err)
	}
}

func TestSelfHostedAuthorityLeavesAuthenticationLayerWithoutAuthority(t *testing.T) {
	selfHostedFixtureEnvironment(t)

	spec := bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		// 认证层不得持有裁决面：它在 operation guard 之外，拿不到 operation
		// 上下文，无法表达 operation 级豁免。
		if asm.Auth.accountSecurityGate != nil {
			t.Error("self-hosted authority must not install an authentication-layer gate")
		}
		if asm.Auth.AccountSecurityAuthority != nil {
			t.Error("self-hosted authority must not build an HTTP client to itself")
		}
		return asm.Auth.ProvideInProcessAccountSecurityGate(passthroughGate)
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	// 远端 authority 就绪检查也不得登记：本服务没有这个外部依赖。
	if result := module.health.Check(context.Background()); resultContainsCheck(
		result.FailedChecks, "account_security_authority",
	) {
		t.Fatal("self-hosted authority must not register a remote readiness check")
	}
}

func TestInProcessGateRunsInsideOperationGuard(t *testing.T) {
	selfHostedFixtureEnvironment(t)

	var order []string
	spec := bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		return func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				order = append(order, "operation_guard")
				next.ServeHTTP(writer, request)
			})
		}, nil
	}
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		asm.Mux.HandleFunc("/greeting", func(writer http.ResponseWriter, _ *http.Request) {
			order = append(order, "domain_route")
			writer.WriteHeader(http.StatusNoContent)
		})
		return asm.Auth.ProvideInProcessAccountSecurityGate(
			func(next http.Handler) http.Handler {
				return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
					order = append(order, "account_security_gate")
					next.ServeHTTP(writer, request)
				})
			},
		)
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}

	module.server.Handler.ServeHTTP(
		httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/greeting", nil),
	)

	expected := []string{"operation_guard", "account_security_gate", "domain_route"}
	if strings.Join(order, ">") != strings.Join(expected, ">") {
		t.Fatalf("gate must run inside the operation guard, got %v", order)
	}
}

func TestSelfHostedAuthorityRejectsRemoteAuthorityDeclaration(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	spec := bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	// 快照里的 base_url 保留、scopes 也保留：两者都指向「远端 authority」，
	// 与自托管声明矛盾，必须被拒而不是二选一静默生效。
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "hosts the account security authority itself") {
		t.Fatalf("expected contradictory authority declaration rejection, got %v", err)
	}

	spec = bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.SkipAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "declares both") {
		t.Fatalf("expected skip/self-hosted conflict rejection, got %v", err)
	}
}

func TestSelfHostedAuthorityRejectsDoubleGateProvision(t *testing.T) {
	selfHostedFixtureEnvironment(t)

	spec := bootstrapFixtureSpec()
	spec.SelfHostedAccountSecurityAuthority = true
	spec.AuthorityScopes = nil
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		if err := asm.Auth.ProvideInProcessAccountSecurityGate(passthroughGate); err != nil {
			return err
		}
		return asm.Auth.ProvideInProcessAccountSecurityGate(passthroughGate)
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "already provided") {
		t.Fatalf("expected double provision rejection, got %v", err)
	}
}

func TestProvideGateRejectedWithoutSelfHostedDeclaration(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	spec := bootstrapFixtureSpec()
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		return asm.Auth.ProvideInProcessAccountSecurityGate(passthroughGate)
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "did not declare SelfHosted") {
		t.Fatalf("expected undeclared provision rejection, got %v", err)
	}
}

func resultContainsCheck(checks []string, name string) bool {
	for _, check := range checks {
		if check == name {
			return true
		}
	}
	return false
}

// 领域专属就绪子路由必须在 admission 开放前可达：发布编排靠它分辨「尚未就绪」
// 与「故障」，若被 admission 门统一判 503，两者不可区分。
func TestReadinessSubroutesAreReachableBeforeAdmission(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	spec := bootstrapFixtureSpec()
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		asm.Unguarded().HandleFunc(
			"/readyz/config-convergence",
			func(writer http.ResponseWriter, _ *http.Request) {
				writer.WriteHeader(http.StatusOK)
			},
		)
		asm.Mux.HandleFunc("/greeting", func(http.ResponseWriter, *http.Request) {})
		return nil
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}

	// 刻意不 OpenAdmission。
	recorder := httptest.NewRecorder()
	module.server.Handler.ServeHTTP(
		recorder,
		httptest.NewRequest(http.MethodGet, "/readyz/config-convergence", nil),
	)
	if recorder.Code != http.StatusOK {
		t.Fatalf("就绪子路由必须绕过 admission 门，得到 %d", recorder.Code)
	}

	// 业务面在 admission 开放前仍必须被拒，放行判据不得扩散。
	recorder = httptest.NewRecorder()
	module.server.Handler.ServeHTTP(
		recorder, httptest.NewRequest(http.MethodGet, "/greeting", nil),
	)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("业务面在 admission 开放前必须被拒，得到 %d", recorder.Code)
	}
}

func TestPreAdmissionPathsOnlyAcceptExactInternalPaths(t *testing.T) {
	for _, path := range []string{
		"/user/profile",        // 业务路由
		"/internal/",           // 前缀式放行
		"/internal/user/*",     // 通配
		"internal/user/health", // 缺前导斜杠
		" /metrics ",           // 非 internal
	} {
		if _, err := normalizePreAdmissionPaths("fixture", []string{path}); err == nil {
			t.Fatalf("expected %q to be rejected as a pre-admission path", path)
		}
	}
	paths, err := normalizePreAdmissionPaths(
		"fixture", []string{"/internal/user/account-security/health"},
	)
	if err != nil {
		t.Fatalf("expected exact internal path to be accepted, got %v", err)
	}
	if !paths["/internal/user/account-security/health"] {
		t.Fatal("normalized pre-admission path is missing")
	}
}

func TestPreAdmissionPathBypassesClosedAdmissionGate(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	const internalPath = "/internal/fixture/health"
	spec := bootstrapFixtureSpec()
	spec.PreAdmissionPaths = []string{internalPath}
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		asm.Mux.HandleFunc(internalPath, func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusNoContent)
		})
		asm.Mux.HandleFunc("/greeting", func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusNoContent)
		})
		return nil
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	handler := module.server.Handler

	// admission 尚未开放：声明的内部端点放行，业务路由仍被挡。
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, internalPath, nil))
	if recorder.Code == http.StatusServiceUnavailable {
		t.Fatal("pre-admission path must not be blocked by the admission gate")
	}
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/greeting", nil))
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("business route must stay blocked before admission, got %d", recorder.Code)
	}
}

func TestWrapOutsideAuthObservesRequestBeforeAuthentication(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	var sawRawCredential string
	spec := bootstrapFixtureSpec()
	spec.WrapOutsideAuth = func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			sawRawCredential = request.Header.Get("Authorization")
			next.ServeHTTP(writer, request)
		})
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}

	request := httptest.NewRequest(http.MethodGet, "/greeting", nil)
	request.Header.Set("Authorization", "Bearer raw-inbound-token")
	module.server.Handler.ServeHTTP(httptest.NewRecorder(), request)

	if sawRawCredential != "Bearer raw-inbound-token" {
		t.Fatalf("outside-auth wrapper must see the raw credential, got %q", sawRawCredential)
	}
}

func TestOperationGuardFactoryReceivesIdentityAndFailsClosed(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	var observedEnv string
	spec := bootstrapFixtureSpec()
	spec.OperationGuard = func(identity Identity) (func(http.Handler) http.Handler, error) {
		observedEnv = identity.AppEnv
		return func(handler http.Handler) http.Handler { return handler }, nil
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if observedEnv != "alpha" {
		t.Fatalf("operation guard factory must receive the resolved env, got %q", observedEnv)
	}

	// 构造失败不得退化成无 guard。
	spec = bootstrapFixtureSpec()
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		return nil, context.DeadlineExceeded
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "operation guard invalid") {
		t.Fatalf("expected guard construction failure to block startup, got %v", err)
	}

	spec = bootstrapFixtureSpec()
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		return nil, nil
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "no middleware") {
		t.Fatalf("expected nil guard middleware rejection, got %v", err)
	}
}

func TestDeclaredCORSOverridesEnvironmentDerivedOptions(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	t.Setenv("OPS_ALLOWED_ORIGINS", "https://drifting.example")

	const declaredOrigin = "https://declared.example"
	spec := bootstrapFixtureSpec()
	spec.CORS = &rthttp.CORSOptions{
		AllowedOrigins: []string{declaredOrigin},
		AllowedMethods: []string{http.MethodGet},
		AllowedHeaders: []string{"Content-Type"},
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/greeting", nil)
	request.Header.Set("Origin", declaredOrigin)
	module.server.Handler.ServeHTTP(recorder, request)
	if got := recorder.Header().Get("Access-Control-Allow-Origin"); got != declaredOrigin {
		t.Fatalf("declared origin must be allowed, got %q", got)
	}

	recorder = httptest.NewRecorder()
	request = httptest.NewRequest(http.MethodGet, "/greeting", nil)
	request.Header.Set("Origin", "https://drifting.example")
	module.server.Handler.ServeHTTP(recorder, request)
	if got := recorder.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("env-derived origin must not leak past a declared policy, got %q", got)
	}
}

// 未声明 CORS 的服务不得挂载 CORS 中间件。rthttp.WithCORS 对 OPTIONS 无条件
// 短路返回 204，那个面不过观测、不过 operation guard、不过共享准入，也不计量；
// 把它设成骨架默认会让每个服务凭空多一个未认证可探测面。
func TestUndeclaredCORSLeavesOptionsToTheOperationGuard(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	t.Setenv("OPS_ALLOWED_ORIGINS", "https://drifting.example")

	var guardSawOptions bool
	spec := bootstrapFixtureSpec()
	spec.OperationGuard = func(Identity) (func(http.Handler) http.Handler, error) {
		return func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				if request.Method == http.MethodOptions {
					guardSawOptions = true
				}
				next.ServeHTTP(writer, request)
			})
		}, nil
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodOptions, "/greeting", nil)
	request.Header.Set("Origin", "https://drifting.example")
	module.server.Handler.ServeHTTP(recorder, request)

	if !guardSawOptions {
		t.Fatal("OPTIONS 必须进入 operation guard，而不是被 CORS 短路")
	}
	if recorder.Code == http.StatusNoContent {
		t.Fatal("未声明 CORS 时不得出现 204 短路面")
	}
	if got := recorder.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("未声明 CORS 时不得写出跨域头，得到 %q", got)
	}
}

// 声明了 CORS 的服务保留 OPTIONS 预检短路——这是浏览器直连入口的既有语义。
func TestDeclaredCORSShortCircuitsPreflight(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	const declaredOrigin = "https://declared.example"
	spec := bootstrapFixtureSpec()
	spec.CORS = &rthttp.CORSOptions{
		AllowedOrigins: []string{declaredOrigin},
		AllowedMethods: []string{http.MethodGet},
		AllowedHeaders: []string{"Content-Type"},
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodOptions, "/greeting", nil)
	request.Header.Set("Origin", declaredOrigin)
	module.server.Handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusNoContent {
		t.Fatalf("declared CORS must answer preflight with 204, got %d", recorder.Code)
	}
}

func TestFallibleWorkerFailureBlocksStart(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	spec := bootstrapFixtureSpec()
	spec.Assemble = func(asm *Assembly, _ *bootstrapFixtureConfig) error {
		asm.Workers.AddFallible("fixture_scheduler", func(context.Context) error {
			return context.DeadlineExceeded
		})
		return nil
	}
	module, err := Bootstrap("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if err := module.Bind(context.Background()); err != nil {
		t.Fatalf("bind: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = module.Shutdown(shutdownCtx)
	}()

	err = module.Start(context.Background())
	if err == nil || !strings.Contains(err.Error(), "fixture_scheduler") {
		t.Fatalf("expected fallible worker failure to fail Start, got %v", err)
	}
}

func TestConfigPathIsWrittenIntoBaseConfig(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	var observedPath string
	spec := bootstrapFixtureSpec()
	spec.ValidateConfig = func(cfg *bootstrapFixtureConfig) error {
		observedPath = cfg.ConfigPath
		return nil
	}
	if _, err := Bootstrap("bootstrap-fixture", spec); err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if !strings.HasSuffix(observedPath, "bootstrap-fixture.yaml") {
		t.Fatalf("ValidateConfig must see the effective snapshot path, got %q", observedPath)
	}
}
