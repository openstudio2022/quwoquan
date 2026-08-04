// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package local_contract

import (
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestDurableExecutorProjectsActualAgentProcessesIntoTaskGraphPatches(
	t *testing.T,
) {
	executor, _, _ := durablePresentationExecutor(
		t,
		&durablePresentationContextResolver{},
	)
	request := durablePresentationRequest(t)
	request.TaskGraph = runruntime.TaskGraph{
		GraphRevision: 1,
		Tasks: []runruntime.TaskNode{{
			TaskID: "task_root",
			Goal:   request.Goal,
			Status: generated.AssistantTaskStatusRunning,
		}},
	}
	updates := make([]runruntime.ExecutionItemUpdate, 0, 8)
	_, err := executor.Execute(
		t.Context(),
		request,
		func(update runruntime.ExecutionItemUpdate) error {
			updates = append(updates, update)
			return nil
		},
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	started := map[string]runruntime.ExecutionItemUpdate{}
	completed := map[string]bool{}
	hasDependency := false
	for _, update := range updates {
		// Budget receipts are first-class RunItem updates and intentionally do
		// not masquerade as TaskGraph patches.
		if update.Task == nil {
			continue
		}
		if update.TaskID == "task_root" {
			t.Fatalf("process update has no durable task patch: %#v", update)
		}
		switch update.Status {
		case generated.AssistantRunItemStatusStarted:
			started[update.TaskID] = update
			if len(update.Task.Dependencies) > 0 {
				hasDependency = true
			}
		case generated.AssistantRunItemStatusCompleted:
			completed[update.TaskID] = true
		}
	}
	if len(started) < 3 || len(completed) != len(started) || !hasDependency {
		t.Fatalf(
			"actual process DAG was not projected: started=%#v completed=%#v",
			started,
			completed,
		)
	}
}
