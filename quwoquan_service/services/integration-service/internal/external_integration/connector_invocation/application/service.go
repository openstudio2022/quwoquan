package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"

	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionports "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/ports"
)

type CommandFacade struct {
	store       ports.Store
	connections connectionports.Reader
	definitions definitionports.Reader
	now         func() time.Time
	newID       func() string
}

type QueryFacade struct {
	reader ports.Reader
}

func NewCommandFacade(
	store ports.Store,
	connections connectionports.Reader,
	definitions definitionports.Reader,
	now func() time.Time,
	newID func() string,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if newID == nil {
		newID = uuid.NewString
	}
	return &CommandFacade{
		store: store, connections: connections, definitions: definitions,
		now: now, newID: newID,
	}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (facade *CommandFacade) Accept(
	ctx context.Context,
	input model.AcceptInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.connections == nil ||
		facade.definitions == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	now := facade.now()
	connection, err := facade.connections.Get(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.ConnectionID),
	)
	if errors.Is(err, connectionmodel.ErrNotFound) {
		return model.MutationResult{}, model.ErrConnectionNotFound
	}
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if !connection.IsActive(now) {
		return model.MutationResult{}, model.ErrConnectionInactive
	}
	if !connection.Grants(strings.TrimSpace(input.Capability)) {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	definition, err := facade.definitions.Get(ctx, connection.ConnectorID)
	if errors.Is(err, definitionmodel.ErrNotFound) {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if !definition.Grants(strings.TrimSpace(input.Capability)) {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	input.InvocationID = facade.newID()
	input.ConfirmationRequired = definition.ConfirmationPolicy == definitionmodel.ConfirmationUser
	input.OccurredAt = now
	command, err := model.NewAcceptCommand(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Accept(ctx, command)
}

func (facade *CommandFacade) Continue(
	ctx context.Context,
	input model.ContinueInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.connections == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	current, err := facade.store.Get(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.InvocationID),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	connection, err := facade.connections.Get(ctx, current.AccountID, current.ConnectionID)
	if errors.Is(err, connectionmodel.ErrNotFound) ||
		(err == nil && !connection.IsActive(facade.now())) {
		return model.MutationResult{}, model.ErrConnectionInactive
	}
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if !connection.Grants(current.Capability) {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	input.OccurredAt = facade.now()
	normalized, err := model.NewContinueInput(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Continue(ctx, normalized)
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	invocationID string,
) (model.Invocation, error) {
	if facade == nil || facade.reader == nil {
		return model.Invocation{}, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	invocationID = strings.TrimSpace(invocationID)
	if accountID == "" || invocationID == "" {
		return model.Invocation{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, accountID, invocationID)
}

func (facade *QueryFacade) List(
	ctx context.Context,
	accountID string,
	connectionID string,
	limit int,
) ([]model.Invocation, error) {
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidArgument
	}
	return facade.reader.List(ctx, accountID, strings.TrimSpace(connectionID), limit)
}
