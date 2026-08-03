package source

import (
	"context"
	"errors"
	"strings"

	mapports "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/ports"
	sharemodel "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	shareports "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
	timelineports "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}

type ProjectionReader struct {
	timelines   timelineports.Store
	maps        mapports.Store
	memberships MembershipAuthority
}

func NewProjectionReader(
	timelines timelineports.Store,
	maps mapports.Store,
	memberships MembershipAuthority,
) *ProjectionReader {
	return &ProjectionReader{timelines: timelines, maps: maps, memberships: memberships}
}

func (reader *ProjectionReader) ReadShareSource(
	ctx context.Context,
	actorPersonaID string,
	tripID string,
) (shareports.Source, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	tripID = strings.TrimSpace(tripID)
	if reader == nil || reader.timelines == nil || reader.maps == nil || reader.memberships == nil ||
		actorPersonaID == "" || tripID == "" {
		return shareports.Source{}, sharemodel.ErrInvalidArgument
	}
	if err := reader.memberships.CanViewTrip(ctx, actorPersonaID, tripID); err != nil {
		return shareports.Source{}, err
	}
	timeline, err := reader.timelines.GetTimeline(ctx, tripID)
	if errors.Is(err, timelineports.ErrNotFound) {
		return shareports.Source{}, sharemodel.ErrSourceConflict
	}
	if err != nil {
		return shareports.Source{}, err
	}
	tripMap, err := reader.maps.GetMap(ctx, tripID)
	if errors.Is(err, mapports.ErrNotFound) {
		return shareports.Source{}, sharemodel.ErrSourceConflict
	}
	if err != nil {
		return shareports.Source{}, err
	}
	if timeline.Validate() != nil || tripMap.Validate() != nil ||
		timeline.TripID != tripMap.TripID ||
		timeline.CurrentRevisionID != tripMap.CurrentRevisionID ||
		timeline.CurrentRevisionNumber != tripMap.CurrentRevisionNumber ||
		timeline.SourceDigest != tripMap.SourceDigest {
		return shareports.Source{}, sharemodel.ErrSourceConflict
	}
	return shareports.Source{Timeline: timeline, Map: tripMap}, nil
}

var _ shareports.SourceReader = (*ProjectionReader)(nil)
