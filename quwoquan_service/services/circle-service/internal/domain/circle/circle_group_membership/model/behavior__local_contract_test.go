package circlegroupmembership

import (
	"errors"
	"testing"
	"time"
)

func TestApplyApprovalAndOwnerInvariants(t *testing.T) {
	now := time.Date(2026, 7, 14, 1, 2, 3, 0, time.UTC)
	pending, eventType, err := (ChangeSet{
		Kind: ChangeApply, MembershipID: "gm-1", GroupID: "g-1", CircleID: "c-1",
		PersonaID: "p-1", ActorPersonaID: "p-1", Role: CircleGroupMembershipRoleMember, OccurredAt: now,
	}).Apply(nil)
	if err != nil || eventType != "CircleGroupMembershipRequested" || pending.State != CircleGroupMembershipStatePending {
		t.Fatalf("apply = %#v, %q, %v", pending, eventType, err)
	}
	active, eventType, err := (ChangeSet{
		Kind: ChangeApprove, MembershipID: "gm-1", GroupID: "g-1", CircleID: "c-1",
		PersonaID: "p-1", ActorPersonaID: "owner", ExpectedVersion: 1, OccurredAt: now.Add(time.Second),
	}).Apply(&pending)
	if err != nil || eventType != "CircleGroupMembershipActivated" || active.State != CircleGroupMembershipStateActive || active.Version != 2 {
		t.Fatalf("approve = %#v, %q, %v", active, eventType, err)
	}
	_, _, err = (ChangeSet{
		Kind: ChangeApprove, MembershipID: "gm-1", GroupID: "g-1", CircleID: "c-1",
		PersonaID: "p-1", ActorPersonaID: "p-1", ExpectedVersion: 1, OccurredAt: now.Add(time.Second),
	}).Apply(&pending)
	if !errors.Is(err, ErrStateConflict) {
		t.Fatalf("self approval error = %v", err)
	}
}

func TestDirectJoinAndReapplyResetHistoricalRole(t *testing.T) {
	now := time.Date(2026, 7, 14, 1, 2, 3, 0, time.UTC)
	removed := CircleGroupMembership{
		ID: "gm-1", Version: 4, GroupID: "g-1", CircleID: "c-1", PersonaID: "p-1",
		Role: CircleGroupMembershipRoleManager, State: CircleGroupMembershipStateRemoved, CreatedAt: now.Add(-time.Hour),
	}
	next, _, err := (ChangeSet{
		Kind: ChangeApply, MembershipID: "gm-1", GroupID: "g-1", CircleID: "c-1",
		PersonaID: "p-1", ActorPersonaID: "p-1", ExpectedVersion: 4,
		Role: CircleGroupMembershipRoleMember, DirectActivate: true, OccurredAt: now,
	}).Apply(&removed)
	if err != nil || next.Role != CircleGroupMembershipRoleMember || next.State != CircleGroupMembershipStateActive || next.Version != 5 {
		t.Fatalf("reapply = %#v, %v", next, err)
	}
}

func TestOwnerCannotLeaveOrBeRemoved(t *testing.T) {
	now := time.Date(2026, 7, 14, 1, 2, 3, 0, time.UTC)
	owner := CircleGroupMembership{
		ID: "gm-owner", Version: 1, GroupID: "g-1", CircleID: "c-1", PersonaID: "owner",
		Role: CircleGroupMembershipRoleOwner, State: CircleGroupMembershipStateActive,
	}
	for _, change := range []ChangeSet{
		{Kind: ChangeLeave, MembershipID: owner.ID, GroupID: owner.GroupID, CircleID: owner.CircleID, PersonaID: owner.PersonaID, ActorPersonaID: owner.PersonaID, ExpectedVersion: 1, OccurredAt: now},
		{Kind: ChangeRemove, MembershipID: owner.ID, GroupID: owner.GroupID, CircleID: owner.CircleID, PersonaID: owner.PersonaID, ActorPersonaID: "manager", ExpectedVersion: 1, OccurredAt: now},
	} {
		_, _, err := change.Apply(&owner)
		if !errors.Is(err, ErrOwnerCannotLeave) && !errors.Is(err, ErrOwnerCannotRemove) {
			t.Fatalf("owner invariant error = %v", err)
		}
	}
}
