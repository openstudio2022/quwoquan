package main

import (
	"net/http"

	accountenforcementhttp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/adapters/inbound/http"
	appreleasehttp "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/adapters/inbound/http"
	eventrecordhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	premiumpoolhttp "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/adapters/inbound/http"
	recoveryfailurehttp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	visithttp "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/adapters/inbound/http"
)

func newServerMux(service *productService) *http.ServeMux {
	mux := http.NewServeMux()
	accountenforcementhttp.NewHandler(service.accountEnforcement).Register(mux)
	service.assignmentHTTP.Register(mux)
	visithttp.NewHandler(service.visits).Register(mux)
	appreleasehttp.NewHandler(service.appRelease).Register(mux)
	recoveryfailurehttp.NewHandler(service.recoveryFailures, writeRuntimeNotFound).Register(mux)
	premiumpoolhttp.NewHandler(service.premiumPool, writeRuntimeNotFound).Register(mux)
	eventrecordhttp.NewHandler(
		service.telemetry,
		recordTelemetryIngestMetrics,
		recordAppExperienceEvents,
	).Register(mux)
	eventrecordhttp.NewStartupTelemetryHandler(
		service.telemetry,
		recordStartupTelemetryMetrics,
	).Register(mux)
	eventrecordhttp.NewOperationsHandler(eventrecordhttp.OperationsDependencies{
		Telemetry: service.telemetry, RuntimeLogs: service.runtimeLogs,
		RuntimeLogStore: service.runtimeLogStore, Growth: service.growth,
		Metrics: application.NewMetricQueryService(service.telemetry, service.prometheus),
		ControlPlane: application.NewControlPlaneQueryService(
			service.store, service.telemetry, service.visits,
		),
		OnIngest: recordTelemetryIngestMetrics,
	}).Register(mux)
	service.experimentHTTP.Register(mux)
	return mux
}
