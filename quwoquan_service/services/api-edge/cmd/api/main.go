// api-edge is the only public business HTTP entry. Caddy terminates TLS and
// overwrites the trusted network attribute; api-edge verifies credentials,
// authorizes the generated ContractGraph operation, consumes shared Redis
// quota, and only then proxies to the owning service.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
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
	admissionredis "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
	rollouthttp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutnetworkcatalog "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/networkcatalog"
	rolloutmetrics "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/observability"
	rolloutredis "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/redisstore"
	graphread "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	ownerquery "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
	registryinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/registry"

	"github.com/prometheus/client_golang/prometheus"
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
	rolloutNetworkResolver, err := rolloutnetworkcatalog.Load(
		config.Rollout.NetworkAttributeCatalog,
		config.Rollout.Policy,
	)
	if err != nil {
		return fmt.Errorf("rollout network attribute catalog invalid: %w", err)
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

	redisClient, err := admissionredis.NewClient(config.redisConfig())
	if err != nil {
		return fmt.Errorf("shared Redis client invalid: %w", err)
	}
	defer redisClient.Close()
	store, err := admissionredis.NewWithClient(redisClient)
	if err != nil {
		return fmt.Errorf("shared admission store invalid: %w", err)
	}
	admission, err := admissionapp.NewService(
		environment,
		store,
		config.policySet(),
		admissionmetrics.NewMetrics(nil),
	)
	if err != nil {
		return fmt.Errorf("admission service invalid: %w", err)
	}
	assignmentStore, err := rolloutredis.New(redisClient)
	if err != nil {
		return fmt.Errorf("rollout assignment store invalid: %w", err)
	}
	allocationKey, err := rolloutapp.AllocationKey(config.Rollout.Enabled, os.LookupEnv)
	if err != nil {
		return fmt.Errorf("rollout allocation key invalid: %w", err)
	}
	rolloutEvaluator, err := rolloutapp.NewEvaluator(
		config.Rollout.Policy,
		allocationKey,
		assignmentStore,
		30*24*time.Hour,
	)
	if err != nil {
		return fmt.Errorf("rollout evaluator invalid: %w", err)
	}
	minimumBuildExemptPaths, err := config.minimumBuildExemptPaths()
	if err != nil {
		return fmt.Errorf("minimum build exemptions invalid: %w", err)
	}
	minimumBuildMiddleware, err := rollouthttp.MinimumBuildMiddleware(
		config.minimumBuildPolicy(),
		minimumBuildExemptPaths,
		newMinimumBuildMetrics(nil),
	)
	if err != nil {
		return fmt.Errorf("minimum build middleware invalid: %w", err)
	}

	descriptors := admissionapp.AllOperationDescriptors()
	ownerRoutes, err := buildOwnerRoutes(config.Upstreams)
	if err != nil {
		return err
	}
	if err := admissionapp.ValidateDescriptorOwners(descriptors); err != nil {
		return err
	}
	var candidateOwnerRoutes []httpadapter.OwnerRoute
	if config.Rollout.Enabled {
		candidateOwnerRoutes, err = buildOwnerRoutes(config.CandidateUpstreams)
		if err != nil {
			return fmt.Errorf("candidate owner routes invalid: %w", err)
		}
	}
	ownerProxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes:               ownerRoutes,
		CandidateRoutes:      candidateOwnerRoutes,
		TrustedNetworkHeader: config.Edge.TrustedNetworkHeader,
		ContractGraphSHA256:  operationsecurity.ContractGraphSHA256,
	})
	if err != nil {
		return fmt.Errorf("owner proxy invalid: %w", err)
	}
	rolloutObserver := rolloutmetrics.NewMetrics(nil)

	// Wrappers are applied inner-to-outer. The effective business sequence is:
	// credential verification -> minimum build -> generated operation
	// authorization -> shared admission -> rollout decision -> owner proxy.
	var businessHandler http.Handler = ownerProxy
	businessHandler = rollouthttp.Middleware(
		rolloutEvaluator,
		rolloutNetworkResolver,
		config.Edge.TrustedNetworkHeader,
		rolloutObserver,
	)(businessHandler)
	businessHandler = httpadapter.AdmissionMiddleware(
		admission,
		httpadapter.SubjectResolver{TrustedNetworkHeader: config.Edge.TrustedNetworkHeader},
	)(businessHandler)
	operationAuthorization, err := rtauth.OperationAuthorizationForRuntime(
		descriptors,
		environment,
		os.LookupEnv,
	)
	if err != nil {
		return fmt.Errorf("operation authorization boundary invalid: %w", err)
	}
	businessHandler = operationAuthorization(businessHandler)
	businessHandler = rollouthttp.MinimumBuildForAuthenticatedClients(
		minimumBuildMiddleware,
		businessHandler,
	)
	credentialMiddleware := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		DeviceTicketVerifier:     deviceVerifier,
		OperatorOIDCVerifier:     operatorVerifier,
		AccountSecurityAuthority: authority,
	})
	businessHandler = credentialMiddleware(businessHandler)
	businessHandler = httpadapter.PreserveCredentialTransport(businessHandler)

	var graphRuntime *graphread.Runtime
	var graphHandler http.Handler
	if config.GraphQLRead.Enabled {
		trustedPublicKeys := map[string]string{}
		if err := json.Unmarshal(
			[]byte(config.GraphQLRead.TrustedPublicKeysJSON),
			&trustedPublicKeys,
		); err != nil {
			return fmt.Errorf("GraphQL trusted public keys invalid: %w", err)
		}
		signatureVerifier, err := registryinfra.NewEd25519SignatureVerifier(
			trustedPublicKeys,
		)
		if err != nil {
			return fmt.Errorf("GraphQL registry signature verifier invalid: %w", err)
		}
		registryLoader, err := registryinfra.NewSignedFileLoader(signatureVerifier)
		if err != nil {
			return fmt.Errorf("GraphQL signed registry loader invalid: %w", err)
		}
		stableContentOrigin, err := parseOrigin(config.Upstreams["content"])
		if err != nil {
			return fmt.Errorf("GraphQL stable content owner origin invalid: %w", err)
		}
		var candidateContentOrigin *url.URL
		if config.Rollout.Enabled {
			candidateContentOrigin, err = parseOrigin(config.CandidateUpstreams["content"])
			if err != nil {
				return fmt.Errorf("GraphQL candidate content owner origin invalid: %w", err)
			}
		}
		stableSearchOrigin, err := parseOrigin(config.Upstreams["search"])
		if err != nil {
			return fmt.Errorf("GraphQL stable search owner origin invalid: %w", err)
		}
		var candidateSearchOrigin *url.URL
		if config.Rollout.Enabled {
			candidateSearchOrigin, err = parseOrigin(config.CandidateUpstreams["search"])
			if err != nil {
				return fmt.Errorf("GraphQL candidate search owner origin invalid: %w", err)
			}
		}
		contentOwnerCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			accessConfig,
			serviceName,
			[]string{ownerquery.ContentPostOwnerReadScope()},
		)
		if err != nil {
			return fmt.Errorf("GraphQL content owner credentials invalid: %w", err)
		}
		contentOwnerExecutor, err := ownerquery.NewContentPostQueryExecutor(
			stableContentOrigin,
			candidateContentOrigin,
			&http.Client{
				Timeout: time.Duration(config.GraphQLRead.OwnerTimeoutMS) * time.Millisecond,
			},
			operationsecurity.ContractGraphSHA256,
			contentOwnerCredentials,
		)
		if err != nil {
			return fmt.Errorf("GraphQL content owner executor invalid: %w", err)
		}
		searchOwnerCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			accessConfig,
			serviceName,
			[]string{ownerquery.SearchOwnerReadScope()},
		)
		if err != nil {
			return fmt.Errorf("GraphQL search owner credentials invalid: %w", err)
		}
		searchOwnerAccountCredentials, err := rtauth.NewHS256ServiceAccountAuthorizationProvider(
			accessConfig,
			serviceName,
			[]string{ownerquery.SearchOwnerReadScope()},
		)
		if err != nil {
			return fmt.Errorf("GraphQL search owner account credentials invalid: %w", err)
		}
		searchOwnerExecutor, err := ownerquery.NewSearchPageQueryExecutor(
			stableSearchOrigin,
			candidateSearchOrigin,
			&http.Client{
				Timeout: time.Duration(config.GraphQLRead.OwnerTimeoutMS) * time.Millisecond,
			},
			operationsecurity.ContractGraphSHA256,
			searchOwnerCredentials,
			searchOwnerAccountCredentials,
		)
		if err != nil {
			return fmt.Errorf("GraphQL search owner executor invalid: %w", err)
		}
		ownerExecutor, err := ownerquery.NewQueryExecutorRouter(
			contentOwnerExecutor,
			searchOwnerExecutor,
		)
		if err != nil {
			return fmt.Errorf("GraphQL owner executor router invalid: %w", err)
		}
		graphRuntime, err = graphread.NewRuntime(context.Background(), graphread.Options{
			Environment:     environment,
			Config:          config.GraphQLRead,
			RegistryLoader:  registryLoader,
			OwnerExecutor:   ownerExecutor,
			Admission:       admission,
			Rollout:         rolloutEvaluator,
			RolloutObserver: rolloutObserver,
		})
		if err != nil {
			return fmt.Errorf("GraphQL read runtime invalid: %w", err)
		}
		graphHandler = graphread.RequestMetadataMiddleware(
			config.Edge.TrustedNetworkHeader,
			rolloutNetworkResolver,
			graphRuntime.Handler(),
		)
		graphHandler = rollouthttp.MinimumBuildForAuthenticatedClients(
			minimumBuildMiddleware,
			graphHandler,
		)
		graphHandler = credentialMiddleware(graphHandler)
	}

	root := http.NewServeMux()
	root.HandleFunc("GET /healthz", writeHealthy)
	readiness := rthealth.NewChecker()
	readiness.Register("admission_redis", admission.Ready)
	readiness.Register("rollout_assignment_redis", rolloutEvaluator.Ready)
	readiness.Register("account_security_authority", authority.CheckAccountSecurityAuthority)
	if graphRuntime != nil {
		readiness.Register("graphql_signed_registry", graphRuntime.Ready)
	}
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
	if graphHandler != nil {
		root.Handle("/graphql", graphHandler)
	}
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

type minimumBuildMetrics struct {
	decisions *prometheus.CounterVec
}

func newMinimumBuildMetrics(registerer prometheus.Registerer) *minimumBuildMetrics {
	if registerer == nil {
		registerer = prometheus.DefaultRegisterer
	}
	metrics := &minimumBuildMetrics{
		decisions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "api_edge_minimum_build_decisions_total",
				Help: "Minimum supported client build decisions at API Edge.",
			},
			[]string{"platform", "app_build", "mode", "reason", "would_block"},
		),
	}
	registerer.MustRegister(metrics.decisions)
	return metrics
}

func (metrics *minimumBuildMetrics) ObserveMinimumBuild(
	platform, build, mode, reason string,
	wouldBlock bool,
) {
	if metrics == nil {
		return
	}
	metrics.decisions.WithLabelValues(
		rolloutapp.NormalizeMetricValue(platform, "unknown"),
		rolloutapp.NormalizeBuildMetricValue(build),
		rolloutapp.NormalizeMetricValue(mode, "unknown"),
		rolloutapp.NormalizeMetricValue(reason, "unknown"),
		strconv.FormatBool(wouldBlock),
	).Inc()
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
