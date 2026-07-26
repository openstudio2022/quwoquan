package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

// RunStore is the run aggregate boundary used by the transport-facing use cases.
type RunStore interface {
	CreateTurn(context.Context, string, string, assistant.CreateTurnInput) (assistant.AssistantTurn, error)
	GetTurn(context.Context, string, string) (assistant.AssistantTurn, error)
	ListConversationTurns(context.Context, string, string, int, string) (assistant.AssistantTurnListView, error)
	CancelRun(context.Context, string, string) (assistant.AssistantTurn, error)
}

type UseCases struct{ runs RunStore }

func NewUseCases(runs RunStore) *UseCases {
	if runs == nil {
		panic("assistant run store is required")
	}
	return &UseCases{runs: runs}
}

func (s *UseCases) Start(ctx context.Context, userID, conversationID string, input assistant.CreateTurnInput) (assistant.AssistantTurn, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(conversationID) == "" {
		return assistant.AssistantTurn{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 和 conversationId 不能为空", "missing run owner or conversation")
	}
	return s.runs.CreateTurn(ctx, userID, conversationID, input)
}

func (s *UseCases) Get(ctx context.Context, userID, runID string) (assistant.AssistantTurn, error) {
	return s.runs.GetTurn(ctx, userID, strings.TrimSpace(runID))
}

func (s *UseCases) ListTurns(ctx context.Context, userID, conversationID string, limit int, cursor string) (assistant.AssistantTurnListView, error) {
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	return s.runs.ListConversationTurns(ctx, userID, conversationID, limit, strings.TrimSpace(cursor))
}

func (s *UseCases) Cancel(ctx context.Context, userID, runID string) (assistant.AssistantTurn, error) {
	return s.runs.CancelRun(ctx, userID, strings.TrimSpace(runID))
}
