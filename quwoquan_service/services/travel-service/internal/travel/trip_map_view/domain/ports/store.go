package ports

import (
	"context"
	"errors"

	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
)

var (
	ErrNotFound              = errors.New("trip map projection not found")
	ErrProjectionUnavailable = errors.New("trip map projection unavailable")
)

type Store interface {
	GetMap(context.Context, string) (model.View, error)
}

type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}
