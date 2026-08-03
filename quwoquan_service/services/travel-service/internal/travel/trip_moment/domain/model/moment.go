package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip moment")
	ErrPermissionDenied = errors.New("trip moment permission denied")
	ErrRevisionConflict = errors.New("trip moment revision conflict")
)

type Kind string

const (
	KindPhoto         Kind = "photo"
	KindVideo         Kind = "video"
	KindVoice         Kind = "voice"
	KindText          Kind = "text"
	KindCheckIn       Kind = "check_in"
	KindPostReference Kind = "post_reference"
)

type Visibility string

const (
	VisibilityPersonal    Visibility = "personal"
	VisibilityTripMembers Visibility = "trip_members"
	VisibilityPublic      Visibility = "public"
)

type AssignmentStatus string

const (
	AssignmentUnassigned AssignmentStatus = "unassigned"
	AssignmentSuggested  AssignmentStatus = "suggested"
	AssignmentConfirmed  AssignmentStatus = "confirmed"
)

type Status string

const (
	StatusActive  Status = "active"
	StatusDeleted Status = "deleted"
)

type ObjectRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Moment struct {
	MomentID             string           `json:"id" bson:"_id"`
	Version              int64            `json:"version" bson:"version"`
	TripID               string           `json:"tripId" bson:"tripId"`
	RevisionNumber       int64            `json:"revisionNumber" bson:"revisionNumber"`
	DayIndex             *int             `json:"dayIndex,omitempty" bson:"dayIndex,omitempty"`
	ItemID               string           `json:"itemId,omitempty" bson:"itemId,omitempty"`
	Kind                 Kind             `json:"kind" bson:"kind"`
	ContentRef           *ObjectRef       `json:"contentRef,omitempty" bson:"contentRef,omitempty"`
	InlineText           string           `json:"inlineText,omitempty" bson:"inlineText,omitempty"`
	CapturedAt           time.Time        `json:"capturedAt" bson:"capturedAt"`
	CoarsePlaceRef       *ObjectRef       `json:"coarsePlaceRef,omitempty" bson:"coarsePlaceRef,omitempty"`
	Visibility           Visibility       `json:"visibility" bson:"visibility"`
	AssignmentStatus     AssignmentStatus `json:"assignmentStatus" bson:"assignmentStatus"`
	AttributionPersonaID string           `json:"attributionPersonaId" bson:"attributionPersonaId"`
	SourceVersion        int64            `json:"sourceVersion" bson:"sourceVersion"`
	Status               Status           `json:"status" bson:"status"`
	CreatedAt            time.Time        `json:"createdAt" bson:"createdAt"`
	UpdatedAt            time.Time        `json:"updatedAt" bson:"updatedAt"`
}

type CreateInput struct {
	MomentID             string
	TripID               string
	RevisionNumber       int64
	DayIndex             *int
	ItemID               string
	Kind                 Kind
	ContentRef           *ObjectRef
	InlineText           string
	CapturedAt           time.Time
	CoarsePlaceRef       *ObjectRef
	Visibility           Visibility
	AssignmentStatus     AssignmentStatus
	AttributionPersonaID string
	SourceVersion        int64
	Now                  time.Time
}

func Create(input CreateInput) (Moment, error) {
	moment := Moment{
		MomentID:             strings.TrimSpace(input.MomentID),
		Version:              1,
		TripID:               strings.TrimSpace(input.TripID),
		RevisionNumber:       input.RevisionNumber,
		DayIndex:             normalizeDay(input.DayIndex),
		ItemID:               strings.TrimSpace(input.ItemID),
		Kind:                 input.Kind,
		ContentRef:           normalizeRef(input.ContentRef),
		InlineText:           strings.TrimSpace(input.InlineText),
		CapturedAt:           input.CapturedAt.UTC(),
		CoarsePlaceRef:       normalizeRef(input.CoarsePlaceRef),
		Visibility:           input.Visibility,
		AssignmentStatus:     input.AssignmentStatus,
		AttributionPersonaID: strings.TrimSpace(input.AttributionPersonaID),
		SourceVersion:        input.SourceVersion,
		Status:               StatusActive,
		CreatedAt:            input.Now.UTC(),
		UpdatedAt:            input.Now.UTC(),
	}
	if err := moment.Validate(); err != nil {
		return Moment{}, err
	}
	return moment, nil
}

func (moment Moment) Assign(
	expectedVersion int64,
	revisionNumber int64,
	dayIndex int,
	itemID string,
	visibility Visibility,
	sourceVersion int64,
	now time.Time,
) (Moment, error) {
	if expectedVersion != moment.Version {
		return Moment{}, ErrRevisionConflict
	}
	if moment.Status != StatusActive || sourceVersion < moment.SourceVersion {
		return Moment{}, ErrInvalidArgument
	}
	next := moment
	next.Version++
	next.RevisionNumber = revisionNumber
	next.DayIndex = normalizeDay(&dayIndex)
	next.ItemID = strings.TrimSpace(itemID)
	next.Visibility = visibility
	next.AssignmentStatus = AssignmentConfirmed
	next.SourceVersion = sourceVersion
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return Moment{}, err
	}
	return next, nil
}

func (moment Moment) Delete(
	expectedVersion int64,
	actorPersonaID string,
	organizerPersonaID string,
	now time.Time,
) (Moment, error) {
	if expectedVersion != moment.Version {
		return Moment{}, ErrRevisionConflict
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if actorPersonaID != moment.AttributionPersonaID && actorPersonaID != strings.TrimSpace(organizerPersonaID) {
		return Moment{}, ErrPermissionDenied
	}
	next := moment
	next.Version++
	next.Status = StatusDeleted
	next.UpdatedAt = now.UTC()
	return next, nil
}

func (moment Moment) Validate() error {
	if strings.TrimSpace(moment.MomentID) == "" || moment.Version <= 0 ||
		strings.TrimSpace(moment.TripID) == "" || moment.RevisionNumber <= 0 ||
		!moment.Kind.Valid() || moment.CapturedAt.IsZero() || !moment.Visibility.Valid() ||
		!moment.AssignmentStatus.Valid() || strings.TrimSpace(moment.AttributionPersonaID) == "" ||
		moment.SourceVersion < 0 || !moment.Status.Valid() || moment.CreatedAt.IsZero() || moment.UpdatedAt.IsZero() {
		return ErrInvalidArgument
	}
	if moment.DayIndex != nil && *moment.DayIndex < 0 || moment.ItemID != "" && moment.DayIndex == nil {
		return ErrInvalidArgument
	}
	if moment.AssignmentStatus == AssignmentConfirmed && moment.DayIndex == nil ||
		moment.AssignmentStatus != AssignmentConfirmed && moment.Visibility != VisibilityPersonal {
		return ErrInvalidArgument
	}
	if moment.AssignmentStatus == AssignmentUnassigned && (moment.DayIndex != nil || moment.ItemID != "") {
		return ErrInvalidArgument
	}
	if err := validateContent(moment.Kind, moment.ContentRef, moment.InlineText, moment.CoarsePlaceRef); err != nil {
		return err
	}
	return nil
}

func validateContent(kind Kind, contentRef *ObjectRef, inlineText string, placeRef *ObjectRef) error {
	if contentRef != nil && (contentRef.ObjectTypeRef == "" || contentRef.ObjectID == "") ||
		placeRef != nil && (placeRef.ObjectTypeRef == "" || placeRef.ObjectID == "") {
		return ErrInvalidArgument
	}
	switch kind {
	case KindText:
		if strings.TrimSpace(inlineText) == "" || contentRef != nil {
			return ErrInvalidArgument
		}
	case KindCheckIn:
		if placeRef == nil || contentRef != nil {
			return ErrInvalidArgument
		}
	case KindPhoto, KindVideo, KindVoice, KindPostReference:
		if contentRef == nil || strings.TrimSpace(inlineText) != "" {
			return ErrInvalidArgument
		}
	default:
		return ErrInvalidArgument
	}
	return nil
}

func normalizeRef(ref *ObjectRef) *ObjectRef {
	if ref == nil {
		return nil
	}
	return &ObjectRef{
		ObjectTypeRef: strings.TrimSpace(ref.ObjectTypeRef),
		ObjectID:      strings.TrimSpace(ref.ObjectID),
	}
}

func normalizeDay(day *int) *int {
	if day == nil {
		return nil
	}
	copyOfDay := *day
	return &copyOfDay
}

func (kind Kind) Valid() bool {
	switch kind {
	case KindPhoto, KindVideo, KindVoice, KindText, KindCheckIn, KindPostReference:
		return true
	default:
		return false
	}
}

func (visibility Visibility) Valid() bool {
	return visibility == VisibilityPersonal || visibility == VisibilityTripMembers || visibility == VisibilityPublic
}

func (status AssignmentStatus) Valid() bool {
	return status == AssignmentUnassigned || status == AssignmentSuggested || status == AssignmentConfirmed
}

func (status Status) Valid() bool {
	return status == StatusActive || status == StatusDeleted
}
