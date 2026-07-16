package circlemembership

import (
	"errors"
	"testing"
	"time"
)

func TestCircleMembershipLifecycleAndOwnerInvariant(t *testing.T) {
	now := time.Date(2026, 7, 14, 11, 0, 0, 0, time.UTC)
	joined, eventType, err := (ChangeSet{
		Kind: ChangeJoin, MembershipID: "cm-1", CircleID: "circle-1",
		PersonaID: "persona-1", Role: CircleMemberRoleMember, OccurredAt: now,
	}).Apply(nil)
	if err != nil || eventType != "CircleMembershipJoined" || joined.Version != 1 ||
		joined.State != CircleMembershipStateActive {
		t.Fatalf("join=%+v event=%q err=%v", joined, eventType, err)
	}
	left, eventType, err := (ChangeSet{
		Kind: ChangeLeave, MembershipID: joined.ID, CircleID: joined.CircleID,
		PersonaID: joined.PersonaID, ExpectedVersion: joined.Version, OccurredAt: now.Add(time.Minute),
	}).Apply(&joined)
	if err != nil || eventType != "CircleMembershipLeft" || left.Version != 2 ||
		left.State != CircleMembershipStateLeft {
		t.Fatalf("leave=%+v event=%q err=%v", left, eventType, err)
	}
	owner := joined
	owner.Role = CircleMemberRoleOwner
	_, _, err = (ChangeSet{
		Kind: ChangeLeave, MembershipID: owner.ID, CircleID: owner.CircleID,
		PersonaID: owner.PersonaID, ExpectedVersion: owner.Version, OccurredAt: now.Add(time.Minute),
	}).Apply(&owner)
	if !errors.Is(err, ErrOwnerCannotLeave) {
		t.Fatalf("owner leave err=%v", err)
	}
}
