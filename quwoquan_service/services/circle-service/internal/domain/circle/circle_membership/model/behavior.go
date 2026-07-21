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
	ErrStateConflict       = errors.New("CircleMembership state conflict")
)

type ChangeKind string

const (
	ChangeJoin    ChangeKind = "join"
	ChangeLeave   ChangeKind = "leave"
	ChangeRole    ChangeKind = "role"
	ChangeApprove ChangeKind = "approve"
	ChangeReject  ChangeKind = "reject"
)

type ChangeSet struct {
	Kind            ChangeKind
	MembershipID    string
	CircleID        string
	PersonaID       string
	ExpectedVersion int64
	Role            CircleMemberRole
	// Pending 表示 joinPolicy=approval 圈子的加入意图：建 pending 档等待审批，
	// 而不是直接达成 active。
	Pending    bool
	OccurredAt time.Time
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
		if change.Pending && change.Role == CircleMemberRoleOwner {
			// owner 加入自己的圈子不需要审批。
			return ErrInvalidChange
		}
	case ChangeLeave, ChangeApprove, ChangeReject:
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
		targetState := CircleMembershipStateActive
		eventType := "CircleMembershipJoined"
		if change.Pending {
			targetState = CircleMembershipStatePending
			eventType = "CircleMembershipRequested"
		}
		if current == nil {
			next := CircleMembership{
				ID: change.MembershipID, Version: 1, CircleID: strings.TrimSpace(change.CircleID),
				PersonaID: strings.TrimSpace(change.PersonaID), Role: change.Role,
				State: targetState, LastActiveAt: now,
				CreatedAt: now, UpdatedAt: now,
			}
			if targetState == CircleMembershipStateActive {
				next.JoinedAt = now
			}
			return next, eventType, nil
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
		if change.Pending && current.State == CircleMembershipStatePending {
			return CircleMembership{}, "", ErrStateConflict
		}
		next := *current
		next.Version++
		next.Role = change.Role
		next.State = targetState
		next.LeftAt = time.Time{}
		next.LastActiveAt = now
		next.UpdatedAt = now
		if targetState == CircleMembershipStateActive {
			next.JoinedAt = now
		}
		return next, eventType, nil
	}
	if current == nil || current.ID != change.MembershipID || current.CircleID != change.CircleID ||
		current.PersonaID != change.PersonaID {
		return CircleMembership{}, "", ErrNotFound
	}
	if current.Version != change.ExpectedVersion {
		return CircleMembership{}, "", ErrVersionConflict
	}
	if change.Kind == ChangeApprove || change.Kind == ChangeReject {
		if current.State != CircleMembershipStatePending {
			return CircleMembership{}, "", ErrStateConflict
		}
		next := *current
		next.Version++
		next.UpdatedAt = now
		if change.Kind == ChangeApprove {
			next.State = CircleMembershipStateActive
			next.JoinedAt = now
			next.LastActiveAt = now
			return next, "CircleMembershipApproved", nil
		}
		next.State = CircleMembershipStateRejected
		return next, "CircleMembershipRejected", nil
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
