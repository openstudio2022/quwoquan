// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001
// readiness_case: join-circle-local
// readiness_case: leave-circle-local
// readiness_case: get-my-circle-membership-local
// readiness_case: list-circle-memberships-local
// readiness_case: list-pending-circle-memberships-local
// readiness_case: approve-circle-member-local
// readiness_case: reject-circle-member-local
// readiness_case: update-circle-membership-role-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/ports"
)

func TestCircleMembershipFacadesExecuteMembershipLifecycleOperations(t *testing.T) {
	store := newMembershipFacadeStore()
	commands := app.NewCommandFacade(store, store, store)
	queries := app.NewQueryFacade(store, store, store)

	requested, err := commands.Join(membershipCommandContext("persona-a", "join-a"), "circle-approval")
	if err != nil || requested.State != string(model.CircleMembershipStatePending) || requested.Role != string(model.CircleMemberRoleMember) {
		t.Fatalf("JoinCircle drift: result=%+v err=%v", requested, err)
	}

	myMembership, err := queries.GetMyCircleMembership(membershipReadContext("persona-a"), "circle-approval")
	if err != nil || myMembership.PersonaID != "persona-a" || myMembership.State != model.CircleMembershipStatePending {
		t.Fatalf("GetMyCircleMembership drift: result=%+v err=%v", myMembership, err)
	}

	roster, err := queries.ListCircleMemberships(context.Background(), "circle-approval", 20, "")
	if err != nil || len(roster.Items) != 0 {
		t.Fatalf("ListCircleMemberships drift: result=%+v err=%v", roster, err)
	}

	pending, err := queries.ListPendingCircleMemberships(membershipReadContext("persona-owner"), "circle-approval", 20, "")
	if err != nil || len(pending.Items) != 1 || pending.Items[0].PersonaID != "persona-a" || pending.Items[0].State != model.CircleMembershipStatePending {
		t.Fatalf("ListPendingCircleMemberships drift: result=%+v err=%v", pending, err)
	}

	approved, err := commands.Approve(membershipCommandContext("persona-owner", "approve-a"), app.DecideCommand{
		CircleID: "circle-approval", TargetPersonaID: "persona-a",
	})
	if err != nil || approved.State != string(model.CircleMembershipStateActive) {
		t.Fatalf("ApproveCircleMember drift: result=%+v err=%v", approved, err)
	}
	roster, err = queries.ListCircleMemberships(context.Background(), "circle-approval", 20, "")
	if err != nil || len(roster.Items) != 1 || roster.Items[0].PersonaID != "persona-a" ||
		roster.Items[0].State != model.CircleMembershipStateActive {
		t.Fatalf("active ListCircleMemberships drift: result=%+v err=%v", roster, err)
	}

	roleUpdated, err := commands.UpdateRole(membershipCommandContext("persona-owner", "role-a"), app.UpdateRoleCommand{
		CircleID: "circle-approval", TargetPersonaID: "persona-a", Role: model.CircleMemberRoleAdmin,
	})
	if err != nil || roleUpdated.Role != string(model.CircleMemberRoleAdmin) || roleUpdated.State != string(model.CircleMembershipStateActive) {
		t.Fatalf("UpdateCircleMembershipRole drift: result=%+v err=%v", roleUpdated, err)
	}

	left, err := commands.Leave(membershipCommandContext("persona-a", "leave-a"), app.LeaveCommand{CircleID: "circle-approval"})
	if err != nil || left.State != string(model.CircleMembershipStateLeft) {
		t.Fatalf("LeaveCircle drift: result=%+v err=%v", left, err)
	}

	if _, err := commands.Join(membershipCommandContext("persona-b", "join-b"), "circle-approval"); err != nil {
		t.Fatalf("JoinCircle for reject path: %v", err)
	}
	rejected, err := commands.Reject(membershipCommandContext("persona-owner", "reject-b"), app.DecideCommand{
		CircleID: "circle-approval", TargetPersonaID: "persona-b",
	})
	if err != nil || rejected.State != string(model.CircleMembershipStateRejected) {
		t.Fatalf("RejectCircleMember drift: result=%+v err=%v", rejected, err)
	}

	stored, found, err := store.LoadByIdentity(context.Background(), "circle-approval", "persona-b")
	if err != nil || !found || stored.State != model.CircleMembershipStateRejected {
		t.Fatalf("rejected membership persistence drift: stored=%+v found=%v err=%v", stored, found, err)
	}
}

type membershipFacadeStore struct {
	memberships map[string]model.CircleMembership
}

func newMembershipFacadeStore() *membershipFacadeStore {
	return &membershipFacadeStore{memberships: make(map[string]model.CircleMembership)}
}

func (store *membershipFacadeStore) Load(_ context.Context, membershipID string) (model.CircleMembership, bool, error) {
	value, found := store.memberships[membershipID]
	return value, found, nil
}

func (store *membershipFacadeStore) LoadByIdentity(_ context.Context, circleID, personaID string) (model.CircleMembership, bool, error) {
	for _, membership := range store.memberships {
		if membership.CircleID == circleID && membership.PersonaID == personaID {
			return membership, true, nil
		}
	}
	return model.CircleMembership{}, false, nil
}

func (store *membershipFacadeStore) Commit(_ context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	var current *model.CircleMembership
	if value, found := store.memberships[request.Change.MembershipID]; found {
		copy := value
		current = &copy
	}
	next, _, err := request.Change.Apply(current)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	store.memberships[next.ID] = next
	return ports.CommitReceipt{
		MembershipID: next.ID,
		Version:      next.Version,
		State:        next.State,
		Role:         next.Role,
	}, nil
}

func (store *membershipFacadeStore) ReadCirclePolicy(_ context.Context, circleID string) (ports.CirclePolicySlice, bool, error) {
	if circleID != "circle-approval" {
		return ports.CirclePolicySlice{}, false, nil
	}
	return ports.CirclePolicySlice{
		CircleID:       circleID,
		OwnerPersonaID: "persona-owner",
		State:          "active",
		JoinPolicy:     "approval",
	}, true, nil
}

func (store *membershipFacadeStore) ReadCircleMembership(ctx context.Context, circleID, personaID string) (model.CircleMembership, bool, error) {
	return store.LoadByIdentity(ctx, circleID, personaID)
}

func (store *membershipFacadeStore) ListCircleMemberships(_ context.Context, circleID string, _ int, _ string) (ports.MembershipSlice, error) {
	items := make([]model.CircleMembership, 0, len(store.memberships))
	for _, membership := range store.memberships {
		if membership.CircleID == circleID && membership.State == model.CircleMembershipStateActive {
			items = append(items, membership)
		}
	}
	return ports.MembershipSlice{Items: items}, nil
}

func (store *membershipFacadeStore) ListPendingCircleMemberships(_ context.Context, circleID string, _ int, _ string) (ports.MembershipSlice, error) {
	items := make([]model.CircleMembership, 0, len(store.memberships))
	for _, membership := range store.memberships {
		if membership.CircleID == circleID && membership.State == model.CircleMembershipStatePending {
			items = append(items, membership)
		}
	}
	return ports.MembershipSlice{Items: items}, nil
}

func (store *membershipFacadeStore) ListPersonaCircles(context.Context, ports.PersonaCircleQuery) (ports.PersonaCircleSlice, error) {
	return ports.PersonaCircleSlice{}, nil
}

func membershipCommandContext(personaID, idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		IdempotencyKey: idempotencyKey,
		Actor:          operation.ActorContext{PersonaID: personaID},
	})
}

func membershipReadContext(personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		Actor: operation.ActorContext{PersonaID: personaID},
	})
}
