package circlegroupmembership

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidChange       = errors.New("invalid CircleGroupMembership change")
	ErrNotFound            = errors.New("CircleGroupMembership not found")
	ErrAlreadyActive       = errors.New("CircleGroupMembership already active")
	ErrStateConflict       = errors.New("CircleGroupMembership state conflict")
	ErrOwnerCannotLeave    = errors.New("CircleGroup owner cannot leave")
	ErrOwnerCannotRemove   = errors.New("CircleGroup owner cannot be removed")
	ErrInvalidRole         = errors.New("invalid CircleGroupMembership role")
	ErrVersionConflict     = errors.New("CircleGroupMembership version conflict")
	ErrIdempotencyConflict = errors.New("CircleGroupMembership idempotency conflict")
)

type ChangeKind string

const (
	ChangeApply         ChangeKind = "apply"
	ChangeActivateOwner ChangeKind = "activate_owner"
	ChangeApprove       ChangeKind = "approve"
	ChangeReject        ChangeKind = "reject"
	ChangeLeave         ChangeKind = "leave"
	ChangeRemove        ChangeKind = "remove"
	ChangeRole          ChangeKind = "role"
)

type ChangeSet struct {
	Kind            ChangeKind
	MembershipID    string
	GroupID         string
	CircleID        string
	PersonaID       string
	ActorPersonaID  string
	ExpectedVersion int64
	Role            CircleGroupMembershipRole
	DirectActivate  bool
	OccurredAt      time.Time
}

func (change ChangeSet) Validate() error {
	if strings.TrimSpace(change.MembershipID) == "" || strings.TrimSpace(change.GroupID) == "" ||
		strings.TrimSpace(change.CircleID) == "" || strings.TrimSpace(change.PersonaID) == "" ||
		strings.TrimSpace(change.ActorPersonaID) == "" || change.ExpectedVersion < 0 || change.OccurredAt.IsZero() {
		return ErrInvalidChange
	}
	switch change.Kind {
	case ChangeApply:
		if change.Role != CircleGroupMembershipRoleMember || change.ActorPersonaID != change.PersonaID {
			return ErrInvalidRole
		}
	case ChangeActivateOwner:
		if change.Role != CircleGroupMembershipRoleOwner || change.ActorPersonaID != change.PersonaID || !change.DirectActivate {
			return ErrInvalidRole
		}
	case ChangeApprove, ChangeReject, ChangeLeave, ChangeRemove:
	case ChangeRole:
		if change.Role != CircleGroupMembershipRoleManager && change.Role != CircleGroupMembershipRoleMember {
			return ErrInvalidRole
		}
	default:
		return ErrInvalidChange
	}
	return nil
}

func (change ChangeSet) Apply(current *CircleGroupMembership) (CircleGroupMembership, string, error) {
	if err := change.Validate(); err != nil {
		return CircleGroupMembership{}, "", err
	}
	if current != nil {
		if current.ID != change.MembershipID || current.GroupID != change.GroupID ||
			current.CircleID != change.CircleID || current.PersonaID != change.PersonaID {
			return CircleGroupMembership{}, "", ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return CircleGroupMembership{}, "", ErrVersionConflict
		}
	}
	now := change.OccurredAt.UTC()
	if change.Kind == ChangeApply || change.Kind == ChangeActivateOwner {
		if current != nil && current.State == CircleGroupMembershipStateActive {
			return CircleGroupMembership{}, "", ErrAlreadyActive
		}
		next := CircleGroupMembership{
			ID: change.MembershipID, Version: 1, GroupID: strings.TrimSpace(change.GroupID),
			CircleID: strings.TrimSpace(change.CircleID), PersonaID: strings.TrimSpace(change.PersonaID),
			Role: change.Role, State: CircleGroupMembershipStatePending, CreatedAt: now, UpdatedAt: now,
		}
		if current != nil {
			next.Version = current.Version + 1
			next.CreatedAt = current.CreatedAt
		}
		if change.DirectActivate {
			next.State = CircleGroupMembershipStateActive
			next.JoinedAt = now
			next.DecidedAt = now
			next.DecidedByPersonaID = change.ActorPersonaID
			return next, "CircleGroupMembershipActivated", nil
		}
		return next, "CircleGroupMembershipRequested", nil
	}
	if current == nil {
		return CircleGroupMembership{}, "", ErrNotFound
	}
	next := *current
	next.Version++
	next.UpdatedAt = now
	switch change.Kind {
	case ChangeApprove:
		if current.State != CircleGroupMembershipStatePending || change.ActorPersonaID == current.PersonaID {
			return CircleGroupMembership{}, "", ErrStateConflict
		}
		next.State = CircleGroupMembershipStateActive
		next.Role = CircleGroupMembershipRoleMember
		next.JoinedAt = now
		next.LeftAt = time.Time{}
		next.DecidedAt = now
		next.DecidedByPersonaID = change.ActorPersonaID
		return next, "CircleGroupMembershipActivated", nil
	case ChangeReject:
		if current.State != CircleGroupMembershipStatePending || change.ActorPersonaID == current.PersonaID {
			return CircleGroupMembership{}, "", ErrStateConflict
		}
		next.State = CircleGroupMembershipStateRejected
		next.DecidedAt = now
		next.DecidedByPersonaID = change.ActorPersonaID
		return next, "CircleGroupMembershipRejected", nil
	case ChangeLeave:
		if current.State != CircleGroupMembershipStateActive {
			return CircleGroupMembership{}, "", ErrStateConflict
		}
		if current.Role == CircleGroupMembershipRoleOwner {
			return CircleGroupMembership{}, "", ErrOwnerCannotLeave
		}
		if change.ActorPersonaID != current.PersonaID {
			return CircleGroupMembership{}, "", ErrInvalidChange
		}
		next.State = CircleGroupMembershipStateLeft
		next.LeftAt = now
		return next, "CircleGroupMembershipLeft", nil
	case ChangeRemove:
		if current.State != CircleGroupMembershipStateActive && current.State != CircleGroupMembershipStatePending {
			return CircleGroupMembership{}, "", ErrStateConflict
		}
		if current.Role == CircleGroupMembershipRoleOwner {
			return CircleGroupMembership{}, "", ErrOwnerCannotRemove
		}
		next.State = CircleGroupMembershipStateRemoved
		next.LeftAt = now
		next.DecidedAt = now
		next.DecidedByPersonaID = change.ActorPersonaID
		return next, "CircleGroupMembershipRemoved", nil
	case ChangeRole:
		if current.State != CircleGroupMembershipStateActive || current.Role == CircleGroupMembershipRoleOwner {
			return CircleGroupMembership{}, "", ErrInvalidRole
		}
		next.Role = change.Role
		next.DecidedAt = now
		next.DecidedByPersonaID = change.ActorPersonaID
		return next, "CircleGroupMembershipRoleChanged", nil
	default:
		return CircleGroupMembership{}, "", ErrInvalidChange
	}
}
