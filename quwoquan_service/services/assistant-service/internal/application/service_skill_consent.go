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
	grantedAt := s.now()
	consent := assistant.SkillConsent{ID: consentID(userID, skillID, grantedAt), UserID: userID, SkillID: skillID, GrantedScope: grantedScope, GrantedAt: grantedAt}
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

// SkillPersonalContentAccess 是唯一 RequiresConsent 的权限型技能；
// 与 ListSkills 目录声明同源，新增 consent 技能时两处必须一起改并补合同测试。
const SkillPersonalContentAccess = "personal_content_access"

func skillRequiresConsent(skillID string) bool {
	return strings.TrimSpace(skillID) == SkillPersonalContentAccess
}

// requireSkillConsent 是敏感技能执行点的强制门（R-CLOUD02）：
// 未授权、已撤权、store 未装配或查询失败一律 fail-closed 拒绝执行。
func (s *AssistantService) requireSkillConsent(ctx context.Context, userID, skillID string) error {
	if !skillRequiresConsent(skillID) {
		return nil
	}
	if s.consents == nil {
		return assistantConsentStoreUnavailable()
	}
	consents, err := s.consents.ListActiveConsents(ctx, userID)
	if err != nil {
		return assistantConsentStoreUnavailable()
	}
	for _, consent := range consents {
		if strings.TrimSpace(consent.SkillID) == strings.TrimSpace(skillID) {
			return nil
		}
	}
	return assistantSkillConsentRequired(skillID)
}

func assistantSkillConsentRequired(skillID string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "skill_consent_required"),
		"该能力需要先授权后使用",
		"skill "+strings.TrimSpace(skillID)+" requires active consent",
	)
	appErr.HTTPStatus = 403
	return appErr
}
