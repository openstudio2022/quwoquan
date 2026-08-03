package ports

import (
	"context"
	"errors"
	"time"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	momentmodel "quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	planmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
)

var (
	ErrNotFound              = errors.New("trip timeline projection not found")
	ErrProjectionUnavailable = errors.New("trip timeline projection unavailable")
	ErrReceiptConflict       = errors.New("trip projection receipt conflict")
)

type ProjectionReceipt struct {
	SourceEventID string    `bson:"_id"`
	TripID        string    `bson:"tripId"`
	SourceDigest  string    `bson:"sourceDigest"`
	AppliedAt     time.Time `bson:"appliedAt"`
}

type ProjectionCommit struct {
	Timeline model.View
	Map      mapmodel.View
	Receipt  ProjectionReceipt
}

type Store interface {
	GetTimeline(context.Context, string) (model.View, error)
	FindReceipt(context.Context, string) (ProjectionReceipt, bool, error)
	CommitProjection(context.Context, ProjectionCommit) error
}

type PlanReader interface {
	GetPlan(context.Context, string) (planmodel.Plan, error)
}

type RevisionReader interface {
	Get(context.Context, string, int64) (revisionmodel.Revision, error)
}

type MomentReader interface {
	ListActive(context.Context, string) ([]momentmodel.Moment, error)
}

type ContentLinkReader interface {
	ListActive(context.Context, string) ([]linkmodel.Link, error)
}

type MembershipAuthority interface {
	CanViewTrip(context.Context, string, string) error
}
