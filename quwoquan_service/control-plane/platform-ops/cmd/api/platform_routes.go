package main

import (
	"net/http"
	"os"
	"strings"

	rtmetrics "quwoquan_service/runtime/metrics"
)

func newServerMux(service *platformService) *http.ServeMux {
	if service.configInstanceReports == nil {
		handler, err := composeConfigInstanceReportHandler(service)
		if err != nil {
			panic(err)
		}
		service.configInstanceReports = handler
	}
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
	mux.HandleFunc("/readyz/config-convergence", service.handleConfigAckConvergence)
	mux.HandleFunc("/control-plane/platform/catalog/services", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListServiceCatalog(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/planes", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListPlaneBindings(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/environments", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListEnvironmentTopologies(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/clusters", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListRuntimeClusters(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/services", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListRuntimeServices(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/instances", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListRuntimeInstances(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/resolve", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/resolve-for-instance", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/snapshot", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/domains", func(w http.ResponseWriter, r *http.Request) {
		service.configLayers.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/instances", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceReports.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/configs/instances/", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceReports.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/alerts/ingest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleIngestAlertmanagerWebhook(w, r)
	})
	mux.HandleFunc("/control-plane/platform/alerts/active", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListActiveAlerts(w, r)
	})
	mux.HandleFunc("/control-plane/platform/alerts/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":ack") {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleAckAlert(w, r)
	})
	mux.HandleFunc("/control-plane/platform/audits", func(w http.ResponseWriter, r *http.Request) {
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
	mux.HandleFunc("/control-plane/platform/approvals", func(w http.ResponseWriter, r *http.Request) {
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
	mux.HandleFunc("/control-plane/platform/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleProjectionSummary(w, r)
	})
	mux.HandleFunc("/control-plane/platform/triage/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetTriageSummary(w, r)
	})
	mux.HandleFunc("/control-plane/platform/releases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeError(w, r, http.StatusMethodNotAllowed, "请求处理失败", "only GET")
			return
		}
		service.handleListReleases(w, r, r.URL.Query().Get("service"))
	})
	mux.HandleFunc("/control-plane/platform/rollout/routing-policy", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetGrayRoutingPolicy(w, r)
	})
	return mux
}
