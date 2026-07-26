package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

var (
	ErrInvalid          = errors.New("assistant learning fact is invalid")
	ErrUnauthorized     = errors.New("assistant learning fact is unauthorized")
	ErrOwnerMismatch    = errors.New("assistant learning fact owner mismatch")
	ErrRunNotFound      = errors.New("assistant learning fact run not found")
	ErrIdentityConflict = errors.New("assistant learning fact identity conflict")
	ErrStoreUnavailable = errors.New("assistant learning fact store unavailable")
)

type Store interface {
	Append(context.Context, model.Fact) (model.Receipt, error)
}

type RunOwner struct {
	UserID           string
	PersonaID        string
	TriggerMessageID string
}

type RunOwnerReader interface {
	ResolveRunOwner(context.Context, string) (RunOwner, bool, error)
}

type Service struct {
	store     Store
	runOwners RunOwnerReader
	now       func() time.Time
}

func NewService(
	store Store,
	runOwners RunOwnerReader,
	now func() time.Time,
) *Service {
	if now == nil {
		now = time.Now
	}
	return &Service{store: store, runOwners: runOwners, now: now}
}

func (service *Service) AppendUserFact(
	ctx context.Context,
	command model.AppendCommand,
	trusted model.TrustedContext,
) (model.Receipt, error) {
	if command.FactType == model.FactTypeServiceScorecard {
		return model.Receipt{}, fmt.Errorf(
			"%w: public command cannot append service scorecard",
			ErrUnauthorized,
		)
	}
	owner, err := service.resolveRunOwner(ctx, command.AssistantTurnID)
	if err != nil {
		return model.Receipt{}, err
	}
	if strings.TrimSpace(trusted.UserID) != owner.UserID ||
		strings.TrimSpace(trusted.PersonaID) != owner.PersonaID {
		return model.Receipt{}, ErrOwnerMismatch
	}
	if triggerMessageID := strings.TrimSpace(command.TriggerMessageID); triggerMessageID != "" &&
		triggerMessageID != owner.TriggerMessageID {
		return model.Receipt{}, fmt.Errorf(
			"%w: trigger message is not bound to assistant turn",
			ErrInvalid,
		)
	}
	return service.append(ctx, command, trusted, "user")
}

func (service *Service) AppendServiceFact(
	ctx context.Context,
	command model.AppendCommand,
) (model.Receipt, error) {
	if command.FactType != model.FactTypeServiceScorecard {
		return model.Receipt{}, fmt.Errorf(
			"%w: internal command only accepts service scorecards",
			ErrInvalid,
		)
	}
	owner, err := service.resolveRunOwner(ctx, command.AssistantTurnID)
	if err != nil {
		return model.Receipt{}, err
	}
	return service.append(ctx, command, model.TrustedContext{
		UserID:    owner.UserID,
		PersonaID: owner.PersonaID,
	}, "service")
}

func (service *Service) append(
	ctx context.Context,
	command model.AppendCommand,
	trusted model.TrustedContext,
	source string,
) (model.Receipt, error) {
	if service.store == nil {
		recordLearningFactAppend(source, string(command.FactType), "store_failed")
		return model.Receipt{}, ErrStoreUnavailable
	}
	fact, err := model.Build(command, trusted, service.now())
	if err != nil {
		recordLearningFactAppend(source, string(command.FactType), "rejected")
		return model.Receipt{}, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	receipt, err := service.store.Append(ctx, fact)
	if err != nil {
		recordLearningFactAppend(source, string(command.FactType), "store_failed")
		return model.Receipt{}, err
	}
	outcome := "accepted"
	if receipt.Deduplicated {
		outcome = "deduplicated"
	}
	recordLearningFactAppend(source, string(command.FactType), outcome)
	return receipt, nil
}

func (service *Service) resolveRunOwner(
	ctx context.Context,
	assistantTurnID string,
) (RunOwner, error) {
	if service.runOwners == nil {
		return RunOwner{}, ErrStoreUnavailable
	}
	owner, found, err := service.runOwners.ResolveRunOwner(
		ctx,
		strings.TrimSpace(assistantTurnID),
	)
	if err != nil {
		return RunOwner{}, fmt.Errorf("%w: %v", ErrStoreUnavailable, err)
	}
	if !found {
		return RunOwner{}, ErrRunNotFound
	}
	owner.UserID = strings.TrimSpace(owner.UserID)
	owner.PersonaID = strings.TrimSpace(owner.PersonaID)
	owner.TriggerMessageID = strings.TrimSpace(owner.TriggerMessageID)
	if owner.UserID == "" || owner.PersonaID == "" {
		return RunOwner{}, fmt.Errorf(
			"%w: referenced run has no trusted owner",
			ErrStoreUnavailable,
		)
	}
	return owner, nil
}
