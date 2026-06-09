package main

import (
	"net/http"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/runtime/controlplane"
	"quwoquan_service/services/product-ops-service/internal/application"
)

type productProjectionSummaryResponse struct {
	WorkflowCount     int              `json:"workflowCount"`
	ApprovalCount     int              `json:"approvalCount"`
	AuditCount        int              `json:"auditCount"`
	PendingDualReview int              `json:"pendingDualReview"`
	ActiveObjectTypes []string         `json:"activeObjectTypes"`
	L1L4Cards         []map[string]any `json:"l1l4Cards"`
}

type dimensionCount struct {
	Value string `json:"value"`
	Count int    `json:"count"`
}

type productTriageSummaryResponse struct {
	ProjectionSummary productProjectionSummaryResponse `json:"projectionSummary"`
	EventSummary      application.EventSummary         `json:"eventSummary"`
	VisitSummary      application.VisitStats           `json:"visitSummary"`
	TopEventHotspots  map[string][]dimensionCount      `json:"topEventHotspots"`
	RecentEvents      []application.EventDrilldownItem `json:"recentEvents"`
	BacklogCandidates []controlplane.BacklogCandidate  `json:"backlogCandidates"`
	RuntimeReady      bool                             `json:"runtimeReady"`
	Source            string                           `json:"source"`
}

func (s *productService) buildProjectionSummary() (productProjectionSummaryResponse, error) {
	workflows, err := s.store.ListWorkflows()
	if err != nil {
		return productProjectionSummaryResponse{}, err
	}
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		return productProjectionSummaryResponse{}, err
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		return productProjectionSummaryResponse{}, err
	}
	l1l4Cards, err := s.buildL1L4Cards()
	if err != nil {
		return productProjectionSummaryResponse{}, err
	}
	pendingDualReview := 0
	for _, workflow := range workflows {
		if workflow.State == "dual_review" || workflow.State == "dual_approval_pending" {
			pendingDualReview++
		}
	}
	return productProjectionSummaryResponse{
		WorkflowCount:     len(workflows),
		ApprovalCount:     len(approvals),
		AuditCount:        len(audits),
		PendingDualReview: pendingDualReview,
		ActiveObjectTypes: []string{
			"moderation_case",
			"recovery_case",
			"appeal_case",
			"experiment",
			"recommendation_policy",
			"entity_homepage",
			"circle_scenario",
			"assistant_comment",
			"campus_homepage",
		},
		L1L4Cards: l1l4Cards,
	}, nil
}

func (s *productService) handleGetTriageSummary(w http.ResponseWriter, r *http.Request) {
	projectionSummary, err := s.buildProjectionSummary()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	eventQuery := application.EventSummaryQuery{
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
	}
	eventSummary, err := s.telemetry.GetEventSummary(r.Context(), eventQuery)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	recentEvents, err := s.telemetry.GetEventDrilldown(r.Context(), application.EventDrilldownQuery{
		EventType:        eventQuery.EventType,
		EventName:        eventQuery.EventName,
		PageName:         eventQuery.PageName,
		SurfaceID:        eventQuery.SurfaceID,
		RouteID:          eventQuery.RouteID,
		TargetType:       eventQuery.TargetType,
		TargetKey:        eventQuery.TargetKey,
		EntityType:       eventQuery.EntityType,
		EntityID:         eventQuery.EntityID,
		ExperimentBucket: eventQuery.ExperimentBucket,
		Source:           eventQuery.Source,
		Limit:            20,
	})
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	visitSummary, err := s.telemetry.GetVisitStats(r.Context(), application.VisitStatsQuery{
		TargetType: firstNonEmpty(strings.TrimSpace(r.URL.Query().Get("visitTargetType")), "page"),
		TargetKey:  strings.TrimSpace(r.URL.Query().Get("visitTargetKey")),
	})
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	recentItems := recentEvents.Items
	writeJSON(w, http.StatusOK, productTriageSummaryResponse{
		ProjectionSummary: projectionSummary,
		EventSummary:      eventSummary,
		VisitSummary:      visitSummary,
		TopEventHotspots:  buildTopEventHotspots(eventSummary),
		RecentEvents:      recentItems,
		BacklogCandidates: buildProductBacklogCandidates(projectionSummary, eventSummary, visitSummary, recentItems),
		RuntimeReady:      projectionSummary.PendingDualReview == 0,
		Source:            "control-plane",
	})
}

func buildTopEventHotspots(summary application.EventSummary) map[string][]dimensionCount {
	keys := []string{"pageName", "surfaceId", "routeId", "operationId", "eventName", "eventType", "targetType", "targetKey", "experimentBucket"}
	out := map[string][]dimensionCount{}
	for _, key := range keys {
		counter := summary.DimensionCounters[key]
		if len(counter) == 0 {
			continue
		}
		out[key] = topDimensionCounts(counter, 5)
	}
	return out
}

func topDimensionCounts(counter map[string]int, limit int) []dimensionCount {
	out := make([]dimensionCount, 0, len(counter))
	for value, count := range counter {
		out = append(out, dimensionCount{Value: value, Count: count})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Count == out[j].Count {
			return out[i].Value < out[j].Value
		}
		return out[i].Count > out[j].Count
	})
	if limit > 0 && len(out) > limit {
		return out[:limit]
	}
	return out
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func buildProductBacklogCandidates(
	projectionSummary productProjectionSummaryResponse,
	eventSummary application.EventSummary,
	visitSummary application.VisitStats,
	recentEvents []application.EventDrilldownItem,
) []controlplane.BacklogCandidate {
	candidates := make([]controlplane.BacklogCandidate, 0, 5)
	if projectionSummary.PendingDualReview > 0 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "product-governance-dual-review",
			Category:       "governance_backlog",
			Severity:       "warning",
			Title:          "处理产品治理双签待办",
			Summary:        "当前仍有 " + strconv.Itoa(projectionSummary.PendingDualReview) + " 个产品治理流程处于双签待处理状态。",
			Owner:          "product-ops",
			NextAction:     "打开 /product/dashboard 处理治理 case，并补齐审批说明。",
			DrilldownRoute: "/product/dashboard",
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
			RepairEntry:    "/product/governance",
			AlertID:        "governance_dual_review_pending",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"pendingDualReview": projectionSummary.PendingDualReview,
				"workflowCount":     projectionSummary.WorkflowCount,
				"approvalCount":     projectionSummary.ApprovalCount,
			},
		})
	}
	missingDimensions := missingProductEventDimensions(eventSummary)
	if len(missingDimensions) > 0 && eventSummary.TotalCount > 0 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "product-event-dimension-gap",
			Category:       "telemetry_gap",
			Severity:       "critical",
			Title:          "补齐事件维度覆盖",
			Summary:        "当前事件汇总缺少 " + strings.Join(missingDimensions, "、") + " 维度，Agent 无法完整还原调用链。",
			Owner:          "app-observability",
			NextAction:     "检查 page_access / event 上报链路，补齐缺失的页面、surface、route 或 operation 维度。",
			DrilldownRoute: "/product/dashboard",
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
			RepairEntry:    "/product/dashboard",
			AlertID:        "OpsEventUploadDrop",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"missingDimensions": missingDimensions,
				"totalEvents":       eventSummary.TotalCount,
			},
		})
	}
	if len(projectionSummary.L1L4Cards) < 4 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "product-l1l4-card-gap",
			Category:       "metric_gap",
			Severity:       "warning",
			Title:          "补齐四层指标注册表",
			Summary:        "当前仅注册了 " + strconv.Itoa(len(projectionSummary.L1L4Cards)) + " 个 L1-L4 指标卡，未达到四层完整覆盖。",
			Owner:          "product-ops",
			NextAction:     "打开 /product/l1-l4/environment 补齐缺失层级指标或接入对应 domain metric snapshot。",
			DrilldownRoute: "/product/l1-l4/environment",
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
			RepairEntry:    "/product/l1-l4/environment",
			AlertID:        "HighP95Latency",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"cardCount": len(projectionSummary.L1L4Cards),
				"cards":     projectionSummary.L1L4Cards,
			},
		})
	}
	if visitSummary.TotalVisits > 0 && eventSummary.TotalCount == 0 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "product-visit-event-gap",
			Category:       "telemetry_gap",
			Severity:       "warning",
			Title:          "补齐访问事件上报",
			Summary:        "当前已有 " + strconv.Itoa(visitSummary.TotalVisits) + " 次访问统计，但未观察到对应事件记录。",
			Owner:          "app-observability",
			NextAction:     "检查页面访问采集、事件批量上报与 visit 汇总之间的链路。",
			DrilldownRoute: "/product/dashboard",
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
			RepairEntry:    "/product/dashboard",
			AlertID:        "OpsEventUploadDrop",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"visitCount": visitSummary.TotalVisits,
				"events":     eventSummary.TotalCount,
			},
		})
	}
	if len(recentEvents) > 0 {
		missingFields := missingRecentEventFields(recentEvents)
		if len(missingFields) > 0 {
			candidates = append(candidates, controlplane.BacklogCandidate{
				ID:             "product-event-field-gap",
				Category:       "telemetry_gap",
				Severity:       "warning",
				Title:          "补齐最近事件关键字段",
				Summary:        "最近事件仍存在 " + strings.Join(missingFields, "、") + " 缺失，影响 Agent 下钻和调用链还原。",
				Owner:          "app-observability",
				NextAction:     "对照最近事件样本修复 AppLog / event uploader 的字段映射。",
				DrilldownRoute: "/product/dashboard",
				RunbookID:      "cfg-rollback-drill",
				RunbookRoute:   "/platform/runbook",
				RepairEntry:    "/product/dashboard",
				AlertID:        "OpsEventUploadDrop",
				AuditRoute:     "/audit",
				Evidence: map[string]any{
					"missingFields": missingFields,
					"sampleEventId": recentEvents[0].EventID,
				},
			})
		}
	}
	return controlplane.LimitBacklogCandidates(controlplane.SortBacklogCandidates(candidates), 5)
}

func missingProductEventDimensions(summary application.EventSummary) []string {
	candidateDimensions := []string{"pageName", "surfaceId", "routeId", "operationId", "targetType", "targetKey", "experimentBucket"}
	missing := make([]string, 0, len(candidateDimensions))
	for _, dimension := range candidateDimensions {
		if len(summary.DimensionCounters[dimension]) == 0 {
			missing = append(missing, dimension)
		}
	}
	return missing
}

func missingRecentEventFields(items []application.EventDrilldownItem) []string {
	fields := map[string]bool{}
	for _, item := range items {
		if strings.TrimSpace(item.PageName) == "" {
			fields["pageName"] = true
		}
		if strings.TrimSpace(item.SurfaceID) == "" {
			fields["surfaceId"] = true
		}
		if strings.TrimSpace(item.RouteID) == "" {
			fields["routeId"] = true
		}
		if strings.TrimSpace(item.OperationID) == "" {
			fields["operationId"] = true
		}
		if strings.TrimSpace(item.TargetType) == "" {
			fields["targetType"] = true
		}
		if strings.TrimSpace(item.TargetKey) == "" {
			fields["targetKey"] = true
		}
	}
	out := make([]string, 0, len(fields))
	for field := range fields {
		out = append(out, field)
	}
	sort.Strings(out)
	return out
}
