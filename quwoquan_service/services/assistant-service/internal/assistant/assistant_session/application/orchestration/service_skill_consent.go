package orchestration

import (
	"context"
	"errors"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	consenterrors "quwoquan_service/services/assistant-service/generated/assistant/skill_consent"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

const SkillPersonalContentAccess = consentapplication.SkillPersonalContentAccess

func skillRequiresConsent(skillID string) bool {
	return skillID == SkillPersonalContentAccess
}

func (service *AssistantService) requireSkillConsent(
	ctx context.Context,
	accountID, skillID string,
) error {
	err := service.consentQueries.Require(ctx, accountID, skillID)
	switch {
	case errors.Is(err, consentmodel.ErrConsentRequired):
		return runerrors.AppErrorFromSkillConsentRequired(
			"active consent is required for skill " + skillID,
		)
	case errors.Is(err, consentmodel.ErrStorageUnavailable):
		return consenterrors.AppErrorFromConsentUnavailable(
			"skill consent reader is unavailable",
		)
	default:
		return err
	}
}
