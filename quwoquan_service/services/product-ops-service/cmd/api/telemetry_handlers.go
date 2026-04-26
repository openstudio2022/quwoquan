package main

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

func (s *productService) handleReportEventBatch(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Events []application.EventRecordInput `json:"events"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	if len(body.Events) == 0 {
		writeRuntimeError(w, r, http.StatusBadRequest, "事件不能为空", "events are required")
		return
	}
	ack, err := s.telemetry.ReportEventBatch(r.Context(), body.Events)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "事件上报暂时不可用", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, ack)
}

func (s *productService) handleGetEventSummary(w http.ResponseWriter, r *http.Request) {
	query := application.EventSummaryQuery{
		EventType:        strings.TrimSpace(r.URL.Query().Get("eventType")),
		EventName:        strings.TrimSpace(r.URL.Query().Get("eventName")),
		PageName:         strings.TrimSpace(r.URL.Query().Get("pageName")),
		SurfaceID:        strings.TrimSpace(r.URL.Query().Get("surfaceId")),
		RouteID:          strings.TrimSpace(r.URL.Query().Get("routeId")),
		TargetType:       strings.TrimSpace(r.URL.Query().Get("targetType")),
		TargetKey:        strings.TrimSpace(r.URL.Query().Get("targetKey")),
		EntityType:       strings.TrimSpace(r.URL.Query().Get("entityType")),
		EntityID:         strings.TrimSpace(r.URL.Query().Get("entityId")),
		ExperimentBucket: strings.TrimSpace(r.URL.Query().Get("experimentBucket")),
		Source:           strings.TrimSpace(r.URL.Query().Get("source")),
		From:             parseOptionalTime(r.URL.Query().Get("from")),
		To:               parseOptionalTime(r.URL.Query().Get("to")),
	}
	out, err := s.telemetry.GetEventSummary(r.Context(), query)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "事件汇总暂时不可用", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *productService) handleGetEventDrilldown(w http.ResponseWriter, r *http.Request) {
	limit := 50
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	query := application.EventDrilldownQuery{
		EventType:        strings.TrimSpace(r.URL.Query().Get("eventType")),
		EventName:        strings.TrimSpace(r.URL.Query().Get("eventName")),
		PageName:         strings.TrimSpace(r.URL.Query().Get("pageName")),
		SurfaceID:        strings.TrimSpace(r.URL.Query().Get("surfaceId")),
		RouteID:          strings.TrimSpace(r.URL.Query().Get("routeId")),
		TargetType:       strings.TrimSpace(r.URL.Query().Get("targetType")),
		TargetKey:        strings.TrimSpace(r.URL.Query().Get("targetKey")),
		EntityType:       strings.TrimSpace(r.URL.Query().Get("entityType")),
		EntityID:         strings.TrimSpace(r.URL.Query().Get("entityId")),
		ExperimentBucket: strings.TrimSpace(r.URL.Query().Get("experimentBucket")),
		Source:           strings.TrimSpace(r.URL.Query().Get("source")),
		From:             parseOptionalTime(r.URL.Query().Get("from")),
		To:               parseOptionalTime(r.URL.Query().Get("to")),
		Limit:            limit,
	}
	out, err := s.telemetry.GetEventDrilldown(r.Context(), query)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "事件明细暂时不可用", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func parseOptionalTime(raw string) time.Time {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return time.Time{}
	}
	if parsed, err := time.Parse(time.RFC3339Nano, trimmed); err == nil {
		return parsed
	}
	if parsed, err := time.Parse("2006-01-02", trimmed); err == nil {
		return parsed
	}
	return time.Time{}
}
