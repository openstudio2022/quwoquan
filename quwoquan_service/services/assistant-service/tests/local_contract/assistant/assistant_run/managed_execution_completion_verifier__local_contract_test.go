// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type managedExecutionUnmarkedExecutor struct{}

func (*managedExecutionUnmarkedExecutor) Execute(
	context.Context,
	runruntime.ExecutionRequest,
	func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	return runruntime.ExecutionResult{}, nil
}

type managedExecutionDisabledVerifierExecutor struct {
	managedExecutionUnmarkedExecutor
}

func (*managedExecutionDisabledVerifierExecutor) VerifiesCompletionWithinExecutionBudget() bool {
	return false
}

func TestManagedRunExecutorPreservesProductionCompletionVerifierMarker(t *testing.T) {
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{},
		time.Now,
	)
	managed := runruntime.NewManagedRunExecutor(
		orchestration.NewDurableRunExecutor(loop),
	)
	if !managed.VerifiesCompletionWithinExecutionBudget() {
		t.Fatal("managed production executor erased the in-execution completion verifier marker")
	}
}

func TestManagedRunExecutorDoesNotInventCompletionVerifierMarker(t *testing.T) {
	for name, executor := range map[string]runruntime.RunExecutor{
		"unmarked": &managedExecutionUnmarkedExecutor{},
		"disabled": &managedExecutionDisabledVerifierExecutor{},
	} {
		t.Run(name, func(t *testing.T) {
			managed := runruntime.NewManagedRunExecutor(executor)
			if managed.VerifiesCompletionWithinExecutionBudget() {
				t.Fatal("managed executor invented an enabled completion verifier marker")
			}
		})
	}

	var absent *runruntime.ManagedRunExecutor
	if absent.VerifiesCompletionWithinExecutionBudget() {
		t.Fatal("nil managed executor reported an enabled completion verifier marker")
	}
}

var _ runruntime.InExecutionCompletionVerifier = (*runruntime.ManagedRunExecutor)(nil)
