// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestDurableCompletionCapsuleCorruptionFailsClosed(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"missing", func(payload map[string]any) { delete(payload, "completionCapsule") }},
		{"digest_mismatch", func(payload map[string]any) {
			payload["completionDigest"] = "sha256:" + strings.Repeat("0", 64)
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			base := newMemoryRunRepository()
			repository := &interruptAfterCommitRepository{
				memoryRunRepository: base, kind: "answer_delta",
				state: generated.AssistantRunStateExecuting,
			}
			queue := newMemoryWorkQueue()
			run, err := workerCommandService(base).Start(t.Context(), runruntime.StartCommand{
				UserID: "user-corrupt-" + test.name, SessionID: "session-corrupt",
				ClientRequestID: "request-corrupt-" + test.name,
				InputText:       "验证损坏 capsule 失败关闭",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &countingTerminalExecutor{}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(repository, queue, executor, "worker-corrupt-a")
			if worked, processErr := worker.ProcessNext(t.Context()); !worked || !errors.Is(processErr, errInjectedTerminalBoundary) {
				t.Fatalf("persist capsule: worked=%t err=%v", worked, processErr)
			}
			corruptCompletionCapsule(t, base, run.RunID, test.mutate)
			worker = runruntime.NewDurableWorker(repository, queue, executor, "worker-corrupt-b")
			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("fail corrupted capsule: worked=%t err=%v", worked, processErr)
			}
			failed, err := base.Load(t.Context(), run.RunID)
			if err != nil || failed.State != generated.AssistantRunStateFailed ||
				!strings.Contains(failed.TerminalReason, "completion_capsule_corrupt") ||
				failed.TerminalSnapshot == nil || failed.TerminalSnapshot.Failure == nil {
				t.Fatalf("corrupted capsule did not fail closed: run=%#v err=%v", failed, err)
			}
			if executor.callCount() != 1 {
				t.Fatalf("corrupted capsule repeated executor: calls=%d", executor.callCount())
			}
		})
	}
}

func TestDurableCompletionCapsuleRejectsUnboundedOrPrivateData(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*runruntime.ExecutionResult)
	}{
		{"oversized_answer", func(result *runruntime.ExecutionResult) {
			result.AnswerText = strings.Repeat("答", 12001)
		}},
		{"oversized_artifact_ref", func(result *runruntime.ExecutionResult) {
			result.ArtifactRefs = append(result.ArtifactRefs, strings.Repeat("a", 1025))
		}},
		{"oversized_process_field", func(result *runruntime.ExecutionResult) {
			result.Processes[0].Summary = strings.Repeat("进", 2049)
		}},
		{"oversized_reference_field", func(result *runruntime.ExecutionResult) {
			result.Processes[0].AcceptedReferences[0].SourceID = strings.Repeat("s", 513)
		}},
		{"provider_diagnostics", func(result *runruntime.ExecutionResult) {
			result.Presentation["providerDiagnostics"] = map[string]any{"trace": "private"}
		}},
		{"credential_url", func(result *runruntime.ExecutionResult) {
			result.Processes[0].AcceptedReferences[0].Destination.URL =
				"https://user:secret@example.com/evidence"
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repository := newMemoryRunRepository()
			queue := newMemoryWorkQueue()
			run, err := workerCommandService(repository).Start(t.Context(), runruntime.StartCommand{
				UserID: "user-private-" + test.name, SessionID: "session-private",
				ClientRequestID: "request-private-" + test.name,
				InputText:       "拒绝不安全终态数据",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &mutatingTerminalExecutor{mutate: test.mutate}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(repository, queue, executor, "worker-private")
			if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
				t.Fatalf("process unsafe result: worked=%t err=%v", worked, err)
			}
			failed, err := repository.Load(t.Context(), run.RunID)
			if err != nil || failed.State != generated.AssistantRunStateFailed ||
				!strings.Contains(failed.TerminalReason, "completion_capsule_rejected") {
				t.Fatalf("unsafe result was persisted: run=%#v err=%v", failed, err)
			}
			for _, item := range failed.Items {
				if item.Kind == generated.AssistantRunItemKindFinalAnswer {
					t.Fatalf("unsafe completion created final answer item: %#v", item)
				}
			}
		})
	}
}

func TestDurableCompletionWithoutPresentationCompletesWithoutProjectionEvents(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(t.Context(), runruntime.StartCommand{
		UserID: "user-no-presentation", SessionID: "session-no-presentation",
		ClientRequestID: "request-no-presentation", InputText: "完成纯文本答案",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	executor := &mutatingTerminalExecutor{mutate: func(result *runruntime.ExecutionResult) {
		result.Presentation = nil
	}}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(repository, queue, executor, "worker-no-presentation")
	if worked, err := worker.ProcessNext(t.Context()); err != nil || !worked {
		t.Fatalf("complete without presentation: worked=%t err=%v", worked, err)
	}
	completed, err := repository.Load(t.Context(), run.RunID)
	if err != nil || completed.State != generated.AssistantRunStateCompleted ||
		len(completed.PresentationDocument) != 0 {
		t.Fatalf("empty presentation did not remain optional: run=%#v err=%v", completed, err)
	}
	events, err := repository.EventsAfter(t.Context(), run.RunID, 0, 256)
	if err != nil {
		t.Fatalf("read journal: %v", err)
	}
	for _, event := range events {
		if event.Kind == "presentation_snapshot" || event.Kind == "presentation_commit" ||
			event.Kind == "presentation_patch" {
			t.Fatalf("empty presentation emitted projection event: %#v", event)
		}
	}
}

func TestCommittedPresentationReplacementRecoveryKeepsRevisionBounded(t *testing.T) {
	for _, boundary := range []string{"presentation_snapshot", "presentation_commit"} {
		t.Run(boundary, func(t *testing.T) {
			base := newMemoryRunRepository()
			repository := &interruptAfterCommitRepository{
				memoryRunRepository: base, kind: boundary,
				state: generated.AssistantRunStateSynthesizing,
			}
			queue := newMemoryWorkQueue()
			run, err := workerCommandService(base).Start(t.Context(), runruntime.StartCommand{
				UserID: "user-replace-" + boundary, SessionID: "session-replace",
				ClientRequestID: "request-replace-" + boundary,
				InputText:       "替换已提交展示",
			})
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			base.mu.Lock()
			seed := base.runs[run.RunID]
			seed.PresentationDocument = map[string]any{
				"templateRef": "assistant.answer.previous", "templateDigest": "sha256:" + strings.Repeat("a", 64),
				"revision": int64(4), "rootNodeId": "previous-root",
				"fallbackPlainText": "旧答案", "committedAt": "2026-08-08T00:00:00Z",
			}
			base.runs[run.RunID] = seed
			base.mu.Unlock()
			executor := &countingTerminalExecutor{}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(repository, queue, executor, "worker-replace-a")
			if worked, processErr := worker.ProcessNext(t.Context()); !worked || !errors.Is(processErr, errInjectedTerminalBoundary) {
				t.Fatalf("interrupt replacement: worked=%t err=%v", worked, processErr)
			}
			worker = runruntime.NewDurableWorker(repository, queue, executor, "worker-replace-b")
			if worked, processErr := worker.ProcessNext(t.Context()); processErr != nil || !worked {
				t.Fatalf("resume replacement: worked=%t err=%v", worked, processErr)
			}
			completed, err := base.Load(t.Context(), run.RunID)
			if err != nil || completed.State != generated.AssistantRunStateCompleted ||
				completed.PresentationDocument["revision"] != int64(6) || executor.callCount() != 1 {
				t.Fatalf("replacement revision inflated: run=%#v calls=%d err=%v", completed, executor.callCount(), err)
			}
			events, err := base.EventsAfter(t.Context(), run.RunID, 0, 256)
			if err != nil {
				t.Fatalf("read journal: %v", err)
			}
			counts := map[string]int{}
			for _, event := range events {
				if event.Kind == "presentation_snapshot" {
					counts[event.Kind]++
					if event.Payload["baseRevision"] != int64(4) || event.Payload["revision"] != int64(5) {
						t.Fatalf("snapshot revision chain=%#v", event.Payload)
					}
				}
				if event.Kind == "presentation_commit" {
					counts[event.Kind]++
					if event.Payload["baseRevision"] != int64(5) || event.Payload["revision"] != int64(6) {
						t.Fatalf("commit revision chain=%#v", event.Payload)
					}
				}
			}
			if counts["presentation_snapshot"] != 1 || counts["presentation_commit"] != 1 {
				t.Fatalf("replacement events duplicated: %#v", counts)
			}
		})
	}
}

type mutatingTerminalExecutor struct {
	mutate func(*runruntime.ExecutionResult)
}

func (e *mutatingTerminalExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	result, err := (&successfulRunExecutor{}).Execute(ctx, request, emit)
	if err == nil {
		e.mutate(&result)
	}
	return result, err
}

func corruptCompletionCapsule(
	t *testing.T,
	repository *memoryRunRepository,
	runID string,
	mutate func(map[string]any),
) {
	t.Helper()
	repository.mu.Lock()
	defer repository.mu.Unlock()
	run := repository.runs[runID]
	for index := range run.Items {
		if run.Items[index].Kind == generated.AssistantRunItemKindFinalAnswer {
			mutate(run.Items[index].Payload)
			repository.runs[runID] = run
			return
		}
	}
	t.Fatal("completion answer item missing before corruption")
}
