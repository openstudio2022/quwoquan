package main

import (
	"log"
	"net/http"
	"strconv"

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
	feedConfig feedRuntimeConfig,
	healthChecker *rthealth.Checker,
	accessTokenConfig rtauth.TokenConfig,
	accountSecurityAuthority rtauth.AccountSecurityAuthority,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *http.Server {
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

	contentDescriptors := operationsecurity.ForDomain("content")
	feedAdmissionPolicy := contentFeedAdmissionPolicy(
		contentDescriptors,
		feedConfig,
	)
	sensitiveOperationGuard := httpadapter.RequireSensitiveOperationPrincipal(handler)
	admissionGuard := rtgov.OperationAdmissionMiddleware(
		[]rtgov.OperationAdmissionPolicy{feedAdmissionPolicy},
		writeContentFeedAdmissionRejection,
	)(sensitiveOperationGuard)
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
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
	}
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

func writeContentFeedAdmissionRejection(
	w http.ResponseWriter,
	r *http.Request,
	reason rtgov.OperationAdmissionRejection,
) {
	const retryAfterSeconds = 1
	w.Header().Set("Retry-After", strconv.Itoa(retryAfterSeconds))
	rterr.WriteHTTPError(
		w,
		contentgenerated.AppErrorFromFeedCapacityUnavailable(
			"content feed owner concurrency exhausted: "+string(reason),
		).WithRecoveryDirective("retry", "snackbar", retryAfterSeconds),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
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
