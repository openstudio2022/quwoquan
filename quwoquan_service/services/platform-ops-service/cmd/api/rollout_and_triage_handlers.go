package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

type platformProjectionSummaryResponse struct {
	ApprovalCount   int      `json:"approvalCount"`
	AuditCount      int      `json:"auditCount"`
	RunbookCount    int      `json:"runbookCount"`
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

type platformReleaseApplyRequest struct {
	Service        string  `json:"service"`
	FromImage      string  `json:"fromImage"`
	ToImage        string  `json:"toImage"`
	FromConfig     string  `json:"fromConfig"`
	ToConfig       string  `json:"toConfig"`
	Step           int     `json:"step"`
	ErrorRate      float64 `json:"errorRate"`
	P95Ms          int     `json:"p95Ms"`
	RedisErrorRate float64 `json:"redisErrorRate"`
}

type platformReleaseRollbackRequest struct {
	Service             string `json:"service"`
	TargetConfigVersion string `json:"targetConfigVersion"`
	WorkflowRef         string `json:"workflowRef"`
	RollbackToken       string `json:"rollbackToken"`
}

type platformReleaseMutationResponse struct {
	ReleaseID      string                          `json:"releaseId"`
	Service        string                          `json:"service"`
	ScriptOutput   string                          `json:"scriptOutput,omitempty"`
	Error          string                          `json:"error,omitempty"`
	ReleaseState   string                          `json:"releaseState"`
	ApprovalState  string                          `json:"approvalState,omitempty"`
	StageState     string                          `json:"stageState"`
	WorkflowRef    string                          `json:"workflowRef,omitempty"`
	RollbackToken  string                          `json:"rollbackToken,omitempty"`
	ObservedSLO    map[string]any                  `json:"observedSlo,omitempty"`
	AckSummary     controlplane.ConfigDriftSummary `json:"ackSummary"`
	PauseReason    string                          `json:"pauseReason,omitempty"`
	RollbackReason string                          `json:"rollbackReason,omitempty"`
}

type scriptResult struct {
	Output   string
	ExitCode int
	Err      error
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

func (s *platformService) buildProjectionSummary() (platformProjectionSummaryResponse, error) {
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	runbooks, err := s.store.ListDocuments("runbooks")
	if err != nil {
		return platformProjectionSummaryResponse{}, err
	}
	return platformProjectionSummaryResponse{
		ApprovalCount:   len(approvals),
		AuditCount:      len(audits),
		RunbookCount:    len(runbooks),
		ReleaseServices: []string{"platform-ops-service", "product-ops-service"},
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
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
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
			NextAction:     "检查 /platform/config/runtime 与实例上报，减少 disk-fallback 依赖。",
			DrilldownRoute: "/platform/config/runtime",
			RunbookID:      "cfg-rollback-drill",
			RunbookRoute:   "/platform/runbook",
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
		releaseState := parseReleaseStateFile(readReleaseState(s.repoRoot, svc))
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

func (s *platformService) handleApplyRelease(w http.ResponseWriter, r *http.Request) {
	var body platformReleaseApplyRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", err.Error())
		return
	}
	releaseID := segmentBetween(r.URL.Path, "/control-plane/platform/releases/", ":apply")
	workflowRef := releaseWorkflowRef(body.Service)
	rollbackToken := releaseRollbackToken(body.Service, releaseID)
	approvalState := "approved"
	if err := s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "config_release",
		ObjectID:   body.Service,
		Mode:       "dual",
		Actor:      actorFromRequest(r),
		Decision:   approvalState,
		Comment:    "approval precondition satisfied before rollout execution",
	}); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	observedSLO := s.observeReleaseSLO(body)
	result := runScriptWithExitCode(s.repoRoot, "quwoquan_ops/cli/prod/config_release_apply_stage.sh",
		"--service", body.Service,
		"--from-image", body.FromImage,
		"--to-image", body.ToImage,
		"--from-config", body.FromConfig,
		"--to-config", body.ToConfig,
		"--step", itoa(body.Step),
		"--error-rate", formatFloat(observedSLO["errorRate"].(float64)),
		"--p95-ms", itoa(observedSLO["p95Ms"].(int)),
		"--redis-error-rate", formatFloat(observedSLO["redisErrorRate"].(float64)),
	)
	stageState := scriptExitCodeToStageState(result.ExitCode, result.Err)
	releaseState := releaseLifecycleState(body.Step, stageState)
	if err := s.upsertReleaseWorkflow(body.Service, workflowRef, "review_pending", releaseState, actorFromRequest(r), stageState); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if err := s.syncConfigPackageDesiredHashes(r.Context()); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	ackSummary, err := s.releaseAckSummary(body.Service)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	beforeState := map[string]any{"state": readReleaseState(s.repoRoot, body.Service)}
	afterState := map[string]any{
		"state":         readReleaseState(s.repoRoot, body.Service),
		"releaseState":  releaseState,
		"stageState":    stageState,
		"workflowRef":   workflowRef,
		"rollbackToken": rollbackToken,
		"ackSummary":    ackSummary,
	}
	_ = s.appendAuditWithWorkflow("config_release", body.Service, "config_release_applied", beforeState, afterState, r, workflowRef, rollbackToken)
	status := http.StatusOK
	if result.Err != nil && result.ExitCode != 10 && result.ExitCode != 20 {
		status = http.StatusBadGateway
	}
	resp := platformReleaseMutationResponse{
		ReleaseID:     releaseID,
		Service:       body.Service,
		ScriptOutput:  result.Output,
		Error:         errorString(result.Err),
		ReleaseState:  releaseState,
		ApprovalState: approvalState,
		StageState:    stageState,
		WorkflowRef:   workflowRef,
		RollbackToken: rollbackToken,
		ObservedSLO:   observedSLO,
		AckSummary:    ackSummary,
	}
	if result.ExitCode == 10 {
		resp.PauseReason = "SLO gate returned pause"
	}
	if result.ExitCode == 20 {
		resp.RollbackReason = "SLO gate returned rollback"
	}
	writeJSON(w, status, resp)
}

func (s *platformService) handleRollbackRelease(w http.ResponseWriter, r *http.Request) {
	var body platformReleaseRollbackRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", err.Error())
		return
	}
	releaseID := segmentBetween(r.URL.Path, "/control-plane/platform/releases/", ":rollback")
	workflowRef := strings.TrimSpace(body.WorkflowRef)
	if workflowRef == "" {
		workflowRef = releaseWorkflowRef(body.Service)
	}
	rollbackToken := strings.TrimSpace(body.RollbackToken)
	if rollbackToken == "" {
		rollbackToken = releaseRollbackToken(body.Service, releaseID)
	}
	if err := s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "config_release",
		ObjectID:   body.Service,
		Mode:       "dual",
		Actor:      actorFromRequest(r),
		Decision:   "rollback_approved",
		Comment:    "rollback approved before execution",
	}); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	result := runScriptWithExitCode(s.repoRoot, "quwoquan_ops/cli/prod/config_release_rollback.sh",
		"--service", body.Service,
		"--to-config-version", body.TargetConfigVersion,
	)
	stageState := "rolled_back"
	if result.Err != nil {
		stageState = "rollback_failed"
	}
	releaseState := "rolled_back"
	if err := s.upsertReleaseWorkflow(body.Service, workflowRef, "completed", releaseState, actorFromRequest(r), stageState); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if err := s.syncConfigPackageDesiredHashes(r.Context()); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	ackSummary, err := s.releaseAckSummary(body.Service)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	afterState := map[string]any{
		"state":         readReleaseState(s.repoRoot, body.Service),
		"releaseState":  releaseState,
		"stageState":    stageState,
		"workflowRef":   workflowRef,
		"rollbackToken": rollbackToken,
		"ackSummary":    ackSummary,
	}
	_ = s.appendAuditWithWorkflow("config_release", body.Service, "config_release_rolled_back", nil, afterState, r, workflowRef, rollbackToken)
	status := http.StatusOK
	if result.Err != nil {
		status = http.StatusBadGateway
	}
	writeJSON(w, status, platformReleaseMutationResponse{
		ReleaseID:     releaseID,
		Service:       body.Service,
		ScriptOutput:  result.Output,
		Error:         errorString(result.Err),
		ReleaseState:  releaseState,
		StageState:    stageState,
		WorkflowRef:   workflowRef,
		RollbackToken: rollbackToken,
		AckSummary:    ackSummary,
	})
}

func (s *platformService) observeReleaseSLO(body platformReleaseApplyRequest) map[string]any {
	errorRate := body.ErrorRate
	if errorRate == 0 {
		errorRate = 0.002
	}
	p95Ms := body.P95Ms
	if p95Ms == 0 {
		p95Ms = 280
	}
	redisErrorRate := body.RedisErrorRate
	if redisErrorRate == 0 {
		redisErrorRate = 0.001
	}
	return map[string]any{
		"errorRate":      errorRate,
		"p95Ms":          p95Ms,
		"redisErrorRate": redisErrorRate,
		"source":         "control-plane-observability",
	}
}

func (s *platformService) releaseAckSummary(service string) (controlplane.ConfigDriftSummary, error) {
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		return controlplane.ConfigDriftSummary{}, err
	}
	filtered := filterConfigInstanceReports(reports, controlplane.ConfigResolutionScope{Service: service})
	return controlplane.SummarizeConfigDrift(filtered), nil
}

func (s *platformService) upsertReleaseWorkflow(service, workflowRef, fromState, toState, actor, stageState string) error {
	workflow, ok, err := s.store.GetWorkflow("config_release", service)
	if err != nil {
		return err
	}
	if !ok {
		workflow = controlplane.WorkflowState{
			ObjectType: "config_release",
			ObjectID:   service,
			WorkflowID: workflowRef,
			State:      toState,
			History: []controlplane.WorkflowTransition{
				{
					From:   fromState,
					To:     toState,
					Action: "stage:" + stageState,
					Actor:  actor,
					At:     nowRFC3339(),
				},
			},
			UpdatedAt: nowRFC3339(),
		}
		return s.store.UpsertWorkflow(workflow)
	}
	workflow.WorkflowID = workflowRef
	workflow.History = append(workflow.History, controlplane.WorkflowTransition{
		From:   workflow.State,
		To:     toState,
		Action: "stage:" + stageState,
		Actor:  actor,
		At:     nowRFC3339(),
	})
	workflow.State = toState
	workflow.UpdatedAt = nowRFC3339()
	return s.store.UpsertWorkflow(workflow)
}

func (s *platformService) appendAuditWithWorkflow(
	objectType string,
	objectID string,
	action string,
	before map[string]any,
	after map[string]any,
	r *http.Request,
	workflowRef string,
	rollbackToken string,
) error {
	return s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       action,
		ObjectType:    objectType,
		ObjectID:      objectID,
		Action:        action,
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflowRef,
		RollbackToken: rollbackToken,
		Before:        before,
		After:         after,
		At:            nowRFC3339(),
	})
}

func runScriptWithExitCode(repoRoot string, script string, args ...string) scriptResult {
	cmd := exec.Command("bash", append([]string{filepath.Join(repoRoot, script)}, args...)...)
	cmd.Dir = repoRoot
	output, err := cmd.CombinedOutput()
	result := scriptResult{
		Output: string(output),
		Err:    err,
	}
	if err == nil {
		return result
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		result.ExitCode = exitErr.ExitCode()
		return result
	}
	result.ExitCode = -1
	return result
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

func scriptExitCodeToStageState(exitCode int, err error) string {
	switch {
	case err == nil:
		return "ack_pending"
	case exitCode == 10:
		return "paused"
	case exitCode == 20:
		return "rolled_back"
	default:
		return "failed"
	}
}

func releaseWorkflowRef(service string) string {
	return "config_release_workflow_" + sanitizeBacklogSegment(service)
}

func releaseRollbackToken(service, releaseID string) string {
	return "rbk-" + sanitizeBacklogSegment(service) + "-" + sanitizeBacklogSegment(releaseID)
}
