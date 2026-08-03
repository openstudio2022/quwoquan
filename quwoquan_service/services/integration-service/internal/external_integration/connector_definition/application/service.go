package application

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
)

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

func (facade *CommandFacade) Publish(
	ctx context.Context,
	input model.PublishInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	input.OccurredAt = facade.now()
	command, err := model.NewPublishCommand(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Publish(ctx, command)
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	connectorID string,
) (model.Definition, error) {
	if facade == nil || facade.reader == nil {
		return model.Definition{}, model.ErrStorageUnavailable
	}
	connectorID = strings.TrimSpace(connectorID)
	if connectorID == "" {
		return model.Definition{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, connectorID)
}

func (facade *QueryFacade) List(
	ctx context.Context,
	capability string,
	limit int,
) ([]model.Definition, error) {
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	if limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidArgument
	}
	return facade.reader.List(ctx, strings.TrimSpace(capability), limit)
}
