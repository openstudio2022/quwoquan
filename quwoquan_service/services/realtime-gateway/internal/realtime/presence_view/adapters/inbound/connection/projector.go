package connection

import (
	"context"
	"errors"

	connectionapp "quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
)

// Projector consumes only trusted Connection lifecycle callbacks. It is the
// anti-corruption boundary that prevents clients from writing presence.
type Projector struct {
	projector *presenceapp.Projector
	revoker   *presenceapp.Revoker
}

func NewProjector(
	projector *presenceapp.Projector,
	revoker *presenceapp.Revoker,
) (*Projector, error) {
	if projector == nil || revoker == nil {
		return nil, errors.New("presence connection adapter requires projector and revoker")
	}
	return &Projector{projector: projector, revoker: revoker}, nil
}

func (adapter *Projector) Attach(
	ctx context.Context,
	identity connectionapp.TrustedIdentity,
	connectionID string,
	nodeID string,
	transport string,
	sequence int64,
) error {
	return adapter.projector.Observe(
		ctx,
		identity.AccountID,
		identity.PersonaID,
		identity.DeviceID,
		connectionID,
		nodeID,
		transport,
		sequence,
	)
}

func (adapter *Projector) Heartbeat(
	ctx context.Context,
	identity connectionapp.TrustedIdentity,
	connectionID string,
	nodeID string,
	transport string,
	sequence int64,
) error {
	return adapter.Attach(
		ctx,
		identity,
		connectionID,
		nodeID,
		transport,
		sequence,
	)
}

func (adapter *Projector) Detach(
	ctx context.Context,
	identity connectionapp.TrustedIdentity,
	connectionID string,
	sequence int64,
) error {
	return adapter.projector.Close(
		ctx,
		identity.PersonaID,
		identity.DeviceID,
		connectionID,
		sequence,
	)
}

func (adapter *Projector) RemoveConnection(
	ctx context.Context,
	accountID string,
	personaID string,
	deviceID string,
	connectionID string,
) error {
	return adapter.revoker.RemoveConnection(
		ctx, accountID, personaID, deviceID, connectionID,
	)
}

func (adapter *Projector) RemoveAccount(
	ctx context.Context,
	accountID string,
	personaIDs []string,
) error {
	return adapter.revoker.RemoveAccount(ctx, accountID, personaIDs)
}
