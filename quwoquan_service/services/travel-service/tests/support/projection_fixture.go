package support

import (
	"time"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	planmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
	timelineports "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

const ProjectionDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

func ProjectionCommit() timelineports.ProjectionCommit {
	projectedAt := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	return timelineports.ProjectionCommit{
		Timeline: timelinemodel.View{
			TripID: "trip_1", TripVersion: 2, TripStatus: planmodel.StatusActive,
			CurrentRevisionID: "trv_2", CurrentRevisionNumber: 2,
			RevisionChangeReason: "调整西湖游览顺序", RevisionSeverity: revisionmodel.SeverityImportant,
			TripContentLinks: []timelinemodel.ContentLinkSlice{},
			Days: []timelinemodel.DaySlice{{
				DayIndex: 0, UnassignedMoments: []timelinemodel.MomentSlice{},
				UnassignedContentLinks: []timelinemodel.ContentLinkSlice{},
				Items: []timelinemodel.ItemSlice{{
					ItemID: "item_west_lake", OrderInDay: 0, Kind: "sight", Title: "西湖",
					PlaceRef: &timelinemodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"},
					Moments:  []timelinemodel.MomentSlice{}, ContentLinks: []timelinemodel.ContentLinkSlice{},
				}},
			}},
			SourceMomentIDs: []string{}, SourceContentLinkIDs: []string{},
			SourceDigest: ProjectionDigest, SourceEventID: "event_projection", ProjectedAt: projectedAt,
		},
		Map: mapmodel.View{
			TripID: "trip_1", CurrentRevisionID: "trv_2", CurrentRevisionNumber: 2,
			Stops: []mapmodel.Stop{{
				StopID: "stop_1", Sequence: 0, DayIndex: 0, ItemID: "item_west_lake", Title: "西湖",
				PlaceRef:  mapmodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"},
				MomentIDs: []string{}, ContentLinkIDs: []string{},
			}},
			RouteSegments: []mapmodel.RouteSegment{}, MomentMarkers: []mapmodel.MomentMarker{},
			SourceMomentIDs: []string{}, SourceContentLinkIDs: []string{},
			SourceDigest: ProjectionDigest, SourceEventID: "event_projection", ProjectedAt: projectedAt,
		},
		Receipt: timelineports.ProjectionReceipt{
			SourceEventID: "event_projection", TripID: "trip_1",
			SourceDigest: ProjectionDigest, AppliedAt: projectedAt,
		},
	}
}
