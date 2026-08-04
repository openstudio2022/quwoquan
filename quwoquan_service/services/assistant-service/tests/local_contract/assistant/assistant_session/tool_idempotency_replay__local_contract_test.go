// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"
	"time"

	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type toolIdempotencyRetryableError struct{}

func (toolIdempotencyRetryableError) Error() string { return "retryable dependency failure" }

func (toolIdempotencyRetryableError) RetryableToolFailure() bool { return true }

func TestToolUseIdentityIsStableAcrossWorkerReplayAndClockChanges(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	metadata := toolIdentityMetadata("stable_read_probe")
	metadata.Idempotency = toolpkg.IdempotencyReadOnly
	registry.Register(metadata, func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{Output: map[string]any{"summary": "ok"}}, nil
	})

	request := stableToolRequest()
	first, err := (orchestration.DefaultToolCoordinator{
		Now:      func() time.Time { return time.Unix(100, 0).UTC() },
		Registry: registry,
	}).Execute(t.Context(), request)
	if err != nil || first.Failure != nil {
		t.Fatalf("first execution err=%v failure=%+v", err, first.Failure)
	}
	// A replay may reconstruct the map in a different insertion order and run
	// on another worker/clock. Neither is part of the invocation identity.
	request.Input = map[string]any{
		"filters": map[string]any{"city": "杭州", "days": 3},
		"query":   "西湖路线",
	}
	second, err := (orchestration.DefaultToolCoordinator{
		Now:      func() time.Time { return time.Unix(900, 0).UTC() },
		Registry: registry,
	}).Execute(t.Context(), request)
	if err != nil || second.Failure != nil {
		t.Fatalf("second execution err=%v failure=%+v", err, second.Failure)
	}
	if first.Requested.ToolUseID != second.Requested.ToolUseID {
		t.Fatalf(
			"worker replay changed tool identity: first=%q second=%q",
			first.Requested.ToolUseID,
			second.Requested.ToolUseID,
		)
	}
	if err := rtid.Validate(first.Requested.ToolUseID); err != nil {
		t.Fatalf("stable ToolUseID is not a canonical runtime identity: %v", err)
	}

	differentStep := request
	differentStep.StepID = "tool:2"
	stepExecution, err := (orchestration.DefaultToolCoordinator{
		Registry: registry,
	}).Execute(t.Context(), differentStep)
	if err != nil {
		t.Fatal(err)
	}
	if stepExecution.Requested.ToolUseID == first.Requested.ToolUseID {
		t.Fatal("different plan steps must not share a tool identity")
	}

	differentRevision := request
	differentRevision.Turn.ClientRequestID = "run:arn_replay:goal:8"
	revisionExecution, err := (orchestration.DefaultToolCoordinator{
		Registry: registry,
	}).Execute(t.Context(), differentRevision)
	if err != nil {
		t.Fatal(err)
	}
	if revisionExecution.Requested.ToolUseID == first.Requested.ToolUseID {
		t.Fatal("different goal revisions must not share a tool identity")
	}

	differentInput := request
	differentInput.Input = map[string]any{
		"query":   "灵隐寺路线",
		"filters": map[string]any{"city": "杭州", "days": 3},
	}
	inputExecution, err := (orchestration.DefaultToolCoordinator{
		Registry: registry,
	}).Execute(t.Context(), differentInput)
	if err != nil {
		t.Fatal(err)
	}
	if inputExecution.Requested.ToolUseID == first.Requested.ToolUseID {
		t.Fatal("different canonical tool input must not share a tool identity")
	}
}

func TestMutatingToolReceivesOneStableKeyAcrossProviderRetries(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	metadata := toolIdentityMetadata("write_probe")
	metadata.ReadOnly = false
	metadata.Idempotency = toolpkg.IdempotencyKey
	metadata.Resilience.MaxAttempts = 2
	metadata.Resilience.RetryBackoffMs = 1

	type capturedRequest struct {
		toolUseID      string
		idempotencyKey string
		mode           string
		query          string
	}
	captured := make([]capturedRequest, 0, 2)
	registry.Register(metadata, func(
		_ context.Context,
		request toolpkg.Request,
	) (toolpkg.Result, error) {
		query, _ := request.Input["query"].(string)
		captured = append(captured, capturedRequest{
			toolUseID:      request.ToolUseID,
			idempotencyKey: request.IdempotencyKey,
			mode:           request.IdempotencyMode,
			query:          query,
		})
		// A faulty adapter must not be able to mutate the next retry payload.
		request.Input["query"] = "mutated by first attempt"
		if len(captured) == 1 {
			return toolpkg.Result{}, toolIdempotencyRetryableError{}
		}
		return toolpkg.Result{Output: map[string]any{"summary": "written once"}}, nil
	})

	execution, err := (orchestration.DefaultToolCoordinator{
		Registry: registry,
	}).Execute(t.Context(), stableToolRequestWithName("write_probe"))
	if err != nil || execution.Failure != nil {
		t.Fatalf("execution err=%v failure=%+v", err, execution.Failure)
	}
	if len(captured) != 2 {
		t.Fatalf("attempts=%d, want two provider attempts", len(captured))
	}
	for index, request := range captured {
		if request.toolUseID == "" ||
			request.idempotencyKey != request.toolUseID ||
			request.toolUseID != execution.Requested.ToolUseID ||
			request.mode != toolpkg.IdempotencyKey ||
			request.query != "西湖路线" {
			t.Fatalf("attempt[%d]=%+v execution=%+v", index, request, execution.Requested)
		}
	}
}

func TestMutatingToolWithoutCanonicalIdempotencyModeIsRejected(t *testing.T) {
	metadata := toolpkg.DefaultMetadata("unsafe_write_probe")
	metadata.ReadOnly = false
	defer func() {
		if recover() == nil {
			t.Fatal("mutating tool without idempotency_key metadata was registered")
		}
	}()
	registry := toolpkg.BaseRegistry()
	registry.Register(metadata, func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{}, nil
	})
}

func TestDeviceActionProposalUsesStableContinuationIdentity(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	registry.RegisterDeviceAction(toolpkg.CalendarCreateReminderMetadata())
	request := orchestration.ToolRequest{
		Turn: assistant.AssistantTurn{
			TurnID:          "execution:arn_calendar_replay",
			ExecutionRunID:  "arn_calendar_replay",
			ClientRequestID: "run:arn_calendar_replay:goal:3",
		},
		Skill:     orchestration.SkillSelection{SkillID: "calendar_task"},
		Iteration: 1,
		StepID:    "tool:1",
		ToolName:  "calendar_create_reminder",
		Input: map[string]any{
			"title":    "集合",
			"startsAt": "2026-08-05T09:00:00+08:00",
		},
	}
	first, err := (orchestration.DefaultToolCoordinator{
		Now:      func() time.Time { return time.Unix(100, 0).UTC() },
		Registry: registry,
	}).Execute(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	second, err := (orchestration.DefaultToolCoordinator{
		Now:      func() time.Time { return time.Unix(900, 0).UTC() },
		Registry: registry,
	}).Execute(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if first.Completed.Status != "waiting_confirmation" ||
		second.Completed.Status != "waiting_confirmation" ||
		first.Requested.ToolUseID != second.Requested.ToolUseID {
		t.Fatalf("device proposal replay first=%+v second=%+v", first, second)
	}
}

func stableToolRequest() orchestration.ToolRequest {
	return stableToolRequestWithName("stable_read_probe")
}

func stableToolRequestWithName(toolName string) orchestration.ToolRequest {
	return orchestration.ToolRequest{
		Turn: assistant.AssistantTurn{
			TurnID:          "execution:arn_replay",
			ExecutionRunID:  "arn_replay",
			ClientRequestID: "run:arn_replay:goal:7",
			Input:           assistant.AssistantTurnInput{Text: "西湖路线"},
		},
		Skill:     orchestration.SkillSelection{SkillID: "travel_companion"},
		Iteration: 2,
		StepID:    "tool:1",
		ToolName:  toolName,
		Input: map[string]any{
			"query":   "西湖路线",
			"filters": map[string]any{"days": 3, "city": "杭州"},
		},
	}
}

func toolIdentityMetadata(toolName string) toolpkg.Metadata {
	metadata := toolpkg.DefaultMetadata(toolName)
	metadata.InputSchema = toolpkg.ObjectSchema(map[string]any{
		"query": toolpkg.StringProperty("query"),
		"filters": map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"city": map[string]any{"type": "string"},
				"days": map[string]any{"type": "integer"},
			},
		},
	}, "query")
	return metadata
}
