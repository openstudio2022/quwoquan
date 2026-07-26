package circlepostplacement

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidChange       = errors.New("invalid circle post placement change")
	ErrNotFound            = errors.New("circle post placement not found")
	ErrAlreadyExists       = errors.New("circle post placement already exists")
	ErrVersionConflict     = errors.New("circle post placement version conflict")
	ErrIdempotencyConflict = errors.New("circle post placement idempotency conflict")
	ErrInactive            = errors.New("circle post placement is not active")
)

type ChangeKind string

const (
	ChangePlace   ChangeKind = "place"
	ChangeRemove  ChangeKind = "remove"
	ChangePin     ChangeKind = "pin"
	ChangeFeature ChangeKind = "feature"
)

// ChangeSet is the closed mutation language for CirclePostPlacement. Adapters
// cannot patch aggregate fields directly.
type ChangeSet struct {
	Kind            ChangeKind
	PlacementID     string
	PostID          string
	OwnerPersonaID  string
	CircleID        string
	GroupID         string
	ExpectedVersion int64
	Enabled         bool
	OccurredAt      time.Time
}

func (change ChangeSet) Validate() error {
	if strings.TrimSpace(change.PlacementID) == "" ||
		strings.TrimSpace(change.CircleID) == "" ||
		change.OccurredAt.IsZero() || change.ExpectedVersion < 0 {
		return ErrInvalidChange
	}
	switch change.Kind {
	case ChangePlace:
		if change.ExpectedVersion != 0 ||
			strings.TrimSpace(change.PostID) == "" ||
			strings.TrimSpace(change.OwnerPersonaID) == "" {
			return ErrInvalidChange
		}
	case ChangeRemove, ChangePin, ChangeFeature:
	default:
		return ErrInvalidChange
	}
	return nil
}

func (change ChangeSet) Apply(current *CirclePostPlacement) (CirclePostPlacement, string, error) {
	if err := change.Validate(); err != nil {
		return CirclePostPlacement{}, "", err
	}
	now := change.OccurredAt.UTC()
	if change.Kind == ChangePlace {
		if current != nil {
			return CirclePostPlacement{}, "", ErrAlreadyExists
		}
		return CirclePostPlacement{
			ID: change.PlacementID, Version: 1, PostID: strings.TrimSpace(change.PostID),
			OwnerPersonaID: strings.TrimSpace(change.OwnerPersonaID),
			CircleID:       strings.TrimSpace(change.CircleID), GroupID: strings.TrimSpace(change.GroupID),
			State: CirclePostPlacementStateActive, LastActiveAt: now, CreatedAt: now, UpdatedAt: now,
		}, "CirclePostPlaced", nil
	}
	if current == nil || current.ID != strings.TrimSpace(change.PlacementID) ||
		current.CircleID != strings.TrimSpace(change.CircleID) {
		return CirclePostPlacement{}, "", ErrNotFound
	}
	if current.Version != change.ExpectedVersion {
		return CirclePostPlacement{}, "", ErrVersionConflict
	}
	if current.State != CirclePostPlacementStateActive {
		return CirclePostPlacement{}, "", ErrInactive
	}

	next := *current
	next.Version++
	next.UpdatedAt = now
	switch change.Kind {
	case ChangeRemove:
		next.State = CirclePostPlacementStateRemoved
		next.Pinned = false
		next.PinnedAt = time.Time{}
		next.Featured = false
		next.FeaturedAt = time.Time{}
		return next, "CirclePostPlacementRemoved", nil
	case ChangePin:
		next.Pinned = change.Enabled
		if change.Enabled {
			next.PinnedAt = now
		} else {
			next.PinnedAt = time.Time{}
		}
		next.LastActiveAt = now
		return next, "CirclePostPlacementPresentationChanged", nil
	case ChangeFeature:
		next.Featured = change.Enabled
		if change.Enabled {
			next.FeaturedAt = now
		} else {
			next.FeaturedAt = time.Time{}
		}
		next.LastActiveAt = now
		return next, "CirclePostPlacementPresentationChanged", nil
	default:
		return CirclePostPlacement{}, "", ErrInvalidChange
	}
}
