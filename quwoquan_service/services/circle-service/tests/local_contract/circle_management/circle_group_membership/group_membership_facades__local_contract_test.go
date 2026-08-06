// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: apply-join-circle-group-local
// readiness_case: list-circle-group-memberships-local
// readiness_case: get-my-circle-group-membership-local
// readiness_case: leave-circle-group-local
// readiness_case: approve-circle-group-member-local
// readiness_case: reject-circle-group-member-local
// readiness_case: remove-circle-group-member-local
// readiness_case: update-circle-group-member-role-local
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/ports"
)

func TestCircleGroupMembershipFacadesExecuteEveryHTTPOperation(t *testing.T) {
	store := newGroupMembershipFacadeStore()
	commands := app.NewCommandFacade(store, store, store, store)
	queries := app.NewQueryFacade(store, store)

	applied, err := commands.Apply(groupMembershipContext("persona-a", "apply-a"), "circle-1", "group-1")
	if err != nil || applied.State != string(model.CircleGroupMembershipStatePending) {
		t.Fatalf("ApplyJoinCircleGroup drift: result=%+v err=%v", applied, err)
	}
	myMembership, err := queries.GetMy(groupMembershipReadContext("persona-a"), "circle-1", "group-1")
	if err != nil || myMembership.PersonaID != "persona-a" || myMembership.State != model.CircleGroupMembershipStatePending {
		t.Fatalf("GetMyCircleGroupMembership drift: result=%+v err=%v", myMembership, err)
	}
	roster, err := queries.List(groupMembershipReadContext("persona-owner"), "circle-1", "group-1", "", 20, "")
	if err != nil || len(roster.Items) != 2 {
		t.Fatalf("ListCircleGroupMemberships drift: result=%+v err=%v", roster, err)
	}
	approved, err := commands.Approve(groupMembershipContext("persona-owner", "approve-a"), app.TargetCommand{
		CircleID: "circle-1", GroupID: "group-1", TargetPersonaID: "persona-a",
	})
	if err != nil || approved.State != string(model.CircleGroupMembershipStateActive) {
		t.Fatalf("ApproveCircleGroupMember drift: result=%+v err=%v", approved, err)
	}
	roleUpdated, err := commands.UpdateRole(groupMembershipContext("persona-owner", "role-a"), app.TargetCommand{
		CircleID: "circle-1", GroupID: "group-1", TargetPersonaID: "persona-a",
		Role: model.CircleGroupMembershipRoleManager,
	})
	if err != nil || roleUpdated.Role != string(model.CircleGroupMembershipRoleManager) {
		t.Fatalf("UpdateCircleGroupMemberRole drift: result=%+v err=%v", roleUpdated, err)
	}
	left, err := commands.Leave(groupMembershipContext("persona-a", "leave-a"), app.SelfCommand{
		CircleID: "circle-1", GroupID: "group-1",
	})
	if err != nil || left.State != string(model.CircleGroupMembershipStateLeft) {
		t.Fatalf("LeaveCircleGroup drift: result=%+v err=%v", left, err)
	}

	if _, err := commands.Apply(groupMembershipContext("persona-b", "apply-b"), "circle-1", "group-1"); err != nil {
		t.Fatalf("Apply persona-b: %v", err)
	}
	rejected, err := commands.Reject(groupMembershipContext("persona-owner", "reject-b"), app.TargetCommand{
		CircleID: "circle-1", GroupID: "group-1", TargetPersonaID: "persona-b",
	})
	if err != nil || rejected.State != string(model.CircleGroupMembershipStateRejected) {
		t.Fatalf("RejectCircleGroupMember drift: result=%+v err=%v", rejected, err)
	}
	if _, err := commands.Apply(groupMembershipContext("persona-c", "apply-c"), "circle-1", "group-1"); err != nil {
		t.Fatalf("Apply persona-c: %v", err)
	}
	removed, err := commands.Remove(groupMembershipContext("persona-owner", "remove-c"), app.TargetCommand{
		CircleID: "circle-1", GroupID: "group-1", TargetPersonaID: "persona-c",
	})
	if err != nil || removed.State != string(model.CircleGroupMembershipStateRemoved) {
		t.Fatalf("RemoveCircleGroupMember drift: result=%+v err=%v", removed, err)
	}
}

type groupMembershipFacadeStore struct {
	memberships map[string]model.CircleGroupMembership
}

func newGroupMembershipFacadeStore() *groupMembershipFacadeStore {
	now := time.Now().UTC()
	return &groupMembershipFacadeStore{memberships: map[string]model.CircleGroupMembership{
		"membership-owner": {
			ID: "membership-owner", Version: 1, GroupID: "group-1", CircleID: "circle-1",
			PersonaID: "persona-owner", Role: model.CircleGroupMembershipRoleOwner,
			State: model.CircleGroupMembershipStateActive, JoinedAt: now,
			CreatedAt: now, UpdatedAt: now,
		},
	}}
}

func (store *groupMembershipFacadeStore) Load(_ context.Context, membershipID string) (model.CircleGroupMembership, bool, error) {
	value, found := store.memberships[membershipID]
	return value, found, nil
}

func (store *groupMembershipFacadeStore) LoadByIdentity(_ context.Context, groupID, personaID string) (model.CircleGroupMembership, bool, error) {
	return store.find(groupID, personaID)
}

func (store *groupMembershipFacadeStore) Commit(_ context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	var current *model.CircleGroupMembership
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
		MembershipID: next.ID, Version: next.Version, Role: next.Role, State: next.State,
	}, nil
}

func (store *groupMembershipFacadeStore) ReadGroupPolicy(_ context.Context, circleID, groupID string) (ports.GroupPolicySlice, bool, error) {
	if circleID != "circle-1" || groupID != "group-1" {
		return ports.GroupPolicySlice{}, false, nil
	}
	return ports.GroupPolicySlice{
		GroupID: groupID, CircleID: circleID, JoinPolicy: "apply_only",
		Status: "active", CreatedByPersonaID: "persona-owner",
	}, true, nil
}

func (store *groupMembershipFacadeStore) IsActiveCircleMember(_ context.Context, circleID, personaID string) (bool, error) {
	return circleID == "circle-1" && personaID != "", nil
}

func (store *groupMembershipFacadeStore) ReadGroupMembership(_ context.Context, groupID, personaID string) (model.CircleGroupMembership, bool, error) {
	return store.find(groupID, personaID)
}

func (store *groupMembershipFacadeStore) ListGroupMemberships(_ context.Context, groupID, state string, _ int, _ string) (ports.MembershipPage, error) {
	items := make([]model.CircleGroupMembership, 0, len(store.memberships))
	for _, value := range store.memberships {
		if value.GroupID == groupID && (state == "" || string(value.State) == state) {
			items = append(items, value)
		}
	}
	return ports.MembershipPage{Items: items}, nil
}

func (store *groupMembershipFacadeStore) find(groupID, personaID string) (model.CircleGroupMembership, bool, error) {
	for _, value := range store.memberships {
		if value.GroupID == groupID && value.PersonaID == personaID {
			return value, true, nil
		}
	}
	return model.CircleGroupMembership{}, false, nil
}

func groupMembershipContext(personaID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		IdempotencyKey: key, Actor: operation.ActorContext{PersonaID: personaID},
	})
}

func groupMembershipReadContext(personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		Actor: operation.ActorContext{PersonaID: personaID},
	})
}
