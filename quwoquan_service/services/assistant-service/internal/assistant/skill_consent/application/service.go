package application

import (
	"context"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
)

const SkillPersonalContentAccess = catalogmodel.PersonalContentAccessSkillID

type CommandFacade struct {
	store ports.Store
	now   func() time.Time
}

type QueryFacade struct {
	reader ports.Reader
}

func NewCommandFacade(store ports.Store, now func() time.Time) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{store: store, now: now}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (facade *QueryFacade) List(
	ctx context.Context,
	accountID string,
) (_ []model.Consent, err error) {
	accountID = strings.TrimSpace(accountID)
	ctx, span := rtobs.StartBusinessSpan(
		ctx, "assistant.ListConsents", attribute.String("account.id", accountID),
	)
	defer func() { rtobs.EndSpan(span, err) }()
	if accountID == "" {
		return []model.Consent{}, nil
	}
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	return facade.reader.ListActiveConsents(ctx, accountID)
}

func (facade *CommandFacade) Grant(
	ctx context.Context,
	idempotencyKey, accountID, skillID string,
	grantedScopes []string,
) (_ model.MutationResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.GrantSkillConsent",
		attribute.String("account.id", strings.TrimSpace(accountID)),
		attribute.String("skill.id", strings.TrimSpace(skillID)),
	)
	defer func() { rtobs.EndSpan(span, err) }()
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	command, err := model.NewGrantCommand(
		accountID, skillID, grantedScopes, idempotencyKey, facade.now(),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Apply(ctx, command)
}

func (facade *CommandFacade) Revoke(
	ctx context.Context,
	idempotencyKey, accountID, skillID string,
) (_ model.MutationResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.RevokeSkillConsent",
		attribute.String("account.id", strings.TrimSpace(accountID)),
		attribute.String("skill.id", strings.TrimSpace(skillID)),
	)
	defer func() { rtobs.EndSpan(span, err) }()
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	command, err := model.NewRevokeCommand(
		accountID, skillID, idempotencyKey, facade.now(),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Apply(ctx, command)
}

func (facade *QueryFacade) Require(
	ctx context.Context,
	accountID, skillID string,
) error {
	if strings.TrimSpace(skillID) != SkillPersonalContentAccess {
		return nil
	}
	consents, err := facade.List(ctx, accountID)
	if err != nil {
		return err
	}
	for _, consent := range consents {
		if consent.IsGranted() &&
			strings.TrimSpace(consent.SkillID) == strings.TrimSpace(skillID) {
			return nil
		}
	}
	return model.ErrConsentRequired
}
