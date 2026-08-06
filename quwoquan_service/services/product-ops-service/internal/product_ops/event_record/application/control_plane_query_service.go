package application

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

type ProductProjectionSummary struct {
	WorkflowCount     int              `json:"workflowCount"`
	ApprovalCount     int              `json:"approvalCount"`
	AuditCount        int              `json:"auditCount"`
	PendingDualReview int              `json:"pendingDualReview"`
	ActiveObjectTypes []string         `json:"activeObjectTypes"`
	L1L4Cards         []map[string]any `json:"l1l4Cards"`
}

type DimensionCount struct {
	Value string `json:"value"`
	Count int    `json:"count"`
}

type ProductTriageSummary struct {
	ProjectionSummary ProductProjectionSummary        `json:"projectionSummary"`
	EventSummary      EventSummary                    `json:"eventSummary"`
	VisitSummary      visitapplication.VisitStats     `json:"visitSummary"`
	TopEventHotspots  map[string][]DimensionCount     `json:"topEventHotspots"`
	RecentEvents      []EventDrilldownItem            `json:"recentEvents"`
	BacklogCandidates []controlplane.BacklogCandidate `json:"backlogCandidates"`
	RuntimeReady      bool                            `json:"runtimeReady"`
	Source            string                          `json:"source"`
}

type ControlPlaneQueryService struct {
	store     controlplane.StateStore
	telemetry *TelemetryService
	visits    VisitStatsReader
}

type VisitStatsReader interface {
	GetVisitStats(context.Context, visitapplication.VisitStatsQuery) (visitapplication.VisitStats, error)
}

func NewControlPlaneQueryService(
	store controlplane.StateStore,
	telemetry *TelemetryService,
	visits VisitStatsReader,
) *ControlPlaneQueryService {
	if store == nil || telemetry == nil || visits == nil {
		panic("control-plane query service requires store, telemetry and visits")
	}
	return &ControlPlaneQueryService{store: store, telemetry: telemetry, visits: visits}
}

func (s *ControlPlaneQueryService) ListProductWorkflows() ([]controlplane.WorkflowState, error) {
	return s.store.ListWorkflows()
}

func (s *ControlPlaneQueryService) ListProductAudits() ([]controlplane.AuditEvent, error) {
	return s.store.ListAudits()
}

func (s *ControlPlaneQueryService) ListProductApprovals() ([]controlplane.ApprovalDecision, error) {
	return s.store.ListAllApprovals()
}

func (s *ControlPlaneQueryService) GetProductProjectionSummary() (ProductProjectionSummary, error) {
	workflows, err := s.store.ListWorkflows()
	if err != nil {
		return ProductProjectionSummary{}, err
	}
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		return ProductProjectionSummary{}, err
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		return ProductProjectionSummary{}, err
	}
	l1l4Cards, err := BuildL1L4Cards()
	if err != nil {
		return ProductProjectionSummary{}, err
	}
	pendingDualReview := 0
	for _, workflow := range workflows {
		if workflow.State == "dual_review" || workflow.State == "dual_approval_pending" {
			pendingDualReview++
		}
	}
	return ProductProjectionSummary{
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

type ProductTriageQuery struct {
	LogType, EventType, PageName, AppVersion, NetworkClass, ErrorCode string
	VisitTargetType, VisitTargetKey                                   string
}

func (s *ControlPlaneQueryService) GetProductTriageSummary(
	ctx context.Context,
	query ProductTriageQuery,
) (ProductTriageSummary, error) {
	projectionSummary, err := s.GetProductProjectionSummary()
	if err != nil {
		return ProductTriageSummary{}, err
	}
	eventQuery := EventSummaryQuery{
		LogType:      strings.TrimSpace(query.LogType),
		EventType:    strings.TrimSpace(query.EventType),
		PageName:     strings.TrimSpace(query.PageName),
		AppVersion:   strings.TrimSpace(query.AppVersion),
		NetworkClass: strings.TrimSpace(query.NetworkClass),
		ErrorCode:    strings.TrimSpace(query.ErrorCode),
	}
	eventSummary, err := s.telemetry.GetEventSummary(ctx, eventQuery)
	if err != nil {
		return ProductTriageSummary{}, err
	}
	recentEvents, err := s.telemetry.GetEventDrilldown(ctx, EventDrilldownQuery{
		LogType:      eventQuery.LogType,
		EventType:    eventQuery.EventType,
		PageName:     eventQuery.PageName,
		AppVersion:   eventQuery.AppVersion,
		NetworkClass: eventQuery.NetworkClass,
		ErrorCode:    eventQuery.ErrorCode,
		From:         time.Now().UTC().Add(-15 * time.Minute),
		To:           time.Now().UTC(),
		Limit:        20,
	})
	if err != nil {
		return ProductTriageSummary{}, err
	}
	visitSummary, err := s.visits.GetVisitStats(ctx, visitapplication.VisitStatsQuery{
		TargetType: firstNonEmpty(strings.TrimSpace(query.VisitTargetType), "page"),
		TargetKey:  strings.TrimSpace(query.VisitTargetKey),
	})
	if err != nil {
		return ProductTriageSummary{}, err
	}
	recentItems := recentEvents.Items
	return ProductTriageSummary{
		ProjectionSummary: projectionSummary,
		EventSummary:      eventSummary,
		VisitSummary:      visitSummary,
		TopEventHotspots:  buildTopEventHotspots(eventSummary),
		RecentEvents:      recentItems,
		BacklogCandidates: buildProductBacklogCandidates(projectionSummary, eventSummary, visitSummary, recentItems),
		RuntimeReady:      projectionSummary.PendingDualReview == 0,
		Source:            "control-plane",
	}, nil
}

func buildTopEventHotspots(summary EventSummary) map[string][]DimensionCount {
	keys := []string{
		"logType",
		"eventType",
		"pageName",
		"appVersion",
		"networkClass",
		"deviceManufacturer",
		"deviceModel",
		"errorCode",
	}
	out := map[string][]DimensionCount{}
	for _, key := range keys {
		counter := summary.DimensionCounters[key]
		if len(counter) == 0 {
			continue
		}
		out[key] = topDimensionCounts(counter, 5)
	}
	return out
}

func topDimensionCounts(counter map[string]int, limit int) []DimensionCount {
	out := make([]DimensionCount, 0, len(counter))
	for value, count := range counter {
		out = append(out, DimensionCount{Value: value, Count: count})
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
	projectionSummary ProductProjectionSummary,
	eventSummary EventSummary,
	visitSummary visitapplication.VisitStats,
	recentEvents []EventDrilldownItem,
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

			RepairEntry: "/product/governance",
			AlertID:     "governance_dual_review_pending",
			AuditRoute:  "/audit",
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
			NextAction:     "检查 page_access / event 上报链路，补齐九字段公共信封与事件目录要求的强类型扩展。",
			DrilldownRoute: "/product/dashboard",

			RepairEntry: "/product/dashboard",
			AlertID:     "OpsEventUploadDrop",
			AuditRoute:  "/audit",
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

			RepairEntry: "/product/l1-l4/environment",
			AlertID:     "HighP95Latency",
			AuditRoute:  "/audit",
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

			RepairEntry: "/product/dashboard",
			AlertID:     "OpsEventUploadDrop",
			AuditRoute:  "/audit",
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

				RepairEntry: "/product/dashboard",
				AlertID:     "OpsEventUploadDrop",
				AuditRoute:  "/audit",
				Evidence: map[string]any{
					"missingFields": missingFields,
					"sampleRowKey":  recentEvents[0].RowKey,
				},
			})
		}
	}
	return controlplane.LimitBacklogCandidates(controlplane.SortBacklogCandidates(candidates), 5)
}

func missingProductEventDimensions(summary EventSummary) []string {
	candidateDimensions := []string{
		"logType",
		"eventType",
		"pageName",
		"appVersion",
		"networkClass",
		"deviceManufacturer",
		"deviceModel",
	}
	missing := make([]string, 0, len(candidateDimensions))
	for _, dimension := range candidateDimensions {
		if len(summary.DimensionCounters[dimension]) == 0 {
			missing = append(missing, dimension)
		}
	}
	return missing
}

func missingRecentEventFields(items []EventDrilldownItem) []string {
	fields := map[string]bool{}
	for _, item := range items {
		if strings.TrimSpace(item.LogType) == "" {
			fields["logType"] = true
		}
		if strings.TrimSpace(item.EventType) == "" {
			fields["eventType"] = true
		}
		if strings.TrimSpace(item.SessionID) == "" {
			fields["sessionId"] = true
		}
		if strings.TrimSpace(item.PageName) == "" {
			fields["pageName"] = true
		}
		if strings.TrimSpace(item.OccurredAt) == "" {
			fields["occurredAt"] = true
		}
		if strings.TrimSpace(item.DeviceManufacturer) == "" {
			fields["deviceManufacturer"] = true
		}
		if strings.TrimSpace(item.DeviceModel) == "" {
			fields["deviceModel"] = true
		}
		if strings.TrimSpace(item.AppVersion) == "" {
			fields["appVersion"] = true
		}
		if strings.TrimSpace(item.NetworkClass) == "" {
			fields["networkClass"] = true
		}
		if item.LogType == "error" && item.ErrorCode == nil {
			fields["errorCode"] = true
		}
	}
	out := make([]string, 0, len(fields))
	for field := range fields {
		out = append(out, field)
	}
	sort.Strings(out)
	return out
}
