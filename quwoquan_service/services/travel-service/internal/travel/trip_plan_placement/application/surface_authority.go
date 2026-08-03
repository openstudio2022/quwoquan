package application

import (
	"context"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

// FailClosedSurfaceAuthority keeps public Placement routes unavailable until
// canonical Chat/Circle authority Readers are configured. It is deliberately
// not an allow-all development fallback.
type FailClosedSurfaceAuthority struct{}

func (FailClosedSurfaceAuthority) RequireAdmin(
	context.Context,
	model.SurfaceKind,
	string,
	string,
	int64,
) error {
	return ports.ErrSurfaceUnavailable
}

func (FailClosedSurfaceAuthority) RequireMember(
	context.Context,
	model.SurfaceKind,
	string,
	string,
) error {
	return ports.ErrSurfaceUnavailable
}

var _ ports.SurfaceAuthority = FailClosedSurfaceAuthority{}
