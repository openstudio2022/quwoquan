package application

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
)

// configReportStaleThreshold 判定实例配置上报失联：同步周期默认 30s，超过
// 该阈值仍无新上报的实例，其 inSync 声明不再可信，单独归入 stale 分类。
const configReportStaleThreshold = 10 * time.Minute

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
	UpdatedAt     string `json:"updatedAt,omitempty"`
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
	StaleInstances     []ConfigInstanceDriftItem          `json:"staleInstances"`
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
	fresh, staleReports := splitByReportFreshness(filtered, facade.now())
	drift := controlplane.SummarizeConfigDrift(fresh)
	drift.StaleInstances = len(staleReports)
	drift.TotalInstances = len(filtered)
	serviceDrift := summarizeDriftByService(fresh)
	outOfSync := collectDriftItems(fresh, 8, func(report controlplane.Document) bool {
		return !boolValue(report["inSync"])
	})
	stale := collectDriftItems(staleReports, 8, nil)
	return TriageSummary{
		Scope: scope, ProjectionSummary: projection, ConfigDrift: drift,
		ServiceDrift: serviceDrift, OutOfSyncInstances: outOfSync,
		StaleInstances:    stale,
		BacklogCandidates: buildBacklogCandidates(scope, drift, serviceDrift, outOfSync, stale),
		RuntimeReady:      drift.OutOfSyncInstances == 0 && drift.StaleInstances == 0,
		Source:            "control-plane",
	}, nil
}

// splitByReportFreshness 按上报新鲜度分流：updatedAt 缺失、不可解析或距 now
// 超过 configReportStaleThreshold 的实例归入 stale——它们无法证明当前收敛
// 状态，其 inSync 声明不参与 in-sync/out-of-sync 计数。恰好等于阈值仍算新鲜。
func splitByReportFreshness(
	reports []controlplane.Document,
	now time.Time,
) (fresh []controlplane.Document, stale []controlplane.Document) {
	fresh = make([]controlplane.Document, 0, len(reports))
	stale = make([]controlplane.Document, 0)
	for _, report := range reports {
		updatedAt, err := time.Parse(time.RFC3339, stringValue(report["updatedAt"]))
		if err != nil || now.Sub(updatedAt) > configReportStaleThreshold {
			stale = append(stale, report)
			continue
		}
		fresh = append(fresh, report)
	}
	return fresh, stale
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

// collectDriftItems 把 report 文档投影为 typed slice：filter 为 nil 时全收，
// 统一按 service/cluster/instanceId 排序并截断到 limit。
func collectDriftItems(
	reports []controlplane.Document,
	limit int,
	filter func(controlplane.Document) bool,
) []ConfigInstanceDriftItem {
	items := make([]ConfigInstanceDriftItem, 0, len(reports))
	for _, report := range reports {
		if filter != nil && !filter(report) {
			continue
		}
		items = append(items, ConfigInstanceDriftItem{
			ID: stringValue(report["id"]), Environment: stringValue(report["environment"]),
			Cluster: stringValue(report["cluster"]), Service: stringValue(report["service"]),
			InstanceID: stringValue(report["instanceId"]), DesiredHash: stringValue(report["desiredHash"]),
			EffectiveHash: stringValue(report["effectiveHash"]), Source: stringValue(report["source"]),
			LastError: stringValue(report["lastError"]), UpdatedAt: stringValue(report["updatedAt"]),
			InSync: boolValue(report["inSync"]),
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
	stale []ConfigInstanceDriftItem,
) []controlplane.BacklogCandidate {
	candidates := make([]controlplane.BacklogCandidate, 0, 4)
	if drift.StaleInstances > 0 {
		severity := "warning"
		if drift.StaleInstances >= 3 {
			severity = "critical"
		}
		staleServices := make([]string, 0, len(stale))
		seenServices := map[string]bool{}
		for _, item := range stale {
			if !seenServices[item.Service] {
				seenServices[item.Service] = true
				staleServices = append(staleServices, item.Service)
			}
		}
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:       "platform-config-staleness-" + scopeKey(scope),
			Category: "config_staleness", Severity: severity,
			Title:   "恢复失联实例的配置上报",
			Summary: "在 " + scopeLabel(scope) + " 下有 " + strconv.Itoa(drift.StaleInstances) + " 个实例超过 " + configReportStaleThreshold.String() + " 未上报配置状态，收敛结论不可信。",
			Owner:   "platform-ops", NextAction: "检查实例存活与 PLATFORM_OPS_BASE_URL 连通性，恢复 config sync 循环。",
			DrilldownRoute: "/platform/config/drift", RepairEntry: "/platform/rollout",
			AlertID: "config_release_error_rate", AuditRoute: "/audit",
			Evidence: map[string]any{"staleInstances": drift.StaleInstances,
				"staleServices": staleServices, "scope": scope},
		})
	}
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
