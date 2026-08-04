// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
)

const durableSubtaskInputDigest = "sha256:2ecb229df8514e214563939488134593efc7f6bc15a4dc97284304c6f3b7069f"

type durableSubtaskStoreStub struct {
	mu sync.Mutex

	claim        orchestration.DurableSubtaskClaim
	terminal     *orchestration.DurableSubtaskTerminalReceipt
	claimErr     error
	heartbeatErr error
	finishErr    error

	claimCalls     int
	heartbeatCalls int
	finishCalls    int
	finishedResult orchestration.DurableSubtaskResult
}

func (s *durableSubtaskStoreStub) Claim(
	_ context.Context,
	request orchestration.DurableSubtaskRequest,
	workerID string,
	ttl time.Duration,
) (
	orchestration.DurableSubtaskClaim,
	*orchestration.DurableSubtaskTerminalReceipt,
	error,
) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.claimCalls++
	if s.claimErr != nil {
		return orchestration.DurableSubtaskClaim{}, nil, s.claimErr
	}
	claim := s.claim
	if claim.RunID == "" {
		claim = orchestration.DurableSubtaskClaim{
			RunID:          request.RunID,
			TaskID:         request.TaskID,
			ClaimID:        "claim-1",
			ClaimOwner:     workerID,
			InputDigest:    request.InputDigest,
			FencingToken:   1,
			Attempt:        1,
			IdempotencyKey: durableSubtaskInputDigest,
			LeaseExpiresAt: time.Now().UTC().Add(ttl),
		}
	}
	var terminal *orchestration.DurableSubtaskTerminalReceipt
	if s.terminal != nil {
		cloned := *s.terminal
		terminal = &cloned
	}
	return claim, terminal, nil
}

func (s *durableSubtaskStoreStub) Heartbeat(
	context.Context,
	orchestration.DurableSubtaskClaim,
	time.Duration,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.heartbeatCalls++
	return s.heartbeatErr
}

func (s *durableSubtaskStoreStub) Finish(
	_ context.Context,
	claim orchestration.DurableSubtaskClaim,
	result orchestration.DurableSubtaskResult,
) (orchestration.DurableSubtaskTerminalReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.finishCalls++
	s.finishedResult = result
	if s.finishErr != nil {
		return orchestration.DurableSubtaskTerminalReceipt{}, s.finishErr
	}
	return durableSubtaskTerminal(claim, result), nil
}

func durableSubtaskRequest() orchestration.DurableSubtaskRequest {
	return orchestration.DurableSubtaskRequest{
		RunID:       "run-durable-child",
		TaskID:      "run:run-durable-child:goal:1:task:subagent:1:travel:executing",
		OwnerAgent:  "subagent:travel_companion",
		InputDigest: durableSubtaskInputDigest,
	}
}

func durableSubtaskTerminal(
	claim orchestration.DurableSubtaskClaim,
	result orchestration.DurableSubtaskResult,
) orchestration.DurableSubtaskTerminalReceipt {
	return orchestration.DurableSubtaskTerminalReceipt{
		ReceiptRef:        "assistant_run_item:" + claim.TaskID + ":terminal",
		RunID:             claim.RunID,
		TaskID:            claim.TaskID,
		InputDigest:       durableSubtaskInputDigest,
		Outcome:           result.Outcome,
		Attempt:           claim.Attempt,
		FencingToken:      claim.FencingToken,
		IdempotencyKey:    claim.IdempotencyKey,
		Summary:           result.Summary,
		FailureCode:       result.FailureCode,
		ResultArtifactRef: "assistant_run_item:" + claim.TaskID + ":result",
		Payload:           result.Payload,
		CompletedAt:       time.Now().UTC(),
	}
}

func TestDurableSubtaskCoordinatorReturnsTerminalWithoutRepeatingWork(
	t *testing.T,
) {
	request := durableSubtaskRequest()
	claim := orchestration.DurableSubtaskClaim{
		RunID:          request.RunID,
		TaskID:         request.TaskID,
		ClaimID:        "claim-completed",
		ClaimOwner:     "worker-a",
		InputDigest:    request.InputDigest,
		FencingToken:   4,
		Attempt:        2,
		IdempotencyKey: durableSubtaskInputDigest,
		LeaseExpiresAt: time.Now().UTC().Add(time.Minute),
	}
	completed := durableSubtaskTerminal(claim, orchestration.DurableSubtaskResult{
		Outcome: orchestration.DurableSubtaskCompleted,
		Summary: "已有可恢复结果",
		Payload: map[string]any{"finalText": "已有可恢复结果"},
	})
	store := &durableSubtaskStoreStub{claim: claim, terminal: &completed}
	coordinator := orchestration.NewDurableSubtaskCoordinator(
		store,
		"worker-a",
		time.Second,
		10*time.Millisecond,
	)
	var workCalls atomic.Int64
	receipt, err := coordinator.Execute(
		t.Context(),
		request,
		func(
			context.Context,
			orchestration.DurableSubtaskClaim,
		) (orchestration.DurableSubtaskResult, error) {
			workCalls.Add(1)
			return orchestration.DurableSubtaskResult{}, nil
		},
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	if workCalls.Load() != 0 || receipt.ReceiptRef != completed.ReceiptRef ||
		store.finishCalls != 0 {
		t.Fatalf(
			"completed child was repeated: work=%d finish=%d receipt=%#v",
			workCalls.Load(),
			store.finishCalls,
			receipt,
		)
	}
}

func TestDurableSubtaskCoordinatorHeartbeatsAndCommitsOneTerminalReceipt(
	t *testing.T,
) {
	store := &durableSubtaskStoreStub{}
	coordinator := orchestration.NewDurableSubtaskCoordinator(
		store,
		"worker-a",
		200*time.Millisecond,
		5*time.Millisecond,
	)
	receipt, err := coordinator.Execute(
		t.Context(),
		durableSubtaskRequest(),
		func(
			ctx context.Context,
			_ orchestration.DurableSubtaskClaim,
		) (orchestration.DurableSubtaskResult, error) {
			select {
			case <-ctx.Done():
				return orchestration.DurableSubtaskResult{}, ctx.Err()
			case <-time.After(18 * time.Millisecond):
			}
			return orchestration.DurableSubtaskResult{
				Outcome: orchestration.DurableSubtaskCompleted,
				Summary: "子任务完成",
				Payload: map[string]any{"finalText": "子任务完成"},
			}, nil
		},
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	store.mu.Lock()
	heartbeats := store.heartbeatCalls
	finishes := store.finishCalls
	store.mu.Unlock()
	if heartbeats == 0 || finishes != 1 ||
		receipt.Outcome != orchestration.DurableSubtaskCompleted {
		t.Fatalf(
			"durable lifecycle incomplete: heartbeats=%d finishes=%d receipt=%#v",
			heartbeats,
			finishes,
			receipt,
		)
	}
}

func TestDurableSubtaskCoordinatorLeavesCancelledWorkRecoverable(
	t *testing.T,
) {
	store := &durableSubtaskStoreStub{}
	coordinator := orchestration.NewDurableSubtaskCoordinator(
		store,
		"worker-a",
		time.Second,
		10*time.Millisecond,
	)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err := coordinator.Execute(
		ctx,
		durableSubtaskRequest(),
		func(
			ctx context.Context,
			_ orchestration.DurableSubtaskClaim,
		) (orchestration.DurableSubtaskResult, error) {
			return orchestration.DurableSubtaskResult{}, ctx.Err()
		},
	)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("Execute() error=%v, want context.Canceled", err)
	}
	if store.finishCalls != 0 {
		t.Fatalf("cancelled worker wrote a terminal receipt: %d", store.finishCalls)
	}
}

func TestDurableSubtaskCoordinatorFencesOnHeartbeatFailure(t *testing.T) {
	heartbeatFailure := errors.New("child lease fenced")
	store := &durableSubtaskStoreStub{heartbeatErr: heartbeatFailure}
	coordinator := orchestration.NewDurableSubtaskCoordinator(
		store,
		"worker-a",
		100*time.Millisecond,
		5*time.Millisecond,
	)
	_, err := coordinator.Execute(
		t.Context(),
		durableSubtaskRequest(),
		func(
			ctx context.Context,
			_ orchestration.DurableSubtaskClaim,
		) (orchestration.DurableSubtaskResult, error) {
			<-ctx.Done()
			return orchestration.DurableSubtaskResult{}, ctx.Err()
		},
	)
	if !errors.Is(err, heartbeatFailure) {
		t.Fatalf("Execute() error=%v, want fencing failure", err)
	}
	if store.finishCalls != 0 {
		t.Fatalf("fenced child wrote a terminal receipt: %d", store.finishCalls)
	}
}
