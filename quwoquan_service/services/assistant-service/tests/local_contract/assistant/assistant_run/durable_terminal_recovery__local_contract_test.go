// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func TestDurableTerminalRecoveryAfterEveryPersistedBoundary(t *testing.T) {
	tests := []struct {
		name  string
		kind  string
		state generated.AssistantRunState
	}{
		{"verdict_answer_capsule", "answer_delta", generated.AssistantRunStateExecuting},
		{"root_task_completed", "process_commit", generated.AssistantRunStateObserving},
		{"reflecting", "run_state_changed", generated.AssistantRunStateReflecting},
		{"synthesizing", "run_state_changed", generated.AssistantRunStateSynthesizing},
		{"presentation_snapshot", "presentation_snapshot", generated.AssistantRunStateSynthesizing},
		{"presentation_commit", "presentation_commit", generated.AssistantRunStateSynthesizing},
		{"verifying", "run_state_changed", generated.AssistantRunStateVerifying},
		{"terminal", "completed", generated.AssistantRunStateCompleted},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			repository := &interruptAfterCommitRepository{
				memoryRunRepository: base,
				kind:                test.kind,
				state:               test.state,
			}
			queue := newMemoryWorkQueue()
			run, err := workerCommandService(base).Start(t.Context(), runruntime.StartCommand{
				UserID: "user-terminal-" + test.name, SessionID: "session-terminal",
				ClientRequestID: "request-terminal-" + test.name,
				InputText:       "完成可恢复答案",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &countingTerminalExecutor{}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, executor, "worker-terminal-a-"+test.name,
			)
			worked, processErr := worker.ProcessNext(t.Context())
			if !worked || !errors.Is(processErr, errInjectedTerminalBoundary) {
				t.Fatalf("interrupt boundary: worked=%t err=%v", worked, processErr)
			}
			if !repository.wasInterrupted() {
				t.Fatal("requested durable boundary was not reached")
			}
			interrupted, err := base.Load(t.Context(), run.RunID)
			if err != nil {
				t.Fatalf("load interrupted run: %v", err)
			}
			if test.kind == "answer_delta" {
				if interrupted.State != generated.AssistantRunStateExecuting {
					t.Fatalf("answer capsule moved state before root completion: %s", interrupted.State)
				}
				assertAcceptedCompletionFacts(t, interrupted)
			}

			worker = runruntime.NewDurableWorker(
				repository, queue, executor, "worker-terminal-b-"+test.name,
			)
			for attempt := 0; attempt < 3; attempt++ {
				stored, loadErr := base.Load(t.Context(), run.RunID)
				if loadErr != nil {
					t.Fatalf("load recovery state: %v", loadErr)
				}
				if stored.State == generated.AssistantRunStateCompleted {
					break
				}
				worked, processErr = worker.ProcessNext(t.Context())
				if processErr != nil || !worked {
					t.Fatalf("resume persisted boundary: worked=%t err=%v", worked, processErr)
				}
			}
			completed, err := base.Load(t.Context(), run.RunID)
			if err != nil {
				t.Fatalf("load completed run: %v", err)
			}
			assertRecoveredTerminalRun(t, completed, base)
			if executor.callCount() != 1 {
				t.Fatalf("executor repeated after durable completion fact: calls=%d", executor.callCount())
			}
			if worked, err = worker.ProcessNext(t.Context()); err != nil || worked {
				t.Fatalf("terminal run remained queued: worked=%t err=%v", worked, err)
			}
		})
	}
}

func TestRunnableCompletionStageWithoutCapsuleDoesNotRescheduleNoOp(t *testing.T) {
	states := []generated.AssistantRunState{
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateVerifying,
	}
	for _, state := range states {
		t.Run(state.WireName(), func(t *testing.T) {
			repository := newMemoryRunRepository()
			queue := newMemoryWorkQueue()
			run := seedCompletionStageWithoutCapsule(t, repository, state)
			executor := &countingTerminalExecutor{}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, executor, "worker-missing-"+state.WireName(),
			)
			if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
				t.Fatalf("fail missing capsule: worked=%t err=%v", worked, err)
			}
			failed, err := repository.Load(t.Context(), run.RunID)
			if err != nil || failed.State != generated.AssistantRunStateFailed ||
				!strings.Contains(failed.TerminalReason, "completion_capsule_missing") {
				t.Fatalf("missing capsule remained runnable: run=%#v err=%v", failed, err)
			}
			if executor.callCount() != 0 {
				t.Fatalf("missing capsule invoked executor: calls=%d", executor.callCount())
			}
			if worked, err := worker.ProcessNext(t.Context()); err != nil || worked {
				t.Fatalf("failed completion stage was rescheduled: worked=%t err=%v", worked, err)
			}
		})
	}
}

var errInjectedTerminalBoundary = errors.New("injected interruption after durable boundary")

type interruptAfterCommitRepository struct {
	*memoryRunRepository
	mu          sync.Mutex
	kind        string
	state       generated.AssistantRunState
	interrupted bool
}

func (r *interruptAfterCommitRepository) Commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if err := r.memoryRunRepository.Commit(
		ctx, expectedRevision, run, events, receipt,
	); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.interrupted && len(events) == 1 && events[0].Kind == r.kind &&
		run.State == r.state {
		r.interrupted = true
		return errInjectedTerminalBoundary
	}
	return nil
}

func (r *interruptAfterCommitRepository) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if err := r.memoryRunRepository.CommitClaim(
		ctx, claim, expectedRevision, run, events, receipt,
	); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.interrupted && len(events) == 1 && events[0].Kind == r.kind &&
		run.State == r.state {
		r.interrupted = true
		return errInjectedTerminalBoundary
	}
	return nil
}

func (r *interruptAfterCommitRepository) wasInterrupted() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.interrupted
}

type countingTerminalExecutor struct {
	mu    sync.Mutex
	calls int
}

func (e *countingTerminalExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.calls++
	e.mu.Unlock()
	result, err := (&successfulRunExecutor{}).Execute(ctx, request, emit)
	result.ConfirmedSlots = assistantmodel.AssistantRunConfirmedSlots{"destination": "杭州"}
	return result, err
}

func (e *countingTerminalExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.calls
}

func assertAcceptedCompletionFacts(t *testing.T, run runruntime.Run) {
	t.Helper()
	if run.ConfirmedSlots["destination"] != "杭州" {
		t.Fatalf("confirmed slots and completion facts did not share CAS: %#v", run)
	}
	verificationCount, answerCount := 0, 0
	for _, item := range run.Items {
		switch item.Kind {
		case generated.AssistantRunItemKindEvidence:
			if item.Payload["accepted"] == true {
				verificationCount++
			}
		case generated.AssistantRunItemKindFinalAnswer:
			answerCount++
			encoded, _ := item.Payload["completionCapsule"].(string)
			digest, _ := item.Payload["completionDigest"].(string)
			hash := sha256.Sum256([]byte(encoded))
			if len(encoded) > 512<<10 || digest != "sha256:"+hex.EncodeToString(hash[:]) ||
				strings.Contains(strings.ToLower(encoded), "providerdiagnostic") {
				t.Fatalf("capsule size/privacy/digest invalid: %#v", item.Payload)
			}
			var decoded map[string]any
			if err := json.Unmarshal([]byte(encoded), &decoded); err != nil {
				t.Fatalf("decode capsule: %v", err)
			}
		}
	}
	if verificationCount != 1 || answerCount != 1 {
		t.Fatalf("accepted facts are not unique: verification=%d answer=%d", verificationCount, answerCount)
	}
}

func assertRecoveredTerminalRun(
	t *testing.T,
	run runruntime.Run,
	repository *memoryRunRepository,
) {
	t.Helper()
	if run.State != generated.AssistantRunStateCompleted || run.TerminalSnapshot == nil ||
		run.TerminalSnapshot.AnswerText != "可回查答案" ||
		len(run.TerminalSnapshot.Processes) != 1 || !run.TaskGraph.AllCompleted() ||
		run.ConfirmedSlots["destination"] != "杭州" {
		t.Fatalf("terminal snapshot did not recover exactly: %#v", run)
	}
	if run.PresentationDocument["revision"] != int64(2) ||
		strings.TrimSpace(stringFieldForTest(run.PresentationDocument, "committedAt")) == "" {
		t.Fatalf("presentation did not converge once: %#v", run.PresentationDocument)
	}
	assertAcceptedCompletionFacts(t, run)
	events, err := repository.EventsAfter(t.Context(), run.RunID, 0, 256)
	if err != nil || int64(len(events)) != run.JournalSequence {
		t.Fatalf("read complete journal: events=%d head=%d err=%v", len(events), run.JournalSequence, err)
	}
	counts := map[string]int{}
	stateCounts := map[string]int{}
	for index, event := range events {
		if event.Sequence != int64(index+1) {
			t.Fatalf("journal gap at %d: %#v", index, event)
		}
		counts[event.Kind]++
		if event.Kind == "process_commit" &&
			event.Payload["status"] == generated.AssistantRunStateObserving.WireName() {
			counts["root_task_completed"]++
		}
		if event.Kind == "run_state_changed" {
			status, _ := event.Payload["status"].(string)
			stateCounts[status]++
		}
		if event.Kind == "answer_delta" {
			if _, leaked := event.Payload["completionCapsule"]; leaked {
				t.Fatalf("SSE answer event leaked recovery capsule: %#v", event.Payload)
			}
		}
	}
	if counts["answer_delta"] != 1 || counts["root_task_completed"] != 1 ||
		counts["presentation_snapshot"] != 1 ||
		counts["presentation_commit"] != 1 ||
		counts["completed"] != 1 ||
		stateCounts[generated.AssistantRunStateReflecting.WireName()] != 1 ||
		stateCounts[generated.AssistantRunStateSynthesizing.WireName()] != 1 ||
		stateCounts[generated.AssistantRunStateVerifying.WireName()] != 1 {
		t.Fatalf("completion lifecycle events are not unique: kinds=%#v states=%#v", counts, stateCounts)
	}
}

func seedCompletionStageWithoutCapsule(
	t *testing.T,
	repository *memoryRunRepository,
	state generated.AssistantRunState,
) runruntime.Run {
	t.Helper()
	run, err := workerCommandService(repository).Start(t.Context(), runruntime.StartCommand{
		UserID: "user-missing-" + state.WireName(), SessionID: "session-missing",
		ClientRequestID: "request-missing-" + state.WireName(), InputText: "恢复缺失终态",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	now := time.Now().UTC()
	for _, next := range []generated.AssistantRunState{
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePlanning,
	} {
		if err := run.Transition(next, "", now); err != nil {
			t.Fatalf("seed state %s: %v", next, err)
		}
	}
	if err := run.TaskGraph.Start("task_root"); err != nil {
		t.Fatalf("start root task: %v", err)
	}
	if err := run.Transition(generated.AssistantRunStateExecuting, "", now); err != nil {
		t.Fatalf("seed executing: %v", err)
	}
	if err := run.TaskGraph.Complete(
		"task_root", nil, runruntime.TaskVerification{Passed: true},
	); err != nil {
		t.Fatalf("complete root task: %v", err)
	}
	for _, next := range []generated.AssistantRunState{
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateVerifying,
	} {
		if err := run.Transition(next, "", now); err != nil {
			t.Fatalf("seed state %s: %v", next, err)
		}
		if next == state {
			break
		}
	}
	repository.mu.Lock()
	repository.runs[run.RunID] = run
	repository.mu.Unlock()
	return run
}

var _ runruntime.WorkerRepository = (*interruptAfterCommitRepository)(nil)
