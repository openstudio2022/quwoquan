package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip plan placement")
	ErrPermissionDenied = errors.New("trip plan placement permission denied")
	ErrRevisionConflict = errors.New("trip plan placement revision conflict")
)

type SurfaceKind string

const (
	SurfaceConversation SurfaceKind = "conversation"
	SurfaceCircle       SurfaceKind = "circle"
)

type Status string

const (
	StatusActive  Status = "active"
	StatusRemoved Status = "removed"
)

type Placement struct {
	PlacementID        string      `json:"id" bson:"_id"`
	Version            int64       `json:"version" bson:"version"`
	TripID             string      `json:"tripId" bson:"tripId"`
	SurfaceKind        SurfaceKind `json:"surfaceKind" bson:"surfaceKind"`
	SurfaceID          string      `json:"surfaceId" bson:"surfaceId"`
	SourceVersion      int64       `json:"sourceVersion" bson:"sourceVersion"`
	Status             Status      `json:"status" bson:"status"`
	CreatedByPersonaID string      `json:"createdByPersonaId" bson:"createdByPersonaId"`
	CreatedAt          time.Time   `json:"createdAt" bson:"createdAt"`
	UpdatedAt          time.Time   `json:"updatedAt" bson:"updatedAt"`
}

type CreateInput struct {
	PlacementID        string
	TripID             string
	SurfaceKind        SurfaceKind
	SurfaceID          string
	SourceVersion      int64
	CreatedByPersonaID string
	Now                time.Time
}

func Create(input CreateInput) (Placement, error) {
	placement := Placement{
		PlacementID:        strings.TrimSpace(input.PlacementID),
		Version:            1,
		TripID:             strings.TrimSpace(input.TripID),
		SurfaceKind:        input.SurfaceKind,
		SurfaceID:          strings.TrimSpace(input.SurfaceID),
		SourceVersion:      input.SourceVersion,
		Status:             StatusActive,
		CreatedByPersonaID: strings.TrimSpace(input.CreatedByPersonaID),
		CreatedAt:          input.Now.UTC(),
		UpdatedAt:          input.Now.UTC(),
	}
	if err := placement.Validate(); err != nil {
		return Placement{}, err
	}
	return placement, nil
}

func (placement Placement) Put(expectedVersion, sourceVersion int64, now time.Time) (Placement, error) {
	if expectedVersion != placement.Version {
		return Placement{}, ErrRevisionConflict
	}
	if sourceVersion < placement.SourceVersion ||
		(placement.Status == StatusRemoved && sourceVersion <= placement.SourceVersion) {
		return Placement{}, ErrInvalidArgument
	}
	next := placement
	next.Version++
	next.SourceVersion = sourceVersion
	next.Status = StatusActive
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return Placement{}, err
	}
	return next, nil
}

func (placement Placement) Remove(expectedVersion, sourceVersion int64, now time.Time) (Placement, error) {
	if expectedVersion != placement.Version {
		return Placement{}, ErrRevisionConflict
	}
	if sourceVersion < placement.SourceVersion {
		return Placement{}, ErrInvalidArgument
	}
	next := placement
	next.Version++
	next.SourceVersion = sourceVersion
	next.Status = StatusRemoved
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return Placement{}, err
	}
	return next, nil
}

func (placement Placement) Validate() error {
	if strings.TrimSpace(placement.PlacementID) == "" || placement.Version <= 0 ||
		strings.TrimSpace(placement.TripID) == "" || !placement.SurfaceKind.Valid() ||
		strings.TrimSpace(placement.SurfaceID) == "" || placement.SourceVersion < 0 ||
		!placement.Status.Valid() || strings.TrimSpace(placement.CreatedByPersonaID) == "" ||
		placement.CreatedAt.IsZero() || placement.UpdatedAt.IsZero() {
		return ErrInvalidArgument
	}
	return nil
}

func (kind SurfaceKind) Valid() bool {
	return kind == SurfaceConversation || kind == SurfaceCircle
}

func (status Status) Valid() bool {
	return status == StatusActive || status == StatusRemoved
}
