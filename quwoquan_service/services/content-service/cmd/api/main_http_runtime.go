package main

import (
	"log"
	"net/http"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	httpadapter "quwoquan_service/services/content-service/internal/adapters/http"
)

// buildContentHTTPServer 装配内容服务的认证、操作授权、观测、跨域与限流中间件。
// 业务 handler 的对象绑定仍由 main 负责，这里只收口传输层组合。
func buildContentHTTPServer(
	addr string,
	instanceID string,
	handler http.Handler,
	healthChecker *rthealth.Checker,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *http.Server {
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("device ticket verifier invalid: %v", err)
	}

	sensitiveOperationGuard := httpadapter.RequireSensitiveOperationPrincipal(handler)
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(sensitiveOperationGuard)

	outerMux := http.NewServeMux()
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.HandleFunc("/livez", healthChecker.Handler())
	outerMux.HandleFunc("/startupz", healthChecker.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	observedHandler := rthttp.NewHTTPServerMiddleware(
		outerMux,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "content-service",
			ServiceName:       "content-service",
			ServiceInstanceID: instanceID,
			Origin:            "service.http",
			Direction:         robs.DirectionInbound,
			SourceID:          "content-service",
			Src:               "content-service",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)

	return &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceTicketVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}
