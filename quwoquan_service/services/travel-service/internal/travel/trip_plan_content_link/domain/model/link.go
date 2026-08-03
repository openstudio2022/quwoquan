package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip plan content link")
	ErrPermissionDenied = errors.New("trip plan content link permission denied")
	ErrRevisionConflict = errors.New("trip plan content link revision conflict")
)

type Visibility string

const (
	VisibilityTripMembers Visibility = "trip_members"
	VisibilityPublic      Visibility = "public"
)

type Status string

const (
	StatusActive  Status = "active"
	StatusRemoved Status = "removed"
)

type TargetKind string

const (
	TargetTrip TargetKind = "trip"
	TargetDay  TargetKind = "day"
	TargetItem TargetKind = "item"
)

type Link struct {
	LinkID            string     `json:"id" bson:"_id"`
	Version           int64      `json:"version" bson:"version"`
	TripID            string     `json:"tripId" bson:"tripId"`
	PostID            string     `json:"postId" bson:"postId"`
	RevisionNumber    int64      `json:"revisionNumber" bson:"revisionNumber"`
	TargetKind        TargetKind `json:"targetKind" bson:"targetKind"`
	DayIndex          *int       `json:"dayIndex,omitempty" bson:"dayIndex,omitempty"`
	ItemID            string     `json:"itemId,omitempty" bson:"itemId,omitempty"`
	Visibility        Visibility `json:"visibility" bson:"visibility"`
	LinkedByPersonaID string     `json:"linkedByPersonaId" bson:"linkedByPersonaId"`
	SourceVersion     int64      `json:"sourceVersion" bson:"sourceVersion"`
	Status            Status     `json:"status" bson:"status"`
	CreatedAt         time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt         time.Time  `json:"updatedAt" bson:"updatedAt"`
}

type CreateInput struct {
	LinkID            string
	TripID            string
	PostID            string
	RevisionNumber    int64
	TargetKind        TargetKind
	DayIndex          *int
	ItemID            string
	Visibility        Visibility
	LinkedByPersonaID string
	SourceVersion     int64
	Now               time.Time
}

func Create(input CreateInput) (Link, error) {
	link := Link{
		LinkID:            strings.TrimSpace(input.LinkID),
		Version:           1,
		TripID:            strings.TrimSpace(input.TripID),
		PostID:            strings.TrimSpace(input.PostID),
		RevisionNumber:    input.RevisionNumber,
		TargetKind:        input.TargetKind,
		DayIndex:          cloneDay(input.DayIndex),
		ItemID:            strings.TrimSpace(input.ItemID),
		Visibility:        input.Visibility,
		LinkedByPersonaID: strings.TrimSpace(input.LinkedByPersonaID),
		SourceVersion:     input.SourceVersion,
		Status:            StatusActive,
		CreatedAt:         input.Now.UTC(),
		UpdatedAt:         input.Now.UTC(),
	}
	if err := link.Validate(); err != nil {
		return Link{}, err
	}
	return link, nil
}

func (link Link) Put(
	expectedVersion int64,
	revisionNumber int64,
	targetKind TargetKind,
	dayIndex *int,
	itemID string,
	visibility Visibility,
	linkedByPersonaID string,
	sourceVersion int64,
	now time.Time,
) (Link, error) {
	if expectedVersion != link.Version {
		return Link{}, ErrRevisionConflict
	}
	if sourceVersion < link.SourceVersion || link.Status == StatusRemoved && sourceVersion <= link.SourceVersion {
		return Link{}, ErrInvalidArgument
	}
	next := link
	next.Version++
	next.RevisionNumber = revisionNumber
	next.TargetKind = targetKind
	next.DayIndex = cloneDay(dayIndex)
	next.ItemID = strings.TrimSpace(itemID)
	next.Visibility = visibility
	next.LinkedByPersonaID = strings.TrimSpace(linkedByPersonaID)
	next.SourceVersion = sourceVersion
	next.Status = StatusActive
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return Link{}, err
	}
	return next, nil
}

func (link Link) Remove(
	expectedVersion int64,
	actorPersonaID string,
	organizerPersonaID string,
	now time.Time,
) (Link, error) {
	if expectedVersion != link.Version {
		return Link{}, ErrRevisionConflict
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if actorPersonaID != link.LinkedByPersonaID && actorPersonaID != strings.TrimSpace(organizerPersonaID) {
		return Link{}, ErrPermissionDenied
	}
	if link.Status != StatusActive {
		return Link{}, ErrInvalidArgument
	}
	next := link
	next.Version++
	next.Status = StatusRemoved
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return Link{}, err
	}
	return next, nil
}

func (link Link) Validate() error {
	if strings.TrimSpace(link.LinkID) == "" || link.Version <= 0 ||
		strings.TrimSpace(link.TripID) == "" || strings.TrimSpace(link.PostID) == "" ||
		link.RevisionNumber <= 0 || !link.validTarget() || !link.Visibility.Valid() ||
		strings.TrimSpace(link.LinkedByPersonaID) == "" || link.SourceVersion < 0 ||
		!link.Status.Valid() || link.CreatedAt.IsZero() || link.UpdatedAt.IsZero() {
		return ErrInvalidArgument
	}
	return nil
}

func (link Link) validTarget() bool {
	switch link.TargetKind {
	case TargetTrip:
		return link.DayIndex == nil && strings.TrimSpace(link.ItemID) == ""
	case TargetDay:
		return link.DayIndex != nil && *link.DayIndex >= 0 && strings.TrimSpace(link.ItemID) == ""
	case TargetItem:
		return link.DayIndex != nil && *link.DayIndex >= 0 && strings.TrimSpace(link.ItemID) != ""
	default:
		return false
	}
}

func (kind TargetKind) Valid() bool {
	return kind == TargetTrip || kind == TargetDay || kind == TargetItem
}

func cloneDay(dayIndex *int) *int {
	if dayIndex == nil {
		return nil
	}
	value := *dayIndex
	return &value
}

func (visibility Visibility) Valid() bool {
	return visibility == VisibilityTripMembers || visibility == VisibilityPublic
}

func (status Status) Valid() bool {
	return status == StatusActive || status == StatusRemoved
}
