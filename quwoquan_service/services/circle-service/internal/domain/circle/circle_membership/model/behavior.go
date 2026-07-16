package circlemembership

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidChange       = errors.New("invalid CircleMembership change")
	ErrNotFound            = errors.New("CircleMembership not found")
	ErrAlreadyActive       = errors.New("CircleMembership already active")
	ErrVersionConflict     = errors.New("CircleMembership version conflict")
	ErrOwnerCannotLeave    = errors.New("Circle owner cannot leave")
	ErrInvalidRole         = errors.New("invalid CircleMembership role")
	ErrIdempotencyConflict = errors.New("CircleMembership idempotency conflict")
)

type ChangeKind string

const (
	ChangeJoin  ChangeKind = "join"
	ChangeLeave ChangeKind = "leave"
	ChangeRole  ChangeKind = "role"
)

type ChangeSet struct {
	Kind            ChangeKind
	MembershipID    string
	CircleID        string
	PersonaID       string
	ExpectedVersion int64
	Role            CircleMemberRole
	OccurredAt      time.Time
}

func (change ChangeSet) Validate() error {
	if strings.TrimSpace(change.MembershipID) == "" || strings.TrimSpace(change.CircleID) == "" ||
		strings.TrimSpace(change.PersonaID) == "" || change.ExpectedVersion < 0 || change.OccurredAt.IsZero() {
		return ErrInvalidChange
	}
	switch change.Kind {
	case ChangeJoin:
		if change.Role != CircleMemberRoleOwner && change.Role != CircleMemberRoleMember {
			return ErrInvalidRole
		}
	case ChangeLeave:
	case ChangeRole:
		if change.Role != CircleMemberRoleAdmin && change.Role != CircleMemberRoleMember {
			return ErrInvalidRole
		}
	default:
		return ErrInvalidChange
	}
	return nil
}

func (change ChangeSet) Apply(current *CircleMembership) (CircleMembership, string, error) {
	if err := change.Validate(); err != nil {
		return CircleMembership{}, "", err
	}
	now := change.OccurredAt.UTC()
	if change.Kind == ChangeJoin {
		if current == nil {
			return CircleMembership{
				ID: change.MembershipID, Version: 1, CircleID: strings.TrimSpace(change.CircleID),
				PersonaID: strings.TrimSpace(change.PersonaID), Role: change.Role,
				State: CircleMembershipStateActive, JoinedAt: now, LastActiveAt: now,
				CreatedAt: now, UpdatedAt: now,
			}, "CircleMembershipJoined", nil
		}
		if current.ID != change.MembershipID || current.CircleID != change.CircleID || current.PersonaID != change.PersonaID {
			return CircleMembership{}, "", ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return CircleMembership{}, "", ErrVersionConflict
		}
		if current.State == CircleMembershipStateActive {
			return CircleMembership{}, "", ErrAlreadyActive
		}
		if current.State == CircleMembershipStateRemoved {
			return CircleMembership{}, "", ErrInvalidChange
		}
		next := *current
		next.Version++
		next.Role = change.Role
		next.State = CircleMembershipStateActive
		next.JoinedAt = now
		next.LeftAt = time.Time{}
		next.LastActiveAt = now
		next.UpdatedAt = now
		return next, "CircleMembershipJoined", nil
	}
	if current == nil || current.ID != change.MembershipID || current.CircleID != change.CircleID ||
		current.PersonaID != change.PersonaID {
		return CircleMembership{}, "", ErrNotFound
	}
	if current.Version != change.ExpectedVersion {
		return CircleMembership{}, "", ErrVersionConflict
	}
	if current.State != CircleMembershipStateActive {
		return CircleMembership{}, "", ErrNotFound
	}
	next := *current
	next.Version++
	next.UpdatedAt = now
	switch change.Kind {
	case ChangeLeave:
		if current.Role == CircleMemberRoleOwner {
			return CircleMembership{}, "", ErrOwnerCannotLeave
		}
		next.State = CircleMembershipStateLeft
		next.LeftAt = now
		return next, "CircleMembershipLeft", nil
	case ChangeRole:
		if current.Role == CircleMemberRoleOwner {
			return CircleMembership{}, "", ErrInvalidRole
		}
		next.Role = change.Role
		return next, "CircleMembershipRoleChanged", nil
	default:
		return CircleMembership{}, "", ErrInvalidChange
	}
}
