// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
// readiness_case: project-circle-group-membership-local
package local_contract

import (
	"context"
	"testing"
	"time"

	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
)

type circleGroupMembershipProjectionAdapter struct {
	projector conversationapp.CircleGroupChatSyncProjector
}

func (adapter circleGroupMembershipProjectionAdapter) ProjectCircleGroupMembership(
	ctx context.Context,
	fact membershipapp.CircleGroupMembershipFact,
) error {
	return adapter.projector.Apply(ctx, conversationapp.CircleGroupChatSourceEvent{
		EventID: fact.EventID, EventType: fact.EventType, GroupID: fact.GroupID,
		CircleID: fact.CircleID, Version: fact.Version, UserID: fact.UserID,
		Role: fact.Role, State: fact.State, OccurredAt: fact.OccurredAt,
	})
}

func TestCircleGroupMembershipConsumerAppliesStateCheckpointAndOutbox(t *testing.T) {
	backend := newCircleGroupMembershipBackend()
	ports := conversationapp.ChatStoragePorts{
		Transactions: backend, Conversations: backend, CircleGroupConversations: backend,
		Members: backend, RosterProjection: backend, UserStates: backend,
		MembershipCommands:                backend,
		CircleGroupMembershipProjections:  backend,
		CircleGroupChatBindingProjections: backend,
	}
	cache := circleGroupMembershipCache{}
	publisher := circleGroupMembershipPublisher{}
	scheduler := &circleGroupMembershipScheduler{}
	conversations := conversationapp.NewConversationService(
		ports, cache, publisher, nil, nil, nil, nil, scheduler,
	)
	members := conversationapp.NewMemberService(
		ports, cache, publisher, nil, nil, nil, scheduler,
	)
	consumer := membershipapp.NewCircleGroupMembershipProjectionHandler(
		circleGroupMembershipProjectionAdapter{
			projector: conversationapp.NewCircleGroupConversationProjectionHandler(conversations, members),
		},
	)
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	activated := membershipapp.CircleGroupMembershipFact{
		EventID: "membership-persona-2:active:1", EventType: "CircleGroupMembershipActivated",
		GroupID: "circle-group-1", CircleID: "circle-1", Version: 1,
		UserID: "persona-2", Role: "member", State: "active", OccurredAt: now,
	}
	if err := consumer.Apply(t.Context(), activated); err != nil {
		t.Fatalf("apply active CircleGroupMembership: %v", err)
	}
	member := backend.members[activated.UserID]
	if member == nil || member.ConversationId != backend.conversation.ID || member.Role != "member" {
		t.Fatalf("active membership state drifted: %+v", member)
	}
	if !backend.userStates[activated.UserID] {
		t.Fatal("active membership did not create ConversationUserState")
	}
	checkpoint := backend.membershipProjection[activated.UserID]
	if checkpoint.SourceVersion != 1 || checkpoint.LastEventID != activated.EventID || checkpoint.State != "active" {
		t.Fatalf("membership checkpoint drifted: %+v", checkpoint)
	}
	if !containsCircleGroupMembershipEvent(backend.outbox, "ConversationMemberAdded") ||
		!containsCircleGroupMembershipEvent(backend.outbox, "ConversationRosterUpdated") {
		t.Fatalf("membership outbox drifted: %+v", backend.outbox)
	}
	firstOutboxCount := len(backend.outbox)
	if err := consumer.Apply(t.Context(), activated); err != nil {
		t.Fatalf("replay active CircleGroupMembership: %v", err)
	}
	if len(backend.outbox) != firstOutboxCount {
		t.Fatalf("event-id replay appended outbox: before=%d after=%d", firstOutboxCount, len(backend.outbox))
	}

	left := activated
	left.EventID = "membership-persona-2:left:2"
	left.EventType = "CircleGroupMembershipLeft"
	left.Version = 2
	left.Role = ""
	left.State = "left"
	left.OccurredAt = now.Add(time.Minute)
	if err := consumer.Apply(t.Context(), left); err != nil {
		t.Fatalf("apply terminal CircleGroupMembership: %v", err)
	}
	if backend.members[left.UserID] != nil || backend.userStates[left.UserID] {
		t.Fatalf("terminal membership did not remove active state: member=%+v userState=%v", backend.members[left.UserID], backend.userStates[left.UserID])
	}
	checkpoint = backend.membershipProjection[left.UserID]
	if checkpoint.SourceVersion != 2 || checkpoint.State != "left" ||
		!containsCircleGroupMembershipEvent(backend.outbox, "ConversationMemberLeft") {
		t.Fatalf("terminal checkpoint/outbox drifted: checkpoint=%+v outbox=%+v", checkpoint, backend.outbox)
	}
	if scheduler.enqueued != 2 {
		t.Fatalf("group-avatar recompute count=%d, want 2 state changes", scheduler.enqueued)
	}
}

type circleGroupMembershipBackend struct {
	conversationapp.ConversationStore
	conversationapp.MemberStore
	conversationapp.UserStateStore
	conversationapp.ConversationRosterProjector
	conversationapp.AggregateCommandStore
	conversationapp.CircleGroupMembershipProjectionStore
	conversationapp.CircleGroupChatBindingProjectionStore

	conversation         *conversationmodel.Conversation
	members              map[string]*conversationmodel.ConversationMember
	userStates           map[string]bool
	membershipProjection map[string]conversationapp.CircleGroupMembershipProjectionState
	outbox               []conversationapp.AggregateOutboxEvent
}

func newCircleGroupMembershipBackend() *circleGroupMembershipBackend {
	return &circleGroupMembershipBackend{
		conversation: &conversationmodel.Conversation{
			ID: "conversation-circle-1", Type: "group", Status: conversationmodel.ConversationStatusActive,
			CircleId: "circle-1", CircleGroupId: "circle-group-1", CreatorId: "owner-1",
			MaxGroupSize: 1000, MemberCount: 1, MembersRosterRevision: 1,
		},
		members: map[string]*conversationmodel.ConversationMember{
			"owner-1": {
				ID: "member-owner", ConversationId: "conversation-circle-1", UserId: "owner-1",
				MemberType: "user", Role: "owner", JoinedAt: time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC),
			},
		},
		userStates:           map[string]bool{"owner-1": true},
		membershipProjection: map[string]conversationapp.CircleGroupMembershipProjectionState{},
	}
}

func (*circleGroupMembershipBackend) RunInTransaction(ctx context.Context, apply func(context.Context) error) error {
	return apply(ctx)
}

func (backend *circleGroupMembershipBackend) FindConversationByCircleGroupID(
	context.Context,
	string,
) (*conversationmodel.Conversation, error) {
	copy := *backend.conversation
	return &copy, nil
}

func (backend *circleGroupMembershipBackend) FindConversationByID(
	context.Context,
	string,
) (*conversationmodel.Conversation, error) {
	copy := *backend.conversation
	return &copy, nil
}

func (backend *circleGroupMembershipBackend) CreateMember(
	_ context.Context,
	member *conversationmodel.ConversationMember,
) error {
	copy := *member
	backend.members[member.UserId] = &copy
	return nil
}

func (backend *circleGroupMembershipBackend) DeleteMember(_ context.Context, _ string, userID string) error {
	delete(backend.members, userID)
	return nil
}

func (backend *circleGroupMembershipBackend) FindMember(
	_ context.Context,
	_ string,
	userID string,
) (*conversationmodel.ConversationMember, error) {
	member := backend.members[userID]
	if member == nil {
		return nil, conversationmodel.ErrMemberNotFound
	}
	copy := *member
	return &copy, nil
}

func (backend *circleGroupMembershipBackend) CountMembers(context.Context, string) (int, error) {
	return len(backend.members), nil
}

func (backend *circleGroupMembershipBackend) CountUserMembers(context.Context, string) (int, error) {
	return len(backend.members), nil
}

func (backend *circleGroupMembershipBackend) UpsertUserState(
	_ context.Context,
	state *conversationmodel.ConversationUserState,
) error {
	backend.userStates[state.UserId] = true
	return nil
}

func (backend *circleGroupMembershipBackend) DeleteUserState(_ context.Context, userID, _ string) error {
	delete(backend.userStates, userID)
	return nil
}

func (backend *circleGroupMembershipBackend) BumpMembersRosterRevision(
	_ context.Context,
	_ string,
	memberCount *int,
) error {
	backend.conversation.MembersRosterRevision++
	if memberCount != nil {
		backend.conversation.MemberCount = *memberCount
	}
	return nil
}

func (backend *circleGroupMembershipBackend) LoadCircleGroupMembershipProjection(
	_ context.Context,
	_ string,
	userID string,
) (conversationapp.CircleGroupMembershipProjectionState, bool, error) {
	state, found := backend.membershipProjection[userID]
	return state, found, nil
}

func (backend *circleGroupMembershipBackend) SaveCircleGroupMembershipProjection(
	_ context.Context,
	state conversationapp.CircleGroupMembershipProjectionState,
) error {
	backend.membershipProjection[state.UserID] = state
	return nil
}

func (*circleGroupMembershipBackend) LoadCircleGroupChatBindingProjection(
	context.Context,
	string,
) (conversationapp.CircleGroupChatBindingProjectionState, bool, error) {
	return conversationapp.CircleGroupChatBindingProjectionState{Status: "active"}, true, nil
}

func (*circleGroupMembershipBackend) SaveCircleGroupChatBindingProjection(
	context.Context,
	conversationapp.CircleGroupChatBindingProjectionState,
) error {
	return nil
}

func (backend *circleGroupMembershipBackend) AppendAggregateOutboxEvents(
	_ context.Context,
	events []conversationapp.AggregateOutboxEvent,
) error {
	backend.outbox = append(backend.outbox, events...)
	return nil
}

func containsCircleGroupMembershipEvent(events []conversationapp.AggregateOutboxEvent, eventType string) bool {
	for _, event := range events {
		if event.EventType == eventType {
			return true
		}
	}
	return false
}

type circleGroupMembershipCache struct{}

func (circleGroupMembershipCache) InvalidateConversation(context.Context, string) error { return nil }

type circleGroupMembershipPublisher struct{}

func (circleGroupMembershipPublisher) PublishDomainEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func (circleGroupMembershipPublisher) PublishRecordedDomainEvent(context.Context, string, string, string, string, map[string]any) error {
	return nil
}

type circleGroupMembershipScheduler struct{ enqueued int }

func (scheduler *circleGroupMembershipScheduler) EnqueueRecompute(
	context.Context,
	conversationapp.GroupAvatarRecomputeTask,
) error {
	scheduler.enqueued++
	return nil
}

func (*circleGroupMembershipScheduler) EnqueueConversationAvatarPatch(
	context.Context,
	conversationapp.ConversationAvatarPatchTask,
) error {
	return nil
}
