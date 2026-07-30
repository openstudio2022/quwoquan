package orchestration

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
)

const SkillPersonalContentAccess = consentapplication.SkillPersonalContentAccess

func (s *AssistantService) ListConsents(ctx context.Context, userID string) ([]assistant.SkillConsent, error) {
	return s.consentUseCases.List(ctx, userID)
}

func (s *AssistantService) GrantSkillConsent(ctx context.Context, userID, skillID, grantedScope string) (assistant.SkillConsent, error) {
	return s.consentUseCases.Grant(ctx, userID, skillID, grantedScope)
}

func (s *AssistantService) RevokeSkillConsent(ctx context.Context, userID, skillID string) error {
	return s.consentUseCases.Revoke(ctx, userID, skillID)
}

func assistantConsentStoreUnavailable() error { return consentapplication.StoreUnavailable() }

func skillRequiresConsent(skillID string) bool { return skillID == SkillPersonalContentAccess }

func (s *AssistantService) requireSkillConsent(ctx context.Context, userID, skillID string) error {
	return s.consentUseCases.Require(ctx, userID, skillID)
}
