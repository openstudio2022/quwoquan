package main

import (
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

type platformProjectionSummaryResponse struct {
	ApprovalCount int `json:"approvalCount"`
	AuditCount    int `json:"auditCount"`
	ActiveAlerts  int `json:"activeAlerts"`
}

type platformTriageSummaryResponse struct {
	Scope              controlplane.ConfigResolutionScope `json:"scope"`
	ProjectionSummary  platformProjectionSummaryResponse  `json:"projectionSummary"`
	ConfigDrift        controlplane.ConfigDriftSummary    `json:"configDrift"`
	ServiceDrift       []platformServiceDriftItem         `json:"serviceDrift"`
	OutOfSyncInstances []platformConfigInstanceDriftItem  `json:"outOfSyncInstances"`
	BacklogCandidates  []controlplane.BacklogCandidate    `json:"backlogCandidates"`
	RuntimeReady       bool                               `json:"runtimeReady"`
	Source             string                             `json:"source"`
}

// grayRoutingPolicyFile 是灰度 IaC 的只读 wire model。全局 dimensions 已退场；
// 所有消费者都只能按 rollout stage 读取 stageDimensions。
type grayRoutingPolicyFile struct {
	Policy grayRoutingPolicy `yaml:"policy" json:"policy"`
}

type grayRoutingPolicy struct {
	Enabled                           bool                                  `yaml:"enabled" json:"enabled"`
	GrayUpstream                      string                                `yaml:"grayUpstream" json:"grayUpstream"`
	GrayUpstreamTLSInsecureSkipVerify bool                                  `yaml:"grayUpstreamTlsInsecureSkipVerify" json:"grayUpstreamTlsInsecureSkipVerify"`
	StageDimensions                   map[string]grayRoutingStageDimensions `yaml:"stageDimensions" json:"stageDimensions"`
}

type grayRoutingStageDimensions struct {
	AppVersions []string `yaml:"appVersions" json:"appVersions"`
	UserIDs     []string `yaml:"userIds" json:"userIds"`
	Provinces   []string `yaml:"provinces" json:"provinces"`
	Carriers    []string `yaml:"carriers" json:"carriers"`
}

type grayRoutingPolicyResponse struct {
	Policy     grayRoutingPolicy `json:"policy"`
	SourcePath string            `json:"sourcePath"`
	RawYAML    string            `json:"rawYaml"`
}

func (s *platformService) buildProjectionSummary() (platformProjectionSummaryResponse, error) {
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	activeAlerts, err := s.countActiveAlerts()
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	return platformProjectionSummaryResponse{
		ApprovalCount: len(approvals),
		AuditCount:    len(audits),
		ActiveAlerts:  activeAlerts,
	}, nil
}

func (s *platformService) handleGetTriageSummary(w http.ResponseWriter, r *http.Request) {
	scope := controlplane.ConfigResolutionScope{
		Environment: strings.TrimSpace(r.URL.Query().Get("env")),
		Cluster:     strings.TrimSpace(r.URL.Query().Get("cluster")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
	}
	projectionSummary, err := s.buildProjectionSummary()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	filtered := filterConfigInstanceReports(reports, scope)
	drift := controlplane.SummarizeConfigDrift(filtered)
	serviceDrift := summarizeConfigDriftByService(filtered)
	outOfSyncInstances := collectOutOfSyncInstances(filtered, 8)
	writeJSON(w, http.StatusOK, platformTriageSummaryResponse{
		Scope:              scope,
		ProjectionSummary:  projectionSummary,
		ConfigDrift:        drift,
		ServiceDrift:       serviceDrift,
		OutOfSyncInstances: outOfSyncInstances,
		BacklogCandidates:  buildPlatformBacklogCandidates(scope, drift, serviceDrift, outOfSyncInstances),
		RuntimeReady:       drift.OutOfSyncInstances == 0,
		Source:             "control-plane",
	})
}

func buildPlatformBacklogCandidates(
	scope controlplane.ConfigResolutionScope,
	drift controlplane.ConfigDriftSummary,
	serviceDrift []platformServiceDriftItem,
	outOfSyncInstances []platformConfigInstanceDriftItem,
) []controlplane.BacklogCandidate {
	candidates := make([]controlplane.BacklogCandidate, 0, 4)
	scopeLabel := backlogScopeLabel(scope)
	if len(serviceDrift) > 0 && drift.OutOfSyncInstances > 0 {
		top := serviceDrift[0]
		severity := "warning"
		if top.OutOfSyncInstances >= 3 || drift.OutOfSyncInstances >= 5 {
			severity = "critical"
		}
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "platform-config-drift-" + sanitizeBacklogSegment(top.Service) + "-" + backlogScopeKey(scope),
			Category:       "config_drift",
			Severity:       severity,
			Title:          "修复 " + top.Service + " 的配置漂移",
			Summary:        "在 " + scopeLabel + " 下观察到 " + itoa(top.OutOfSyncInstances) + " 个 " + top.Service + " 实例与期望配置不一致。",
			Owner:          "platform-ops",
			NextAction:     "打开 /platform/config/drift 对比 desiredHash 与 effectiveHash，并推动实例重新对齐。",
			DrilldownRoute: "/platform/config/drift",
			RepairEntry:    "/platform/rollout",
			AlertID:        "config_release_error_rate",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"service":            top.Service,
				"totalInstances":     top.TotalInstances,
				"inSyncInstances":    top.InSyncInstances,
				"outOfSyncInstances": top.OutOfSyncInstances,
				"drift":              drift,
				"scope":              scope,
			},
		})
	}
	fallbackCount := 0
	for _, item := range outOfSyncInstances {
		if strings.TrimSpace(item.Source) == "disk-fallback" || strings.TrimSpace(item.LastError) != "" {
			fallbackCount++
		}
	}
	if fallbackCount > 0 {
		candidates = append(candidates, controlplane.BacklogCandidate{
			ID:             "platform-config-fallback-" + backlogScopeKey(scope),
			Category:       "config_recovery",
			Severity:       "warning",
			Title:          "回收实例磁盘回退链路",
			Summary:        "有 " + itoa(fallbackCount) + " 个实例依赖磁盘回退或携带最近错误，需要补齐在线控制面恢复链路。",
			Owner:          "platform-ops",
			NextAction:     "检查 /platform/config/drift 与实例上报，减少 disk-fallback 依赖。",
			DrilldownRoute: "/platform/config/drift",
			RepairEntry:    "/platform/rollout",
			AlertID:        "rollback_readiness",
			AuditRoute:     "/audit",
			Evidence: map[string]any{
				"fallbackCount": fallbackCount,
				"scope":         scope,
			},
		})
	}
	return controlplane.LimitBacklogCandidates(controlplane.SortBacklogCandidates(candidates), 5)
}

func backlogScopeKey(scope controlplane.ConfigResolutionScope) string {
	return sanitizeBacklogSegment(scope.Environment + "-" + scope.Cluster + "-" + scope.Service)
}

func backlogScopeLabel(scope controlplane.ConfigResolutionScope) string {
	parts := make([]string, 0, 3)
	for _, value := range []string{scope.Environment, scope.Cluster, scope.Service} {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			parts = append(parts, trimmed)
		}
	}
	if len(parts) == 0 {
		return "platform scope"
	}
	return strings.Join(parts, " / ")
}

func sanitizeBacklogSegment(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "all"
	}
	replacer := strings.NewReplacer("/", "-", " ", "-", "|", "-", ":", "-", "_", "-")
	return replacer.Replace(trimmed)
}

// handleGetGrayRoutingPolicy 只读返回灰度路由策略（IaC 真相源随发布包落盘）。
// 生产模式读 config-root/gray-routing/policy.yaml；开发/测试读仓库文件。
func (s *platformService) handleGetGrayRoutingPolicy(w http.ResponseWriter, r *http.Request) {
	candidates := []string{}
	if configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT")); configRoot != "" {
		candidates = append(candidates, filepath.Join(configRoot, "gray-routing", "policy.yaml"))
	}
	candidates = append(
		candidates,
		filepath.Join(s.repoRoot, "quwoquan_ops", "environments", "prod", "rollout", "routing_policy.yaml"),
	)
	for _, path := range candidates {
		raw, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var doc grayRoutingPolicyFile
		if err := s.readYAMLInto(path, &doc); err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		writeJSON(w, http.StatusOK, grayRoutingPolicyResponse{
			Policy:     doc.Policy,
			SourcePath: path,
			RawYAML:    string(raw),
		})
		return
	}
	writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "gray routing policy not found")
}

func (s *platformService) handleListReleases(w http.ResponseWriter, r *http.Request, _ string) {
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !isCanonicalSHA256(s.releaseManifestDigest) {
		writeJSON(w, http.StatusOK, map[string]any{"items": []map[string]any{}})
		return
	}

	type serviceCandidate struct {
		configVersion string
		updatedAt     string
		inSync        bool
	}
	services := map[string]serviceCandidate{}
	for _, report := range reports {
		if stringifyDocumentValue(report["releaseManifestDigest"]) != s.releaseManifestDigest {
			continue
		}
		service := strings.TrimSpace(stringifyDocumentValue(report["service"]))
		if service == "" {
			continue
		}
		candidate, alreadyReported := services[service]
		if alreadyReported {
			candidate.inSync = candidate.inSync && documentBool(report["inSync"])
		} else {
			candidate.inSync = documentBool(report["inSync"])
		}
		if candidate.configVersion == "" {
			candidate.configVersion = strings.TrimSpace(stringifyDocumentValue(report["configVersion"]))
		}
		if updatedAt := strings.TrimSpace(stringifyDocumentValue(report["updatedAt"])); updatedAt > candidate.updatedAt {
			candidate.updatedAt = updatedAt
		}
		services[service] = candidate
	}

	serviceNames := make([]string, 0, len(services))
	for service := range services {
		serviceNames = append(serviceNames, service)
	}
	sort.Strings(serviceNames)
	items := make([]map[string]any, 0, len(serviceNames))
	for _, service := range serviceNames {
		candidate := services[service]
		releaseState := "drift"
		if candidate.inSync {
			releaseState = "in_sync"
		}
		items = append(items, map[string]any{
			"releaseId":     s.releaseManifestDigest,
			"service":       service,
			"configVersion": candidate.configVersion,
			"releaseState":  releaseState,
			"updatedAt":     candidate.updatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
