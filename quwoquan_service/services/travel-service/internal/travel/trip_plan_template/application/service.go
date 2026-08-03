package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

type Service struct {
	store      ports.Store
	references ports.ReferenceAuthority
	ids        ports.IDGenerator
	now        func() time.Time
}

func NewService(store ports.Store, references ports.ReferenceAuthority, ids ports.IDGenerator, now func() time.Time) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, references: references, ids: ids, now: now}
}

type PutCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TemplateID      string
	ExpectedVersion int64
	Input           model.PutInput
}

func (service *Service) Create(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(command); err != nil || command.TemplateID != "" || command.ExpectedVersion != 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.references.ValidateTemplateAttributions(ctx, command.ActorPersonaID, command.Input.Attributions); err != nil {
		return ports.CommandResult{}, err
	}
	templateID, err := service.ids.NewTripPlanTemplateID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	template, err := model.Create(templateID, command.ActorPersonaID, command.Input, service.now().UTC())
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command, digest, 0, template)
}

func (service *Service) Revise(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(command); err != nil || strings.TrimSpace(command.TemplateID) == "" || command.ExpectedVersion <= 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	current, err := service.store.Get(ctx, strings.TrimSpace(command.TemplateID))
	if err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.references.ValidateTemplateAttributions(ctx, command.ActorPersonaID, command.Input.Attributions); err != nil {
		return ports.CommandResult{}, err
	}
	next, err := current.Revise(command.ActorPersonaID, command.ExpectedVersion, command.Input, service.now().UTC())
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command, digest, current.Version, next)
}

func (service *Service) Get(ctx context.Context, actorPersonaID, templateID string) (model.Template, error) {
	if service == nil || service.store == nil || strings.TrimSpace(actorPersonaID) == "" || strings.TrimSpace(templateID) == "" {
		return model.Template{}, model.ErrInvalidArgument
	}
	template, err := service.store.Get(ctx, strings.TrimSpace(templateID))
	if err != nil {
		return model.Template{}, err
	}
	if template.OwnerPersonaID != strings.TrimSpace(actorPersonaID) {
		return model.Template{}, model.ErrPermissionDenied
	}
	return template, nil
}

func (service *Service) List(ctx context.Context, ownerPersonaID string) ([]model.Template, error) {
	if service == nil || service.store == nil || strings.TrimSpace(ownerPersonaID) == "" {
		return nil, model.ErrInvalidArgument
	}
	return service.store.ListByOwner(ctx, strings.TrimSpace(ownerPersonaID))
}

func (service *Service) ready(command PutCommand) error {
	if service == nil || service.store == nil || service.references == nil || service.ids == nil ||
		strings.TrimSpace(command.ActorPersonaID) == "" || strings.TrimSpace(command.IdempotencyKey) == "" {
		return model.ErrInvalidArgument
	}
	return nil
}

func (service *Service) replay(ctx context.Context, key, digest string) (ports.CommandResult, bool, error) {
	receipt, found, err := service.store.FindReceipt(ctx, strings.TrimSpace(key))
	if err != nil || !found {
		return ports.CommandResult{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommandResult{}, true, ports.ErrIdempotencyConflict
	}
	result := receipt.Result
	result.IdempotentReplay = true
	return result, true, nil
}

func (service *Service) persist(ctx context.Context, command PutCommand, digest string, expectedVersion int64, template model.Template) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Template: template}
	commit := ports.Commit{
		ExpectedVersion: expectedVersion, Template: template,
		Receipt: ports.Receipt{IdempotencyKey: command.IdempotencyKey, CommandDigest: digest, Result: result, ExpiresAt: template.UpdatedAt.Add(7 * 24 * time.Hour)},
		Event: ports.OutboxEvent{EventID: eventID, EventType: "TripPlanTemplateChanged", AggregateID: template.TemplateID, AggregateVersion: template.Version, OccurredAt: template.UpdatedAt, Payload: map[string]any{
			"templateId": template.TemplateID, "version": template.Version, "ownerPersonaId": template.OwnerPersonaID,
			"status": template.Status, "updatedAt": template.UpdatedAt,
		}},
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		if errors.Is(err, ports.ErrCommitConflict) {
			if replay, handled, replayErr := service.replay(ctx, command.IdempotencyKey, digest); handled || replayErr != nil {
				return replay, replayErr
			}
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		return ports.CommandResult{}, err
	}
	return result, nil
}

func commandDigest(command PutCommand) string {
	raw, _ := json.Marshal(command)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}
