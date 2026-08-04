package runruntime

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func (w *DurableWorker) persistExecutionUpdate(
	ctx context.Context,
	runID string,
	update ExecutionItemUpdate,
) error {
	kind := "process_append"
	if update.Budget != nil {
		kind = "checkpoint_committed"
	} else if update.Status != generated.AssistantRunItemStatusStarted {
		kind = "process_commit"
	}
	replanned := false
	_, err := w.commitMutation(ctx, runID, kind, func(run *Run, now time.Time) error {
		if update.Budget != nil {
			if err := run.RecordBudgetConsumption(*update.Budget, now); err != nil {
				return err
			}
			if strings.TrimSpace(update.ItemID) == "" {
				return nil
			}
		}
		if err := applyExecutionTaskUpdate(&run.TaskGraph, update); err != nil {
			return err
		}
		if err := applyExecutionItemUpdate(run, update, now); err != nil {
			return err
		}
		if update.Status != generated.AssistantRunItemStatusCompleted ||
			len(run.PendingSteer) == 0 {
			return nil
		}
		previousGoalRevision := run.GoalRevision
		run.applyPendingSteer(now)
		if run.GoalRevision == previousGoalRevision {
			return nil
		}
		replanned = true
		return appendGoalRevisionPlanItem(run, now)
	})
	if err != nil {
		return err
	}
	if replanned {
		return ErrExecutionReplanned
	}
	return nil
}

func applyExecutionTaskUpdate(
	graph *TaskGraph,
	update ExecutionItemUpdate,
) error {
	if update.Task == nil {
		return nil
	}
	index := graph.taskIndex(update.TaskID)
	if index < 0 {
		if update.Status != generated.AssistantRunItemStatusStarted {
			return ErrTaskNotReady
		}
		if err := graph.Add(TaskNode{
			TaskID:       update.TaskID,
			Goal:         update.Task.Goal,
			Dependencies: append([]string{}, update.Task.Dependencies...),
			OwnerAgent:   update.Task.OwnerAgent,
			Budget:       update.Task.Budget,
		}); err != nil {
			return err
		}
		index = graph.taskIndex(update.TaskID)
	}
	task := graph.Tasks[index]
	if !sameExecutionTaskDefinition(task, *update.Task) {
		return ErrRevisionConflict
	}
	switch update.Status {
	case generated.AssistantRunItemStatusStarted:
		switch task.Status {
		case generated.AssistantTaskStatusReady:
			return graph.Start(update.TaskID)
		case generated.AssistantTaskStatusRunning,
			generated.AssistantTaskStatusCompleted:
			return nil
		default:
			return ErrTaskNotReady
		}
	case generated.AssistantRunItemStatusCompleted:
		switch task.Status {
		case generated.AssistantTaskStatusRunning:
			return graph.Complete(
				update.TaskID,
				update.ArtifactRefs,
				TaskVerification{Passed: true},
			)
		case generated.AssistantTaskStatusCompleted:
			return nil
		default:
			return ErrTaskNotReady
		}
	case generated.AssistantRunItemStatusFailed:
		if task.Status == generated.AssistantTaskStatusFailed {
			return nil
		}
		return graph.Fail(update.TaskID, update.Summary, false)
	case generated.AssistantRunItemStatusCancelled:
		if task.Status == generated.AssistantTaskStatusCancelled {
			return nil
		}
		if task.Status == generated.AssistantTaskStatusCompleted {
			return ErrTaskNotReady
		}
		graph.Tasks[index].Status = generated.AssistantTaskStatusCancelled
		graph.Tasks[index].BlockReason = strings.TrimSpace(update.Summary)
		graph.GraphRevision++
		return nil
	default:
		return ErrItemStateConflict
	}
}

func applyExecutionItemUpdate(
	run *Run,
	update ExecutionItemUpdate,
	now time.Time,
) error {
	for index := range run.Items {
		item := run.Items[index]
		if item.ItemID != update.ItemID {
			continue
		}
		if item.Kind != update.Kind || item.TaskID != strings.TrimSpace(update.TaskID) {
			return ErrItemStateConflict
		}
		if update.Status == generated.AssistantRunItemStatusStarted {
			if item.Status == generated.AssistantRunItemStatusStarted ||
				item.Status == generated.AssistantRunItemStatusCompleted {
				return nil
			}
			return ErrItemStateConflict
		}
		if item.Status == update.Status {
			if update.Status != generated.AssistantRunItemStatusStarted &&
				(!sameStringSequence(
					uniqueSorted(item.ArtifactRefs),
					uniqueSorted(update.ArtifactRefs),
				) || (strings.TrimSpace(update.Summary) != "" &&
					item.Summary != strings.TrimSpace(update.Summary))) {
				return ErrRevisionConflict
			}
			return nil
		}
		return run.CompleteItem(
			update.ItemID,
			update.Status,
			update.ArtifactRefs,
			update.Summary,
			now,
		)
	}
	if update.Status != generated.AssistantRunItemStatusStarted {
		return ErrItemStateConflict
	}
	return run.BeginItem(
		update.ItemID,
		update.Kind,
		update.TaskID,
		update.Summary,
		update.Payload,
		now,
	)
}

func sameExecutionTaskDefinition(
	task TaskNode,
	update ExecutionTaskUpdate,
) bool {
	return task.Goal == strings.TrimSpace(update.Goal) &&
		task.OwnerAgent == strings.TrimSpace(update.OwnerAgent) &&
		task.Budget == update.Budget &&
		sameStringSequence(task.Dependencies, update.Dependencies)
}

func sameStringSequence(left []string, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if strings.TrimSpace(left[index]) != strings.TrimSpace(right[index]) {
			return false
		}
	}
	return true
}

func appendGoalRevisionPlanItem(run *Run, now time.Time) error {
	itemID := "plan:" + run.RunID + ":goal:" + fmt.Sprint(run.GoalRevision)
	for _, item := range run.Items {
		if item.ItemID == itemID {
			return nil
		}
	}
	summary := "目标约束已更新，执行计划将在下一安全边界重建"
	if err := run.BeginItem(
		itemID,
		generated.AssistantRunItemKindPlan,
		"task_root",
		summary,
		map[string]any{"goalRevision": run.GoalRevision},
		now,
	); err != nil {
		return err
	}
	return run.CompleteItem(
		itemID,
		generated.AssistantRunItemStatusCompleted,
		nil,
		summary,
		now,
	)
}

func (w *DurableWorker) persistPresentation(
	ctx context.Context,
	current Run,
	presentation map[string]any,
) (Run, error) {
	if len(presentation) == 0 {
		return current, nil
	}
	nextRevision := int64(1)
	if revision, ok := presentationRevision(current.PresentationDocument["revision"]); ok {
		nextRevision = revision + 1
	}
	document := cloneMap(presentation)
	document["revision"] = nextRevision
	document["committedAt"] = ""
	run, err := w.commitMutation(ctx, current.RunID, "presentation_snapshot", func(
		run *Run,
		now time.Time,
	) error {
		return run.SetPresentationDocument(document, now)
	})
	observePresentationProjection("snapshot", err)
	if err != nil {
		return Run{}, err
	}
	committed, err := w.commitMutation(ctx, run.RunID, "presentation_commit", func(
		run *Run,
		now time.Time,
	) error {
		return run.CommitPresentation(now)
	})
	observePresentationProjection("commit", err)
	return committed, err
}

func (w *DurableWorker) commitMutation(
	ctx context.Context,
	runID string,
	eventKind string,
	change func(*Run, time.Time) error,
) (Run, error) {
	for attempt := 0; attempt < 4; attempt++ {
		run, err := w.repository.Load(ctx, runID)
		if err != nil {
			return Run{}, err
		}
		if terminalRunState(run.State) {
			return run, nil
		}
		expectedRevision := run.Revision
		if err := change(&run, w.now().UTC()); err != nil {
			return Run{}, err
		}
		if run.Revision == expectedRevision {
			return run, nil
		}
		run.JournalSequence++
		event := JournalEvent{
			EventID:   run.RunID + ":" + int64String(run.JournalSequence),
			RunID:     run.RunID,
			Sequence:  run.JournalSequence,
			Revision:  run.Revision,
			Kind:      strings.TrimSpace(eventKind),
			Payload:   mutationPayload(run, eventKind),
			CreatedAt: w.now().UTC(),
		}
		if err := w.repository.Commit(
			ctx,
			expectedRevision,
			run,
			[]JournalEvent{event},
			nil,
		); err == nil {
			return run, nil
		} else if !errors.Is(err, ErrRevisionConflict) {
			return Run{}, err
		}
	}
	return Run{}, ErrRevisionConflict
}

func mutationPayload(run Run, eventKind string) map[string]any {
	if eventKind == "completed" || eventKind == "failed" || eventKind == "cancelled" {
		return terminalMutationPayload(run, eventKind)
	}
	payload := map[string]any{
		"status":       run.State.WireName(),
		"runRevision":  run.Revision,
		"goalRevision": run.GoalRevision,
	}
	switch eventKind {
	case "answer_delta":
		for index := len(run.Items) - 1; index >= 0; index-- {
			if run.Items[index].Kind == generated.AssistantRunItemKindFinalAnswer {
				payload["text"] = run.Items[index].Payload["text"]
				break
			}
		}
	case "process_append", "process_commit":
		if process := latestVisibleProcess(run); process != nil {
			payload["process"] = process
		}
	case "presentation_snapshot":
		revision, _ := presentationRevision(run.PresentationDocument["revision"])
		payload["baseRevision"] = int64(0)
		payload["revision"] = revision
		payload["document"] = cloneMap(run.PresentationDocument)
	case "presentation_commit":
		revision, _ := presentationRevision(run.PresentationDocument["revision"])
		payload["baseRevision"] = revision - 1
		payload["revision"] = revision
	}
	return payload
}

func terminalMutationPayload(run Run, eventKind string) map[string]any {
	if run.TerminalSnapshot == nil {
		return map[string]any{
			"status":      run.State.WireName(),
			"finalAnswer": "",
			"processes":   []any{},
		}
	}
	payload := map[string]any{
		"status":      run.State.WireName(),
		"finalAnswer": run.TerminalSnapshot.AnswerText,
		"processes":   run.TerminalSnapshot.Processes,
	}
	if eventKind == "failed" && run.TerminalSnapshot.Failure != nil {
		payload["runtimeFailure"] = run.TerminalSnapshot.Failure
	}
	return payload
}

// TerminalReplayEvent projects the no-TTL terminal snapshot into the one
// terminal SSE event required after the bounded journal has expired.

func TerminalReplayEvent(run Run) (JournalEvent, bool) {
	if run.CompletedAt == nil || run.TerminalSnapshot == nil ||
		!terminalRunState(run.State) || run.JournalSequence <= 0 {
		return JournalEvent{}, false
	}
	kind := run.State.WireName()
	return JournalEvent{
		EventID:   run.RunID + ":terminal-replay",
		RunID:     run.RunID,
		Sequence:  run.JournalSequence,
		Revision:  run.Revision,
		Kind:      kind,
		Payload:   mutationPayload(run, kind),
		CreatedAt: run.CompletedAt.UTC(),
	}, true
}

func latestVisibleProcess(run Run) map[string]any {
	for index := len(run.Items) - 1; index >= 0; index-- {
		item := run.Items[index]
		if item.Kind == generated.AssistantRunItemKindPlan ||
			item.Kind == generated.AssistantRunItemKindFinalAnswer {
			continue
		}
		process := cloneMap(item.Payload)
		if process == nil {
			process = map[string]any{}
		}
		process["processId"] = item.ItemID
		process["order"] = item.Sequence
		process["summary"] = item.Summary
		if strings.TrimSpace(fmt.Sprint(process["scope"])) == "" {
			process["scope"] = string(item.Kind)
		}
		if strings.TrimSpace(fmt.Sprint(process["stage"])) == "" {
			process["stage"] = string(item.Kind)
		}
		switch item.Status {
		case generated.AssistantRunItemStatusStarted:
			process["status"] = "active"
		default:
			process["status"] = string(item.Status)
		}
		return process
	}
	return nil
}
