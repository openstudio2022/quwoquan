package main

import (
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

type platformProjectionSummaryResponse struct {
	ApprovalCount   int      `json:"approvalCount"`
	AuditCount      int      `json:"auditCount"`
	ActiveAlerts    int      `json:"activeAlerts"`
	ReleaseServices []string `json:"releaseServices"`
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

type releaseStateFile struct {
	Service    string
	FromImage  string
	ToImage    string
	FromConfig string
	ToConfig   string
	Step       int
	UpdatedAt  string
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
		ApprovalCount:   len(approvals),
		AuditCount:      len(audits),
		ActiveAlerts:    activeAlerts,
		ReleaseServices: []string{"prod-stack"},
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
		filepath.Join(s.repoRoot, "quwoquan_ops", "environments", "gray_routing_policy.yaml"),
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

func (s *platformService) handleListReleases(w http.ResponseWriter, service string) {
	base := filepath.Join(s.repoRoot, "quwoquan_service", "services")
	items := make([]map[string]any, 0)
	services := []string{}
	if strings.TrimSpace(service) != "" {
		services = append(services, strings.TrimSpace(service))
	} else {
		entries, _ := os.ReadDir(base)
		for _, entry := range entries {
			if entry.IsDir() {
				services = append(services, entry.Name())
			}
		}
	}
	sort.Strings(services)
	for _, svc := range services {
		pattern := filepath.Join(base, svc, "configs", "releases", "v*.yaml")
		files, _ := filepath.Glob(pattern)
		sort.Strings(files)
		releaseState := parseReleaseStateFile(readReleaseState(s.repoRoot, "prod-stack"))
		for index, file := range files {
			releaseID := strings.TrimSuffix(filepath.Base(file), ".yaml")
			fromConfig := ""
			if releaseState.FromConfig != "" {
				fromConfig = releaseState.FromConfig
			} else if index > 0 {
				fromConfig = strings.TrimSuffix(filepath.Base(files[index-1]), ".yaml")
			}
			items = append(items, map[string]any{
				"releaseId":     releaseID,
				"service":       svc,
				"configPath":    file,
				"grayStages":    []int{5, 25, 50, 100},
				"releaseState":  releaseLifecycleState(releaseState.Step, ""),
				"stageState":    releaseStageState(releaseState.Step, ""),
				"fromConfig":    fromConfig,
				"toConfig":      releaseID,
				"currentStage":  releaseState.Step,
				"updatedAt":     releaseState.UpdatedAt,
				"workflowRef":   releaseWorkflowRef(svc),
				"rollbackToken": releaseRollbackToken(svc, releaseID),
			})
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func parseReleaseStateFile(raw string) releaseStateFile {
	out := releaseStateFile{}
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		switch key {
		case "service":
			out.Service = value
		case "from_image":
			out.FromImage = value
		case "to_image":
			out.ToImage = value
		case "from_config":
			out.FromConfig = value
		case "to_config":
			out.ToConfig = value
		case "step":
			parsed, _ := strconv.Atoi(value)
			out.Step = parsed
		case "updated_at":
			out.UpdatedAt = value
		}
	}
	return out
}

func releaseLifecycleState(step int, stageState string) string {
	switch stageState {
	case "paused":
		return "paused"
	case "rolled_back":
		return "rolled_back"
	case "rollback_failed":
		return "failed"
	}
	switch {
	case step >= 100:
		return "completed"
	case step > 0:
		return "rolling_out"
	default:
		return "ready"
	}
}

func releaseStageState(step int, stageState string) string {
	if strings.TrimSpace(stageState) != "" {
		return stageState
	}
	if step <= 0 {
		return "pending"
	}
	return "rolling_" + itoa(step)
}

func releaseWorkflowRef(service string) string {
	return "config_release_workflow_" + sanitizeBacklogSegment(service)
}

func releaseRollbackToken(service, releaseID string) string {
	return "rbk-" + sanitizeBacklogSegment(service) + "-" + sanitizeBacklogSegment(releaseID)
}
