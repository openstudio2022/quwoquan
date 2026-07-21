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

// GWT1（member-role-permission）：approval 圈子加入进入 pending，
// Approve→active 发 Joined、Reject→rejected 发 Rejected，且只对 pending 生效。
func TestCircleMembershipApprovalStateMachine(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	requested, eventType, err := (ChangeSet{
		Kind: ChangeJoin, Pending: true, MembershipID: "cm-2", CircleID: "circle-2",
		PersonaID: "persona-2", Role: CircleMemberRoleMember, OccurredAt: now,
	}).Apply(nil)
	if err != nil || eventType != "CircleMembershipRequested" ||
		requested.State != CircleMembershipStatePending || !requested.JoinedAt.IsZero() {
		t.Fatalf("request=%+v event=%q err=%v", requested, eventType, err)
	}

	// pending 重复申请（不同 Idempotency-Key）返回状态冲突。
	_, _, err = (ChangeSet{
		Kind: ChangeJoin, Pending: true, MembershipID: requested.ID, CircleID: requested.CircleID,
		PersonaID: requested.PersonaID, Role: CircleMemberRoleMember,
		ExpectedVersion: requested.Version, OccurredAt: now.Add(time.Minute),
	}).Apply(&requested)
	if !errors.Is(err, ErrStateConflict) {
		t.Fatalf("duplicate pending err=%v", err)
	}

	approved, eventType, err := (ChangeSet{
		Kind: ChangeApprove, MembershipID: requested.ID, CircleID: requested.CircleID,
		PersonaID: requested.PersonaID, ExpectedVersion: requested.Version,
		OccurredAt: now.Add(2 * time.Minute),
	}).Apply(&requested)
	if err != nil || eventType != "CircleMembershipApproved" ||
		approved.State != CircleMembershipStateActive || approved.JoinedAt.IsZero() {
		t.Fatalf("approve=%+v event=%q err=%v", approved, eventType, err)
	}

	// 非 pending 态不可再审批。
	_, _, err = (ChangeSet{
		Kind: ChangeApprove, MembershipID: approved.ID, CircleID: approved.CircleID,
		PersonaID: approved.PersonaID, ExpectedVersion: approved.Version,
		OccurredAt: now.Add(3 * time.Minute),
	}).Apply(&approved)
	if !errors.Is(err, ErrStateConflict) {
		t.Fatalf("approve non-pending err=%v", err)
	}

	rejected, eventType, err := (ChangeSet{
		Kind: ChangeReject, MembershipID: requested.ID, CircleID: requested.CircleID,
		PersonaID: requested.PersonaID, ExpectedVersion: requested.Version,
		OccurredAt: now.Add(2 * time.Minute),
	}).Apply(&requested)
	if err != nil || eventType != "CircleMembershipRejected" ||
		rejected.State != CircleMembershipStateRejected {
		t.Fatalf("reject=%+v event=%q err=%v", rejected, eventType, err)
	}

	// 被拒后可重新申请（rejected → pending）。
	reapplied, eventType, err := (ChangeSet{
		Kind: ChangeJoin, Pending: true, MembershipID: rejected.ID, CircleID: rejected.CircleID,
		PersonaID: rejected.PersonaID, Role: CircleMemberRoleMember,
		ExpectedVersion: rejected.Version, OccurredAt: now.Add(4 * time.Minute),
	}).Apply(&rejected)
	if err != nil || eventType != "CircleMembershipRequested" ||
		reapplied.State != CircleMembershipStatePending {
		t.Fatalf("reapply=%+v event=%q err=%v", reapplied, eventType, err)
	}

	// owner 加入自己的圈子不需要审批（Pending+owner 非法）。
	_, _, err = (ChangeSet{
		Kind: ChangeJoin, Pending: true, MembershipID: "cm-3", CircleID: "circle-2",
		PersonaID: "owner-1", Role: CircleMemberRoleOwner, OccurredAt: now,
	}).Apply(nil)
	if !errors.Is(err, ErrInvalidChange) {
		t.Fatalf("pending owner err=%v", err)
	}
}
