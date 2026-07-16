package main

import (
	"net/http"
	"os"
	"strings"

	rtmetrics "quwoquan_service/runtime/metrics"
)

func newServerMux(service *platformService) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if service.health == nil || service.health(r.Context()) != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{
				"status": "degraded",
				"error":  "postgres unavailable",
			})
			return
		}
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
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":update") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/layers", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/control-plane/platform/configs/resolve", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
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
