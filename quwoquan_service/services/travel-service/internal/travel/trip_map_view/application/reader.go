package application

import (
	"context"
	"errors"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/ports"
)

type Reader struct {
	store       ports.Store
	memberships ports.MembershipAuthority
}

func NewReader(store ports.Store, memberships ports.MembershipAuthority) *Reader {
	return &Reader{store: store, memberships: memberships}
}

func (reader *Reader) Get(ctx context.Context, actorPersonaID, tripID string) (model.View, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	tripID = strings.TrimSpace(tripID)
	if reader == nil || reader.store == nil || reader.memberships == nil || actorPersonaID == "" || tripID == "" {
		return model.View{}, model.ErrInvalidView
	}
	if err := reader.memberships.CanViewTrip(ctx, actorPersonaID, tripID); err != nil {
		return model.View{}, err
	}
	view, err := reader.store.GetMap(ctx, tripID)
	if errors.Is(err, ports.ErrNotFound) {
		return model.View{}, ports.ErrProjectionUnavailable
	}
	if err != nil {
		return model.View{}, err
	}
	if err := view.Validate(); err != nil {
		return model.View{}, ports.ErrProjectionUnavailable
	}
	return view, nil
}
