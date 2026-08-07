// api-edge is the only public business HTTP entry. Caddy terminates TLS and
// overwrites the trusted network attribute; api-edge verifies credentials,
// authorizes the generated ContractGraph operation, consumes shared Redis
// quota, and only then proxies to the owning service.
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"os"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	rtobs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
	admissionapp "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	admissionmetrics "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/observability"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("api-edge: %v", err)
	}
}

func run() error {
	serviceName := envOrDefault("SERVICE_NAME", "api-edge")
	environment := envOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	config, err := loadRuntimeConfig(serviceName, environment, configRoot)
	if err != nil {
		return fmt.Errorf("runtime config invalid: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName,
		environment,
		configRoot,
		strings.TrimSpace(os.Getenv("CONFIG_VERSION")),
		strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	)

	accessConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	deviceConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return fmt.Errorf("device ticket config invalid: %w", err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceConfig)
	if err != nil {
		return fmt.Errorf("device ticket verifier invalid: %w", err)
	}
	operatorVerifier, err := rtauth.NewOIDCVerifierFromEnv("OPS_OIDC")
	if err != nil {
		return fmt.Errorf("operator OIDC verifier invalid: %w", err)
	}
	if environment == "prod" && operatorVerifier == nil {
		return fmt.Errorf("operator OIDC verifier is required in prod")
	}

	authorityTimeout := time.Duration(
		config.UserService.AccountSecurity.TimeoutMS,
	) * time.Millisecond
	authorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return fmt.Errorf("account security authority credentials invalid: %w", err)
	}
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL: config.UserService.AccountSecurity.BaseURL,
			HTTPClient: &http.Client{
				Timeout: authorityTimeout,
			},
			Credentials: authorityCredentials,
			Timeout:     authorityTimeout,
		},
	)
	if err != nil {
		return fmt.Errorf("account security authority invalid: %w", err)
	}

	store, err := redisstore.New(config.redisConfig())
	if err != nil {
		return fmt.Errorf("shared admission store invalid: %w", err)
	}
	defer store.Close()
	admission, err := admissionapp.NewService(
		environment,
		store,
		config.policySet(),
		admissionmetrics.NewMetrics(nil),
	)
	if err != nil {
		return fmt.Errorf("admission service invalid: %w", err)
	}

	descriptors := admissionapp.AllOperationDescriptors()
	ownerRoutes, err := buildOwnerRoutes(config.Upstreams)
	if err != nil {
		return err
	}
	if err := admissionapp.ValidateDescriptorOwners(descriptors); err != nil {
		return err
	}
	ownerProxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes:               ownerRoutes,
		TrustedNetworkHeader: config.Edge.TrustedNetworkHeader,
		ContractGraphSHA256:  operationsecurity.ContractGraphSHA256,
	})
	if err != nil {
		return fmt.Errorf("owner proxy invalid: %w", err)
	}

	businessHandler := httpadapter.AdmissionMiddleware(
		admission,
		httpadapter.SubjectResolver{TrustedNetworkHeader: config.Edge.TrustedNetworkHeader},
	)(ownerProxy)
	businessHandler = rtauth.RequireGeneratedOperationAuthorization(descriptors)(businessHandler)
	businessHandler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		DeviceTicketVerifier:     deviceVerifier,
		OperatorOIDCVerifier:     operatorVerifier,
		AccountSecurityAuthority: authority,
	})(businessHandler)
	businessHandler = httpadapter.PreserveCredentialTransport(businessHandler)

	root := http.NewServeMux()
	root.HandleFunc("GET /healthz", writeHealthy)
	readiness := rthealth.NewChecker()
	readiness.Register("admission_redis", admission.Ready)
	readiness.Register("account_security_authority", authority.CheckAccountSecurityAuthority)
	root.HandleFunc("GET /readyz", func(response http.ResponseWriter, request *http.Request) {
		if result := readiness.Check(request.Context()); result.Status != "ok" {
			writeUnavailable(response)
			return
		}
		writeJSONStatus(response, http.StatusOK, "ready")
	})
	root.Handle("GET /metrics", rtmetrics.Handler())
	// WebSocket identity is derived only by consuming realtime-gateway's
	// one-time ticket. It still traverses api-edge, but remains outside business
	// HTTP operation admission so the edge never invents a second ticket truth.
	realtimeOrigin, _ := parseOrigin(config.Upstreams["realtime"])
	realtimeProxy := httputil.NewSingleHostReverseProxy(realtimeOrigin)
	root.Handle("GET /realtime/ws", stripEdgeOnlyHeader(
		config.Edge.TrustedNetworkHeader,
		realtimeProxy,
	))
	root.Handle("/", businessHandler)

	nodeID := envOrDefault("SERVICE_INSTANCE_ID", hostName())
	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   serviceName,
		SamplingRatio: 0.1,
	})
	defer otelShutdown()
	runtimeLogExporter, err := rtobs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return fmt.Errorf("runtime log exporter invalid: %w", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := rtobs.NewRuntimeLogExportWriter(
		os.Stdout,
		512,
		runtimeLogExporter.Export,
	)
	errorLogWriter := rtobs.NewRuntimeLogExportWriter(
		os.Stderr,
		512,
		runtimeLogExporter.Export,
	)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := rtobs.NewIOAccessLogger(standardLogWriter)
	filter := rtobs.NewKVMetadataFilter(nil)
	processLogger, err := rtobs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		rtobs.TraceLogLevelInfo,
		filter,
	)
	if err != nil {
		return fmt.Errorf("process logger invalid: %w", err)
	}
	exceptionLogger, err := rtobs.NewExceptionLogger(standardLogWriter, errorLogWriter, filter)
	if err != nil {
		return fmt.Errorf("exception logger invalid: %w", err)
	}
	observed := rthttp.NewHTTPServerMiddleware(
		root,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           serviceName,
			Origin:            "cloud",
			Direction:         "inbound",
			SourceID:          "api-edge.http",
			Src:               "gateway",
			ServiceName:       serviceName,
			ServiceInstanceID: nodeID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	// The edge fronts every domain, so its transport ceiling is the widest
	// declared operation budget: a hand-written value here would silently cut
	// the longest streaming operation short.
	timeouts := rtauth.ContractHTTPServerTimeouts(descriptors)
	server := &http.Server{
		Addr:              config.Service.HTTP.Addr,
		Handler:           observed,
		BaseContext:       func(net.Listener) context.Context { return context.Background() },
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	log.Printf("api-edge listening on %s contractGraph=%s", server.Addr, operationsecurity.ContractGraphSHA256)
	return rthttp.ListenAndServeGraceful(server, 15*time.Second)
}

func buildOwnerRoutes(upstreams map[string]string) ([]httpadapter.OwnerRoute, error) {
	bindings := admissionapp.OperationOwnerBindings()
	routes := make([]httpadapter.OwnerRoute, 0, len(bindings))
	for _, binding := range bindings {
		origin, err := parseOrigin(upstreams[binding.UpstreamName])
		if err != nil {
			return nil, fmt.Errorf(
				"owner upstream %s: %w",
				binding.UpstreamName,
				err,
			)
		}
		routes = append(routes, httpadapter.OwnerRoute{
			OperationPrefix: binding.OperationPrefix,
			Upstream:        origin,
		})
	}
	return routes, nil
}

func stripEdgeOnlyHeader(header string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		request.Header.Del(strings.TrimSpace(header))
		next.ServeHTTP(response, request)
	})
}

func writeHealthy(response http.ResponseWriter, _ *http.Request) {
	writeJSONStatus(response, http.StatusOK, "ok")
}

func writeUnavailable(response http.ResponseWriter) {
	writeJSONStatus(response, http.StatusServiceUnavailable, "unavailable")
}

func writeJSONStatus(response http.ResponseWriter, status int, value string) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_, _ = response.Write([]byte(`{"status":"` + value + `"}`))
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func hostName() string {
	value, err := os.Hostname()
	if err != nil || strings.TrimSpace(value) == "" {
		return "api-edge-local"
	}
	return strings.TrimSpace(value)
}
