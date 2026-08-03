// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
package local_contract

import (
	"context"
	"fmt"
	"testing"
	"time"

	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

func TestGatheringProjectionConvergesMembershipAndRejectsVersionReuse(t *testing.T) {
	backend := newGatheringProjectionBackend()
	facade := membershipapp.NewGatheringProjectionFacade(
		backend, backend, backend, backend, backend, backend, backend, backend,
	)
	command := membershipapp.GatheringProjectionCommand{
		SourceEventID: "gathering-1:join:persona-2", SourceVersion: 20,
		GatheringID: "gathering-1", PersonaID: "persona-2", OwnerPersonaID: "persona-owner",
		State: membershipapp.GatheringProjectionJoined,
	}
	result, err := facade.Project(context.Background(), command)
	if err != nil {
		t.Fatalf("Project joined: %v", err)
	}
	if result.ConversationID != "conversation-1" || backend.members["persona-2"] == nil ||
		!backend.userStates["persona-2"] || backend.memberCount != 2 {
		t.Fatalf("joined projection did not converge: result=%+v backend=%+v", result, backend)
	}
	if len(backend.membershipEvents) != 1 || len(backend.conversationEvents) != 1 {
		t.Fatalf("projection outbox counts = membership:%d conversation:%d", len(backend.membershipEvents), len(backend.conversationEvents))
	}

	if _, err := facade.Project(context.Background(), command); err != nil {
		t.Fatalf("exact replay must be idempotent: %v", err)
	}
	if len(backend.membershipEvents) != 1 || backend.memberCount != 2 {
		t.Fatal("exact replay emitted a second side effect")
	}

	conflict := command
	conflict.SourceEventID = "gathering-1:another-fact"
	if _, err := facade.Project(context.Background(), conflict); err == nil {
		t.Fatal("same sourceVersion with another event must fail closed")
	}

	left := command
	left.SourceEventID = "gathering-1:leave:persona-2"
	left.SourceVersion = 30
	left.State = membershipapp.GatheringProjectionLeft
	if _, err := facade.Project(context.Background(), left); err != nil {
		t.Fatalf("Project left: %v", err)
	}
	if backend.members["persona-2"] != nil || backend.userStates["persona-2"] || backend.memberCount != 1 {
		t.Fatalf("left projection did not converge: %+v", backend)
	}
}

type gatheringProjectionBackend struct {
	members            map[string]*membershipmodel.Member
	userStates         map[string]bool
	states             map[string]membershipapp.GatheringProjectionState
	membershipEvents   []membershipapp.GatheringOutboxEvent
	conversationEvents []membershipapp.GatheringOutboxEvent
	memberCount        int
}

func newGatheringProjectionBackend() *gatheringProjectionBackend {
	return &gatheringProjectionBackend{
		members: map[string]*membershipmodel.Member{
			"persona-owner": {
				ID: "member-owner", ConversationId: "conversation-1", UserId: "persona-owner",
				MemberType: "user", Role: "owner", JoinedAt: time.Now().UTC(),
			},
		},
		userStates: map[string]bool{"persona-owner": true},
		states:     map[string]membershipapp.GatheringProjectionState{}, memberCount: 1,
	}
}

func (backend *gatheringProjectionBackend) RunInTransaction(ctx context.Context, apply func(context.Context) error) error {
	return apply(ctx)
}

func (backend *gatheringProjectionBackend) ReadGatheringConversation(context.Context, string) (membershipapp.GatheringBinding, bool, error) {
	return membershipapp.GatheringBinding{
		GatheringID: "gathering-1", ConversationID: "conversation-1",
		OwnerPersonaID: "persona-owner", MaxGroupSize: 4, Active: true,
	}, true, nil
}

func (backend *gatheringProjectionBackend) CreateMember(_ context.Context, member *membershipmodel.Member) error {
	if backend.members[member.UserId] != nil {
		return fmt.Errorf("duplicate member")
	}
	copy := *member
	backend.members[member.UserId] = &copy
	return nil
}

func (backend *gatheringProjectionBackend) DeleteMember(_ context.Context, _, userID string) error {
	delete(backend.members, userID)
	return nil
}

func (backend *gatheringProjectionBackend) FindMember(_ context.Context, _, userID string) (*membershipmodel.Member, error) {
	member := backend.members[userID]
	if member == nil {
		return nil, fmt.Errorf("%w: %s", membershipmodel.ErrNotFound, userID)
	}
	copy := *member
	return &copy, nil
}

func (backend *gatheringProjectionBackend) CountUserMembers(context.Context, string) (int, error) {
	return len(backend.members), nil
}

func (backend *gatheringProjectionBackend) EnsureGatheringUserState(_ context.Context, userID, _ string, _ time.Time) error {
	backend.userStates[userID] = true
	return nil
}

func (backend *gatheringProjectionBackend) DeleteGatheringUserState(_ context.Context, userID, _ string) error {
	delete(backend.userStates, userID)
	return nil
}

func (backend *gatheringProjectionBackend) BumpGatheringRoster(_ context.Context, _ string, memberCount int) error {
	backend.memberCount = memberCount
	return nil
}

func (backend *gatheringProjectionBackend) ReadGatheringMemberProfile(context.Context, string) (membershipapp.GatheringMemberProfile, error) {
	return membershipapp.GatheringMemberProfile{DisplayName: "同行者"}, nil
}

func (backend *gatheringProjectionBackend) LoadGatheringProjectionState(_ context.Context, gatheringID, personaID string) (membershipapp.GatheringProjectionState, bool, error) {
	state, found := backend.states[gatheringID+":"+personaID]
	return state, found, nil
}

func (backend *gatheringProjectionBackend) SaveGatheringProjectionState(_ context.Context, state membershipapp.GatheringProjectionState) error {
	backend.states[state.GatheringID+":"+state.PersonaID] = state
	return nil
}

func (backend *gatheringProjectionBackend) AppendGatheringProjectionEvents(_ context.Context, membershipEvents, conversationEvents []membershipapp.GatheringOutboxEvent) error {
	backend.membershipEvents = append(backend.membershipEvents, membershipEvents...)
	backend.conversationEvents = append(backend.conversationEvents, conversationEvents...)
	return nil
}
