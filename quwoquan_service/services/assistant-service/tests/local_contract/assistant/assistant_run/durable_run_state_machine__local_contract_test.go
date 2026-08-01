// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestAssistantRunTaskGraphEnforcesDAGAndDependencyReadiness(t *testing.T) {
	graph, err := runruntime.NewTaskGraph([]runruntime.TaskNode{
		{TaskID: "research", Goal: "collect evidence"},
		{TaskID: "synthesize", Goal: "write answer", Dependencies: []string{"research"}},
	})
	if err != nil {
		t.Fatalf("NewTaskGraph() error = %v", err)
	}
	if graph.Tasks[0].Status != generated.AssistantTaskStatusReady || graph.Tasks[1].Status != generated.AssistantTaskStatusPending {
		t.Fatalf("initial statuses = %s, %s", graph.Tasks[0].Status, graph.Tasks[1].Status)
	}
	if err := graph.Start("synthesize"); !errors.Is(err, runruntime.ErrTaskNotReady) {
		t.Fatalf("Start(dependent) error = %v", err)
	}
	if err := graph.Start("research"); err != nil {
		t.Fatalf("Start(research) error = %v", err)
	}
	if err := graph.Complete("research", []string{"artifact:source"}, runruntime.TaskVerification{
		Requirements: []string{"source quality"},
		EvidenceRefs: []string{"artifact:source"},
		Passed:       true,
	}); err != nil {
		t.Fatalf("Complete(research) error = %v", err)
	}
	if graph.Tasks[1].Status != generated.AssistantTaskStatusReady {
		t.Fatalf("dependent status = %s", graph.Tasks[1].Status)
	}

	_, err = runruntime.NewTaskGraph([]runruntime.TaskNode{
		{TaskID: "a", Goal: "a", Dependencies: []string{"b"}},
		{TaskID: "b", Goal: "b", Dependencies: []string{"a"}},
	})
	if !errors.Is(err, runruntime.ErrInvalidTaskGraph) {
		t.Fatalf("cyclic NewTaskGraph() error = %v", err)
	}
}

func TestAssistantRunAppliesSteerAndPauseOnlyAtSafeBoundary(t *testing.T) {
	now := time.Date(2026, 7, 31, 3, 0, 0, 0, time.UTC)
	run := newDurableRun(t, now)
	if err := run.Transition(generated.AssistantRunStateOrienting, "", now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := run.Transition(generated.AssistantRunStatePlanning, "", now.Add(2*time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := run.Transition(generated.AssistantRunStateExecuting, "", now.Add(3*time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := run.RequestSteer("add current weather evidence", now.Add(4*time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := run.RequestPause("user requested pause", now.Add(5*time.Second)); err != nil {
		t.Fatal(err)
	}
	if run.State != generated.AssistantRunStateExecuting || len(run.PendingSteer) != 1 || !run.PauseRequested {
		t.Fatalf("unsafe-boundary mutation = state %s steer %#v pause %v", run.State, run.PendingSteer, run.PauseRequested)
	}
	if err := run.Transition(generated.AssistantRunStateObserving, "", now.Add(6*time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := run.ApplySafeBoundary(now.Add(7 * time.Second)); err != nil {
		t.Fatal(err)
	}
	if run.State != generated.AssistantRunStatePaused || run.GoalRevision != 2 || len(run.GoalHistory) != 1 {
		t.Fatalf("safe-boundary result = %#v", run)
	}
	if err := run.Resume(now.Add(8 * time.Second)); err != nil {
		t.Fatal(err)
	}
	if run.State != generated.AssistantRunStateObserving {
		t.Fatalf("resumed state = %s", run.State)
	}
}

func TestAssistantRunJournalRejectsReasoningTraceAndCheckpointKeepsCanonicalFacts(t *testing.T) {
	now := time.Date(2026, 7, 31, 4, 0, 0, 0, time.UTC)
	run := newDurableRun(t, now)
	if err := run.BeginItem(
		"item_bad",
		generated.AssistantRunItemKindDecisionSummary,
		"research",
		"public summary",
		map[string]any{"nested": map[string]any{"chain_of_thought": "secret"}},
		now,
	); !errors.Is(err, runruntime.ErrUnsafePayload) {
		t.Fatalf("BeginItem(reasoning trace) error = %v", err)
	}
	if err := run.BeginItem(
		"item_ok",
		generated.AssistantRunItemKindEvidence,
		"research",
		"verified two sources",
		map[string]any{"sourceCount": 2},
		now.Add(time.Second),
	); err != nil {
		t.Fatal(err)
	}
	if err := run.CompleteItem(
		"item_ok",
		generated.AssistantRunItemStatusCompleted,
		[]string{"artifact:b", "artifact:a", "artifact:a"},
		"",
		now.Add(2*time.Second),
	); err != nil {
		t.Fatal(err)
	}
	checkpoint, err := run.CreateCheckpoint(
		"checkpoint_1",
		"answer with cited evidence",
		[]string{"selected primary sources"},
		"",
		map[string]int64{"tokens": 5000},
		now.Add(3*time.Second),
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := checkpoint.EvidenceRefs; len(got) != 2 || got[0] != "artifact:a" || got[1] != "artifact:b" {
		t.Fatalf("checkpoint evidence = %#v", got)
	}
	if run.DefinitionOfDone.Outcome != "answer with cited evidence" || len(run.DefinitionOfDone.VerificationRequirements) != 1 {
		t.Fatalf("DefinitionOfDone was compacted away: %#v", run.DefinitionOfDone)
	}
}

func TestAssistantRunVerifierBlocksDishonestCompletion(t *testing.T) {
	now := time.Date(2026, 7, 31, 5, 0, 0, 0, time.UTC)
	run := newDurableRun(t, now)
	for _, state := range []generated.AssistantRunState{
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateExecuting,
	} {
		if err := run.Transition(state, "", now); err != nil {
			t.Fatal(err)
		}
	}
	if err := run.TaskGraph.Start("research"); err != nil {
		t.Fatal(err)
	}
	if err := run.TaskGraph.Complete("research", []string{"artifact:report"}, runruntime.TaskVerification{
		Requirements: []string{"citations verified"},
		EvidenceRefs: []string{"artifact:report"},
		Passed:       true,
	}); err != nil {
		t.Fatal(err)
	}
	for _, state := range []generated.AssistantRunState{
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateVerifying,
	} {
		if err := run.Transition(state, "", now); err != nil {
			t.Fatal(err)
		}
	}
	rejected := runruntime.VerifyDefinitionOfDone(
		run.DefinitionOfDone,
		[]runruntime.VerificationEvidence{{Requirement: "citations verified", Passed: true}},
	)
	if rejected.Accepted || len(rejected.Failed) != 1 {
		t.Fatalf("artifact-free verdict = %#v", rejected)
	}
	if err := run.AcceptVerification(rejected, now); !errors.Is(err, runruntime.ErrCompletionRejected) {
		t.Fatalf("AcceptVerification(rejected) error = %v", err)
	}
	accepted := runruntime.VerifyDefinitionOfDone(
		run.DefinitionOfDone,
		[]runruntime.VerificationEvidence{{
			Requirement:  "citations verified",
			Passed:       true,
			EvidenceRefs: []string{"artifact:report"},
		}},
	)
	if err := run.AcceptVerification(accepted, now.Add(time.Second)); err != nil {
		t.Fatalf("AcceptVerification(accepted) error = %v", err)
	}
	if run.State != generated.AssistantRunStateCompleted {
		t.Fatalf("final state = %s", run.State)
	}
	if err := run.Transition(generated.AssistantRunStateExecuting, "", now); !errors.Is(err, runruntime.ErrInvalidTransition) {
		t.Fatalf("terminal transition error = %v", err)
	}
}

func newDurableRun(t *testing.T, now time.Time) runruntime.Run {
	t.Helper()
	graph, err := runruntime.NewTaskGraph([]runruntime.TaskNode{{
		TaskID: "research",
		Goal:   "collect and verify evidence",
	}})
	if err != nil {
		t.Fatal(err)
	}
	run, err := runruntime.NewRun(
		"run_1",
		generated.AssistantReasoningProfileDeep,
		runruntime.DefinitionOfDone{
			Outcome:                  "answer with cited evidence",
			Constraints:              []string{"public sources only"},
			VerificationRequirements: []string{"citations verified"},
			FrozenAt:                 now,
		},
		graph,
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	return run
}
