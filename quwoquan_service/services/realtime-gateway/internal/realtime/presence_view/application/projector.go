package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/domain/model"
)

type Store interface {
	UpsertIfNewer(context.Context, model.Device) (bool, error)
	DeleteConnection(
		context.Context,
		string,
		string,
		string,
		int64,
	) (bool, error)
	ReadPresence(context.Context, string, time.Time) (model.View, error)
	RemoveConnection(context.Context, string, string, string, string) error
	RemoveAccount(context.Context, string, []string) error
}

type Projector struct {
	store Store
	now   func() time.Time
}

func NewProjector(store Store) (*Projector, error) {
	if store == nil {
		return nil, errors.New("presence projector requires a store")
	}
	return &Projector{store: store, now: time.Now}, nil
}

func (projector *Projector) Observe(
	ctx context.Context,
	accountID string,
	personaID string,
	deviceID string,
	connectionID string,
	nodeID string,
	transport string,
	sequence int64,
) error {
	device, err := model.NewDevice(
		accountID,
		personaID,
		deviceID,
		connectionID,
		nodeID,
		transport,
		projector.now().UTC(),
		sequence,
	)
	if err != nil {
		return err
	}
	_, err = projector.store.UpsertIfNewer(ctx, device)
	return err
}

func (projector *Projector) Close(
	ctx context.Context,
	personaID string,
	deviceID string,
	connectionID string,
	sequence int64,
) error {
	if strings.TrimSpace(personaID) == "" ||
		strings.TrimSpace(deviceID) == "" ||
		strings.TrimSpace(connectionID) == "" || sequence <= 0 {
		return errors.New("presence close projection is invalid")
	}
	_, err := projector.store.DeleteConnection(
		ctx,
		strings.TrimSpace(personaID),
		strings.TrimSpace(deviceID),
		strings.TrimSpace(connectionID),
		sequence,
	)
	return err
}

type QueryFacade struct{ store Store }

func NewQueryFacade(store Store) (*QueryFacade, error) {
	if store == nil {
		return nil, errors.New("presence query requires a store")
	}
	return &QueryFacade{store: store}, nil
}

func (facade *QueryFacade) GetPersonaPresence(
	ctx context.Context,
	personaID string,
	now time.Time,
) (model.View, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return model.View{}, errors.New("personaId is required")
	}
	return facade.store.ReadPresence(ctx, personaID, now.UTC())
}

type Revoker struct{ store Store }

func NewRevoker(store Store) (*Revoker, error) {
	if store == nil {
		return nil, errors.New("presence revoker requires a store")
	}
	return &Revoker{store: store}, nil
}

func (revoker *Revoker) RemoveConnection(
	ctx context.Context,
	accountID string,
	personaID string,
	deviceID string,
	connectionID string,
) error {
	return revoker.store.RemoveConnection(
		ctx,
		accountID,
		personaID,
		deviceID,
		connectionID,
	)
}

func (revoker *Revoker) RemoveAccount(
	ctx context.Context,
	accountID string,
	personaIDs []string,
) error {
	return revoker.store.RemoveAccount(ctx, accountID, personaIDs)
}
