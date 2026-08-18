package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	configreporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	configreportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	configreportmessaging "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/messaging"
	configreportpersistence "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	configrepository "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/infrastructure/repository"
	generatedcontrolplane "quwoquan_service/generated/control_plane"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/runtime/artifactidentity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
)

type platformService struct {
	repoRoot              string
	store                 controlplane.StateStore
	configLayer           *configapp.Facade
	configLayers          http.Handler
	configTopology        http.Handler
	configInstanceReports http.Handler
	configInstanceRuntime http.Handler
	releaseManifestDigest string
	health                func(context.Context) error
}

func composeConfigSnapshotTopologyHandler(service *platformService) (http.Handler, error) {
	if service == nil {
		return nil, errors.New("config snapshot topology composition requires service")
	}
	source, err := configrepository.NewTopologySource(
		service.repoRoot,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
	)
	if err != nil {
		return nil, err
	}
	facade, err := configapp.NewTopologyFacade(source)
	if err != nil {
		return nil, err
	}
	return confighttp.NewTopologyHandler(facade)
}

func composeConfigInstanceRuntimeHandler(
	service *platformService,
) (http.Handler, error) {
	if service == nil || service.store == nil {
		return nil, errors.New("config instance runtime composition requires state store")
	}
	topologySource, err := configrepository.NewTopologySource(
		service.repoRoot,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
	)
	if err != nil {
		return nil, err
	}
	topologyReader := configreportapp.RuntimeTopologyReaderFunc(func(
		ctx context.Context,
	) (configreportapp.RuntimeTopology, error) {
		current, err := topologySource.ReadRuntimeTopology(ctx)
		if err != nil {
			return configreportapp.RuntimeTopology{}, err
		}
		result := configreportapp.RuntimeTopology{
			Environments: make(map[string]configreportapp.RuntimeTopologyEnvironment, len(current.Environments)),
			Targets:      make(map[string]configreportapp.RuntimeTopologyTarget, len(current.Targets)),
		}
		for environment, value := range current.Environments {
			workloads := make([]configreportapp.RuntimeTopologyWorkload, 0, len(value.Workloads))
			for _, workload := range value.Workloads {
				workloads = append(workloads, configreportapp.RuntimeTopologyWorkload{
					ID: workload.ID, Plane: workload.Plane, DeploymentRef: workload.DeploymentRef,
				})
			}
			result.Environments[environment] = configreportapp.RuntimeTopologyEnvironment{Workloads: workloads}
		}
		for targetID, value := range current.Targets {
			result.Targets[targetID] = configreportapp.RuntimeTopologyTarget{Environment: value.Environment}
		}
		return result, nil
	})
	facade, err := configreportapp.NewRuntimeFacade(
		service.store,
		topologyReader,
		service.releaseManifestDigest,
		nil,
	)
	if err != nil {
		return nil, err
	}
	return configreporthttp.NewRuntimeHandler(facade)
}

func composeConfigInstanceReportHandler(
	service *platformService,
) (http.Handler, error) {
	if service == nil || service.store == nil || service.configLayer == nil {
		return nil, errors.New("config instance report composition requires store and ConfigSnapshot")
	}
	atomicStore, ok := service.store.(controlplane.AtomicMutationStore)
	if !ok {
		return nil, errors.New("config instance report composition requires atomic mutation store")
	}
	stateStore, err := configreportpersistence.NewStateStore(service.store, atomicStore)
	if err != nil {
		return nil, err
	}
	desiredHash := configreportapp.DesiredHashReaderFunc(func(
		ctx context.Context,
		environment string,
		serviceName string,
	) (string, error) {
		resolved, err := service.configLayer.Resolve(ctx, controlplane.ConfigResolutionScope{
			Environment: environment,
			Service:     serviceName,
		})
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(resolved.DesiredHash), nil
	})
	return configreporthttp.NewHandler(
		configreportapp.NewCommandFacade(stateStore, desiredHash, nil),
		configreportapp.NewQueryFacade(stateStore),
		service.releaseManifestDigest,
	)
}

func platformOperatorOIDCRequired(appEnv string) bool {
	switch strings.ToLower(strings.TrimSpace(appEnv)) {
	case "alpha", "beta", "gamma":
		return false
	default:
		return true
	}
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("platform-ops-service artifact identity invalid: %v", err)
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "platform-ops-service", SamplingRatio: 0.1})
	defer otelShutdown()

	serviceName, appEnv, configRoot, configVersion, imageVersion := resolvePlatformRuntimeIdentity()
	cfg, err := loadPlatformRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("platform-ops-service config load failed: %v", err)
	}
	applyPlatformEnvOverrides(&cfg)
	if err := validatePlatformRuntimeConfig(cfg); err != nil {
		log.Fatalf("platform-ops-service required runtime config invalid: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("platform-ops-service access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("platform-ops-service access token verifier invalid: %v", err)
	}
	operatorOIDCVerifier, err := rtauth.NewOIDCVerifierFromEnv("OPS_OIDC")
	if err != nil {
		log.Fatalf("platform-ops-service operator OIDC verifier invalid: %v", err)
	}
	if operatorOIDCVerifier == nil && platformOperatorOIDCRequired(appEnv) {
		log.Fatal("platform-ops-service operator OIDC issuer/audience/JWKS configuration is required")
	}
	addr := strings.TrimSpace(os.Getenv("PLATFORM_OPS_SERVICE_ADDR"))
	if addr == "" {
		addr = strings.TrimSpace(cfg.Service.HTTP.Addr)
	}
	if addr == "" {
		addr = ":18087"
	}
	repoRoot := resolveRepoRoot()
	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	postgresConfig, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("platform-ops-service postgres config invalid: %v", err)
	}
	postgresConfig.MaxConns = 20
	postgresConfig.MinConns = 2
	postgresConfig.HealthCheckPeriod = 30 * time.Second
	postgresPool, err := pgxpool.NewWithConfig(ctx, postgresConfig)
	if err != nil {
		log.Fatalf("platform-ops-service postgres connect failed: %v", err)
	}
	defer postgresPool.Close()
	if err := postgresPool.Ping(ctx); err != nil {
		log.Fatalf("platform-ops-service postgres unavailable: %v", err)
	}
	store, err := controlplanepersistence.NewPostgresStore(postgresPool, "platform-ops")
	if err != nil {
		log.Fatalf("platform-ops-service control plane store invalid: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		log.Fatalf("platform-ops-service control plane schema initialization failed: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone",
				Addr: strings.TrimSpace(cfg.Redis.General.Addr),
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		log.Fatalf("platform-ops-service Redis router invalid: %v", err)
	}
	defer redisRouter.Close()
	generalRedis := redisRouter.Scene("general")
	if err := generalRedis.Ping(ctx); err != nil {
		log.Fatalf("platform-ops-service Redis unavailable: %v", err)
	}
	messageTransport, err := runtimemessaging.NewRedisMessageTransport(
		generalRedis,
		generalRedis,
	)
	if err != nil {
		log.Fatalf("platform-ops-service message transport invalid: %v", err)
	}
	configReportPublisher, err := configreportmessaging.NewPublisher(messageTransport)
	if err != nil {
		log.Fatalf("platform-ops-service ConfigInstanceReport publisher invalid: %v", err)
	}
	configReportDispatcher, err := pgoutbox.NewDispatcher(
		postgresPool,
		configReportPublisher,
		"platform_control_plane_outbox",
	)
	if err != nil {
		log.Fatalf("platform-ops-service ConfigInstanceReport outbox invalid: %v", err)
	}
	go configReportDispatcher.Run(ctx)
	configKeyCatalog, err := configapp.NewConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfig(),
	)
	if err != nil {
		log.Fatalf("platform-ops-service generated config key catalog invalid: %v", err)
	}
	// IaC 收口：配置唯一真相源是版本化发布包（config-root 树或仓库配置树），
	// 平台只提供只读快照与漂移核对，不存在任何在线写路径。
	configSnapshotSource, err := configapp.NewSnapshotSource(configRoot, repoRoot)
	if err != nil {
		log.Fatalf("platform-ops-service config snapshot source invalid: %v", err)
	}
	configLayerFacade, err := configapp.NewFacade(configSnapshotSource, configKeyCatalog)
	if err != nil {
		log.Fatalf("platform-ops-service config snapshot facade invalid: %v", err)
	}
	configLayerHandler, err := confighttp.NewHandler(configLayerFacade)
	if err != nil {
		log.Fatalf("platform-ops-service config snapshot HTTP adapter invalid: %v", err)
	}
	releaseManifestDigest := strings.TrimSpace(os.Getenv("RELEASE_MANIFEST_DIGEST"))
	if appEnv == "prod" && !isCanonicalSHA256(releaseManifestDigest) {
		log.Fatal("platform-ops-service RELEASE_MANIFEST_DIGEST is required in prod")
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	service := &platformService{
		repoRoot: repoRoot, store: store, configLayer: configLayerFacade, configLayers: configLayerHandler,
		releaseManifestDigest: releaseManifestDigest,
		health: func(healthCtx context.Context) error {
			if err := postgresPool.Ping(healthCtx); err != nil {
				return err
			}
			return generalRedis.Ping(healthCtx)
		},
	}
	mux := newServerMux(service)
	outerMux := http.NewServeMux()
	outerMux.Handle("/healthz", mux)
	outerMux.Handle("/metrics", mux)
	outerMux.Handle("/readyz/config-convergence", mux)
	// Alertmanager webhook 使用专用机器 token，并由 handler 前的独立认证边界
	// fail-closed；其余控制面 operation 全部由 metadata codegen 描述符执行
	// OIDC principal + scope 授权，不保留迁移期 fallback。
	outerMux.Handle(
		"/control-plane/platform/alerts/ingest",
		requireControlPlanePrincipal(mux),
	)
	outerMux.Handle(
		"/",
		rtauth.EnforceGeneratedOperationAuthorization(
			generatedcontrolplane.PlatformOperationSecurityDescriptors,
		)(mux),
	)

	instanceID, _ := os.Hostname()
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout（本地/测试），推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("platform-ops-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("platform-ops-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("platform-ops-service exception logger init failed: %v", err)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "platform-ops-service",
		ServiceName:       "platform-ops-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	log.Printf(
		"platform-ops-service runtime identity env=%s config_version=%s image_version=%s config_root=%s",
		appEnv,
		configVersion,
		imageVersion,
		strings.TrimSpace(configRoot),
	)

	timeouts := rtauth.ContractHTTPServerTimeouts(
		generatedcontrolplane.PlatformOperationSecurityDescriptors,
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			OperatorOIDCVerifier: operatorOIDCVerifier,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	log.Printf("platform-ops-service listening on %s", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("platform-ops-service: %v", err)
	}
}

func resolveRepoRoot() string {
	if root := strings.TrimSpace(os.Getenv("REPO_ROOT")); root != "" {
		return root
	}
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	current := wd
	for {
		if _, err := os.Stat(filepath.Join(current, "quwoquan_service", "services")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			return wd
		}
		current = parent
	}
}

func stringify(value any) string {
	text, _ := value.(string)
	return text
}

func stringifyDocumentValue(value any) string {
	return strings.TrimSpace(stringify(value))
}

func actorFromRequest(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if actor := strings.TrimSpace(principal.Actor.AccountID); actor != "" {
			return actor
		}
		if actor := strings.TrimSpace(principal.Actor.DeviceActorID); actor != "" {
			return actor
		}
	}
	return "unverified"
}

func environmentFromRequest(r *http.Request) string {
	_ = r
	if env := strings.TrimSpace(os.Getenv("APP_ENV")); env != "" {
		return env
	}
	return "unknown"
}

func requestIDFromRequest(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return "req-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func traceIDFromRequest(r *http.Request) string {
	if traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id")); traceID != "" {
		return traceID
	}
	return "trace-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func segmentBetween(path, prefix, suffix string) string {
	value := strings.TrimPrefix(path, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.Trim(value, "/")
}

func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func itoa(value int) string {
	return strconv.Itoa(value)
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func cloneMap(in map[string]any) map[string]any {
	if in == nil {
		return nil
	}
	data, _ := json.Marshal(in)
	var out map[string]any
	_ = json.Unmarshal(data, &out)
	return out
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
