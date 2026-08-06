package application

import (
	"context"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

type ProjectionSummary struct {
	ApprovalCount int `json:"approvalCount"`
	AuditCount    int `json:"auditCount"`
	ActiveAlerts  int `json:"activeAlerts"`
}

type ConfigInstanceDriftItem struct {
	ID            string `json:"id"`
	Environment   string `json:"environment"`
	Cluster       string `json:"cluster"`
	Service       string `json:"service"`
	InstanceID    string `json:"instanceId"`
	DesiredHash   string `json:"desiredHash,omitempty"`
	EffectiveHash string `json:"effectiveHash,omitempty"`
	Source        string `json:"source,omitempty"`
	LastError     string `json:"lastError,omitempty"`
	InSync        bool   `json:"inSync"`
}

type ServiceDriftItem struct {
	Service            string `json:"service"`
	TotalInstances     int    `json:"totalInstances"`
	InSyncInstances    int    `json:"inSyncInstances"`
	OutOfSyncInstances int    `json:"outOfSyncInstances"`
}

type TriageSummary struct {
	Scope              controlplane.ConfigResolutionScope `json:"scope"`
	ProjectionSummary  ProjectionSummary                  `json:"projectionSummary"`
	ConfigDrift        controlplane.ConfigDriftSummary    `json:"configDrift"`
	ServiceDrift       []ServiceDriftItem                 `json:"serviceDrift"`
	OutOfSyncInstances []ConfigInstanceDriftItem          `json:"outOfSyncInstances"`
	BacklogCandidates  []controlplane.BacklogCandidate    `json:"backlogCandidates"`
	RuntimeReady       bool                               `json:"runtimeReady"`
	Source             string                             `json:"source"`
}

func (facade *RuntimeFacade) GetProjectionSummary(
	context.Context,
) (ProjectionSummary, error) {
	approvals, err := facade.store.ListAllApprovals()
	if err != nil {
		return ProjectionSummary{}, err
	}
	audits, err := facade.store.ListAudits()
	if err != nil {
		return ProjectionSummary{}, err
	}
	alerts, err := facade.store.ListDocuments(activeAlertsNamespace)
	if err != nil {
		return ProjectionSummary{}, err
	}
	active := 0
	for _, alert := range alerts {
		if status := stringValue(alert["status"]); status == "firing" || status == "acknowledged" {
			active++
		}
	}
	return ProjectionSummary{ApprovalCount: len(approvals), AuditCount: len(audits), ActiveAlerts: active}, nil
}

func (facade *RuntimeFacade) GetTriageSummary(
	ctx context.Context,
	scope controlplane.ConfigResolutionScope,
) (TriageSummary, error) {
	projection, err := facade.GetProjectionSummary(ctx)
	if err != nil {
		return TriageSummary{}, err
	}
	reports, err := facade.store.ListDocuments("config_instance_reports")
	if err != nil {
		return TriageSummary{}, err
	}
	filtered := filterReports(reports, scope)
	drift := controlplane.SummarizeConfigDrift(filtered)
	serviceDrift := summarizeDriftByService(filtered)
	outOfSync := collectOutOfSync(filtered, 8)
	return TriageSummary{
		Scope: scope, ProjectionSummary: projection, ConfigDrift: drift,
		ServiceDrift: serviceDrift, OutOfSyncInstances: outOfSync,
		BacklogCandidates: buildBacklogCandidates(scope, drift, serviceDrift, outOfSync),
		RuntimeReady:      drift.OutOfSyncInstances == 0,
		Source:            "control-plane",
	}, nil
}

func filterReports(
	reports []controlplane.Document,
	scope controlplane.ConfigResolutionScope,
) []controlplane.Document {
	filtered := make([]controlplane.Document, 0, len(reports))
	for _, item := range reports {
		if scope.Environment != "" && stringValue(item["environment"]) != scope.Environment {
			continue
		}
		if scope.Cluster != "" && stringValue(item["cluster"]) != scope.Cluster {
			continue
		}
		if scope.Service != "" && stringValue(item["service"]) != scope.Service {
			continue
		}
		filtered = append(filtered, item)
	}
	return filtered
}

func summarizeDriftByService(reports []controlplane.Document) []ServiceDriftItem {
	type aggregate struct{ total, inSync, outOfSync int }
	aggregates := map[string]*aggregate{}
	for _, report := range reports {
		service := stringValue(report["service"])
		if service == "" {
			service = "unknown"
		}
		item := aggregates[service]
		if item == nil {
			item = &aggregate{}
			aggregates[service] = item
		}
		item.total++
		if boolValue(report["inSync"]) {
			item.inSync++
		} else {
			item.outOfSync++
		}
	}
	items := make([]ServiceDriftItem, 0, len(aggregates))
	for service, aggregate := range aggregates {
		items = append(items, ServiceDriftItem{
			Service: service, TotalInstances: aggregate.total,
			InSyncInstances: aggregate.inSync, OutOfSyncInstances: aggregate.outOfSync,
		})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].OutOfSyncInstances == items[j].OutOfSyncInstances {
			return items[i].Service < items[j].Service
		}
		return items[i].OutOfSyncInstances > items[j].OutOfSyncInstances
	})
	return items
}

func collectOutOfSync(reports []controlplane.Document, limit int) []ConfigInstanceDriftItem {
	items := make([]ConfigInstanceDriftItem, 0, len(reports))
	for _, report := range reports {
		if boolValue(report["inSync"]) {
			continue
		}
		items = append(items, ConfigInstanceDriftItem{
			ID: stringValue(report["id"]), Environment: stringValue(report["environment"]),
			Cluster: stringValue(report["cluster"]), Service: stringValue(report["service"]),
			InstanceID: stringValue(report["instanceId"]), DesiredHash: stringValue(report["desiredHash"]),
			EffectiveHash: stringValue(report["effectiveHash"]), Source: stringValue(report["source"]),
			LastError: stringValue(report["lastError"]), InSync: boolValue(report["inSync"]),
		})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].Service != items[j].Service {
			return items[i].Service < items[j].Service
		}
		if items[i].Cluster != items[j].Cluster {
			return items[i].Cluster < items[j].Cluster
		}
		return items[i].InstanceID < items[j].InstanceID
	})
	if limit > 0 && len(items) > limit {
		return items[:limit]
	}
	return items
}

func buildBacklogCandidates(
	scope controlplane.ConfigResolutionScope,
	drift controlplane.ConfigDriftSummary,
	serviceDrift []ServiceDriftItem,
	outOfSync []ConfigInstanceDriftItem,
) []controlplane.BacklogCandidate {
	candidates := make([]controlplane.BacklogCandidate, 0, 4)
	if len(serviceDrift) > 0 && drift.OutOfSyncInstances > 0 {
		top := serviceDrift[0]
		severity := "warning"
		if top.OutOfSyncInstances >= 3 || drift.OutOfSyncInstances >= 5 {
			severity = "critical"
		}
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:       "platform-config-drift-" + sanitizeSegment(top.Service) + "-" + scopeKey(scope),
			Category: "config_drift", Severity: severity,
			Title:   "修复 " + top.Service + " 的配置漂移",
			Summary: "在 " + scopeLabel(scope) + " 下观察到 " + strconv.Itoa(top.OutOfSyncInstances) + " 个 " + top.Service + " 实例与期望配置不一致。",
			Owner:   "platform-ops", NextAction: "打开 /platform/config/drift 对比 desiredHash 与 effectiveHash，并推动实例重新对齐。",
			DrilldownRoute: "/platform/config/drift", RepairEntry: "/platform/rollout",
			AlertID: "config_release_error_rate", AuditRoute: "/audit",
			Evidence: map[string]any{"service": top.Service, "totalInstances": top.TotalInstances,
				"inSyncInstances": top.InSyncInstances, "outOfSyncInstances": top.OutOfSyncInstances,
				"drift": drift, "scope": scope},
		})
	}
	fallbackCount := 0
	for _, item := range outOfSync {
		if strings.TrimSpace(item.Source) == "disk-fallback" || strings.TrimSpace(item.LastError) != "" {
			fallbackCount++
		}
	}
	if fallbackCount > 0 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID: "platform-config-fallback-" + scopeKey(scope), Category: "config_recovery",
			Severity: "warning", Title: "回收实例磁盘回退链路",
			Summary: "有 " + strconv.Itoa(fallbackCount) + " 个实例依赖磁盘回退或携带最近错误，需要补齐在线控制面恢复链路。",
			Owner:   "platform-ops", NextAction: "检查 /platform/config/drift 与实例上报，减少 disk-fallback 依赖。",
			DrilldownRoute: "/platform/config/drift", RepairEntry: "/platform/rollout",
			AlertID: "rollback_readiness", AuditRoute: "/audit",
			Evidence: map[string]any{"fallbackCount": fallbackCount, "scope": scope},
		})
	}
	return controlplane.LimitBacklogCandidates(controlplane.SortBacklogCandidates(candidates), 5)
}

func scopeKey(scope controlplane.ConfigResolutionScope) string {
	return sanitizeSegment(scope.Environment + "-" + scope.Cluster + "-" + scope.Service)
}

func scopeLabel(scope controlplane.ConfigResolutionScope) string {
	parts := make([]string, 0, 3)
	for _, value := range []string{scope.Environment, scope.Cluster, scope.Service} {
		if value = strings.TrimSpace(value); value != "" {
			parts = append(parts, value)
		}
	}
	if len(parts) == 0 {
		return "platform scope"
	}
	return strings.Join(parts, " / ")
}

func sanitizeSegment(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "all"
	}
	return strings.NewReplacer("/", "-", " ", "-", "|", "-", ":", "-", "_", "-").Replace(value)
}
