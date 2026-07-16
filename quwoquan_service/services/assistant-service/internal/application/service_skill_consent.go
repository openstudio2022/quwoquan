package application

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func (s *AssistantService) ListConsents(ctx context.Context, userID string) (_ []assistant.SkillConsent, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListConsents", attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(userID) == "" {
		return []assistant.SkillConsent{}, nil
	}
	if s.consents == nil {
		return nil, assistantConsentStoreUnavailable()
	}
	return s.consents.ListActiveConsents(ctx, userID)
}

func (s *AssistantService) GrantSkillConsent(ctx context.Context, userID string, skillID string, grantedScope string) (_ assistant.SkillConsent, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GrantSkillConsent", attribute.String("user.id", userID), attribute.String("skill.id", skillID))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(userID) == "" {
		return assistant.SkillConsent{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if strings.TrimSpace(skillID) == "" {
		return assistant.SkillConsent{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "skillId 不能为空", "missing skillId")
	}
	if strings.TrimSpace(grantedScope) == "" {
		grantedScope = skillID
	}
	if s.consents == nil {
		return assistant.SkillConsent{}, assistantConsentStoreUnavailable()
	}
	consent := assistant.SkillConsent{ID: consentID(userID, skillID), UserID: userID, SkillID: skillID, GrantedScope: grantedScope, GrantedAt: s.now()}
	return s.consents.UpsertConsent(ctx, consent)
}

func (s *AssistantService) RevokeSkillConsent(ctx context.Context, userID string, skillID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.RevokeSkillConsent", attribute.String("user.id", userID), attribute.String("skill.id", skillID))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(userID) == "" {
		return rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if strings.TrimSpace(skillID) == "" {
		return rterr.NewInvalidArgument(rterr.ModuleAssistant, "skillId 不能为空", "missing skillId")
	}
	if s.consents == nil {
		return assistantConsentStoreUnavailable()
	}
	return s.consents.RevokeConsent(ctx, userID, skillID, s.now())
}

func assistantConsentStoreUnavailable() error {
	return rterr.NewUnavailable(rterr.ModuleAssistant, "授权服务暂不可用", "assistant consent store is not configured")
}
