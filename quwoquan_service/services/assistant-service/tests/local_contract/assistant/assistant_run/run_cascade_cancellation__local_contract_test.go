// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type childRegistryStub struct {
	children []runruntime.ChildExecution
	fenced   bool
}

func (s *childRegistryStub) FenceAndList(
	context.Context,
	string,
) ([]runruntime.ChildExecution, error) {
	s.fenced = true
	return append([]runruntime.ChildExecution{}, s.children...), nil
}

type childExecutionSpy struct {
	id        string
	kind      runruntime.ChildExecutionKind
	cancelErr error
	awaitErr  error
	mu        sync.Mutex
	cancelled bool
	awaited   bool
}

func (s *childExecutionSpy) ExecutionID() string                 { return s.id }
func (s *childExecutionSpy) Kind() runruntime.ChildExecutionKind { return s.kind }
func (s *childExecutionSpy) Cancel(context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cancelled = true
	return s.cancelErr
}
func (s *childExecutionSpy) AwaitStopped(context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.awaited = true
	return s.awaitErr
}

func TestRunCancellationFencesAndAwaitsToolsAndSubagentsBeforeTerminalState(t *testing.T) {
	now := time.Now().UTC()
	run := newDurableRun(t, now)
	if err := run.Transition(generated.AssistantRunStateOrienting, "", now); err != nil {
		t.Fatal(err)
	}
	if err := run.Transition(generated.AssistantRunStatePlanning, "", now); err != nil {
		t.Fatal(err)
	}
	if err := run.Transition(generated.AssistantRunStateExecuting, "", now); err != nil {
		t.Fatal(err)
	}
	tool := &childExecutionSpy{id: "tool_1", kind: runruntime.ChildTool}
	subagent := &childExecutionSpy{id: "subagent_1", kind: runruntime.ChildSubagent}
	registry := &childRegistryStub{children: []runruntime.ChildExecution{tool, subagent}}
	coordinator := runruntime.NewCancellationCoordinator(registry, time.Second)
	if err := coordinator.Cancel(context.Background(), &run, "user cancelled", now.Add(time.Second)); err != nil {
		t.Fatalf("Cancel() error = %v", err)
	}
	if !registry.fenced || !tool.cancelled || !tool.awaited || !subagent.cancelled || !subagent.awaited {
		t.Fatalf("cleanup = registry %#v tool %#v subagent %#v", registry, tool, subagent)
	}
	if run.State != generated.AssistantRunStateCancelled || run.TerminalReason != "user cancelled" {
		t.Fatalf("run terminal state = %#v", run)
	}
	if err := coordinator.Cancel(context.Background(), &run, "duplicate", now); err != nil {
		t.Fatalf("idempotent Cancel() error = %v", err)
	}
}

func TestRunCancellationDoesNotWriteTerminalStateWhenChildCleanupFails(t *testing.T) {
	now := time.Now().UTC()
	run := newDurableRun(t, now)
	tool := &childExecutionSpy{
		id:        "tool_1",
		kind:      runruntime.ChildTool,
		cancelErr: errors.New("provider did not acknowledge cancellation"),
	}
	registry := &childRegistryStub{children: []runruntime.ChildExecution{tool}}
	coordinator := runruntime.NewCancellationCoordinator(registry, time.Second)
	if err := coordinator.Cancel(context.Background(), &run, "user cancelled", now); err == nil {
		t.Fatal("Cancel() unexpectedly succeeded")
	}
	if run.State == generated.AssistantRunStateCancelled || tool.awaited {
		t.Fatalf("dishonest terminal state or await = run %s tool %#v", run.State, tool)
	}
}
