package main

import (
	"fmt"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/health"
	rtmetrics "quwoquan_service/runtime/metrics"
	accountenforcementhttp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/adapters/inbound/http"
	appreleasehttp "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/adapters/inbound/http"
	eventrecordhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	experimentassignmenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/http"
	premiumpoolhttp "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/adapters/inbound/http"
	recoveryfailurehttp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	visithttp "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/adapters/inbound/http"
)

const getRtcMediaQoeSummaryOperationID = "ops.event_record.GetRtcMediaQoeSummary"

func newServerMux(service *productService, healthChecker *health.Checker) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthChecker.Handler())
	mux.Handle("/metrics", rtmetrics.Handler())
	accountenforcementhttp.NewHandler(service.accountEnforcement).Register(mux)
	mux.HandleFunc("/ops/experiments/", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	experimentassignmenthttp.Register(mux, service.experimentHTTP)
	visithttp.NewHandler(service.visits).Register(mux)
	appreleasehttp.NewHandler(service.appRelease).Register(mux)
	recoveryfailurehttp.NewHandler(service.recoveryFailures, writeRuntimeError).Register(mux)
	premiumpoolhttp.NewHandler(service.premiumPool, writeRuntimeError).Register(mux)
	eventrecordhttp.NewHandler(
		service.telemetry,
		recordTelemetryIngestMetrics,
		recordAppExperienceEvents,
	).Register(mux)
	mux.HandleFunc("/ops/runtime-logs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleReportRuntimeLogBatch(w, r)
	})
	mux.HandleFunc("/ops/runtime-logs/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetRuntimeLogSummary(w, r)
	})
	mux.HandleFunc("/ops/runtime-logs/drilldown", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetRuntimeLogDrilldown(w, r)
	})
	mux.HandleFunc("/ops/startup-events", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleReportStartupEventBatch(w, r)
	})
	mux.HandleFunc("/ops/internal/runtime-logs:ingest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleInternalRuntimeLogIngest(w, r)
	})
	mux.HandleFunc("/ops/events/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetEventSummary(w, r)
	})
	rtcMediaQoeMethod, rtcMediaQoePath := mustOpsOperationRoute(
		getRtcMediaQoeSummaryOperationID,
	)
	mux.HandleFunc(rtcMediaQoePath, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != rtcMediaQoeMethod {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetRtcMediaQoeSummary(w, r)
	})
	mux.HandleFunc("/ops/events/drilldown", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetEventDrilldown(w, r)
	})
	mux.HandleFunc("/control-plane/product/experiments", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/product/experiments/", func(w http.ResponseWriter, r *http.Request) {
		service.experimentHTTP.ServeHTTP(w, r)
	})
	mux.HandleFunc("/control-plane/product/workflows", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListWorkflows(w, r)
	})
	mux.HandleFunc("/control-plane/product/audits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListAudits(w, r)
	})
	mux.HandleFunc("/control-plane/product/approvals", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleListApprovals(w, r)
	})
	mux.HandleFunc("/control-plane/product/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleProjectionSummary(w, r)
	})
	mux.HandleFunc("/control-plane/product/triage/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetTriageSummary(w, r)
	})
	mux.HandleFunc("/control-plane/product/metrics/l1l4", func(w http.ResponseWriter, r *http.Request) {
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
	mux.HandleFunc("/control-plane/product/metrics/red-routes", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetServiceRouteRED(w, r)
	})
	mux.HandleFunc("/control-plane/product/growth/overview", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetGrowthOverview(w, r)
	})
	mux.HandleFunc("/control-plane/product/experience/pages", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		service.handleGetPageExperience(w, r)
	})
	return mux
}

func mustOpsOperationRoute(canonicalOperationID string) (method string, path string) {
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor.Method, descriptor.PathTemplate
		}
	}
	panic(fmt.Sprintf("missing generated operation descriptor: %s", canonicalOperationID))
}
