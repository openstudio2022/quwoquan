// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
// readiness_case: activate-circle-group-owner-local
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
	membershipports "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/ports"
)

type ownerActivationDependencies struct {
	committed membershipmodel.CircleGroupMembership
}

func (dependencies *ownerActivationDependencies) Load(context.Context, string) (membershipmodel.CircleGroupMembership, bool, error) {
	return membershipmodel.CircleGroupMembership{}, false, nil
}

func (dependencies *ownerActivationDependencies) LoadByIdentity(context.Context, string, string) (membershipmodel.CircleGroupMembership, bool, error) {
	return membershipmodel.CircleGroupMembership{}, false, nil
}

func (dependencies *ownerActivationDependencies) Commit(_ context.Context, request membershipports.CommitRequest) (membershipports.CommitReceipt, error) {
	next, _, err := request.Change.Apply(nil)
	if err != nil {
		return membershipports.CommitReceipt{}, err
	}
	dependencies.committed = next
	return membershipports.CommitReceipt{
		MembershipID: next.ID,
		Version:      next.Version,
		Role:         next.Role,
		State:        next.State,
	}, nil
}

func (dependencies *ownerActivationDependencies) ReadGroupPolicy(_ context.Context, circleID, groupID string) (membershipports.GroupPolicySlice, bool, error) {
	return membershipports.GroupPolicySlice{
		GroupID: groupID, CircleID: circleID, Status: "active", CreatedByPersonaID: "persona-owner",
	}, true, nil
}

func (dependencies *ownerActivationDependencies) IsActiveCircleMember(context.Context, string, string) (bool, error) {
	return true, nil
}

func (dependencies *ownerActivationDependencies) ReadGroupMembership(context.Context, string, string) (membershipmodel.CircleGroupMembership, bool, error) {
	return membershipmodel.CircleGroupMembership{}, false, nil
}

func (dependencies *ownerActivationDependencies) ListGroupMemberships(context.Context, string, string, int, string) (membershipports.MembershipPage, error) {
	return membershipports.MembershipPage{}, nil
}

type groupOwnerRelayStore struct {
	events     []groupports.OutboxEvent
	checkpoint string
}

func (store *groupOwnerRelayStore) ReadAfter(_ context.Context, checkpoint string, _ int) ([]groupports.OutboxEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return store.events, nil
}

func (store *groupOwnerRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return store.checkpoint, nil
}

func (store *groupOwnerRelayStore) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	store.checkpoint = checkpoint
	return nil
}

func TestCircleGroupOwnerActivationConsumesCreatedEventBeforeCheckpoint(t *testing.T) {
	dependencies := &ownerActivationDependencies{}
	commands := membershipapp.NewCommandFacade(
		dependencies, dependencies, dependencies, dependencies,
	)
	payload, err := json.Marshal(map[string]string{
		"groupId": "group-1", "circleId": "circle-1", "createdByPersonaId": "persona-owner",
	})
	if err != nil {
		t.Fatal(err)
	}
	store := &groupOwnerRelayStore{events: []groupports.OutboxEvent{{
		EventID: "group-1:CircleGroupCreated:1", EventType: "CircleGroupCreated",
		AggregateID: "group-1", AggregateVersion: 1, Payload: payload,
		OccurredAt: time.Date(2026, 8, 5, 8, 0, 0, 0, time.UTC), Checkpoint: "1",
	}}}
	relay := groupapp.NewOutboxRelay(
		store,
		store,
		membershipapp.NewCircleGroupOwnerProjector(commands),
		"circle-group-owner",
	)

	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	if dependencies.committed.GroupID != "group-1" ||
		dependencies.committed.PersonaID != "persona-owner" ||
		dependencies.committed.Role != membershipmodel.CircleGroupMembershipRoleOwner ||
		dependencies.committed.State != membershipmodel.CircleGroupMembershipStateActive {
		t.Fatalf("owner activation state=%+v", dependencies.committed)
	}
	if store.checkpoint != "1" {
		t.Fatalf("owner activation checkpoint=%q want=1", store.checkpoint)
	}
}
