package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

// Reader 是 AssistantSession 等消费方唯一可见的只读边界。
type Reader interface {
	ListActiveConsents(context.Context, string) ([]model.Consent, error)
}

// Store 只由 SkillConsent command/query facade 持有。
type Store interface {
	Reader
	Apply(context.Context, model.Command) (model.MutationResult, error)
}
