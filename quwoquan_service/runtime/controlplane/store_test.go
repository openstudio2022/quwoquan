package controlplane

import (
	"path/filepath"
	"testing"
)

func TestFileStorePersistsDocumentsWorkflowAndAudit(t *testing.T) {
	store := NewFileStore(filepath.Join(t.TempDir(), "control-plane.json"))

	if err := store.PutDocument("experiments", "exp-1", Document{"id": "exp-1", "enabled": true}); err != nil {
		t.Fatalf("put document: %v", err)
	}
	if err := store.UpsertWorkflow(WorkflowState{
		ObjectType: "experiment",
		ObjectID:   "exp-1",
		WorkflowID: "experiment_rollout_v1",
		State:      "running",
		History: []WorkflowTransition{{
			From:   "review_pending",
			To:     "running",
			Action: "approve",
			Actor:  "ops-1",
		}},
	}); err != nil {
		t.Fatalf("upsert workflow: %v", err)
	}
	if err := store.AppendApproval(ApprovalDecision{
		ObjectType: "experiment",
		ObjectID:   "exp-1",
		Mode:       "single",
		Actor:      "ops-1",
		Decision:   "approved",
	}); err != nil {
		t.Fatalf("append approval: %v", err)
	}
	if err := store.AppendAudit(AuditEvent{
		AuditID:     "experiment_rollout_changed",
		ObjectType:  "experiment",
		ObjectID:    "exp-1",
		Action:      "rollout",
		DangerLevel: "high",
		Actor:       "ops-1",
		Environment: "beta",
		RequestID:   "req-1",
		TraceID:     "trace-1",
	}); err != nil {
		t.Fatalf("append audit: %v", err)
	}

	doc, ok, err := store.GetDocument("experiments", "exp-1")
	if err != nil || !ok {
		t.Fatalf("get document: ok=%v err=%v", ok, err)
	}
	if doc["enabled"] != true {
		t.Fatalf("unexpected doc: %#v", doc)
	}

	workflow, ok, err := store.GetWorkflow("experiment", "exp-1")
	if err != nil || !ok {
		t.Fatalf("get workflow: ok=%v err=%v", ok, err)
	}
	if workflow.State != "running" {
		t.Fatalf("unexpected workflow: %#v", workflow)
	}

	approvals, err := store.ListApprovals("experiment", "exp-1")
	if err != nil {
		t.Fatalf("list approvals: %v", err)
	}
	if len(approvals) != 1 || approvals[0].Decision != "approved" {
		t.Fatalf("unexpected approvals: %#v", approvals)
	}

	audits, err := store.ListAudits()
	if err != nil {
		t.Fatalf("list audits: %v", err)
	}
	if len(audits) != 1 || audits[0].AuditID != "experiment_rollout_changed" {
		t.Fatalf("unexpected audits: %#v", audits)
	}

	allApprovals, err := store.ListAllApprovals()
	if err != nil {
		t.Fatalf("list all approvals: %v", err)
	}
	if len(allApprovals) != 1 || allApprovals[0].ObjectID != "exp-1" {
		t.Fatalf("unexpected all approvals: %#v", allApprovals)
	}
}

func TestResolveEffectiveConfigStopsAtServiceLayers(t *testing.T) {
	configKeys := []Document{
		{"key": "sys.gateway.rate_limit.per_user_rps", "default": 30},
		{"key": "sys.orchestrator.downstream.timeout_ms", "default": 800},
	}
	configLayers := []Document{
		{
			"id":         "global:all",
			"scopeLevel": "global",
			"scopeID":    "all",
			"values": map[string]any{
				"sys.orchestrator.downstream.timeout_ms": 900,
			},
		},
		{
			"id":         "environment:beta",
			"scopeLevel": "environment",
			"scopeID":    "beta",
			"values": map[string]any{
				"sys.gateway.rate_limit.per_user_rps": 40,
			},
		},
		{
			"id":         "cluster:beta-control-a",
			"scopeLevel": "cluster",
			"scopeID":    "beta-control-a",
			"values": map[string]any{
				"sys.gateway.rate_limit.per_user_rps": 45,
			},
		},
		{
			"id":         "service:product-ops-service",
			"scopeLevel": "service",
			"scopeID":    "product-ops-service",
			"values": map[string]any{
				"sys.gateway.rate_limit.per_user_rps":    50,
				"sys.orchestrator.downstream.timeout_ms": 780,
			},
		},
		{
			"id":         "instance:product-ops-service-beta-control-a-0",
			"scopeLevel": "instance",
			"scopeID":    "product-ops-service-beta-control-a-0",
			"values": map[string]any{
				"sys.orchestrator.downstream.timeout_ms": 720,
			},
		},
	}

	items := ResolveEffectiveConfig(configLayers, configKeys, ConfigResolutionScope{
		Environment: "beta",
		Cluster:     "beta-control-a",
		Service:     "product-ops-service",
	})
	if len(items) != 2 {
		t.Fatalf("expected 2 config items, got %d", len(items))
	}

	byKey := map[string]ResolvedConfigValue{}
	for _, item := range items {
		byKey[item.Key] = item
	}
	if got := byKey["sys.gateway.rate_limit.per_user_rps"].Value; got != 50 {
		t.Fatalf("expected service layer to win, got %#v", got)
	}
	if byKey["sys.gateway.rate_limit.per_user_rps"].ScopeLevel != "service" {
		t.Fatalf("expected service scope level, got %s", byKey["sys.gateway.rate_limit.per_user_rps"].ScopeLevel)
	}
	if got := byKey["sys.orchestrator.downstream.timeout_ms"].Value; got != 780 {
		t.Fatalf("expected service layer to win, got %#v", got)
	}
	if byKey["sys.orchestrator.downstream.timeout_ms"].ScopeLevel != "service" {
		t.Fatalf("expected service scope level, got %s", byKey["sys.orchestrator.downstream.timeout_ms"].ScopeLevel)
	}
}

func TestDeleteDocumentRemovesEntry(t *testing.T) {
	store := NewFileStore(filepath.Join(t.TempDir(), "control-plane.json"))

	if err := store.PutDocument("config_layers", "instance:abc", Document{"id": "instance:abc", "scopeLevel": "instance"}); err != nil {
		t.Fatalf("put: %v", err)
	}
	if err := store.PutDocument("config_layers", "service:svc", Document{"id": "service:svc", "scopeLevel": "service"}); err != nil {
		t.Fatalf("put: %v", err)
	}

	if err := store.DeleteDocument("config_layers", "instance:abc"); err != nil {
		t.Fatalf("delete: %v", err)
	}

	items, err := store.ListDocuments("config_layers")
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 remaining, got %d", len(items))
	}
	if items[0]["id"] != "service:svc" {
		t.Fatalf("unexpected remaining doc: %v", items[0]["id"])
	}

	if err := store.DeleteDocument("config_layers", "nonexistent"); err != nil {
		t.Fatalf("delete nonexistent: %v", err)
	}
}

func TestHotConfigStoreApplyAndGet(t *testing.T) {
	store := NewHotConfigStore()

	resolved := []ResolvedConfigValue{
		{Key: "sys.gateway.rate_limit.per_user_rps", Value: 50.0, ScopeLevel: "service", ScopeID: "product-ops-service"},
		{Key: "sys.config_center.disk_fallback_enabled", Value: true, ScopeLevel: "environment", ScopeID: "beta"},
	}
	hash := store.Apply(resolved)
	if hash == "" {
		t.Fatal("apply returned empty hash")
	}
	if store.EffectiveHash() != hash {
		t.Fatalf("hash mismatch: %s vs %s", store.EffectiveHash(), hash)
	}

	if got := store.GetInt("sys.gateway.rate_limit.per_user_rps", 0); got != 50 {
		t.Fatalf("expected 50, got %d", got)
	}
	if got := store.GetBool("sys.config_center.disk_fallback_enabled", false); !got {
		t.Fatal("expected true, got false")
	}
	if got := store.GetInt("nonexistent", 99); got != 99 {
		t.Fatalf("expected fallback 99, got %d", got)
	}

	snapshot := store.Snapshot()
	if len(snapshot) != 2 {
		t.Fatalf("expected 2 items in snapshot, got %d", len(snapshot))
	}
}

func TestSummarizeConfigDriftCountsInstances(t *testing.T) {
	summary := SummarizeConfigDrift([]Document{
		{"id": "a", "inSync": true},
		{"id": "b", "inSync": false},
		{"id": "c", "inSync": false},
	})
	if summary.TotalInstances != 3 {
		t.Fatalf("expected total=3, got %d", summary.TotalInstances)
	}
	if summary.InSyncInstances != 1 {
		t.Fatalf("expected inSync=1, got %d", summary.InSyncInstances)
	}
	if summary.OutOfSyncInstances != 2 {
		t.Fatalf("expected outOfSync=2, got %d", summary.OutOfSyncInstances)
	}
}
