package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"

	"gopkg.in/yaml.v3"
)

type platformService struct {
	repoRoot string
	store    *controlplane.FileStore
}

func main() {
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "platform-ops-service", SamplingRatio: 0.1})
	defer otelShutdown()

	serviceName, appEnv, configRoot, configVersion, imageVersion := resolvePlatformRuntimeIdentity()
	cfg, err := loadPlatformRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("platform-ops-service config load failed: %v", err)
	}
	addr := strings.TrimSpace(os.Getenv("PLATFORM_OPS_SERVICE_ADDR"))
	if addr == "" {
		addr = strings.TrimSpace(cfg.Service.HTTP.Addr)
	}
	if addr == "" {
		addr = ":18087"
	}
	repoRoot := resolveRepoRoot()
	service := &platformService{
		repoRoot: repoRoot,
		store:    controlplane.NewFileStore(filepath.Join(repoRoot, "state", "control-plane", "platform-ops-service.json")),
	}
	if err := service.seed(); err != nil {
		log.Fatalf("seed platform ops service: %v", err)
	}
	mux := newServerMux(service)

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
	observedHandler := rthttp.NewHTTPServerMiddleware(mux, rthttp.HTTPServerMiddlewareConfig{
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
		Addr:              addr,
		Handler:           rateLimited,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("platform-ops-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("platform-ops-service: %v", err)
	}
}

func newServerMux(service *platformService) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		if _, err := os.Stat(service.repoRoot); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{
				"status": "degraded",
				"error":  "repo root inaccessible",
			})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	mux.Handle("/metrics", rtmetrics.Handler())
	mux.HandleFunc("/v1/control-plane/platform/catalog/services", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListServiceCatalog(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/onboarding/domains", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListOnboardingDomains(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/planes", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListPlaneBindings(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/planes/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":update") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleUpdatePlaneBinding(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/environments", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListEnvironmentTopologies(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/clusters", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "runtime_clusters")
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/services", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "runtime_services")
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/instances", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "runtime_instances")
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/dependencies", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "dependency_profiles")
	})
	mux.HandleFunc("/v1/control-plane/platform/topology/capacity", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "capacity_profiles")
	})
	mux.HandleFunc("/v1/control-plane/platform/configs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListConfigKeys(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && strings.HasSuffix(r.URL.Path, ":effective"):
			service.handleGetEffectiveConfig(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":update"):
			service.handleUpdateNamespaceDocument(w, r, "config_layers", "config_layer_updated")
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/layers", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "config_layers")
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/resolve", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleResolveConfig(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/packages", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "config_packages")
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/instances", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListConfigInstanceReports(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/instances/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":report") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleReportConfigInstance(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/governance/bindings", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "governance_bindings")
	})
	mux.HandleFunc("/v1/control-plane/platform/governance/templates", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "governance_templates")
	})
	mux.HandleFunc("/v1/control-plane/platform/governance/bindings/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":update") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleUpdateNamespaceDocument(w, r, "governance_bindings", "governance_binding_updated")
	})
	mux.HandleFunc("/v1/control-plane/platform/observability/slos", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "slo_policies")
	})
	mux.HandleFunc("/v1/control-plane/platform/observability/alerts", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "alert_templates")
	})
	mux.HandleFunc("/v1/control-plane/platform/observability/dashboards/cards", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "dashboard_cards")
	})
	mux.HandleFunc("/v1/control-plane/platform/runbooks", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "runbooks")
	})
	mux.HandleFunc("/v1/control-plane/platform/runbooks/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":runDrill") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleRunDrill(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/gates", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListNamespace(w, r, "gate_rules")
	})
	mux.HandleFunc("/v1/control-plane/platform/gates/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":override") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleUpdateNamespaceDocument(w, r, "gate_rules", "gate_rule_overridden")
	})
	mux.HandleFunc("/v1/control-plane/platform/audits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		items, err := service.store.ListAudits()
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"items": items})
	})
	mux.HandleFunc("/v1/control-plane/platform/approvals", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		items, err := service.store.ListAllApprovals()
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"items": items})
	})
	mux.HandleFunc("/v1/control-plane/platform/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleProjectionSummary(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/triage/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetTriageSummary(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/releases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeError(w, r, http.StatusMethodNotAllowed, "请求处理失败", "only GET")
			return
		}
		service.handleListReleases(w, r.URL.Query().Get("service"))
	})
	mux.HandleFunc("/v1/control-plane/platform/releases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":apply"):
			service.handleApplyRelease(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":rollback"):
			service.handleRollbackRelease(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	return mux
}

func (s *platformService) seed() error {
	schemaPath := resolveConfigSchemaPath(s.repoRoot)
	schemaKeys, schemaErr := controlplane.LoadConfigKeysFromSchema(schemaPath)
	if schemaErr != nil {
		log.Printf("WARN: platform-ops-service: load config_schema.yaml failed, using empty keys: %v", schemaErr)
		schemaKeys = nil
	}

	defaultDocs := map[string][]controlplane.Document{
		"config_keys": schemaKeys,
		"config_layers": {
			{
				"id":          "global:all",
				"title":       "系统级默认",
				"scopeLevel":  "global",
				"scopeID":     "all",
				"environment": "all",
				"values": map[string]any{
					"sys.gateway.rate_limit.per_user_rps":    30,
					"sys.orchestrator.downstream.timeout_ms": 900,
					"sys.client_state_sync.flush_delay_sec":  12,
					"sys.assistant.otel.trace_sample_ratio":  0.15,
					"sys.content.mongo.max_pool_size":        100,
				},
			},
			{
				"id":          "environment:beta",
				"title":       "beta 环境默认",
				"scopeLevel":  "environment",
				"scopeID":     "beta",
				"environment": "beta",
				"values": map[string]any{
					"sys.orchestrator.downstream.timeout_ms": 850,
				},
			},
			{
				"id":          "cluster:beta-control-a",
				"title":       "beta 控制面集群 A",
				"scopeLevel":  "cluster",
				"scopeID":     "beta-control-a",
				"environment": "beta",
				"cluster":     "beta-control-a",
				"values": map[string]any{
					"sys.gateway.rate_limit.per_user_rps": 45,
				},
			},
			{
				"id":          "service:product-ops-service",
				"title":       "product-ops-service 服务层",
				"scopeLevel":  "service",
				"scopeID":     "product-ops-service",
				"environment": "beta",
				"cluster":     "beta-control-a",
				"service":     "product-ops-service",
				"values": map[string]any{
					"sys.gateway.rate_limit.per_user_rps":    50,
					"sys.client_state_sync.flush_delay_sec":  9,
					"sys.orchestrator.downstream.timeout_ms": 720,
				},
			},
		},
		"config_packages": {
			{
				"id":            "beta-control-a-product-ops-service-v2026.03.08.0",
				"packageId":     "beta-control-a-product-ops-service-v2026.03.08.0",
				"environment":   "beta",
				"cluster":       "beta-control-a",
				"service":       "product-ops-service",
				"configVersion": "v2026.03.08.0",
				"imageVersion":  "0.0.1",
				"releaseState":  "ready",
				"distribution":  "config-center+disk",
			},
			{
				"id":            "beta-control-a-platform-ops-service-v2026.03.08.0",
				"packageId":     "beta-control-a-platform-ops-service-v2026.03.08.0",
				"environment":   "beta",
				"cluster":       "beta-control-a",
				"service":       "platform-ops-service",
				"configVersion": "v2026.03.08.0",
				"imageVersion":  "0.0.1",
				"releaseState":  "ready",
				"distribution":  "config-center+disk",
			},
		},
		"config_instance_reports": {
			{
				"id":            "product-ops-service-beta-control-a-0",
				"environment":   "beta",
				"cluster":       "beta-control-a",
				"service":       "product-ops-service",
				"instanceId":    "product-ops-service-beta-control-a-0",
				"configVersion": "v2026.03.08.0",
				"imageVersion":  "0.0.1",
				"desiredHash":   "bootstrap-product-hash",
				"effectiveHash": "bootstrap-product-hash",
				"inSync":        true,
				"source":        "config-center",
			},
			{
				"id":            "platform-ops-service-beta-control-a-0",
				"environment":   "beta",
				"cluster":       "beta-control-a",
				"service":       "platform-ops-service",
				"instanceId":    "platform-ops-service-beta-control-a-0",
				"configVersion": "v2026.03.08.0",
				"imageVersion":  "0.0.1",
				"desiredHash":   "bootstrap-platform-hash",
				"effectiveHash": "stale-bootstrap-platform-hash",
				"inSync":        false,
				"source":        "disk-fallback",
				"lastError":     "config center timeout",
			},
		},
		"runtime_clusters": {
			{"id": "beta-control-a", "environment": "beta", "cluster": "beta-control-a", "plane": "control-plane", "services": []string{"platform-ops-service", "product-ops-service", "seed-box"}, "status": "success"},
			{"id": "beta-user-a", "environment": "beta", "cluster": "beta-user-a", "plane": "user-plane", "services": []string{"realtime-gateway", "recommendation-service"}, "status": "warning"},
		},
		"runtime_services": {
			{"id": "platform-ops-service", "environment": "beta", "cluster": "beta-control-a", "service": "platform-ops-service", "plane": "platform-control-plane", "instances": 1, "status": "warning"},
			{"id": "product-ops-service", "environment": "beta", "cluster": "beta-control-a", "service": "product-ops-service", "plane": "product-control-plane", "instances": 1, "status": "success"},
			{"id": "realtime-gateway", "environment": "beta", "cluster": "beta-user-a", "service": "realtime-gateway", "plane": "user-plane", "instances": 2, "status": "success"},
		},
		"runtime_instances": {
			{"id": "platform-ops-service-beta-control-a-0", "environment": "beta", "cluster": "beta-control-a", "service": "platform-ops-service", "plane": "platform-control-plane", "status": "warning"},
			{"id": "product-ops-service-beta-control-a-0", "environment": "beta", "cluster": "beta-control-a", "service": "product-ops-service", "plane": "product-control-plane", "status": "success"},
			{"id": "realtime-gateway-beta-user-a-0", "environment": "beta", "cluster": "beta-user-a", "service": "realtime-gateway", "plane": "user-plane", "status": "success"},
		},
		"governance_bindings": {
			{"id": "gateway.timeout.default", "title": "gateway.timeout.default", "subtitle": "默认超时 800ms · 作用于 orchestrator / gateway。", "status": "warning"},
			{"id": "content.mongo.pool", "title": "content.mongo.pool", "subtitle": "Mongo 连接池上限 120 · 需要 restart 生效。", "status": "neutral"},
			{"id": "assistant.trace.sampling", "title": "assistant.trace.sampling", "subtitle": "OTel 采样率 0.2 · 支持热更新。", "status": "success"},
		},
		"governance_templates": {
			{"id": "timeout-template", "title": "默认超时模板", "summary": "用于 gateway / orchestrator / integration 服务", "status": "success"},
			{"id": "rate-limit-template", "title": "限流模板", "summary": "覆盖 user-plane 入口与控制面后台任务", "status": "warning"},
		},
		"dependency_profiles": {
			{"id": "mongo-content", "dependency": "MongoDB / content-primary", "profile": "primary-write", "latency": "12ms", "status": "success"},
			{"id": "redis-cluster-a", "dependency": "Redis / cache-cluster-a", "profile": "rate-limit + cache", "latency": "4ms", "status": "success"},
			{"id": "llm-gateway", "dependency": "LLM Gateway / assistant-upstream", "profile": "external-api", "latency": "480ms", "status": "warning"},
		},
		"capacity_profiles": {
			{"id": "user-plane", "plane": "user-plane", "resourceClass": "4c8g", "scaling": "HPA CPU / QPS", "splitTrigger": "user traffic spike"},
			{"id": "platform-control-plane", "plane": "platform-control-plane", "resourceClass": "2c4g", "scaling": "manual + batch window", "splitTrigger": "config release / audit backlog"},
			{"id": "product-control-plane", "plane": "product-control-plane", "resourceClass": "2c4g", "scaling": "case backlog / operator concurrency", "splitTrigger": "SLA backlog growth"},
		},
		"slo_policies": {
			{"id": "release-success-rate", "service": "platform-control-plane", "objective": "99.2%", "window": "30m", "status": "warning"},
			{"id": "config-latency-p95", "service": "gateway-orchestrator", "objective": "p95<900ms", "window": "15m", "status": "success"},
		},
		"alert_templates": {
			{"id": "HighP95Latency", "title": "服务 P95 延迟过高", "severity": "warning", "status": "warning", "owner": "platform-ops", "runbookId": "cfg-rollback-drill", "runbookRoute": "/platform/runbook", "repairEntry": "/platform/rollout", "alertId": "HighP95Latency", "auditRoute": "/audit"},
			{"id": "config_release_error_rate", "title": "配置发布错误率门禁", "severity": "critical", "status": "warning", "owner": "platform-ops", "runbookId": "cfg-rollback-drill", "runbookRoute": "/platform/runbook", "repairEntry": "/platform/rollout", "alertId": "config_release_error_rate", "auditRoute": "/audit"},
			{"id": "rollback_readiness", "title": "回滚准备度检查", "severity": "warning", "status": "neutral", "owner": "platform-ops", "runbookId": "cfg-rollback-drill", "runbookRoute": "/platform/runbook", "repairEntry": "/platform/rollout", "alertId": "rollback_readiness", "auditRoute": "/audit"},
		},
		"dashboard_cards": {
			{"id": "release_health", "title": "配置灰度健康", "summary": "success_rate / latency / rollback readiness"},
			{"id": "sla_watch", "title": "SLA 风险队列", "summary": "集中观察接近阈值的链路"},
		},
		"runbooks": {
			{"id": "cfg-rollback-drill", "title": "配置发布回滚演练", "subtitle": "每周一次，验证 rollback token、SLO gate 与恢复路径。", "status": "success"},
			{"id": "mongo-failover-drill", "title": "Mongo 主从切换演练", "subtitle": "覆盖 content / user 关键写路径。", "status": "warning"},
			{"id": "control-plane-split-drill", "title": "控制面独立扩容演练", "subtitle": "验证 seed-box 到独立 Pod 的切换准备度。", "status": "neutral"},
		},
		"gate_rules": {
			{"id": "config_release_error_rate", "rule": "config_release_error_rate", "stage": "25%", "status": "success", "summary": "error_rate < 0.5% 且 p95 < 900ms"},
			{"id": "dependency_health_mongo", "rule": "dependency_health_mongo", "stage": "50%", "status": "warning", "summary": "副本延迟接近阈值，需人工复核"},
			{"id": "rollback_readiness", "rule": "rollback_readiness", "stage": "100%", "status": "neutral", "summary": "回滚包与上一个稳定版本均已就绪"},
		},
	}
	for namespace, items := range defaultDocs {
		for _, item := range items {
			id := item["id"].(string)
			switch namespace {
			case "config_keys", "config_layers":
				if err := s.store.PutDocument(namespace, id, item); err != nil {
					return err
				}
			default:
				_, ok, err := s.store.GetDocument(namespace, id)
				if err != nil {
					return err
				}
				if ok {
					continue
				}
				if err := s.store.PutDocument(namespace, id, item); err != nil {
					return err
				}
			}
		}
	}
	configLayers, err := s.store.ListDocuments("config_layers")
	if err != nil {
		return err
	}
	for _, layer := range configLayers {
		if stringifyDocumentValue(layer["scopeLevel"]) != "instance" {
			continue
		}
		if err := s.store.DeleteDocument("config_layers", stringifyDocumentValue(layer["id"])); err != nil {
			return err
		}
	}
	if err := s.syncConfigPackageDesiredHashes(); err != nil {
		return err
	}
	return nil
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
	if err := s.readYAMLInto(filepath.Join(s.repoRoot, "deploy", "shared", "process_domain_plane_mapping.yaml"), &doc); err != nil {
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
	bindingID := segmentBetween(r.URL.Path, "/v1/control-plane/platform/topology/planes/", ":update")
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

func (s *platformService) handleListConfigKeys(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("config_keys")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleGetEffectiveConfig(w http.ResponseWriter, r *http.Request) {
	layerID := segmentBetween(r.URL.Path, "/v1/control-plane/platform/configs/", ":effective")
	layer, ok, err := s.store.GetDocument("config_layers", layerID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "config layer not found")
		return
	}
	writeJSON(w, http.StatusOK, layer)
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

func (s *platformService) syncConfigPackageDesiredHashes() error {
	configLayers, err := s.store.ListDocuments("config_layers")
	if err != nil {
		return err
	}
	configKeys, err := s.store.ListDocuments("config_keys")
	if err != nil {
		return err
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
		values := controlplane.ResolveEffectiveConfig(configLayers, configKeys, scope)
		desiredHash := controlplane.EffectiveConfigHash(values)
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
	runbookID := segmentBetween(r.URL.Path, "/v1/control-plane/platform/runbooks/", ":runDrill")
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
	stateFile := filepath.Join(repoRoot, "state", "release", service+".state")
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
		if _, err := os.Stat(filepath.Join(current, "releases", "config")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			return wd
		}
		current = parent
	}
}

func resolveConfigSchemaPath(repoRoot string) string {
	candidates := []string{
		filepath.Join(repoRoot, "quwoquan_service", "contracts", "metadata", "_control_plane", "platform", "config_schema.yaml"),
		filepath.Join(repoRoot, "contracts", "metadata", "_control_plane", "platform", "config_schema.yaml"),
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return candidates[0]
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
