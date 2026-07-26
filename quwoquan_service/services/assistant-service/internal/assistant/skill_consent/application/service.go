package application

import (
	"context"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

const SkillPersonalContentAccess = "personal_content_access"

type Store interface {
	ListActiveConsents(context.Context, string) ([]assistant.SkillConsent, error)
	UpsertConsent(context.Context, assistant.SkillConsent) (assistant.SkillConsent, error)
	RevokeConsent(context.Context, string, string, time.Time) error
}

type Service struct {
	store Store
	now   func() time.Time
}

func NewService(store Store, now func() time.Time) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, now: now}
}

func (s *Service) List(ctx context.Context, userID string) (_ []assistant.SkillConsent, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListConsents", attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()
	if strings.TrimSpace(userID) == "" {
		return []assistant.SkillConsent{}, nil
	}
	if s.store == nil {
		return nil, StoreUnavailable()
	}
	return s.store.ListActiveConsents(ctx, userID)
}

func (s *Service) Grant(ctx context.Context, userID, skillID, grantedScope string) (_ assistant.SkillConsent, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GrantSkillConsent", attribute.String("user.id", userID), attribute.String("skill.id", skillID))
	defer func() { rtobs.EndSpan(span, err) }()
	userID, skillID = strings.TrimSpace(userID), strings.TrimSpace(skillID)
	if userID == "" {
		return assistant.SkillConsent{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if skillID == "" {
		return assistant.SkillConsent{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "skillId 不能为空", "missing skillId")
	}
	if strings.TrimSpace(grantedScope) == "" {
		grantedScope = skillID
	}
	if s.store == nil {
		return assistant.SkillConsent{}, StoreUnavailable()
	}
	grantedAt := s.now().UTC()
	consent := assistant.SkillConsent{ID: consentID(userID, skillID, grantedAt), UserID: userID, SkillID: skillID, GrantedScope: grantedScope, GrantedAt: grantedAt}
	return s.store.UpsertConsent(ctx, consent)
}

func (s *Service) Revoke(ctx context.Context, userID, skillID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.RevokeSkillConsent", attribute.String("user.id", userID), attribute.String("skill.id", skillID))
	defer func() { rtobs.EndSpan(span, err) }()
	userID, skillID = strings.TrimSpace(userID), strings.TrimSpace(skillID)
	if userID == "" || skillID == "" {
		return rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 和 skillId 不能为空", "missing userId or skillId")
	}
	if s.store == nil {
		return StoreUnavailable()
	}
	return s.store.RevokeConsent(ctx, userID, skillID, s.now().UTC())
}

func (s *Service) Require(ctx context.Context, userID, skillID string) error {
	if strings.TrimSpace(skillID) != SkillPersonalContentAccess {
		return nil
	}
	if s.store == nil {
		return StoreUnavailable()
	}
	consents, err := s.store.ListActiveConsents(ctx, userID)
	if err != nil {
		return StoreUnavailable()
	}
	for _, consent := range consents {
		if strings.TrimSpace(consent.SkillID) == strings.TrimSpace(skillID) {
			return nil
		}
	}
	appErr := rterr.NewAppError(rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "skill_consent_required"), "该能力需要先授权后使用", "skill "+strings.TrimSpace(skillID)+" requires active consent")
	appErr.HTTPStatus = 403
	return appErr
}

func StoreUnavailable() error {
	return rterr.NewUnavailable(rterr.ModuleAssistant, "授权服务暂不可用", "assistant consent store is not configured")
}

func consentID(userID, skillID string, grantedAt time.Time) string {
	return strings.TrimSpace(userID) + ":" + strings.TrimSpace(skillID) + ":" + strconv.FormatInt(grantedAt.UTC().UnixNano(), 36)
}
