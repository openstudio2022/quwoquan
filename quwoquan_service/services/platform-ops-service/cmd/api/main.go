package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	confighttp "quwoquan_service/services/platform-ops-service/internal/adapters/http/config_layer"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
	configmodel "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	configpersistence "quwoquan_service/services/platform-ops-service/internal/infrastructure/platform_ops/config_layer/persistence"

	"gopkg.in/yaml.v3"
)

type platformService struct {
	repoRoot     string
	store        controlplane.StateStore
	configLayer  *configapp.Facade
	configLayers http.Handler
	health       func(context.Context) error
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
	configLayerStore, err := configpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("platform-ops-service config layer store invalid: %v", err)
	}
	if err := configLayerStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("platform-ops-service config layer schema initialization failed: %v", err)
	}
	configKeyCatalog, err := configpersistence.NewGeneratedConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfigSchema(),
	)
	if err != nil {
		log.Fatalf("platform-ops-service generated config key catalog invalid: %v", err)
	}
	configLayerFacade, err := configapp.NewFacade(configLayerStore, configLayerStore, configKeyCatalog)
	if err != nil {
		log.Fatalf("platform-ops-service config layer facade invalid: %v", err)
	}
	configLayerHandler, err := confighttp.NewHandler(configLayerFacade)
	if err != nil {
		log.Fatalf("platform-ops-service config layer HTTP adapter invalid: %v", err)
	}
	service := &platformService{
		repoRoot: repoRoot, store: store, configLayer: configLayerFacade, configLayers: configLayerHandler,
		health: postgresPool.Ping,
	}
	mux := newServerMux(service)
	outerMux := http.NewServeMux()
	outerMux.Handle("/healthz", mux)
	outerMux.Handle("/metrics", mux)
	outerMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("ops"),
		)(mux),
	)

	instanceID, _ := os.Hostname()
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("platform-ops-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
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

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("platform-ops-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("platform-ops-service: %v", err)
	}
}

func (s *platformService) handleListServiceCatalog(w http.ResponseWriter, r *http.Request) {
	items, err := s.readOnboardingDomains()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	out := make([]map[string]any, 0)
	for _, item := range items {
		blockers := asStringSlice(item["blocking_gaps"])
		for _, serviceName := range asStringSlice(item["service_names"]) {
			planes := []string{}
			if controlPlanes, ok := item["control_planes"].(map[string]any); ok {
				if controlPlanes["platform"] != nil {
					planes = append(planes, "platform-control-plane")
				}
				if controlPlanes["product"] != nil {
					planes = append(planes, "product-control-plane")
				}
			}
			out = append(out, map[string]any{
				"id":      serviceName,
				"service": serviceName,
				"plane":   strings.Join(planes, " / "),
				"owner":   item["domain"].(string) + "-team",
				"health":  healthFromBlockers(blockers),
				"summary": "status=" + item["acceptance_status"].(string) + " · blockers=" + strconv.Itoa(len(blockers)),
			})
		}
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i]["service"].(string) < out[j]["service"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

func (s *platformService) handleListOnboardingDomains(w http.ResponseWriter, r *http.Request) {
	items, err := s.readOnboardingDomains()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	sort.Slice(items, func(i, j int) bool {
		return stringify(items[i]["domain"]) < stringify(items[j]["domain"])
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleListPlaneBindings(w http.ResponseWriter, r *http.Request) {
	var doc struct {
		Environments map[string]map[string]struct {
			Bindings []struct {
				Domain string   `yaml:"domain"`
				Planes []string `yaml:"planes"`
			} `yaml:"bindings"`
		} `yaml:"environments"`
	}
	if err := s.readYAMLInto(filepath.Join(s.repoRoot, "quwoquan_ops", "environments", "process_domain_plane_mapping.yaml"), &doc); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0)
	for env, processes := range doc.Environments {
		for process, cfg := range processes {
			for _, binding := range cfg.Bindings {
				items = append(items, map[string]any{
					"id":      env + ":" + process + ":" + binding.Domain,
					"env":     env,
					"process": process,
					"domain":  binding.Domain,
					"planes":  binding.Planes,
				})
			}
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleUpdatePlaneBinding(w http.ResponseWriter, r *http.Request) {
	bindingID := segmentBetween(r.URL.Path, "/control-plane/platform/topology/planes/", ":update")
	var body map[string]any
	_ = json.NewDecoder(r.Body).Decode(&body)
	body["id"] = bindingID
	body["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("plane_binding_overrides", bindingID, body); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "plane_binding",
		ObjectID:   bindingID,
		Mode:       "dual",
		Actor:      actorFromRequest(r),
		Decision:   "update",
	})
	_ = s.appendAudit("plane_binding", bindingID, "plane_binding_updated", body, nil, r)
	writeJSON(w, http.StatusOK, body)
}

func (s *platformService) handleListEnvironmentTopologies(w http.ResponseWriter, r *http.Request) {
	var doc struct {
		Environments map[string]map[string]struct {
			Domains []string `yaml:"domains"`
		} `yaml:"environments"`
	}
	if err := s.readYAMLInto(filepath.Join(s.repoRoot, "deploy", "shared", "process_domain_mapping.yaml"), &doc); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0)
	for env, processes := range doc.Environments {
		for process, cfg := range processes {
			items = append(items, map[string]any{
				"id":      env + ":" + process,
				"env":     env,
				"process": process,
				"domains": cfg.Domains,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleListNamespace(w http.ResponseWriter, r *http.Request, namespace string) {
	items, err := s.store.ListDocuments(namespace)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleUpdateNamespaceDocument(w http.ResponseWriter, r *http.Request, namespace, auditAction string) {
	id := pathActionID(r.URL.Path)
	current, _, _ := s.store.GetDocument(namespace, id)
	before := cloneMap(current)
	var body map[string]any
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body == nil {
		body = map[string]any{}
	}
	body["id"] = id
	body["updatedAt"] = nowRFC3339()
	if current != nil {
		for key, value := range current {
			if _, ok := body[key]; !ok {
				body[key] = value
			}
		}
	}
	if err := s.store.PutDocument(namespace, id, body); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	mode := "single"
	if namespace == "gate_rules" {
		mode = "dual"
	}
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: namespace,
		ObjectID:   id,
		Mode:       mode,
		Actor:      actorFromRequest(r),
		Decision:   "update",
	})
	_ = s.appendAudit(namespace, id, auditAction, before, body, r)
	writeJSON(w, http.StatusOK, body)
}

func (s *platformService) syncConfigPackageDesiredHashes(ctx context.Context) error {
	if s.configLayer == nil {
		return fmt.Errorf("config layer facade is required")
	}
	configPackages, err := s.store.ListDocuments("config_packages")
	if err != nil {
		return err
	}
	packageDesiredHashes := map[string]string{}
	for _, pkg := range configPackages {
		pkgID := stringifyDocumentValue(pkg["id"])
		if pkgID == "" {
			continue
		}
		scope := controlplane.ConfigResolutionScope{
			Environment: stringifyDocumentValue(pkg["environment"]),
			Cluster:     stringifyDocumentValue(pkg["cluster"]),
			Service:     stringifyDocumentValue(pkg["service"]),
		}
		resolved, err := s.configLayer.Resolve(ctx, configmodel.Scope{
			Environment: scope.Environment,
			Cluster:     scope.Cluster,
			Service:     scope.Service,
		})
		if err != nil {
			return err
		}
		desiredHash := resolved.EffectiveHash
		pkg["desiredHash"] = desiredHash
		if err := s.store.PutDocument("config_packages", pkgID, pkg); err != nil {
			return err
		}
		packageDesiredHashes[configPackageScopeKey(scope)] = desiredHash
	}
	configInstanceReports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		return err
	}
	for _, report := range configInstanceReports {
		reportID := stringifyDocumentValue(report["id"])
		if reportID == "" {
			continue
		}
		scope := controlplane.ConfigResolutionScope{
			Environment: stringifyDocumentValue(report["environment"]),
			Cluster:     stringifyDocumentValue(report["cluster"]),
			Service:     stringifyDocumentValue(report["service"]),
		}
		if desiredHash := packageDesiredHashes[configPackageScopeKey(scope)]; desiredHash != "" {
			report["desiredHash"] = desiredHash
			if stringifyDocumentValue(report["effectiveHash"]) == "" {
				report["effectiveHash"] = desiredHash
			}
			report["inSync"] = stringifyDocumentValue(report["desiredHash"]) == stringifyDocumentValue(report["effectiveHash"])
			if err := s.store.PutDocument("config_instance_reports", reportID, report); err != nil {
				return err
			}
		}
	}
	return nil
}

func (s *platformService) lookupConfigPackageDesiredHash(scope controlplane.ConfigResolutionScope, fallback string) (string, error) {
	configPackages, err := s.store.ListDocuments("config_packages")
	if err != nil {
		return "", err
	}
	for _, pkg := range configPackages {
		if configPackageMatchesScope(pkg, scope) {
			if desiredHash := stringifyDocumentValue(pkg["desiredHash"]); desiredHash != "" {
				return desiredHash, nil
			}
			break
		}
	}
	return fallback, nil
}

func configPackageMatchesScope(pkg controlplane.Document, scope controlplane.ConfigResolutionScope) bool {
	return stringifyDocumentValue(pkg["environment"]) == scope.Environment &&
		stringifyDocumentValue(pkg["cluster"]) == scope.Cluster &&
		stringifyDocumentValue(pkg["service"]) == scope.Service
}

func configPackageScopeKey(scope controlplane.ConfigResolutionScope) string {
	return scope.Environment + "|" + scope.Cluster + "|" + scope.Service
}

func (s *platformService) handleRunDrill(w http.ResponseWriter, r *http.Request) {
	runbookID := segmentBetween(r.URL.Path, "/control-plane/platform/runbooks/", ":runDrill")
	current, ok, err := s.store.GetDocument("runbooks", runbookID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "runbook not found")
		return
	}
	before := cloneMap(current)
	current["status"] = "success"
	current["lastRunAt"] = nowRFC3339()
	current["lastActor"] = actorFromRequest(r)
	if err := s.store.PutDocument("runbooks", runbookID, current); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "runbook",
		ObjectID:   runbookID,
		Mode:       "single",
		Actor:      actorFromRequest(r),
		Decision:   "run_drill",
	})
	_ = s.appendAudit("runbook", runbookID, "runbook_drill_executed", before, current, r)
	writeJSON(w, http.StatusOK, current)
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
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	runbooks, err := s.store.ListDocuments("runbooks")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"approvalCount":   len(approvals),
		"auditCount":      len(audits),
		"runbookCount":    len(runbooks),
		"releaseServices": []string{"platform-ops-service", "product-ops-service"},
	})
}

func (s *platformService) readYAMLInto(path string, target any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(data, target)
}

func (s *platformService) readOnboardingDomains() ([]map[string]any, error) {
	domainsDir := filepath.Join(s.repoRoot, "quwoquan_service", "contracts", "metadata", "_control_plane", "domains")
	entries, err := os.ReadDir(domainsDir)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0)
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}
		var item map[string]any
		if err := s.readYAMLInto(filepath.Join(domainsDir, entry.Name()), &item); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, nil
}

func readReleaseState(repoRoot, service string) string {
	stateFile := filepath.Join(repoRoot, ".qwq_output", "env", "repo", "local", "release-state", service+".state")
	data, err := os.ReadFile(stateFile)
	if err != nil {
		return ""
	}
	return string(data)
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

func healthFromBlockers(blockers []string) string {
	if len(blockers) > 0 {
		return "warning"
	}
	return "success"
}

func asStringSlice(value any) []string {
	items, ok := value.([]any)
	if ok {
		out := make([]string, 0, len(items))
		for _, item := range items {
			if text, ok := item.(string); ok {
				out = append(out, text)
			}
		}
		return out
	}
	if items, ok := value.([]string); ok {
		return append([]string(nil), items...)
	}
	return nil
}

func stringify(value any) string {
	text, _ := value.(string)
	return text
}

func stringifyDocumentValue(value any) string {
	return strings.TrimSpace(stringify(value))
}

func actorFromRequest(r *http.Request) string {
	if actor := strings.TrimSpace(r.Header.Get("X-Actor")); actor != "" {
		return actor
	}
	return "platform.ops"
}

func environmentFromRequest(r *http.Request) string {
	if env := strings.TrimSpace(r.Header.Get("X-Environment")); env != "" {
		return env
	}
	return "beta"
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

func pathActionID(path string) string {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	last := parts[len(parts)-1]
	return strings.TrimSuffix(last, ":update")
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
