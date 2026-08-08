// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

func TestWorkClaimFencingRejectsExpiredWorkerBeforeRevisionCAS(t *testing.T) {
	clock := time.Date(2026, 8, 8, 17, 0, 0, 0, time.UTC)
	runtime := assistantruntest.NewMemoryRuntimeWithClock(func() time.Time {
		return clock
	})
	run, err := workClaimCommandService(runtime).Start(t.Context(), runruntime.StartCommand{
		UserID:          "work-claim-owner",
		SessionID:       "work-claim-session",
		ClientRequestID: "work-claim-start",
		InputText:       "验证过期 Worker 不能提交",
	})
	if err != nil {
		t.Fatalf("start Run: %v", err)
	}
	first, err := runtime.ClaimNext(t.Context(), "worker-old", time.Minute)
	if err != nil {
		t.Fatalf("claim old worker: %v", err)
	}
	clock = clock.Add(2 * time.Minute)
	second, err := runtime.ClaimNext(t.Context(), "worker-current", time.Minute)
	if err != nil {
		t.Fatalf("take over expired claim: %v", err)
	}
	if second.FencingToken != first.FencingToken+1 {
		t.Fatalf("takeover fencingToken=%d want=%d", second.FencingToken, first.FencingToken+1)
	}

	baseline, err := runtime.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load baseline: %v", err)
	}
	staleRun, staleEvent := workClaimMutation(
		t, baseline, generated.AssistantRunStateOrienting, "stale_worker_commit", clock,
	)
	if err := runtime.CommitClaim(
		t.Context(), first, baseline.Revision, staleRun,
		[]runruntime.JournalEvent{staleEvent}, nil,
	); !errors.Is(err, runruntime.ErrExecutionFenced) {
		t.Fatalf("expired worker CommitClaim error=%v want ErrExecutionFenced", err)
	}
	unchanged, err := runtime.Load(t.Context(), run.RunID)
	if err != nil || unchanged.Revision != baseline.Revision ||
		unchanged.JournalSequence != baseline.JournalSequence {
		t.Fatalf("stale worker changed Run: run=%#v err=%v", unchanged, err)
	}

	winnerRun, winnerEvent := workClaimMutation(
		t, baseline, generated.AssistantRunStateOrienting, "current_worker_commit", clock,
	)
	if err := runtime.CommitClaim(
		t.Context(), second, baseline.Revision, winnerRun,
		[]runruntime.JournalEvent{winnerEvent}, nil,
	); err != nil {
		t.Fatalf("current worker CommitClaim: %v", err)
	}
	current, err := runtime.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load current Run: %v", err)
	}
	staleAfterTakeover, staleAfterEvent := workClaimMutation(
		t, current, generated.AssistantRunStatePlanning, "stale_retry", clock.Add(time.Second),
	)
	if err := runtime.CommitClaim(
		t.Context(), first, current.Revision, staleAfterTakeover,
		[]runruntime.JournalEvent{staleAfterEvent}, nil,
	); !errors.Is(err, runruntime.ErrExecutionFenced) {
		t.Fatalf("stale retry at current revision error=%v want ErrExecutionFenced", err)
	}
	events, err := runtime.EventsAfter(
		t.Context(), run.RunID, baseline.JournalSequence, 10,
	)
	if err != nil || len(events) != 1 || events[0].Kind != "current_worker_commit" {
		t.Fatalf("journal after takeover=%#v err=%v", events, err)
	}
}

func TestDurableWorkerUsesClaimBoundCommitPath(t *testing.T) {
	runtime := &claimCommitSpy{MemoryRuntime: assistantruntest.NewMemoryRuntime()}
	if _, err := workClaimCommandService(runtime).Start(t.Context(), runruntime.StartCommand{
		UserID:          "claim-path-owner",
		SessionID:       "claim-path-session",
		ClientRequestID: "claim-path-start",
		InputText:       "只允许 claim-bound worker commit",
	}); err != nil {
		t.Fatalf("start Run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		runtime, runtime, &successfulRunExecutor{}, "claim-path-worker",
	)
	worked, err := worker.ProcessNext(t.Context())
	if err != nil || !worked {
		t.Fatalf("ProcessNext()=(%t,%v)", worked, err)
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if runtime.genericCommits != 1 {
		t.Fatalf("generic Commit calls=%d want only Start commit", runtime.genericCommits)
	}
	if runtime.claimCommits == 0 {
		t.Fatal("durable worker performed no claim-bound commits")
	}
}

type claimCommitSpy struct {
	*assistantruntest.MemoryRuntime
	mu             sync.Mutex
	genericCommits int
	claimCommits   int
}

func workClaimCommandService(repository runruntime.Repository) *runruntime.CommandService {
	return runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
}

func (runtime *claimCommitSpy) Commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	runtime.mu.Lock()
	runtime.genericCommits++
	runtime.mu.Unlock()
	return runtime.MemoryRuntime.Commit(ctx, expectedRevision, run, events, receipt)
}

func (runtime *claimCommitSpy) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	runtime.mu.Lock()
	runtime.claimCommits++
	runtime.mu.Unlock()
	return runtime.MemoryRuntime.CommitClaim(
		ctx, claim, expectedRevision, run, events, receipt,
	)
}

func workClaimMutation(
	t *testing.T,
	baseline runruntime.Run,
	next generated.AssistantRunState,
	kind string,
	now time.Time,
) (runruntime.Run, runruntime.JournalEvent) {
	t.Helper()
	mutated := baseline
	if err := mutated.Transition(next, "", now); err != nil {
		t.Fatalf("transition to %s: %v", next, err)
	}
	mutated.JournalSequence++
	return mutated, runruntime.JournalEvent{
		EventID:   mutated.RunID + ":" + kind,
		RunID:     mutated.RunID,
		Sequence:  mutated.JournalSequence,
		Revision:  mutated.Revision,
		Kind:      kind,
		CreatedAt: now,
	}
}
