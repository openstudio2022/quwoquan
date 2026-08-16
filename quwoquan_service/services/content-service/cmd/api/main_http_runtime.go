package bootstrap

import (
	"fmt"
	"net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
)

// buildContentHTTPServer 装配内容服务的认证、操作授权、观测、跨域与限流中间件。
// 业务 handler 的对象绑定仍由 main 负责，这里只收口传输层组合。
func buildContentHTTPServer(
	addr string,
	instanceID string,
	handler http.Handler,
	internalGraphQLHandler http.Handler,
	publicWebHandler http.Handler,
	feedConfig feedRuntimeConfig,
	healthChecker *rthealth.Checker,
	accessTokenConfig rtauth.TokenConfig,
	accountSecurityAuthority rtauth.AccountSecurityAuthority,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) (*http.Server, error) {
	if internalGraphQLHandler == nil {
		return nil, fmt.Errorf("content-service internal GraphQL handler is not configured")
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("access token verifier invalid: %w", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, fmt.Errorf("device ticket config invalid: %w", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return nil, fmt.Errorf("device ticket verifier invalid: %w", err)
	}

	contentDescriptors := operationsecurity.ForDomain("content")
	feedAdmissionPolicy := contentFeedAdmissionPolicy(
		contentDescriptors,
		feedConfig,
	)
	sensitiveOperationGuard := httpadapter.RequireSensitiveOperationPrincipal(handler)
	admissionGuard := rtgov.OperationAdmissionMiddleware(
		[]rtgov.OperationAdmissionPolicy{feedAdmissionPolicy},
		httpadapter.WriteFeedAdmissionRejection,
	)(sensitiveOperationGuard)
	generatedOperationGuard := rtauth.EnforceRuntimeOperationContract(
		contentDescriptors,
	)(admissionGuard)

	outerMux := http.NewServeMux()
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	// Liveness is intentionally process-only: a stale worker/dependency must
	// remove this instance from traffic through readiness without triggering a
	// restart storm that abandons FFmpeg work during a transient outage.
	outerMux.HandleFunc("/livez", contentLivenessHandler)
	outerMux.HandleFunc("/startupz", healthChecker.Handler())
	// Owner-internal persisted GraphQL is deliberately outside the generated
	// public REST operation router. It still traverses the credential verifier,
	// and its handler requires the exact api-edge service subject, scope,
	// persisted hash and ContractGraph digest before touching the read port.
	outerMux.Handle("POST /internal/graphql", internalGraphQLHandler)
	// 公开 SEO HTML 读面（public-content-web-entry 第一段）：匿名可读、
	// 只输出公开已发布对象；未配置 CONTENT_PUBLIC_WEB_ORIGIN 时不挂载。
	if publicWebHandler != nil {
		outerMux.Handle("/public-web/", publicWebHandler)
	}
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

	timeouts := rtauth.ContractHTTPServerTimeouts(contentDescriptors)
	return &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}, nil
}

func contentFeedAdmissionPolicy(
	descriptors []rtauth.OperationSecurityDescriptor,
	feedConfig feedRuntimeConfig,
) rtgov.OperationAdmissionPolicy {
	operationID := ""
	for _, descriptor := range descriptors {
		if descriptor.Method != contentgenerated.RouteGetFeedMethod ||
			descriptor.PathTemplate != contentgenerated.RouteGetFeedPath {
			continue
		}
		if operationID != "" {
			panic("content feed operation descriptor is not unique")
		}
		operationID = descriptor.CanonicalOperationID
	}
	if operationID == "" {
		panic("content feed operation descriptor is missing")
	}
	return rtgov.OperationAdmissionPolicy{
		CanonicalOperationID: operationID,
		InflightLimiter:      rtgov.NewInflightLimiter(feedConfig.MaxInflight),
	}
}

func contentLivenessHandler(w http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		rterr.WriteHTTPError(
			w,
			rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"仅支持 GET 健康检查",
				"liveness endpoint only accepts GET",
			).WithMetadata("invalid_argument", http.StatusMethodNotAllowed),
			rterr.HTTPWriteOptions{
				RequestID: request.Header.Get("X-Request-Id"),
				TraceID:   request.Header.Get("X-Trace-Id"),
			},
		)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"live"}`))
}
