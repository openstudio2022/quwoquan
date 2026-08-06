package compaction

import (
	"context"
	"errors"
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

// AssistantRunReader is the AssistantSession-side application port for the
// immutable terminal AssistantRun snapshot. The owning AssistantRun adapter is
// wired only at the service composition root.
type AssistantRunReader interface {
	Load(context.Context, string) (runruntime.Run, error)
}

// AssistantRunTerminalCoordinator owns the AssistantRunCompleted lifecycle
// consumer declared by assistant.assistant_session. It loads the authoritative
// terminal Run, applies the bounded compaction hooks and commits the session
// summary before the source relay is allowed to acknowledge the event.
type AssistantRunTerminalCoordinator struct {
	runs      AssistantRunReader
	compactor *Service
	hooks     *runruntime.HookRegistry
}

func NewAssistantRunTerminalCoordinator(
	runs AssistantRunReader,
	compactor *Service,
	hooks *runruntime.HookRegistry,
) *AssistantRunTerminalCoordinator {
	if runs == nil || compactor == nil || hooks == nil {
		panic("assistant session terminal coordinator dependencies are required")
	}
	return &AssistantRunTerminalCoordinator{
		runs:      runs,
		compactor: compactor,
		hooks:     hooks,
	}
}

func (coordinator *AssistantRunTerminalCoordinator) HandleTerminalEvent(
	ctx context.Context,
	event runruntime.TerminalEvent,
) error {
	return coordinator.CompactSession(ctx, event)
}

func (coordinator *AssistantRunTerminalCoordinator) CompactSession(
	ctx context.Context,
	event runruntime.TerminalEvent,
) error {
	if event.Outcome != "completed" {
		return nil
	}
	run, err := coordinator.runs.Load(ctx, event.RunID)
	if err != nil {
		return err
	}
	if run.RunID != event.RunID || run.SessionID != event.SessionID ||
		run.UserID != event.UserID || run.State != assistantgenerated.AssistantRunStateCompleted {
		return errors.New("assistant terminal event does not match completed Run")
	}
	switch strings.ToLower(strings.TrimSpace(run.RequestContext.SurfaceKind)) {
	case "conversation", "circle":
		return nil
	}
	answerText := ""
	if run.TerminalSnapshot != nil {
		answerText = run.TerminalSnapshot.AnswerText
	}
	source := CompletedRunSource{
		CompletionEventID: event.EventID,
		RunID:             run.RunID,
		SessionID:         run.SessionID,
		UserID:            run.UserID,
		CurrentGoal:       run.EffectiveGoal(),
		UserInput:         run.InputText,
		AnswerText:        strings.TrimSpace(answerText),
		PendingItems:      pendingSessionItems(run.TaskGraph),
		ConfirmedSlots:    run.ConfirmedSlotSnapshot(),
		CompletedAt:       event.OccurredAt,
	}
	hookCtx := runruntime.WithExecutionHooks(ctx, coordinator.hooks, run)
	preCompact, err := runruntime.InvokeExecutionHook(
		hookCtx,
		runruntime.HookPreCompact,
		"task_root",
		"",
		map[string]any{
			"userInput":  source.UserInput,
			"answerText": source.AnswerText,
		},
	)
	if err != nil {
		return err
	}
	if preCompact.Decision != runruntime.HookAllow {
		return fmt.Errorf(
			"pre_compact hook %s: %s",
			preCompact.Decision,
			strings.TrimSpace(preCompact.Reason),
		)
	}
	if value, ok := preCompact.Data["userInput"].(string); ok &&
		strings.TrimSpace(value) != "" {
		source.UserInput = strings.TrimSpace(value)
	}
	if value, ok := preCompact.Data["answerText"].(string); ok &&
		strings.TrimSpace(value) != "" {
		source.AnswerText = strings.TrimSpace(value)
	}
	summary, err := coordinator.compactor.CompactCompletedRun(ctx, source)
	if err != nil {
		return err
	}
	postCompact, err := runruntime.InvokeExecutionHook(
		hookCtx,
		runruntime.HookPostCompact,
		"task_root",
		"",
		map[string]any{
			"summaryId": summary.SummaryID,
			"turnCount": summary.TurnCount,
			"textRunes": len([]rune(summary.Text)),
		},
	)
	if err != nil {
		return err
	}
	if postCompact.Decision != runruntime.HookAllow {
		return fmt.Errorf(
			"post_compact hook %s: %s",
			postCompact.Decision,
			strings.TrimSpace(postCompact.Reason),
		)
	}
	return nil
}

func pendingSessionItems(graph runruntime.TaskGraph) []string {
	items := make([]string, 0, len(graph.Tasks))
	for _, task := range graph.Tasks {
		switch task.Status {
		case assistantgenerated.AssistantTaskStatusCompleted,
			assistantgenerated.AssistantTaskStatusCancelled:
			continue
		}
		if value := strings.TrimSpace(task.Goal); value != "" {
			items = append(items, value)
		}
	}
	return items
}
