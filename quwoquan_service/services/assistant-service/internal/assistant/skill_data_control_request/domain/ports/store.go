package ports

import (
	"context"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
)

type Store interface {
	Create(context.Context, model.CreateCommand) (model.MutationResult, error)
	Confirm(context.Context, model.ConfirmCommand) (model.MutationResult, error)
	Get(context.Context, string, string) (model.Request, error)
	ClaimNextExecution(context.Context, string, time.Time, time.Duration) (model.ExecutionClaim, bool, error)
	HeartbeatExecution(context.Context, model.ExecutionFence, time.Time, time.Duration) (model.ExecutionFence, error)
	MarkActionCompleted(context.Context, model.ExecutionFence, string, int64, time.Time) (model.Request, error)
	MarkCompleted(context.Context, model.ExecutionFence, int64, time.Time) (model.Request, error)
	MarkFailed(context.Context, model.ExecutionFence, string, string, int64, time.Time) (model.Request, error)
	ListSkillDataControlActivities(context.Context, string, string, int) ([]model.ActivityEvent, error)
}
