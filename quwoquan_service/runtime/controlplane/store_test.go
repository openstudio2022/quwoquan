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
		Environment: "integration",
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
