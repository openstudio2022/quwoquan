package application

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
)

type ConfigurationValidator interface {
	ValidateConfiguration(context.Context, string, string, json.RawMessage) error
}

type CommandFacade struct {
	store     ports.Store
	validator ConfigurationValidator
	now       func() time.Time
}

type QueryFacade struct {
	reader ports.Reader
}

func NewCommandFacade(
	store ports.Store,
	validator ConfigurationValidator,
	now func() time.Time,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{store: store, validator: validator, now: now}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	skillID string,
) (model.Setting, error) {
	if facade == nil || facade.reader == nil {
		return model.Setting{}, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	if accountID == "" || skillID == "" {
		return model.Setting{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, accountID, skillID)
}

// List returns only explicitly persisted account settings. Missing Skills keep
// the active package default and are deliberately not materialized here.
func (facade *QueryFacade) List(
	ctx context.Context,
	accountID string,
	limit int,
) ([]model.Setting, error) {
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidArgument
	}
	return facade.reader.List(ctx, accountID, limit)
}

// IsEnabled exposes the dynamic setting boundary consumed by AssistantRun.
// Absence deliberately means package default enabled; storage failure is not
// converted to enabled.
func (facade *QueryFacade) IsEnabled(
	ctx context.Context,
	accountID string,
	skillID string,
) (bool, error) {
	setting, err := facade.Get(ctx, accountID, skillID)
	if errors.Is(err, model.ErrNotFound) {
		return true, nil
	}
	if err != nil {
		return false, err
	}
	return setting.Status == model.StatusEnabled, nil
}

func (facade *CommandFacade) Put(
	ctx context.Context,
	input model.PutInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if facade.validator == nil {
		return model.MutationResult{}, model.ErrPackageUnavailable
	}
	input.OccurredAt = facade.now()
	command, err := model.NewPutCommand(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	if err := facade.validator.ValidateConfiguration(
		ctx,
		command.SkillID,
		command.ConfigurationSchemaDigest,
		command.ConfigurationData,
	); err != nil {
		switch {
		case errors.Is(err, catalogmodel.ErrConfigurationSchemaDigestMismatch):
			return model.MutationResult{}, model.ErrSchemaMismatch
		case errors.Is(err, catalogmodel.ErrConfigurationInvalid),
			errors.Is(err, catalogmodel.ErrSkillNotFound):
			return model.MutationResult{}, model.ErrInvalidArgument
		default:
			return model.MutationResult{}, model.ErrPackageUnavailable
		}
	}
	return facade.store.Apply(ctx, command)
}
