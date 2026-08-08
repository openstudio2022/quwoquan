package httpadapter

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	eventgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

type OperationsDependencies struct {
	Telemetry       *eventapp.TelemetryService
	RuntimeLogs     *eventapp.RuntimeLogService
	RuntimeLogStore eventapp.RuntimeLogStore
	Growth          *eventapp.GrowthService
	Metrics         *eventapp.MetricQueryService
	ControlPlane    *eventapp.ControlPlaneQueryService
	OnIngest        IngestObserver
}

type OperationsHandler struct {
	telemetry       *eventapp.TelemetryService
	runtimeLogs     *eventapp.RuntimeLogService
	runtimeLogStore eventapp.RuntimeLogStore
	growth          *eventapp.GrowthService
	metrics         *eventapp.MetricQueryService
	controlPlane    *eventapp.ControlPlaneQueryService
	onIngest        IngestObserver
}

func NewOperationsHandler(deps OperationsDependencies) *OperationsHandler {
	if deps.Telemetry == nil || deps.RuntimeLogs == nil || deps.RuntimeLogStore == nil ||
		deps.Growth == nil || deps.Metrics == nil || deps.ControlPlane == nil {
		panic("event record operations handler requires all application dependencies")
	}
	return &OperationsHandler{
		telemetry: deps.Telemetry, runtimeLogs: deps.RuntimeLogs,
		runtimeLogStore: deps.RuntimeLogStore, growth: deps.Growth,
		metrics: deps.Metrics, controlPlane: deps.ControlPlane,
		onIngest: deps.OnIngest,
	}
}

func (s *OperationsHandler) Register(mux *http.ServeMux) {
	register := func(operationID string, handler http.HandlerFunc) {
		method, path := mustEventRecordOperationRoute(operationID)
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
			if r.Method != method {
				writeRuntimeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
				return
			}
			handler(w, r)
		})
	}
	register("GetRuntimeLogSummary", s.handleGetRuntimeLogSummary)
	register("GetRuntimeLogDrilldown", s.handleGetRuntimeLogDrilldown)
	register("ReportRuntimeLogBatch", s.handleReportRuntimeLogBatch)
	register("GetEventSummary", s.handleGetEventSummary)
	register("GetEventDrilldown", s.handleGetEventDrilldown)
	register("GetRtcMediaQoeSummary", s.handleGetRtcMediaQoeSummary)
	register("ListL1L4MetricSnapshots", s.handleListL1L4MetricSnapshots)
	register("GetServiceRouteRED", s.handleGetServiceRouteRED)
	register("GetGrowthOverview", s.handleGetGrowthOverview)
	register("GetPageExperience", s.handleGetPageExperience)
	register("ListProductWorkflows", s.handleListWorkflows)
	register("ListProductAudits", s.handleListAudits)
	register("ListProductApprovals", s.handleListApprovals)
	register("GetProductProjectionSummary", s.handleProjectionSummary)
	register("GetProductTriageSummary", s.handleGetTriageSummary)
	mux.HandleFunc("/ops/internal/runtime-logs:ingest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
			return
		}
		s.handleInternalRuntimeLogIngest(w, r)
	})
}

func mustEventRecordOperationRoute(operationID string) (string, string) {
	canonicalID := "ops.event_record." + operationID
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if descriptor.CanonicalOperationID == canonicalID {
			return descriptor.Method, descriptor.PathTemplate
		}
	}
	panic(fmt.Sprintf("missing generated event record operation descriptor: %s", canonicalID))
}

func verifiedTelemetryActorHash(r *http.Request) (string, bool) {
	if r == nil {
		return "", false
	}
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", false
	}
	actorID, ok := principal.Actor.BusinessActorID()
	if !ok || strings.TrimSpace(actorID) == "" {
		return "", false
	}
	digest := sha256.Sum256([]byte(actorID))
	return hex.EncodeToString(digest[:]), true
}

func writeRuntimeError(
	w http.ResponseWriter,
	r *http.Request,
	status int,
	userMessage string,
	debugMessage string,
) {
	var appError *rterr.AppError
	switch status {
	case http.StatusBadRequest, http.StatusMethodNotAllowed:
		appError = eventgenerated.AppErrorFromRuntimeLogBatchInvalid(debugMessage)
	case http.StatusUnauthorized:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
			userMessage,
			debugMessage,
		)
	case http.StatusForbidden:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "forbidden"),
			userMessage,
			debugMessage,
		)
	case http.StatusNotFound:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			userMessage,
			debugMessage,
		)
	default:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleOps, rterr.KindSystem, "internal_error"),
			userMessage,
			debugMessage,
		)
	}
	if status == http.StatusUnauthorized {
		appError.WithMetadata("unauthorized", http.StatusUnauthorized)
	}
	writeError(w, r, appError)
}
