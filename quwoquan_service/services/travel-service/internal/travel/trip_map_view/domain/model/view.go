package model

import (
	"errors"
	"strings"
	"time"
)

var ErrInvalidView = errors.New("invalid trip map view")

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Stop struct {
	StopID         string   `json:"stopId" bson:"stopId"`
	Sequence       int      `json:"sequence" bson:"sequence"`
	DayIndex       int      `json:"dayIndex" bson:"dayIndex"`
	ItemID         string   `json:"itemId" bson:"itemId"`
	Title          string   `json:"title" bson:"title"`
	PlaceRef       PlaceRef `json:"placeRef" bson:"placeRef"`
	MomentIDs      []string `json:"momentIds" bson:"momentIds"`
	ContentLinkIDs []string `json:"contentLinkIds" bson:"contentLinkIds"`
}

type RouteSegment struct {
	SegmentID  string `json:"segmentId" bson:"segmentId"`
	Sequence   int    `json:"sequence" bson:"sequence"`
	FromStopID string `json:"fromStopId" bson:"fromStopId"`
	ToStopID   string `json:"toStopId" bson:"toStopId"`
}

type MomentMarker struct {
	MomentID string   `json:"momentId" bson:"momentId"`
	DayIndex int      `json:"dayIndex" bson:"dayIndex"`
	ItemID   string   `json:"itemId,omitempty" bson:"itemId,omitempty"`
	PlaceRef PlaceRef `json:"placeRef" bson:"placeRef"`
}

type View struct {
	TripID                string         `json:"tripId" bson:"_id"`
	CurrentRevisionID     string         `json:"currentRevisionId" bson:"currentRevisionId"`
	CurrentRevisionNumber int64          `json:"currentRevisionNumber" bson:"currentRevisionNumber"`
	Stops                 []Stop         `json:"stops" bson:"stops"`
	RouteSegments         []RouteSegment `json:"routeSegments" bson:"routeSegments"`
	MomentMarkers         []MomentMarker `json:"momentMarkers" bson:"momentMarkers"`
	SourceMomentIDs       []string       `json:"sourceMomentIds" bson:"sourceMomentIds"`
	SourceContentLinkIDs  []string       `json:"sourceContentLinkIds" bson:"sourceContentLinkIds"`
	SourceDigest          string         `json:"sourceDigest" bson:"sourceDigest"`
	SourceEventID         string         `json:"sourceEventId" bson:"sourceEventId"`
	ProjectedAt           time.Time      `json:"projectedAt" bson:"projectedAt"`
}

func (view View) Validate() error {
	if strings.TrimSpace(view.TripID) == "" || strings.TrimSpace(view.CurrentRevisionID) == "" ||
		view.CurrentRevisionNumber <= 0 || view.Stops == nil || view.RouteSegments == nil ||
		view.MomentMarkers == nil || view.SourceMomentIDs == nil || view.SourceContentLinkIDs == nil ||
		strings.TrimSpace(view.SourceDigest) == "" || strings.TrimSpace(view.SourceEventID) == "" ||
		view.ProjectedAt.IsZero() {
		return ErrInvalidView
	}
	seenStops := map[string]bool{}
	for index, stop := range view.Stops {
		if strings.TrimSpace(stop.StopID) == "" || stop.Sequence != index || stop.DayIndex < 0 ||
			strings.TrimSpace(stop.ItemID) == "" || strings.TrimSpace(stop.Title) == "" ||
			strings.TrimSpace(stop.PlaceRef.ObjectTypeRef) == "" || strings.TrimSpace(stop.PlaceRef.ObjectID) == "" ||
			stop.MomentIDs == nil || stop.ContentLinkIDs == nil || seenStops[stop.StopID] {
			return ErrInvalidView
		}
		seenStops[stop.StopID] = true
	}
	for index, segment := range view.RouteSegments {
		if strings.TrimSpace(segment.SegmentID) == "" || segment.Sequence != index ||
			!seenStops[segment.FromStopID] || !seenStops[segment.ToStopID] {
			return ErrInvalidView
		}
	}
	for _, marker := range view.MomentMarkers {
		if strings.TrimSpace(marker.MomentID) == "" || marker.DayIndex < 0 ||
			strings.TrimSpace(marker.PlaceRef.ObjectTypeRef) == "" || strings.TrimSpace(marker.PlaceRef.ObjectID) == "" {
			return ErrInvalidView
		}
	}
	return nil
}
