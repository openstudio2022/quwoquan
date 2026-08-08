// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestCompletionBoundaryRejectsExactAndForwardGoalChainDrift(t *testing.T) {
	t.Run("exact_malformed_goal_history", func(t *testing.T) {
		base := newMemoryRunRepository()
		run, err := workerCommandService(base).Start(t.Context(), runruntime.StartCommand{
			UserID: "user-exact-malformed", SessionID: "session-exact-malformed",
			ClientRequestID: "request-exact-malformed", InputText: "目标链必须连续",
		})
		if err != nil {
			t.Fatalf("start run: %v", err)
		}
		base.mu.Lock()
		malformed := base.runs[run.RunID]
		malformed.GoalRevision = 2
		malformed.Revision++
		base.runs[run.RunID] = malformed
		base.mu.Unlock()
		queue := newMemoryWorkQueue()
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			base, queue, &completionRaceExecutor{}, "worker-exact-malformed",
		)
		if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
			t.Fatalf("malformed exact goal chain: worked=%t err=%v", worked, processErr)
		}
		failed := loadCompletionBoundaryRun(t, base, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "completion_boundary_corrupt" {
			t.Fatalf("malformed exact goal chain completed: %#v", failed)
		}
		assertNoCompletionFacts(t, failed)
	})

	t.Run("exact_input_rewrite", func(t *testing.T) {
		base := newMemoryRunRepository()
		commands := workerCommandService(base)
		run, err := commands.Start(t.Context(), runruntime.StartCommand{
			UserID: "user-exact-goal-drift", SessionID: "session-exact-goal-drift",
			ClientRequestID: "request-exact-goal-drift", InputText: "不可改写的原始目标",
		})
		if err != nil {
			t.Fatalf("start run: %v", err)
		}
		var once sync.Once
		repository := &completionCommitInterceptor{
			memoryRunRepository: base,
			before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
				if !completionCommitContainsCapsule(candidate, events) {
					return nil
				}
				once.Do(func() {
					base.mu.Lock()
					mutated := base.runs[run.RunID]
					mutated.InputText = "被非法替换的原始目标"
					mutated.Revision++
					base.runs[run.RunID] = mutated
					base.mu.Unlock()
				})
				return nil
			},
		}
		queue := newMemoryWorkQueue()
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			repository, queue, &completionRaceExecutor{}, "worker-exact-goal-drift",
		)
		worked, processErr := worker.ProcessNext(t.Context())
		if !worked || !errors.Is(processErr, runruntime.ErrRevisionConflict) {
			t.Fatalf("exact goal drift: worked=%t err=%v", worked, processErr)
		}
		persisted := loadCompletionBoundaryRun(t, base, run.RunID)
		if persisted.State != generated.AssistantRunStateExecuting ||
			persisted.InputText != "被非法替换的原始目标" {
			t.Fatalf("exact goal drift was overwritten or terminalized: %#v", persisted)
		}
		assertNoCompletionFacts(t, persisted)
	})

	t.Run("forward_discontinuous_history_with_matching_plan", func(t *testing.T) {
		base := newMemoryRunRepository()
		commands := workerCommandService(base)
		run, err := commands.Start(t.Context(), runruntime.StartCommand{
			UserID: "user-forward-goal-drift", SessionID: "session-forward-goal-drift",
			ClientRequestID: "request-forward-goal-drift", InputText: "原始目标",
		})
		if err != nil {
			t.Fatalf("start run: %v", err)
		}
		var once sync.Once
		repository := &completionCommitInterceptor{
			memoryRunRepository: base,
			before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
				if !completionCommitContainsGoalReplan(candidate, events) {
					return nil
				}
				once.Do(func() {
					candidate.GoalHistory[len(candidate.GoalHistory)-1].Revision++
					setGoalPlanDigestForTest(&candidate)
					base.mu.Lock()
					base.runs[run.RunID] = candidate
					base.events[run.RunID] = append(base.events[run.RunID], events...)
					base.mu.Unlock()
				})
				return nil
			},
		}
		executor := &completionBoundaryGapExecutor{
			commands: commands, userID: run.UserID, mode: "final_only",
			instruction: "合法追加目标",
		}
		queue := newMemoryWorkQueue()
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			repository, queue, executor, "worker-forward-goal-drift",
		)
		worked, processErr := worker.ProcessNext(t.Context())
		if processErr != nil || !worked {
			t.Fatalf("forward goal drift: worked=%t err=%v", worked, processErr)
		}
		failed := loadCompletionBoundaryRun(t, base, run.RunID)
		if failed.State != generated.AssistantRunStateFailed ||
			failed.TerminalReason != "completion_boundary_corrupt" {
			t.Fatalf("discontinuous forward history was not terminalized: %#v", failed)
		}
		assertNoCompletionFacts(t, failed)
	})

	t.Run("forward_rewrites_existing_history_prefix", func(t *testing.T) {
		base := newMemoryRunRepository()
		commands := workerCommandService(base)
		run, err := commands.Start(t.Context(), runruntime.StartCommand{
			UserID: "user-forward-prefix", SessionID: "session-forward-prefix",
			ClientRequestID: "request-forward-prefix", InputText: "原始目标",
		})
		if err != nil {
			t.Fatalf("start run: %v", err)
		}
		if _, err = commands.Steer(
			t.Context(), run.UserID, run.RunID,
			"seed-goal-revision", "第一条合法修订",
		); err != nil {
			t.Fatalf("seed goal revision: %v", err)
		}
		var once sync.Once
		repository := &completionCommitInterceptor{
			memoryRunRepository: base,
			before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
				if !completionCommitContainsCapsule(candidate, events) {
					return nil
				}
				once.Do(func() {
					base.mu.Lock()
					mutated := base.runs[run.RunID]
					mutated.GoalHistory[0].Instruction = "被替换的既有修订"
					mutated.GoalRevision = 3
					mutated.GoalHistory = append(mutated.GoalHistory, runruntime.GoalRevision{
						Revision: 3, Instruction: "并发追加修订", AppliedAt: time.Now().UTC(),
					})
					mutated.Items = append(mutated.Items, goalPlanItemForTest(mutated))
					mutated.Revision++
					base.runs[run.RunID] = mutated
					base.mu.Unlock()
				})
				return nil
			},
		}
		queue := newMemoryWorkQueue()
		queue.enqueue(run.RunID)
		worker := runruntime.NewDurableWorker(
			repository, queue, &completionRaceExecutor{}, "worker-forward-prefix",
		)
		worked, processErr := worker.ProcessNext(t.Context())
		if !worked || !errors.Is(processErr, runruntime.ErrRevisionConflict) {
			t.Fatalf("forward prefix rewrite: worked=%t err=%v", worked, processErr)
		}
		assertNoCompletionFacts(t, loadCompletionBoundaryRun(t, base, run.RunID))
	})
}

func TestCompletionBoundaryRejectsMalformedPendingGoalChain(t *testing.T) {
	base := newMemoryRunRepository()
	run, err := workerCommandService(base).Start(t.Context(), runruntime.StartCommand{
		UserID: "user-pending-malformed", SessionID: "session-pending-malformed",
		ClientRequestID: "request-pending-malformed", InputText: "空白修订不得持久化",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsCapsule(candidate, events) {
				return nil
			}
			once.Do(func() {
				base.mu.Lock()
				corrupt := base.runs[run.RunID]
				corrupt.PendingSteer = []string{"   "}
				corrupt.Revision++
				base.runs[run.RunID] = corrupt
				base.mu.Unlock()
			})
			return nil
		},
	}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, &completionRaceExecutor{}, "worker-pending-malformed",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("malformed pending goal chain: worked=%t err=%v", worked, processErr)
	}
	failed := loadCompletionBoundaryRun(t, base, run.RunID)
	if failed.State != generated.AssistantRunStateFailed ||
		failed.TerminalReason != "completion_capsule_rejected" {
		t.Fatalf("malformed pending goal chain completed: %#v", failed)
	}
	assertNoCompletionFacts(t, failed)
}

func TestCompletionBoundaryRejectsMalformedExistingGoalPlan(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{
			name: "fractional_goal_revision",
			mutate: func(payload map[string]any) {
				payload["goalRevision"] = float64(2.9)
			},
		},
		{
			name: "whitespace_wrapped_goal_digest",
			mutate: func(payload map[string]any) {
				payload["goalDigest"] = " " + payload["goalDigest"].(string) + " "
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			commands := workerCommandService(base)
			run, err := commands.Start(t.Context(), runruntime.StartCommand{
				UserID:    "user-malformed-plan-" + test.name,
				SessionID: "session-malformed-plan", ClientRequestID: "request-malformed-plan-" + test.name,
				InputText: "合法历史不能掩盖损坏计划",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			if _, err = commands.Steer(
				t.Context(), run.UserID, run.RunID,
				"seed-malformed-plan-"+test.name, "合法目标修订",
			); err != nil {
				t.Fatalf("seed goal revision: %v", err)
			}
			base.mu.Lock()
			malformed := base.runs[run.RunID]
			item := goalPlanItemForTest(malformed)
			test.mutate(item.Payload)
			malformed.Items = append(malformed.Items, item)
			malformed.Revision++
			base.runs[run.RunID] = malformed
			base.mu.Unlock()
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				base, queue, &completionRaceExecutor{}, "worker-malformed-plan-"+test.name,
			)
			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("malformed plan: worked=%t err=%v", worked, processErr)
			}
			failed := loadCompletionBoundaryRun(t, base, run.RunID)
			if failed.State != generated.AssistantRunStateFailed ||
				failed.TerminalReason != "completion_boundary_corrupt" {
				t.Fatalf("malformed existing plan completed: %#v", failed)
			}
			assertNoCompletionFacts(t, failed)
		})
	}
}

func TestPauseWinnerRecoversCheckpointWithoutReexecuting(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-pause-checkpoint-retry", SessionID: "session-pause-checkpoint-retry",
		ClientRequestID: "request-pause-checkpoint-retry", InputText: "暂停必须跨进程恢复",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	var pauseOnce, checkpointOnce sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if completionCommitContainsCapsule(candidate, events) {
				var pauseErr error
				pauseOnce.Do(func() {
					_, pauseErr = commands.Pause(
						t.Context(), run.UserID, run.RunID,
						"pause-before-checkpoint-retry", "暂停并等待恢复",
					)
				})
				return pauseErr
			}
			if len(events) == 1 && events[0].Kind == "checkpoint_committed" {
				var injected error
				checkpointOnce.Do(func() { injected = errCompletionBoundaryTransient })
				return injected
			}
			return nil
		},
	}
	executor := &completionRaceExecutor{}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-pause-checkpoint-retry-a",
	)
	worked, processErr := worker.ProcessNext(t.Context())
	if !worked || !errors.Is(processErr, errCompletionBoundaryTransient) {
		t.Fatalf("checkpoint transient: worked=%t err=%v", worked, processErr)
	}
	pending := loadCompletionBoundaryRun(t, base, run.RunID)
	if pending.State != generated.AssistantRunStateExecuting || !pending.PauseRequested {
		t.Fatalf("pause intent was not durable before checkpoint retry: %#v", pending)
	}
	worker = runruntime.NewDurableWorker(
		repository, queue, executor, "worker-pause-checkpoint-retry-b",
	)
	if worked, processErr = worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("recover pause checkpoint: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil ||
		paused.PauseRequested || executor.callCount() != 1 {
		t.Fatalf("pause checkpoint recovery reexecuted work: run=%#v calls=%d", paused, executor.callCount())
	}
	assertNoCompletionFacts(t, paused)
}

func TestSteerAndPauseAtCompletionBoundaryReplanThenPause(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-steer-pause", SessionID: "session-steer-pause",
		ClientRequestID: "request-steer-pause", InputText: "旧目标",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	executor := &steerPauseCompletionExecutor{commands: commands, userID: run.UserID}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(base, queue, executor, "worker-steer-pause")
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("steer+pause completion boundary: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil ||
		paused.PauseRequested || paused.GoalRevision != 2 ||
		len(paused.GoalHistory) != 1 || !goalPlanCompletedForTest(paused, 2) ||
		executor.callCount() != 1 {
		t.Fatalf("steer+pause did not pause after audited replan: %#v", paused)
	}
	assertNoCompletionFacts(t, paused)
}

func TestRejectedVerdictPauseWinsBeforeRepair(t *testing.T) {
	base := newMemoryRunRepository()
	run := startVerifierRepairRun(
		t, base, generated.AssistantReasoningProfileBalanced, "rejected-pause-race",
	)
	commands := workerCommandService(base)
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		after: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsRejectedVerdict(candidate, events) {
				return nil
			}
			var pauseErr error
			once.Do(func() {
				_, pauseErr = commands.Pause(
					t.Context(), run.UserID, run.RunID,
					"pause-after-rejected-verdict", "拒绝后暂停而非自动修复",
				)
			})
			return pauseErr
		},
	}
	executor := &completionRaceExecutor{rejectFirst: true}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-rejected-pause-race",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("rejected pause race: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	root := verifierRepairRootTask(t, paused)
	if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil ||
		paused.PauseRequested || root.Attempt != 1 || executor.callCount() != 1 {
		t.Fatalf("rejected verdict bypassed pause into repair: run=%#v root=%#v", paused, root)
	}
	assertNoCompletionCapsule(t, paused)
}

func TestVerificationRepairExhaustionCASLosesToPause(t *testing.T) {
	base := newMemoryRunRepository()
	run := startVerifierRepairRun(
		t, base, generated.AssistantReasoningProfileFast, "repair-exhaustion-pause-race",
	)
	commands := workerCommandService(base)
	blockedHookCount := 0
	registry, err := runruntime.NewHookRegistry(runruntime.RegisteredHook{Hook: hookStub{
		name:   "pause-winner-block-audit",
		phases: []runruntime.HookPhase{runruntime.HookOnBlocked},
		invoke: func(runruntime.HookInput) runruntime.HookResult {
			blockedHookCount++
			return runruntime.HookResult{Decision: runruntime.HookAllow}
		},
	}})
	if err != nil {
		t.Fatalf("new hook registry: %v", err)
	}
	profiles, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default reasoning profiles: %v", err)
	}
	var once sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if len(events) != 1 || events[0].Kind != "failed" {
				return nil
			}
			var pauseErr error
			once.Do(func() {
				_, pauseErr = commands.Pause(
					t.Context(), run.UserID, run.RunID,
					"pause-before-verification-failure", "失败终态提交前暂停",
				)
			})
			return pauseErr
		},
	}
	executor := &completionRaceExecutor{rejectFirst: true}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewConfiguredDurableWorker(
		repository, queue, executor, "worker-repair-exhaustion-pause-race",
		profiles, registry,
	)
	if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("verification failure pause race: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil ||
		paused.TerminalSnapshot != nil || paused.TerminalReason != "" ||
		executor.callCount() != 1 || blockedHookCount != 0 {
		t.Fatalf("verification failure swallowed pause: %#v", paused)
	}
}

func TestRejectedVerdictRecoveryTerminalCASLosesToPause(t *testing.T) {
	base := newMemoryRunRepository()
	run := startVerifierRepairRun(
		t, base, generated.AssistantReasoningProfileFast, "rejected-recovery-pause-race",
	)
	commands := workerCommandService(base)
	var interruptOnce, pauseOnce sync.Once
	repository := &completionCommitInterceptor{
		memoryRunRepository: base,
		after: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if !completionCommitContainsRejectedVerdict(candidate, events) {
				return nil
			}
			var injected error
			interruptOnce.Do(func() { injected = errCompletionBoundaryTransient })
			return injected
		},
		before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
			if len(events) != 1 || events[0].Kind != "failed" {
				return nil
			}
			var pauseErr error
			pauseOnce.Do(func() {
				_, pauseErr = commands.Pause(
					t.Context(), run.UserID, run.RunID,
					"pause-rejected-recovery", "恢复终态提交前暂停",
				)
			})
			return pauseErr
		},
	}
	executor := &completionRaceExecutor{rejectFirst: true}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, executor, "worker-rejected-recovery-pause-a",
	)
	worked, processErr := worker.ProcessNext(t.Context())
	if !worked || !errors.Is(processErr, errCompletionBoundaryTransient) {
		t.Fatalf("persist rejected verdict: worked=%t err=%v", worked, processErr)
	}
	worker = runruntime.NewDurableWorker(
		repository, queue, executor, "worker-rejected-recovery-pause-b",
	)
	if worked, processErr = worker.ProcessNext(t.Context()); processErr != nil || !worked {
		t.Fatalf("recover rejected verdict with pause: worked=%t err=%v", worked, processErr)
	}
	paused := loadCompletionBoundaryRun(t, base, run.RunID)
	if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil ||
		paused.TerminalSnapshot != nil || executor.callCount() != 1 {
		t.Fatalf("rejected recovery terminalized across pause: %#v", paused)
	}
}

func TestWaitingPresentationCASLosesToPauseWithoutProjection(t *testing.T) {
	for _, phase := range []string{"presentation_snapshot", "presentation_commit"} {
		t.Run(phase, func(t *testing.T) {
			base := newMemoryRunRepository()
			commands := workerCommandService(base)
			run, err := commands.Start(t.Context(), runruntime.StartCommand{
				UserID:          "user-wait-presentation-pause-" + phase,
				SessionID:       "session-wait-presentation-pause",
				ClientRequestID: "request-wait-presentation-pause-" + phase,
				InputText:       "等待前暂停",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			var once sync.Once
			repository := &completionCommitInterceptor{
				memoryRunRepository: base,
				before: func(candidate runruntime.Run, events []runruntime.JournalEvent) error {
					if len(events) != 1 || events[0].Kind != phase {
						return nil
					}
					var pauseErr error
					once.Do(func() {
						_, pauseErr = commands.Pause(
							t.Context(), run.UserID, run.RunID,
							"pause-before-wait-"+phase, "先暂停再决定是否展示等待态",
						)
					})
					return pauseErr
				},
			}
			queue := newMemoryWorkQueue()
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository, queue, &waitingPresentationExecutor{},
				"worker-wait-presentation-pause-"+phase,
			)
			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("wait presentation pause race: worked=%t err=%v", worked, processErr)
			}
			paused := loadCompletionBoundaryRun(t, base, run.RunID)
			if paused.State != generated.AssistantRunStatePaused || paused.Checkpoint == nil {
				t.Fatalf("pause winner did not checkpoint: %#v", paused)
			}
			if phase == "presentation_snapshot" && len(paused.PresentationDocument) != 0 {
				t.Fatalf("snapshot loser persisted presentation: %#v", paused.PresentationDocument)
			}
			if phase == "presentation_commit" &&
				(len(paused.PresentationDocument) == 0 || paused.PresentationDocument["committedAt"] != "") {
				t.Fatalf("commit loser did not retain only uncommitted snapshot: %#v", paused.PresentationDocument)
			}
			events, eventErr := base.EventsAfter(t.Context(), run.RunID, 0, 100)
			if eventErr != nil {
				t.Fatalf("load journal events: %v", eventErr)
			}
			snapshots, commits := 0, 0
			for _, event := range events {
				if event.Kind == "presentation_snapshot" {
					snapshots++
				}
				if event.Kind == "presentation_commit" {
					commits++
				}
			}
			wantSnapshots := 0
			if phase == "presentation_commit" {
				wantSnapshots = 1
			}
			if snapshots != wantSnapshots || commits != 0 {
				t.Fatalf("pause projection events: snapshots=%d commits=%d events=%#v", snapshots, commits, events)
			}
		})
	}
}

func TestAcceptedCompletionPausedStateCannotResume(t *testing.T) {
	base := newMemoryRunRepository()
	commands := workerCommandService(base)
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID: "user-paused-pair", SessionID: "session-paused-pair",
		ClientRequestID: "request-paused-pair", InputText: "损坏完成事实不得恢复",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	repository := &interruptAfterCommitRepository{
		memoryRunRepository: base,
		kind:                "answer_delta",
		state:               generated.AssistantRunStateExecuting,
	}
	queue := newMemoryWorkQueue()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository, queue, &countingTerminalExecutor{}, "worker-paused-pair",
	)
	if worked, processErr := worker.ProcessNext(t.Context()); !worked ||
		!errors.Is(processErr, errInjectedTerminalBoundary) {
		t.Fatalf("persist accepted pair: worked=%t err=%v", worked, processErr)
	}
	base.mu.Lock()
	corrupt := base.runs[run.RunID]
	corrupt.State = generated.AssistantRunStatePaused
	corrupt.PauseRequested = false
	corrupt.SuspendedFrom = generated.AssistantRunStateExecuting
	base.runs[run.RunID] = corrupt
	base.mu.Unlock()
	if _, resumeErr := commands.Resume(
		t.Context(), run.UserID, run.RunID, "resume-corrupt-accepted-pair",
	); !errors.Is(resumeErr, runruntime.ErrJournalCorrupt) {
		t.Fatalf("paused accepted pair resumed: %v", resumeErr)
	}
	if persisted := loadCompletionBoundaryRun(t, base, run.RunID); persisted.State != generated.AssistantRunStatePaused {
		t.Fatalf("corrupt paused pair changed state: %#v", persisted)
	}
}

type steerPauseCompletionExecutor struct {
	mu       sync.Mutex
	commands *runruntime.CommandService
	userID   string
	calls    int
}

type waitingPresentationExecutor struct{}

func (*waitingPresentationExecutor) Execute(
	_ context.Context,
	_ runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	return runruntime.ExecutionResult{
		WaitingState: generated.AssistantRunStateWaitingUser,
		WaitReason:   "等待用户确认",
		Presentation: map[string]any{
			"templateRef":       "assistant.answer.default@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"templateDigest":    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"revision":          int64(1),
			"rootNodeId":        "root",
			"nodes":             []map[string]any{{"nodeId": "root", "kind": "markdown", "body": "等待用户确认"}},
			"dataDigest":        "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			"selectedVariant":   "standard",
			"fallbackMarkdown":  "等待用户确认",
			"fallbackPlainText": "等待用户确认",
			"committedAt":       "",
		},
	}, nil
}

func (e *steerPauseCompletionExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.mu.Lock()
	e.calls++
	e.mu.Unlock()
	if _, err := e.commands.Steer(
		ctx, e.userID, request.RunID, "steer-with-pause", "先应用新目标",
	); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	if _, err := e.commands.Pause(
		ctx, e.userID, request.RunID, "pause-with-steer", "新目标暂停等待",
	); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	return completionBoundaryResult(request, true), nil
}

func (e *steerPauseCompletionExecutor) callCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.calls
}

func goalPlanCompletedForTest(run runruntime.Run, goalRevision int64) bool {
	wantID := "plan:" + run.RunID + ":goal:" + strconv.FormatInt(goalRevision, 10)
	wantDigest := goalDigestForTest(run)
	for _, item := range run.Items {
		if item.ItemID == wantID && item.Kind == generated.AssistantRunItemKindPlan &&
			item.Status == generated.AssistantRunItemStatusCompleted &&
			item.TaskID == "task_root" &&
			exactGoalRevisionForTest(item.Payload["goalRevision"], goalRevision) &&
			item.Payload["goalDigest"] == wantDigest {
			return true
		}
	}
	return false
}

func exactGoalRevisionForTest(value any, want int64) bool {
	switch typed := value.(type) {
	case int:
		return int64(typed) == want
	case int32:
		return int64(typed) == want
	case int64:
		return typed == want
	case float64:
		return typed == float64(want)
	default:
		return false
	}
}

func setGoalPlanDigestForTest(run *runruntime.Run) {
	wantID := "plan:" + run.RunID + ":goal:" + strconv.FormatInt(run.GoalRevision, 10)
	for index := range run.Items {
		if run.Items[index].ItemID == wantID {
			run.Items[index].Payload["goalDigest"] = goalDigestForTest(*run)
			return
		}
	}
}

func goalPlanItemForTest(run runruntime.Run) runruntime.RunItem {
	now := time.Now().UTC()
	return runruntime.RunItem{
		ItemID: "plan:" + run.RunID + ":goal:" + strconv.FormatInt(run.GoalRevision, 10),
		Kind:   generated.AssistantRunItemKindPlan, Status: generated.AssistantRunItemStatusCompleted,
		Sequence: int64(len(run.Items) + 1), TaskID: "task_root", Summary: "并发目标审计",
		Payload: map[string]any{
			"goalRevision": run.GoalRevision,
			"goalDigest":   goalDigestForTest(run),
		},
		StartedAt: now, CompletedAt: now,
	}
}

func goalDigestForTest(run runruntime.Run) string {
	payload := struct {
		GoalRevision  int64  `json:"goalRevision"`
		EffectiveGoal string `json:"effectiveGoal"`
	}{GoalRevision: run.GoalRevision, EffectiveGoal: run.EffectiveGoal()}
	encoded, err := json.Marshal(struct {
		Kind    string `json:"kind"`
		Payload any    `json:"payload"`
	}{Kind: "assistant_run_goal_chain", Payload: payload})
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(sum[:])
}
