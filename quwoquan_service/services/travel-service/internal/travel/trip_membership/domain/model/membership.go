package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip membership")
	ErrPermissionDenied = errors.New("trip membership permission denied")
	ErrRevisionConflict = errors.New("trip membership revision conflict")
)

type Role string

const (
	RoleOrganizer      Role = "organizer"
	RoleParticipant    Role = "participant"
	RoleLeader         Role = "leader"
	RoleAssistantGuide Role = "assistant_guide"
	RoleGuide          Role = "guide"
	RoleLocalExpert    Role = "local_expert"
)

type State string

const (
	StateActive  State = "active"
	StateLeft    State = "left"
	StateRevoked State = "revoked"
)

type SourceKind string

const (
	SourceTripInvitation SourceKind = "trip_invitation"
	SourceConversation   SourceKind = "conversation"
	SourceCircle         SourceKind = "circle"
	SourceGathering      SourceKind = "gathering"
)

type SourceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Membership struct {
	MembershipID    string     `json:"id" bson:"_id"`
	Version         int64      `json:"version" bson:"version"`
	TripID          string     `json:"tripId" bson:"tripId"`
	PersonaID       string     `json:"personaId" bson:"personaId"`
	Role            Role       `json:"role" bson:"role"`
	State           State      `json:"state" bson:"state"`
	SourceKind      SourceKind `json:"sourceKind" bson:"sourceKind"`
	SourceObjectRef *SourceRef `json:"sourceObjectRef,omitempty" bson:"sourceObjectRef,omitempty"`
	SourceVersion   int64      `json:"sourceVersion" bson:"sourceVersion"`
	JoinedAt        time.Time  `json:"joinedAt" bson:"joinedAt"`
	UpdatedAt       time.Time  `json:"updatedAt" bson:"updatedAt"`
}

type PutInput struct {
	MembershipID    string
	TripID          string
	PersonaID       string
	OrganizerID     string
	Role            Role
	SourceKind      SourceKind
	SourceObjectRef *SourceRef
	SourceVersion   int64
	Now             time.Time
}

func Create(input PutInput) (Membership, error) {
	membership := Membership{
		MembershipID:    strings.TrimSpace(input.MembershipID),
		Version:         1,
		TripID:          strings.TrimSpace(input.TripID),
		PersonaID:       strings.TrimSpace(input.PersonaID),
		Role:            input.Role,
		State:           StateActive,
		SourceKind:      input.SourceKind,
		SourceObjectRef: normalizeSourceRef(input.SourceObjectRef),
		SourceVersion:   input.SourceVersion,
		JoinedAt:        input.Now.UTC(),
		UpdatedAt:       input.Now.UTC(),
	}
	if err := validateMembership(membership, strings.TrimSpace(input.OrganizerID)); err != nil {
		return Membership{}, err
	}
	return membership, nil
}

func (membership Membership) Put(
	expectedVersion int64,
	organizerID string,
	role Role,
	sourceKind SourceKind,
	sourceRef *SourceRef,
	sourceVersion int64,
	now time.Time,
) (Membership, error) {
	if expectedVersion != membership.Version {
		return Membership{}, ErrRevisionConflict
	}
	next := membership
	next.Version++
	next.Role = role
	next.State = StateActive
	next.SourceKind = sourceKind
	next.SourceObjectRef = normalizeSourceRef(sourceRef)
	next.SourceVersion = sourceVersion
	next.UpdatedAt = now.UTC()
	if sourceVersion < membership.SourceVersion {
		return Membership{}, ErrInvalidArgument
	}
	if err := validateMembership(next, strings.TrimSpace(organizerID)); err != nil {
		return Membership{}, err
	}
	return next, nil
}

func (membership Membership) Depart(
	expectedVersion int64,
	actorPersonaID string,
	organizerID string,
	now time.Time,
) (Membership, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	organizerID = strings.TrimSpace(organizerID)
	if expectedVersion != membership.Version {
		return Membership{}, ErrRevisionConflict
	}
	if membership.PersonaID == organizerID ||
		(actorPersonaID != membership.PersonaID && actorPersonaID != organizerID) {
		return Membership{}, ErrPermissionDenied
	}
	next := membership
	next.Version++
	if actorPersonaID == membership.PersonaID {
		next.State = StateLeft
	} else {
		next.State = StateRevoked
	}
	next.UpdatedAt = now.UTC()
	return next, nil
}

func validateMembership(membership Membership, organizerID string) error {
	if membership.MembershipID == "" || membership.TripID == "" || membership.PersonaID == "" ||
		membership.Version <= 0 || !membership.Role.Valid() || !membership.State.Valid() ||
		!membership.SourceKind.Valid() || membership.SourceVersion < 0 ||
		membership.JoinedAt.IsZero() || membership.UpdatedAt.IsZero() {
		return ErrInvalidArgument
	}
	if membership.PersonaID == organizerID && membership.Role != RoleOrganizer {
		return ErrInvalidArgument
	}
	if membership.PersonaID != organizerID && membership.Role == RoleOrganizer {
		return ErrPermissionDenied
	}
	if membership.SourceKind == SourceTripInvitation {
		if membership.SourceObjectRef != nil {
			return ErrInvalidArgument
		}
	} else if membership.SourceObjectRef == nil ||
		membership.SourceObjectRef.ObjectTypeRef == "" || membership.SourceObjectRef.ObjectID == "" {
		return ErrInvalidArgument
	}
	return nil
}

func (membership Membership) Validate(organizerID string) error {
	return validateMembership(membership, strings.TrimSpace(organizerID))
}

func normalizeSourceRef(source *SourceRef) *SourceRef {
	if source == nil {
		return nil
	}
	return &SourceRef{
		ObjectTypeRef: strings.TrimSpace(source.ObjectTypeRef),
		ObjectID:      strings.TrimSpace(source.ObjectID),
	}
}

func (role Role) Valid() bool {
	switch role {
	case RoleOrganizer, RoleParticipant, RoleLeader, RoleAssistantGuide, RoleGuide, RoleLocalExpert:
		return true
	default:
		return false
	}
}

func (state State) Valid() bool {
	return state == StateActive || state == StateLeft || state == StateRevoked
}

func (kind SourceKind) Valid() bool {
	switch kind {
	case SourceTripInvitation, SourceConversation, SourceCircle, SourceGathering:
		return true
	default:
		return false
	}
}
