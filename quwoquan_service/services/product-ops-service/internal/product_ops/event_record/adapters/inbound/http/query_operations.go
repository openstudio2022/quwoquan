package httpadapter

import (
	"errors"
	"net/http"
	"strings"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

func (s *OperationsHandler) handleListL1L4MetricSnapshots(w http.ResponseWriter, r *http.Request) {
	payload, err := s.metrics.ListL1L4MetricSnapshots(r.Context(), eventapp.L1L4MetricsScope{
		Environment: strings.TrimSpace(firstQuery(r, "environment", "env")),
		Cluster:     strings.TrimSpace(firstQuery(r, "cluster")),
		Service:     strings.TrimSpace(firstQuery(r, "service")),
		InstanceID:  strings.TrimSpace(firstQuery(r, "instance", "instanceId")),
		Level:       strings.TrimSpace(firstQuery(r, "level")),
	})
	if err != nil {
		writeEventAppError(w, r, generated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (s *OperationsHandler) handleGetServiceRouteRED(w http.ResponseWriter, r *http.Request) {
	payload, err := s.metrics.GetServiceRouteRED(r.Context(), r.URL.Query().Get("service"))
	if errors.Is(err, eventapp.ErrInvalidEventQuery) {
		writeEventAppError(w, r, generated.AppErrorFromQueryWindowInvalid("service is required"))
		return
	}
	if err != nil {
		writeEventAppError(w, r, generated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (s *OperationsHandler) handleGetTriageSummary(w http.ResponseWriter, r *http.Request) {
	payload, err := s.controlPlane.GetProductTriageSummary(r.Context(), eventapp.ProductTriageQuery{
		LogType: r.URL.Query().Get("logType"), EventType: r.URL.Query().Get("eventType"),
		PageName: r.URL.Query().Get("pageName"), AppVersion: r.URL.Query().Get("appVersion"),
		NetworkClass: r.URL.Query().Get("networkClass"), ErrorCode: r.URL.Query().Get("errorCode"),
		VisitTargetType: r.URL.Query().Get("visitTargetType"), VisitTargetKey: r.URL.Query().Get("visitTargetKey"),
	})
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func firstQuery(r *http.Request, names ...string) string {
	for _, name := range names {
		if value := strings.TrimSpace(r.URL.Query().Get(name)); value != "" {
			return value
		}
	}
	return ""
}
