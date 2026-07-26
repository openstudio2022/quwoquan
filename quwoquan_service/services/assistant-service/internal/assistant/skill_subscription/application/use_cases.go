package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type Backend interface {
	CreateSkillSubscription(context.Context, string, assistant.CreateSkillSubscriptionInput) (assistant.SkillSubscription, error)
	ListSkillSubscriptions(context.Context, string, string, int) (assistant.SkillSubscriptionListView, error)
	GetSkillSubscription(context.Context, string, string) (assistant.SkillSubscription, error)
	UpdateSkillSubscriptionStatus(context.Context, string, string, assistant.UpdateSkillSubscriptionStatusInput) (assistant.SkillSubscription, error)
	TickSkillSubscriptionCron(context.Context, assistant.SkillSubscriptionCronTickInput) (assistant.SkillSubscriptionCronTickResult, error)
}

type UseCases struct{ backend Backend }

func NewUseCases(backend Backend) *UseCases {
	if backend == nil {
		panic("skill subscription backend is required")
	}
	return &UseCases{backend: backend}
}

func (s *UseCases) Create(ctx context.Context, userID string, input assistant.CreateSkillSubscriptionInput) (assistant.SkillSubscription, error) {
	if strings.TrimSpace(userID) == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	return s.backend.CreateSkillSubscription(ctx, userID, input)
}

func (s *UseCases) List(ctx context.Context, userID, status string, limit int) (assistant.SkillSubscriptionListView, error) {
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	return s.backend.ListSkillSubscriptions(ctx, userID, strings.TrimSpace(status), limit)
}

func (s *UseCases) Get(ctx context.Context, userID, subscriptionID string) (assistant.SkillSubscription, error) {
	return s.backend.GetSkillSubscription(ctx, strings.TrimSpace(userID), strings.TrimSpace(subscriptionID))
}

func (s *UseCases) UpdateStatus(ctx context.Context, userID, subscriptionID string, input assistant.UpdateSkillSubscriptionStatusInput) (assistant.SkillSubscription, error) {
	return s.backend.UpdateSkillSubscriptionStatus(ctx, strings.TrimSpace(userID), strings.TrimSpace(subscriptionID), input)
}

func (s *UseCases) Tick(ctx context.Context, input assistant.SkillSubscriptionCronTickInput) (assistant.SkillSubscriptionCronTickResult, error) {
	return s.backend.TickSkillSubscriptionCron(ctx, input)
}
