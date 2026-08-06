package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"strings"
	"time"

	configreportgenerated "quwoquan_service/control-plane/platform-ops/generated/platform_ops/config_instance_report"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
)

type RuntimeHandler struct {
	facade *reportapp.RuntimeFacade
}

func NewRuntimeHandler(facade *reportapp.RuntimeFacade) (*RuntimeHandler, error) {
	if facade == nil {
		return nil, errors.New("config instance runtime handler requires facade")
	}
	return &RuntimeHandler{facade: facade}, nil
}

func (handler *RuntimeHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/releases":
		handler.listReleaseCandidateAcks(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/topology/services":
		handler.listRuntimeServices(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/topology/instances":
		handler.listRuntimeInstances(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/control-plane/platform/alerts/ingest":
		handler.ingestAlertmanagerWebhook(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/alerts/active":
		handler.listActiveAlerts(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/control-plane/platform/alerts/") && strings.HasSuffix(r.URL.Path, ":ack"):
		handler.acknowledgeAlert(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/audits":
		handler.listPlatformAudits(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/approvals":
		handler.listPlatformApprovals(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/projections/summary":
		handler.getProjectionSummary(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/triage/summary":
		handler.getTriageSummary(w, r)
	default:
		http.NotFound(w, r)
	}
}

func (handler *RuntimeHandler) listReleaseCandidateAcks(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListReleaseCandidateAcks(r.Context())
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) listRuntimeServices(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListRuntimeServices(r.Context())
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) listRuntimeInstances(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListRuntimeInstances(r.Context())
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) ingestAlertmanagerWebhook(w http.ResponseWriter, r *http.Request) {
	var payload reportapp.AlertmanagerWebhook
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("decode alertmanager webhook: "+err.Error()))
		return
	}
	ingested, err := handler.facade.IngestAlertmanagerWebhook(r.Context(), payload)
	if errors.Is(err, reportapp.ErrInvalidAlertPayload) {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid(err.Error()))
		return
	}
	writeRuntimeResult(w, r, map[string]any{"ingested": ingested}, err)
}

func (handler *RuntimeHandler) listActiveAlerts(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListActiveAlerts(r.Context(), r.URL.Query().Get("status"))
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) acknowledgeAlert(w http.ResponseWriter, r *http.Request) {
	fingerprint := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/control-plane/platform/alerts/"), ":ack")
	item, err := handler.facade.AcknowledgeAlert(r.Context(), fingerprint, requestAuditContext(r))
	if errors.Is(err, reportapp.ErrAlertNotFound) {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid(err.Error()))
		return
	}
	writeRuntimeResult(w, r, item, err)
}

func (handler *RuntimeHandler) listPlatformAudits(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListPlatformAudits(r.Context())
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) listPlatformApprovals(w http.ResponseWriter, r *http.Request) {
	items, err := handler.facade.ListPlatformApprovals(r.Context())
	writeRuntimeResult(w, r, map[string]any{"items": items}, err)
}

func (handler *RuntimeHandler) getProjectionSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := handler.facade.GetProjectionSummary(r.Context())
	writeRuntimeResult(w, r, summary, err)
}

func (handler *RuntimeHandler) getTriageSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := handler.facade.GetTriageSummary(r.Context(), controlplane.ConfigResolutionScope{
		Environment: strings.TrimSpace(r.URL.Query().Get("env")),
		Cluster:     strings.TrimSpace(r.URL.Query().Get("cluster")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
	})
	writeRuntimeResult(w, r, summary, err)
}

func writeRuntimeResult(w http.ResponseWriter, r *http.Request, payload any, err error) {
	if err != nil {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportStorageFailed(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func requestAuditContext(r *http.Request) reportapp.AuditContext {
	actor := "unverified"
	if principal, found := rtauth.PrincipalFromContext(r.Context()); found {
		if value := strings.TrimSpace(principal.Actor.AccountID); value != "" {
			actor = value
		} else if value := strings.TrimSpace(principal.Actor.DeviceActorID); value != "" {
			actor = value
		}
	}
	environment := strings.TrimSpace(os.Getenv("APP_ENV"))
	if environment == "" {
		environment = "unknown"
	}
	requestID := strings.TrimSpace(r.Header.Get("X-Request-Id"))
	traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id"))
	now := strings.ReplaceAll(time.Now().UTC().Format(time.RFC3339), ":", "")
	if requestID == "" {
		requestID = "req-" + now
	}
	if traceID == "" {
		traceID = "trace-" + now
	}
	return reportapp.AuditContext{
		Actor: actor, Environment: environment, RequestID: requestID, TraceID: traceID,
	}
}
