package main

import (
	"net/http"
	"os"

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
	if service.configTopology == nil {
		handler, err := composeConfigSnapshotTopologyHandler(service)
		if err != nil {
			panic(err)
		}
		service.configTopology = handler
	}
	if service.configInstanceRuntime == nil {
		handler, err := composeConfigInstanceRuntimeHandler(service)
		if err != nil {
			panic(err)
		}
		service.configInstanceRuntime = handler
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
		service.configTopology.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/planes", func(w http.ResponseWriter, r *http.Request) {
		service.configTopology.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/prod-plane-access-isolation", func(w http.ResponseWriter, r *http.Request) {
		service.configTopology.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/environments", func(w http.ResponseWriter, r *http.Request) {
		service.configTopology.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/clusters", func(w http.ResponseWriter, r *http.Request) {
		service.configTopology.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/services", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/topology/instances", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
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
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/alerts/active", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/alerts/", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/audits", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/approvals", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/triage/summary", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/releases", func(w http.ResponseWriter, r *http.Request) {
		service.configInstanceRuntime.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/platform/rollout/routing-policy", func(w http.ResponseWriter, r *http.Request) {
		service.configTopology.ServeHTTP(w, r)
	})
	return mux
}
