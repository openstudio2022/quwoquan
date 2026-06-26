package main

import (
	"encoding/json"
	"net/http"
	"sort"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

func (s *productService) handleGetBucket(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/bucket")
	subjectKey := strings.TrimSpace(r.URL.Query().Get("subjectKey"))
	if subjectKey == "" {
		subjectKey = "anonymous"
	}
	result, err := s.resolveExperimentAssignment(experimentID, subjectKey)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *productService) handleAssignBucket(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/assign")
	var body struct {
		SubjectKey string `json:"subjectKey"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	subjectKey := strings.TrimSpace(body.SubjectKey)
	if subjectKey == "" {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "subjectKey is required")
		return
	}
	result, err := s.resolveExperimentAssignment(experimentID, subjectKey)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *productService) handleGetStats(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/stats")
	experiment, ok, err := s.getExperiment(experimentID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "experiment not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"experimentId":     experiment.ID,
		"policyVersion":    experiment.PolicyVersion,
		"enabled":          experiment.Enabled,
		"bucketStats":      experiment.BucketStats,
		"assignedSubjects": len(experiment.Assignments),
	})
}

func (s *productService) handleGetL1L4Metrics(w http.ResponseWriter, r *http.Request) {
	environment := strings.TrimSpace(r.URL.Query().Get("env"))
	cluster := strings.TrimSpace(r.URL.Query().Get("cluster"))
	serviceName := strings.TrimSpace(r.URL.Query().Get("service"))
	instanceID := strings.TrimSpace(r.URL.Query().Get("instance"))
	level := strings.TrimSpace(r.URL.Query().Get("level"))

	items, err := s.store.ListDocuments("l1l4_metric_snapshots")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}

	out := make([]metricSnapshot, 0, len(items))
	for _, item := range items {
		snapshot, err := decodeDocument[metricSnapshot](item)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		if environment != "" && snapshot.Environment != environment {
			continue
		}
		if level != "" && snapshot.Level != level {
			continue
		}
		isInfraLevel := snapshot.Level == "L3" || snapshot.Level == "L4"
		if cluster != "" && isInfraLevel && snapshot.Cluster != cluster {
			continue
		}
		if serviceName != "" && isInfraLevel && snapshot.Service != serviceName {
			continue
		}
		if instanceID != "" && isInfraLevel && snapshot.InstanceID != instanceID {
			continue
		}
		out = append(out, snapshot)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Level == out[j].Level {
			return out[i].ID < out[j].ID
		}
		return out[i].Level < out[j].Level
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"scope": map[string]any{
			"env":      environment,
			"cluster":  cluster,
			"service":  serviceName,
			"instance": instanceID,
			"level":    level,
		},
		"items": out,
	})
}

func (s *productService) handleListExperiments(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("experiments")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		experiment, err := decodeDocument[experimentDef](item)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		out = append(out, map[string]any{
			"id":               experiment.ID,
			"name":             experiment.Name,
			"enabled":          experiment.Enabled,
			"policyVersion":    experiment.PolicyVersion,
			"buckets":          experiment.Buckets,
			"bucketStats":      experiment.BucketStats,
			"assignedSubjects": len(experiment.Assignments),
		})
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i]["id"].(string) < out[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

func (s *productService) handleRollout(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/control-plane/product/experiments/", ":rollout")
	var body struct {
		Enabled bool        `json:"enabled"`
		Buckets []bucketDef `json:"buckets"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)

	experiment, ok, err := s.getExperiment(experimentID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "experiment not found")
		return
	}
	before := documentFromStruct(experiment)
	experiment.Enabled = body.Enabled
	if len(body.Buckets) > 0 {
		experiment.Buckets = body.Buckets
		experiment.PolicyVersion = experiment.PolicyVersion + "+rollout"
		experiment.BucketStats = map[string]int{}
		experiment.Assignments = map[string]assignment{}
	}
	if err := s.putDocument("experiments", experiment.ID, experiment); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "experiment",
		ObjectID:   experiment.ID,
		WorkflowID: "experiment_rollout_v1",
		State:      "ramping",
		History: []controlplane.WorkflowTransition{{
			From:   "running",
			To:     "ramping",
			Action: "rollout",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "experiment",
		ObjectID:   experiment.ID,
		Mode:       "single",
		Actor:      actorFromRequest(r),
		Decision:   "approved",
	})
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       "experiment_rollout_changed",
		ObjectType:    "experiment",
		ObjectID:      experiment.ID,
		Action:        "rollout",
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: "rbk-" + experiment.ID,
		Before:        before,
		After:         documentFromStruct(experiment),
		Metadata:      map[string]any{"bucketCount": len(experiment.Buckets)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"id":            experiment.ID,
		"enabled":       experiment.Enabled,
		"policyVersion": experiment.PolicyVersion,
		"buckets":       experiment.Buckets,
	})
}
