package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"

	"gopkg.in/yaml.v3"
)

type platformService struct {
	repoRoot              string
	store                 controlplane.StateStore
	configLayer           *configapp.Facade
	configLayers          http.Handler
	releaseManifestDigest string
	health                func(context.Context) error
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
	ctx := context.Background()
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
		health:                postgresPool.Ping,
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
			append(
				operationsecurity.ForDomain("ops"),
				generatedcontrolplane.PlatformOperationSecurityDescriptors...,
			),
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

	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			OperatorOIDCVerifier: operatorOIDCVerifier,
		})(corsHandler),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("platform-ops-service listening on %s", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("platform-ops-service: %v", err)
	}
}

func (s *platformService) handleListServiceCatalog(w http.ResponseWriter, r *http.Request) {
	topology, err := s.readEnvironmentTopology()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	type catalogEntry struct {
		planes         map[string]struct{}
		deploymentRefs map[string]struct{}
	}
	byWorkload := map[string]*catalogEntry{}
	for _, environment := range topology.Environments {
		for _, workload := range environment.Workloads {
			entry := byWorkload[workload.ID]
			if entry == nil {
				entry = &catalogEntry{planes: map[string]struct{}{}, deploymentRefs: map[string]struct{}{}}
				byWorkload[workload.ID] = entry
			}
			entry.planes[workload.Plane] = struct{}{}
			entry.deploymentRefs[workload.DeploymentRef] = struct{}{}
		}
	}
	out := make([]map[string]any, 0, len(byWorkload))
	for workloadID, entry := range byWorkload {
		planes := sortedSet(entry.planes)
		deploymentRefs := sortedSet(entry.deploymentRefs)
		out = append(out, map[string]any{
			"id":      workloadID,
			"service": workloadID,
			"plane":   strings.Join(planes, " / "),
			"owner":   "environment-topology",
			"health":  "neutral",
			"summary": strings.Join(deploymentRefs, " · "),
		})
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i]["service"].(string) < out[j]["service"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

func (s *platformService) handleListPlaneBindings(w http.ResponseWriter, r *http.Request) {
	topology, err := s.readEnvironmentTopology()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0)
	for env, environment := range topology.Environments {
		for _, workload := range environment.Workloads {
			items = append(items, map[string]any{
				"id":            env + ":" + workload.ID,
				"env":           env,
				"workload":      workload.ID,
				"plane":         workload.Plane,
				"deploymentRef": workload.DeploymentRef,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleListEnvironmentTopologies(w http.ResponseWriter, r *http.Request) {
	topology, err := s.readEnvironmentTopology()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0)
	for env, environment := range topology.Environments {
		for _, workload := range environment.Workloads {
			items = append(items, map[string]any{
				"id":            env + ":" + workload.ID,
				"env":           env,
				"workload":      workload.ID,
				"plane":         workload.Plane,
				"deploymentRef": workload.DeploymentRef,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) appendAudit(objectType, objectID, action string, before, after map[string]any, r *http.Request) error {
	return s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     action,
		ObjectType:  objectType,
		ObjectID:    objectID,
		Action:      action,
		DangerLevel: "high",
		Actor:       actorFromRequest(r),
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		Before:      before,
		After:       after,
	})
}

func (s *platformService) handleProjectionSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := s.buildProjectionSummary()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (s *platformService) readYAMLInto(path string, target any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(data, target)
}

type environmentTopology struct {
	Environments map[string]environmentTopologyEnvironment
	Targets      map[string]environmentTopologyTarget
}

type environmentTopologyEnvironment struct {
	Workloads []environmentTopologyWorkload
}

type environmentTopologyWorkload struct {
	ID            string
	Plane         string
	DeploymentRef string
}

type environmentTopologyTarget struct {
	Environment string `yaml:"env"`
}

func (s *platformService) readEnvironmentTopology() (environmentTopology, error) {
	topology := environmentTopology{
		Environments: make(map[string]environmentTopologyEnvironment, 4),
		Targets:      make(map[string]environmentTopologyTarget),
	}
	servicesRoot := filepath.Join(s.repoRoot, "quwoquan_service", "services")
	services, err := os.ReadDir(servicesRoot)
	if err != nil {
		return topology, err
	}
	externalRoot := filepath.Join(s.repoRoot, "quwoquan_ops", "external")
	externals, err := os.ReadDir(externalRoot)
	if err != nil {
		return topology, err
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		entry := environmentTopologyEnvironment{}
		for _, service := range services {
			if !service.IsDir() {
				continue
			}
			deployDir := filepath.Join(servicesRoot, service.Name(), "environments", environment, "deploy")
			if _, statErr := os.Stat(filepath.Join(deployDir, "kustomization.yaml")); statErr != nil {
				continue
			}
			entry.Workloads = append(entry.Workloads, environmentTopologyWorkload{
				ID:            service.Name(),
				Plane:         workloadPlane(service.Name()),
				DeploymentRef: repositoryRelativePath(s.repoRoot, deployDir),
			})
		}
		for _, external := range externals {
			if !external.IsDir() {
				continue
			}
			deployDir := filepath.Join(externalRoot, external.Name(), "environments", environment)
			if _, statErr := os.Stat(filepath.Join(deployDir, "kustomization.yaml")); statErr != nil {
				continue
			}
			entry.Workloads = append(entry.Workloads, environmentTopologyWorkload{
				ID:            external.Name(),
				Plane:         workloadPlane(external.Name()),
				DeploymentRef: repositoryRelativePath(s.repoRoot, deployDir),
			})
		}
		platformDeployDir := filepath.Join(s.repoRoot, "quwoquan_ops", "platform", "deploy", "base")
		if _, statErr := os.Stat(filepath.Join(platformDeployDir, "kustomization.yaml")); statErr == nil {
			entry.Workloads = append(entry.Workloads, environmentTopologyWorkload{
				ID:            "platform-ops-service",
				Plane:         "service",
				DeploymentRef: repositoryRelativePath(s.repoRoot, platformDeployDir),
			})
		}
		sort.Slice(entry.Workloads, func(i, j int) bool {
			return entry.Workloads[i].ID < entry.Workloads[j].ID
		})
		topology.Environments[environment] = entry

		var runtime struct {
			Targets map[string]environmentTopologyTarget `yaml:"targets"`
		}
		if err := s.readYAMLInto(
			filepath.Join(s.repoRoot, "quwoquan_ops", "environments", environment, "runtime.yaml"),
			&runtime,
		); err != nil {
			return topology, err
		}
		for targetID, target := range runtime.Targets {
			topology.Targets[targetID] = target
		}
	}
	return topology, nil
}

func workloadPlane(workloadID string) string {
	if workloadID == "realtime-gateway" {
		return "edge"
	}
	if workloadID == "rtc-service" || workloadID == "coturn" || workloadID == "livekit" {
		return "media"
	}
	return "service"
}

func repositoryRelativePath(repositoryRoot, target string) string {
	relativePath, err := filepath.Rel(repositoryRoot, target)
	if err != nil {
		return filepath.ToSlash(target)
	}
	return filepath.ToSlash(relativePath)
}

func sortedSet(values map[string]struct{}) []string {
	out := make([]string, 0, len(values))
	for value := range values {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
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
	writeRuntimeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
}

func writeRuntimeError(
	w http.ResponseWriter,
	r *http.Request,
	status int,
	userMessage string,
	debugMessage string,
) {
	reason := "internal_error"
	kind := rterr.KindSystem
	if status == http.StatusBadRequest || status == http.StatusMethodNotAllowed || status == http.StatusNotFound {
		reason = "invalid_argument"
		kind = rterr.KindUser
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleOps, kind, reason),
			userMessage,
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
