package main

import (
	"net/http"
	"strings"

	"quwoquan_service/runtime/health"
	rtmetrics "quwoquan_service/runtime/metrics"
)

func newServerMux(service *productService, healthChecker *health.Checker) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthChecker.Handler())
	mux.Handle("/metrics", rtmetrics.Handler())
	mux.HandleFunc("/v1/ops/experiments/", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/ops/visits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleRecordVisit(w, r)
	})
	mux.HandleFunc("/v1/ops/visits/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetVisitStats(w, r)
	})
	mux.HandleFunc("/v1/ops/events", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleReportEventBatch(w, r)
	})
	mux.HandleFunc("/v1/ops/events/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetEventSummary(w, r)
	})
	mux.HandleFunc("/v1/ops/events/drilldown", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetEventDrilldown(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/experiments", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/experiments/", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/moderation/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListModerationCases(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/moderation/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetModerationCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":startReview"):
			service.handleStartModerationReview(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":applyAction"):
			service.handleApplyEnforcementAction(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recovery/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListRecoveryCases(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/recovery/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetRecoveryCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":submitDecision"):
			service.handleSubmitRecoveryDecision(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/appeal/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListAppealCases(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/appeal/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetAppealCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":submitDecision"):
			service.handleSubmitAppealDecision(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/policies", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListRecommendationPolicies(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/policies/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":simulate"):
			service.handleSimulateRecommendationPolicy(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":activate"):
			service.handleActivateRecommendationPolicy(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/premium-pool", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			service.handleListPremiumPool(w, r)
		case http.MethodPost:
			service.handleUpsertPremiumPool(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/premium-pool/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":rollback"):
			service.handleRollbackPremiumPool(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":takedown"):
			service.handleTakedownPremiumPool(w, r)
		default:
			writeRuntimeNotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/workflows", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListWorkflows(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/audits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListAudits(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/approvals", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListApprovals(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleProjectionSummary(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/triage/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetTriageSummary(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/metrics/l1l4", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		scope := l1l4MetricsScope{
			Environment: strings.TrimSpace(r.URL.Query().Get("env")),
			Cluster:     strings.TrimSpace(r.URL.Query().Get("cluster")),
			Service:     strings.TrimSpace(r.URL.Query().Get("service")),
			InstanceID:  strings.TrimSpace(r.URL.Query().Get("instance")),
			Level:       strings.TrimSpace(r.URL.Query().Get("level")),
		}
		payload, err := service.buildL1L4MetricsResponse(r.Context(), scope)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		writeJSON(w, http.StatusOK, payload)
	})
	return mux
}
