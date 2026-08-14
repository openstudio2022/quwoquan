package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	rterr "quwoquan_service/runtime/errors"
	"sync/atomic"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/servicehost"
)

// Module is assistant-service's service-owned servicehost adapter.
type Module struct {
	runtime        *assistantAPIRuntime
	infrastructure *assistantInfrastructure
	assistant      *assistantComponents
	workers        *assistantBackgroundWorkers
	server         *http.Server
	listener       net.Listener
	admissionOpen  atomic.Bool
	serveError     chan error
}

var _ servicehost.Module = (*Module)(nil)

// NewModule performs service-owned configuration and dependency assembly. The
// host subsequently controls listener binding, worker start, admission and
// shutdown without reaching into assistant private implementation.
func NewModule() (*Module, error) {
	runtime, err := bootstrapAssistantAPIRuntime()
	if err != nil {
		return nil, err
	}

	infrastructure, err := bootstrapAssistantInfrastructure(runtime)
	if err != nil {
		runtime.Close()
		return nil, err
	}

	assistant, err := wireAssistantRuntime(runtime, infrastructure)
	if err != nil {
		infrastructure.Close()
		runtime.Close()
		return nil, err
	}

	server := buildAssistantHTTPServer(runtime, infrastructure, assistant)
	module := &Module{
		runtime:        runtime,
		infrastructure: infrastructure,
		assistant:      assistant,
		server:         server,
		serveError:     make(chan error, 1),
	}
	server.Handler = module.admissionHandler(server.Handler)
	return module, nil
}

func (module *Module) Name() string { return "assistant-service" }

func (module *Module) ConfigDigest() string {
	if module == nil || module.runtime == nil {
		return ""
	}
	return module.runtime.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.runtime == nil || module.infrastructure == nil || module.assistant == nil {
		return errors.New("assistant-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(ctx context.Context) error {
	// 把官方 Skill package 激活收敛到 candidate 挂载的签名 publication:
	// 空环境首次激活、candidate 更迭受控升级、已收敛零写入,使 readiness
	// 的 active-package 检查不再与环境启动死锁。
	return bootstrapOfficialSkillPackage(
		ctx,
		module.assistant.skillPackageService,
		module.infrastructure.dependencies.skillPackageStore,
		module.runtime.config.SkillPackage.AssetRoot,
	)
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("assistant-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("assistant-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(context.Context) error {
	workers, err := startAssistantBackgroundWorkers(
		module.runtime,
		module.infrastructure,
		module.assistant,
	)
	if err != nil {
		return err
	}
	module.workers = workers
	go func() {
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			module.serveError <- err
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.infrastructure.healthChecker.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("assistant-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("assistant-service listener failed: %w", err)
	default:
		return nil
	}
}

func (module *Module) OpenAdmission(context.Context) error {
	module.admissionOpen.Store(true)
	return nil
}

func (module *Module) Shutdown(ctx context.Context) error {
	module.admissionOpen.Store(false)
	var result error
	if module.server != nil {
		result = errors.Join(result, module.server.Shutdown(ctx))
	}
	if module.workers != nil {
		result = errors.Join(result, module.workers.Close())
	}
	if module.infrastructure != nil {
		module.infrastructure.Close()
	}
	if module.runtime != nil {
		module.runtime.Close()
	}
	return result
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/readyz", "/metrics":
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admissionOpen.Load() {
			rterr.WriteHTTPError(
				writer,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindMiddleware, "upstream_unavailable"),
					"服务暂不可用，请稍后重试",
					"service admission is not ready",
				).WithMetadata("upstream_unavailable", http.StatusServiceUnavailable).
					WithRecoveryDirective("retry", "snackbar", 1),
				rterr.HTTPWriteOptionsFromRequest(request),
			)
			return
		}
		next.ServeHTTP(writer, request)
	})
}

func buildAccountSecurityAuthority(
	cfg config,
	accessTokenConfig rtauth.TokenConfig,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority credential init failed: %w", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.AccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient:  &http.Client{Timeout: accountSecurityAuthorityTimeout},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority config invalid: %w", err)
	}
	return accountSecurityAuthority, nil
}

func registerAccountSecurityAuthorityHealth(
	healthChecker *rthealth.Checker,
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority,
	router *rtredis.Router,
) {
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})
}

func withAssistantAccessMiddleware(
	handler http.Handler,
	accessVerifier *rtauth.Verifier,
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority,
) http.Handler {
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		AccountSecurityAuthority: accountSecurityAuthority,
	})(handler)
}
