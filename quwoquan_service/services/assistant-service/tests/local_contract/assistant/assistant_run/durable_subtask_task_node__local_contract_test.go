// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
package assistant_run_test

import (
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

const durableTaskNodeInputDigest = "sha256:3b036068de14106df50accc8d115f950182c8237c61a81076efa1bf26e86d190"

func TestDurableSubtaskTaskNodePersistsClaimHeartbeatAndTerminalReceipt(
	t *testing.T,
) {
	now := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	run := durableSubtaskAggregate(generated.AssistantTaskStatusRunning)
	claim, terminal, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-a",
		30*time.Second,
		now,
	)
	if err != nil || terminal != nil {
		t.Fatalf("ClaimDurableSubtask() claim=%#v terminal=%#v err=%v", claim, terminal, err)
	}
	if claim.Attempt != 1 || claim.FencingToken != 1 ||
		claim.InputDigest != durableTaskNodeInputDigest ||
		claim.IdempotencyKey == "" {
		t.Fatalf("claim is incomplete: %#v", claim)
	}
	updated, err := run.HeartbeatDurableSubtask(
		claim,
		30*time.Second,
		now.Add(5*time.Second),
	)
	if err != nil || !updated.LeaseExpiresAt.After(claim.LeaseExpiresAt) {
		t.Fatalf("HeartbeatDurableSubtask() claim=%#v err=%v", updated, err)
	}
	receipt, err := run.FinishDurableSubtask(
		updated,
		runruntime.DurableSubtaskResult{
			Outcome: "completed",
			Summary: "路线证据已收敛",
			Payload: map[string]any{
				"finalText":      "路线证据已收敛",
				"referenceCount": 2,
			},
			ArtifactRefs: []string{"evidence:route-2", "evidence:route-1"},
		},
		now.Add(6*time.Second),
	)
	if err != nil {
		t.Fatalf("FinishDurableSubtask() error=%v", err)
	}
	if receipt.Outcome != "completed" || receipt.ReceiptRef == "" ||
		receipt.ReceiptRef != receipt.ResultArtifactRef ||
		receipt.Payload["finalText"] != "路线证据已收敛" {
		t.Fatalf("terminal receipt is incomplete: %#v", receipt)
	}
	task := run.TaskGraph.Tasks[0]
	if task.Status != generated.AssistantTaskStatusCompleted ||
		task.TerminalReceiptRef != receipt.ReceiptRef ||
		task.ResultArtifactRef != receipt.ResultArtifactRef ||
		len(run.Items) != 1 ||
		run.Items[0].Status != generated.AssistantRunItemStatusCompleted {
		t.Fatalf("canonical run did not own terminal state: task=%#v items=%#v", task, run.Items)
	}
	_, recovered, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-recovery",
		30*time.Second,
		now.Add(time.Minute),
	)
	if err != nil || recovered == nil ||
		recovered.ReceiptRef != receipt.ReceiptRef || len(run.Items) != 1 {
		t.Fatalf("completed child was not recovered exactly once: receipt=%#v err=%v", recovered, err)
	}
}

func TestDurableSubtaskTaskNodeFencesExpiredAttemptAndOldWorker(t *testing.T) {
	now := time.Date(2026, 8, 4, 11, 0, 0, 0, time.UTC)
	run := durableSubtaskAggregate(generated.AssistantTaskStatusRunning)
	first, _, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-a",
		10*time.Second,
		now,
	)
	if err != nil {
		t.Fatalf("first claim error=%v", err)
	}
	if _, _, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-b",
		10*time.Second,
		now.Add(9*time.Second),
	); !errors.Is(err, runruntime.ErrLeaseConflict) {
		t.Fatalf("active claim error=%v, want lease conflict", err)
	}
	second, _, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-b",
		10*time.Second,
		now.Add(11*time.Second),
	)
	if err != nil {
		t.Fatalf("takeover claim error=%v", err)
	}
	if second.Attempt != first.Attempt+1 ||
		second.FencingToken != first.FencingToken+1 ||
		second.ClaimID == first.ClaimID {
		t.Fatalf("takeover did not advance fencing: first=%#v second=%#v", first, second)
	}
	if _, err := run.HeartbeatDurableSubtask(
		first,
		10*time.Second,
		now.Add(12*time.Second),
	); !errors.Is(err, runruntime.ErrExecutionFenced) {
		t.Fatalf("old heartbeat error=%v, want fenced", err)
	}
	if _, err := run.FinishDurableSubtask(
		first,
		runruntime.DurableSubtaskResult{
			Outcome: "completed",
			Summary: "stale",
			Payload: map[string]any{"finalText": "stale"},
		},
		now.Add(12*time.Second),
	); !errors.Is(err, runruntime.ErrExecutionFenced) {
		t.Fatalf("old finish error=%v, want fenced", err)
	}
	if _, err := run.FinishDurableSubtask(
		second,
		runruntime.DurableSubtaskResult{
			Outcome: "completed",
			Summary: "fresh",
			Payload: map[string]any{"finalText": "fresh"},
		},
		now.Add(12*time.Second),
	); err != nil {
		t.Fatalf("current finish error=%v", err)
	}
}

func TestDurableSubtaskTaskNodeCancellationCascadesAndFencesReceipt(t *testing.T) {
	now := time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	run := durableSubtaskAggregate(generated.AssistantTaskStatusRunning)
	claim, _, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-a",
		30*time.Second,
		now,
	)
	if err != nil {
		t.Fatalf("claim error=%v", err)
	}
	run.CancelActiveWork("用户取消", now.Add(time.Second))
	if run.TaskGraph.Tasks[0].Status != generated.AssistantTaskStatusCancelled {
		t.Fatalf("child task was not cancelled: %#v", run.TaskGraph.Tasks[0])
	}
	if _, err := run.HeartbeatDurableSubtask(
		claim,
		30*time.Second,
		now.Add(2*time.Second),
	); !errors.Is(err, runruntime.ErrExecutionCancelled) {
		t.Fatalf("cancelled heartbeat error=%v", err)
	}
	if _, err := run.FinishDurableSubtask(
		claim,
		runruntime.DurableSubtaskResult{
			Outcome: "completed",
			Summary: "late result",
			Payload: map[string]any{"finalText": "late result"},
		},
		now.Add(2*time.Second),
	); !errors.Is(err, runruntime.ErrExecutionCancelled) {
		t.Fatalf("cancelled finish error=%v", err)
	}
	if len(run.Items) != 0 {
		t.Fatalf("cancelled worker committed terminal item: %#v", run.Items)
	}
}

func TestDurableSubtaskTaskNodeRejectsDifferentFrozenInput(t *testing.T) {
	now := time.Date(2026, 8, 4, 13, 0, 0, 0, time.UTC)
	run := durableSubtaskAggregate(generated.AssistantTaskStatusRunning)
	if _, _, err := run.ClaimDurableSubtask(
		durableTaskNodeClaimRequest(durableTaskNodeInputDigest),
		"worker-a",
		30*time.Second,
		now,
	); err != nil {
		t.Fatalf("claim error=%v", err)
	}
	request := durableTaskNodeClaimRequest(
		"sha256:a258c351150ade26c6fd8bbac59db9f87de44516bc7869ef0755b2b9fbd5a580",
	)
	if _, _, err := run.ClaimDurableSubtask(
		request,
		"worker-b",
		30*time.Second,
		now.Add(time.Minute),
	); !errors.Is(err, runruntime.ErrRevisionConflict) {
		t.Fatalf("different input error=%v, want revision conflict", err)
	}
}

func durableSubtaskAggregate(
	status generated.AssistantTaskStatus,
) runruntime.Run {
	return runruntime.Run{
		RunID:        "run-durable-subtask",
		GoalRevision: 1,
		State:        generated.AssistantRunStateExecuting,
		TaskGraph: runruntime.TaskGraph{
			GraphRevision: 2,
			Tasks: []runruntime.TaskNode{{
				TaskID:     "run:run-durable-subtask:goal:1:task:subagent:travel:executing",
				Goal:       "收敛旅行路线证据",
				Status:     status,
				OwnerAgent: "subagent:travel_companion",
				Attempt:    1,
			}},
		},
	}
}

func durableTaskNodeClaimRequest(
	inputDigest string,
) runruntime.DurableSubtaskClaimRequest {
	return runruntime.DurableSubtaskClaimRequest{
		TaskID:      "run:run-durable-subtask:goal:1:task:subagent:travel:executing",
		OwnerAgent:  "subagent:travel_companion",
		InputDigest: inputDigest,
	}
}
