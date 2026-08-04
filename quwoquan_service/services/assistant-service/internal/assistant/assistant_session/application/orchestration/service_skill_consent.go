package orchestration

import (
	"context"
	"errors"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	consenterrors "quwoquan_service/services/assistant-service/generated/assistant/skill_consent"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

func (service *AssistantService) requireSkillConsent(
	ctx context.Context,
	accountID, skillID string,
) error {
	manifest, found, err := service.resolveSkillManifest(ctx, skillID)
	if err != nil || !found {
		return runruntime.ErrSkillPackageUnavailable
	}
	err = service.consentQueries.Require(
		ctx,
		accountID,
		skillID,
		catalogapplication.RequiredContextConsentScopes(
			manifest.ContextProfile,
		),
	)
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
