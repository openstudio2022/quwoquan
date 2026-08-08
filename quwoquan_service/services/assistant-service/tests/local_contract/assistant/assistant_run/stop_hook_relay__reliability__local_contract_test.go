// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type stopHookRelayStoreFixture struct {
	mu                sync.Mutex
	invocation        runruntime.StopHookInvocation
	claimOwner        string
	claimUntil        time.Time
	nextAttemptAt     time.Time
	acknowledged      bool
	receiptDigest     string
	attemptCount      int
	scheduled         int
	lastFailure       string
	commitThenLoseAck bool
}

func (store *stopHookRelayStoreFixture) ClaimPendingStopHooks(
	_ context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
	_ int,
) ([]runruntime.StopHookInvocation, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.acknowledged ||
		(!store.nextAttemptAt.IsZero() && now.Before(store.nextAttemptAt)) ||
		(store.claimOwner != "" && now.Before(store.claimUntil)) {
		return nil, nil
	}
	store.claimOwner = ownerID
	store.claimUntil = now.Add(lease)
	store.attemptCount++
	invocation := store.invocation
	invocation.AttemptCount = store.attemptCount
	return []runruntime.StopHookInvocation{invocation}, nil
}

func (store *stopHookRelayStoreFixture) AcknowledgeStopHook(
	_ context.Context,
	invocationID string,
	ownerID string,
	processedAt time.Time,
	receiptDigest string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if invocationID != store.invocation.InvocationID ||
		ownerID != store.claimOwner || !processedAt.Before(store.claimUntil) {
		return runruntime.ErrStopHookClaimLost
	}
	store.acknowledged = true
	store.receiptDigest = receiptDigest
	store.claimOwner = ""
	store.claimUntil = time.Time{}
	if store.commitThenLoseAck {
		store.commitThenLoseAck = false
		return errors.New("acknowledgement response lost after commit")
	}
	return nil
}

func (store *stopHookRelayStoreFixture) ScheduleStopHookRetry(
	_ context.Context,
	invocationID string,
	ownerID string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.acknowledged || invocationID != store.invocation.InvocationID ||
		ownerID != store.claimOwner || !failedAt.Before(store.claimUntil) {
		return runruntime.ErrStopHookClaimLost
	}
	store.scheduled++
	store.lastFailure = failureCode
	store.nextAttemptAt = nextAttemptAt
	store.claimOwner = ""
	store.claimUntil = time.Time{}
	return nil
}

func (store *stopHookRelayStoreFixture) ReleaseStopHookClaim(
	_ context.Context,
	invocationID string,
	ownerID string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.acknowledged || invocationID != store.invocation.InvocationID ||
		ownerID != store.claimOwner {
		return runruntime.ErrStopHookClaimLost
	}
	store.claimOwner = ""
	store.claimUntil = time.Time{}
	return nil
}

type stopHookRelayHook struct {
	mu            sync.Mutex
	failRemaining int
	invocations   []runruntime.HookInput
}

func (*stopHookRelayHook) Name() string { return "test.stop_hook_receipt" }

func (*stopHookRelayHook) Phases() []runruntime.HookPhase {
	return []runruntime.HookPhase{runruntime.HookOnStop}
}

func (hook *stopHookRelayHook) Invoke(
	_ context.Context,
	input runruntime.HookInput,
) (runruntime.HookResult, error) {
	hook.mu.Lock()
	defer hook.mu.Unlock()
	hook.invocations = append(hook.invocations, input)
	if hook.failRemaining > 0 {
		hook.failRemaining--
		return runruntime.HookResult{}, errors.New("hook sink unavailable")
	}
	return runruntime.HookResult{
		Decision:             runruntime.HookAllow,
		ProtectedFactsDigest: input.ProtectedFactsDigest,
	}, nil
}

func TestStopHookRelayRetriesAfterFailureWithStableInvocationAcrossRestart(t *testing.T) {
	now := time.Date(2026, 8, 8, 9, 0, 0, 0, time.UTC)
	clock := now
	invocation := stopHookRelayInvocation("run-stop-retry", 9, "waiting_external", now)
	store := &stopHookRelayStoreFixture{invocation: invocation}
	hook := &stopHookRelayHook{failRemaining: 1}
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hook},
	)
	if err != nil {
		t.Fatal(err)
	}
	first := runruntime.NewStopHookRelay(
		store,
		registry,
		"stop-hook-worker-a",
		time.Second,
		1,
		runruntime.WithStopHookRelayClock(func() time.Time { return clock }),
	)
	if processed, err := first.FlushOnce(t.Context()); err == nil || processed != 0 {
		t.Fatalf("first FlushOnce=(%d,%v), want hook failure", processed, err)
	}
	if store.scheduled != 1 || store.lastFailure != "hook_failed" ||
		store.nextAttemptAt != now.Add(time.Second) || store.acknowledged {
		t.Fatalf("retry state=%+v", store)
	}
	if processed, err := first.FlushOnce(t.Context()); err != nil || processed != 0 {
		t.Fatalf("early retry=(%d,%v), want no due work", processed, err)
	}

	clock = now.Add(time.Second)
	restarted := runruntime.NewStopHookRelay(
		store,
		registry,
		"stop-hook-worker-b",
		time.Second,
		1,
		runruntime.WithStopHookRelayClock(func() time.Time { return clock }),
	)
	if processed, err := restarted.FlushOnce(t.Context()); err != nil || processed != 1 {
		t.Fatalf("restart FlushOnce=(%d,%v), want one receipt", processed, err)
	}
	if !store.acknowledged || !stopHookRelayCanonicalDigest(store.receiptDigest) ||
		len(hook.invocations) != 2 {
		t.Fatalf("delivery state=%+v invocations=%+v", store, hook.invocations)
	}
	for _, input := range hook.invocations {
		if input.InvocationID != invocation.InvocationID ||
			input.RunRevision != invocation.RunRevision ||
			input.Outcome != invocation.Outcome ||
			input.Run.RunID != invocation.RunID ||
			input.Run.Revision != invocation.RunRevision ||
			input.Run.State.WireName() != invocation.Outcome {
			t.Fatalf("unstable HookInput=%+v invocation=%+v", input, invocation)
		}
	}
}

func TestStopHookRelayDoesNotRepeatHookAfterCommittedAckResponseIsLost(t *testing.T) {
	now := time.Date(2026, 8, 8, 10, 0, 0, 0, time.UTC)
	invocation := stopHookRelayInvocation("run-stop-ack-loss", 5, "paused", now)
	store := &stopHookRelayStoreFixture{
		invocation:        invocation,
		commitThenLoseAck: true,
	}
	hook := &stopHookRelayHook{}
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hook},
	)
	if err != nil {
		t.Fatal(err)
	}
	relay := runruntime.NewStopHookRelay(
		store,
		registry,
		"stop-hook-ack-worker",
		time.Second,
		1,
		runruntime.WithStopHookRelayClock(func() time.Time { return now }),
	)
	if processed, err := relay.FlushOnce(t.Context()); err == nil || processed != 0 {
		t.Fatalf("lost ack FlushOnce=(%d,%v), want uncertain acknowledgement", processed, err)
	}
	if !store.acknowledged || len(hook.invocations) != 1 ||
		!stopHookRelayCanonicalDigest(store.receiptDigest) {
		t.Fatalf("committed acknowledgement not retained: store=%+v hooks=%d", store, len(hook.invocations))
	}
	restarted := runruntime.NewStopHookRelay(
		store,
		registry,
		"stop-hook-ack-restart",
		time.Second,
		1,
		runruntime.WithStopHookRelayClock(func() time.Time { return now.Add(time.Hour) }),
	)
	if processed, err := restarted.FlushOnce(t.Context()); err != nil || processed != 0 {
		t.Fatalf("post-ack restart=(%d,%v), want no replay", processed, err)
	}
	if len(hook.invocations) != 1 {
		t.Fatalf("hook repeated after committed acknowledgement: %+v", hook.invocations)
	}
}

func stopHookRelayInvocation(
	runID string,
	revision int64,
	outcome string,
	createdAt time.Time,
) runruntime.StopHookInvocation {
	digest := sha256.Sum256([]byte("protected facts for " + runID))
	return runruntime.StopHookInvocation{
		InvocationID: runruntime.StableHookInvocationID(
			runID,
			runruntime.HookOnStop,
			revision,
		),
		RunID:                runID,
		Phase:                runruntime.HookOnStop,
		Outcome:              outcome,
		RunRevision:          revision,
		ProtectedFactsDigest: "sha256:" + hex.EncodeToString(digest[:]),
		Data:                 map[string]any{"outcome": outcome},
		CreatedAt:            createdAt,
	}
}

func stopHookRelayCanonicalDigest(value string) bool {
	if len(value) != 71 || value[:7] != "sha256:" {
		return false
	}
	decoded, err := hex.DecodeString(value[7:])
	return err == nil && len(decoded) == sha256.Size
}

var _ runruntime.StopHookStore = (*stopHookRelayStoreFixture)(nil)
var _ runruntime.Hook = (*stopHookRelayHook)(nil)
