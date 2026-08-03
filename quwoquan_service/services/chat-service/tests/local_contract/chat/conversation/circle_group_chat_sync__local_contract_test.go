package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"strings"
	"testing"
	"time"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func TestCircleGroupChatSyncProjectsLifecycleAndRejectsLateMembership(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	commands := newMemoryAggregateCommandStore()
	conversationService := NewConversationService(
		ChatStoragePorts{
			Transactions:                      passthroughTransactionRunner{},
			Conversations:                     store,
			CircleGroupConversations:          store,
			Members:                           store,
			UserStates:                        store,
			ConversationCommands:              commands,
			CircleGroupChatBindingProjections: store,
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
	memberService := NewMemberService(
		ChatStoragePorts{
			Transactions:                      passthroughTransactionRunner{},
			Conversations:                     store,
			Members:                           store,
			RosterProjection:                  store,
			UserStates:                        store,
			MembershipCommands:                commands,
			CircleGroupMembershipProjections:  store,
			CircleGroupChatBindingProjections: store,
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
	syncService := NewCircleGroupChatSyncService(conversationService, memberService)
	now := time.Date(2026, 7, 21, 1, 2, 3, 0, time.UTC)

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "group-1:created:1", EventType: "CircleGroupCreated",
		GroupID: "group-1", CircleID: "circle-1", Version: 1,
		Name: "摄影小组", OwnerID: "owner-1", OccurredAt: now,
	}); err != nil {
		t.Fatalf("project CircleGroupCreated: %v", err)
	}
	conv, err := store.FindConversationByCircleGroupID(context.Background(), "group-1")
	if err != nil {
		t.Fatalf("bound conversation missing: %v", err)
	}
	if conv.MaxGroupSize != 1000 || conv.CreatorId != "owner-1" ||
		conv.CircleId != "circle-1" || conv.CircleGroupId != "group-1" {
		t.Fatalf("invalid bound conversation: %+v", conv)
	}
	if _, err := store.FindMember(context.Background(), conv.ID, "owner-1"); err != nil {
		t.Fatalf("owner member missing: %v", err)
	}
	if _, err := store.FindUserState(context.Background(), "owner-1", conv.ID); err != nil {
		t.Fatalf("owner inbox state missing: %v", err)
	}
	if !containsAggregateEvent(commands.events, "CircleGroupConversationProvisioned") {
		t.Fatalf("provisioning must enqueue reverse durable binding event: %#v", commands.eventTypes())
	}

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "membership-p2:active:1", EventType: "CircleGroupMembershipActivated",
		GroupID: "group-1", CircleID: "circle-1", Version: 1,
		UserID: "p2", Role: "manager", State: "active", OccurredAt: now.Add(time.Second),
	}); err != nil {
		t.Fatalf("project active member: %v", err)
	}
	member, err := store.FindMember(context.Background(), conv.ID, "p2")
	if err != nil || member.Role != "admin" {
		t.Fatalf("manager must map to Chat admin, member=%+v err=%v", member, err)
	}
	if _, err := store.FindUserState(context.Background(), "p2", conv.ID); err != nil {
		t.Fatalf("active member state missing: %v", err)
	}

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "membership-p2:left:2", EventType: "CircleGroupMembershipLeft",
		GroupID: "group-1", CircleID: "circle-1", Version: 2,
		UserID: "p2", Role: "manager", State: "left", OccurredAt: now.Add(2 * time.Second),
	}); err != nil {
		t.Fatalf("project left member: %v", err)
	}
	if _, err := store.FindMember(context.Background(), conv.ID, "p2"); !errors.Is(err, model.ErrMemberNotFound) {
		t.Fatalf("left member must be deleted, got %v", err)
	}
	if _, err := store.FindUserState(context.Background(), "p2", conv.ID); !errors.Is(err, model.ErrUserStateNotFound) {
		t.Fatalf("left member Inbox must be deleted, got %v", err)
	}
	if !containsAggregateEvent(commands.events, "ConversationMemberLeft") {
		t.Fatalf("left member must enqueue terminal realtime event: %#v", commands.eventTypes())
	}

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "membership-p2:active:1", EventType: "CircleGroupMembershipActivated",
		GroupID: "group-1", CircleID: "circle-1", Version: 1,
		UserID: "p2", Role: "manager", State: "active", OccurredAt: now,
	}); err != nil {
		t.Fatalf("late active replay must be no-op: %v", err)
	}
	if _, err := store.FindMember(context.Background(), conv.ID, "p2"); !errors.Is(err, model.ErrMemberNotFound) {
		t.Fatalf("late active must not resurrect terminal member, got %v", err)
	}

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "group-1:archived:2", EventType: "CircleGroupArchived",
		GroupID: "group-1", CircleID: "circle-1", Version: 2, OccurredAt: now.Add(3 * time.Second),
	}); err != nil {
		t.Fatalf("project CircleGroupArchived: %v", err)
	}
	conv, err = store.FindConversationByID(context.Background(), conv.ID)
	if err != nil || conv.Status != model.ConversationStatusDissolved {
		t.Fatalf("archive must dissolve bound conversation, conv=%+v err=%v", conv, err)
	}
	if _, err := store.FindMember(context.Background(), conv.ID, "owner-1"); !errors.Is(err, model.ErrMemberNotFound) {
		t.Fatalf("archive must remove owner roster entry, got %v", err)
	}

	if err := syncService.Apply(context.Background(), CircleGroupChatSourceEvent{
		EventID: "membership-p3:active:3", EventType: "CircleGroupMembershipActivated",
		GroupID: "group-1", CircleID: "circle-1", Version: 3,
		UserID: "p3", Role: "member", State: "active", OccurredAt: now.Add(4 * time.Second),
	}); err != nil {
		t.Fatalf("late membership after archive must be no-op: %v", err)
	}
	if _, err := store.FindMember(context.Background(), conv.ID, "p3"); !errors.Is(err, model.ErrMemberNotFound) {
		t.Fatalf("archive must win over late membership, got %v", err)
	}
}

func TestCircleGroupChatSyncRejectsPublicChatGovernance(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	store.conversations["conv-circle"] = &model.Conversation{
		ID: "conv-circle", Type: "group", Status: model.ConversationStatusActive,
		CircleId: "circle-1", CircleGroupId: "group-1", MaxGroupSize: 1000,
	}
	store.members[store.memberKey("conv-circle", "owner")] = &model.ConversationMember{
		ID: "member-owner", ConversationId: "conv-circle", UserId: "owner", MemberType: "user", Role: "owner",
	}
	memberService := NewMemberService(
		ChatStoragePorts{
			Transactions:       passthroughTransactionRunner{},
			Conversations:      store,
			Members:            store,
			RosterProjection:   store,
			UserStates:         store,
			MembershipCommands: newMemoryAggregateCommandStore(),
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
	err := memberService.AddMembers(commandContext("owner", "attempt-private-add"), AddMembersRequest{
		ConversationId: "conv-circle", InvitedBy: "owner", UserIds: []string{"p2"},
	})
	if err == nil || !strings.Contains(err.Error(), "CHAT.USER.source_managed_conversation") {
		t.Fatalf("Circle-bound Chat HTTP governance must be rejected, got %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestGatheringConversationRejectsPublicChatGovernance(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	store.conversations["conv-gathering"] = &model.Conversation{
		ID: "conv-gathering", Type: "group", Status: model.ConversationStatusActive,
		GatheringId: "gathering-1", MaxGroupSize: 8,
	}
	store.members[store.memberKey("conv-gathering", "owner")] = &model.ConversationMember{
		ID: "member-owner", ConversationId: "conv-gathering", UserId: "owner", MemberType: "user", Role: "owner",
	}
	memberService := NewMemberService(
		ChatStoragePorts{
			Transactions: passthroughTransactionRunner{}, Conversations: store, Members: store,
			RosterProjection: store, UserStates: store, MembershipCommands: newMemoryAggregateCommandStore(),
		},
		noopCache{}, syncNoopEventPublisher{}, nil, nil, nil,
		syncNoopGroupAvatarScheduler{},
	)
	err := memberService.AddMembers(commandContext("owner", "attempt-gathering-add"), AddMembersRequest{
		ConversationId: "conv-gathering", InvitedBy: "owner", UserIds: []string{"p2"},
	})
	if err == nil || !strings.Contains(err.Error(), "CHAT.USER.source_managed_conversation") {
		t.Fatalf("Gathering-bound Chat governance must be rejected, got %v", err)
	}
}

func TestProvisionCircleGroupConversationRecoversConcurrentBinding(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	store.hideNextCircleGroupLookup = true
	store.conversations["already-bound"] = &model.Conversation{
		ID:            "already-bound",
		Type:          "group",
		Status:        model.ConversationStatusActive,
		CircleId:      "circle-1",
		CircleGroupId: "group-1",
		CreatorId:     "owner-1",
	}
	service := NewConversationService(
		ChatStoragePorts{
			Transactions:             passthroughTransactionRunner{},
			Conversations:            store,
			CircleGroupConversations: store,
			Members:                  store,
			UserStates:               store,
			ConversationCommands:     newMemoryAggregateCommandStore(),
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)

	conversation, err := service.ProvisionCircleGroupConversation(
		context.Background(),
		CircleGroupConversationProvisioningRequest{
			SourceEventID:  "group-1:created:1",
			CircleID:       "circle-1",
			CircleGroupID:  "group-1",
			OwnerPersonaID: "owner-1",
			Title:          "摄影小组",
		},
	)
	if err != nil {
		t.Fatalf("unique index conflict must recover by returning persisted binding: %v", err)
	}
	if conversation.ID != "already-bound" {
		t.Fatalf("expected existing circle group binding, got %+v", conversation)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
func TestProvisionGatheringConversationCommitsSoleBindingOwnerAndOutbox(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	commands := newMemoryAggregateCommandStore()
	service := NewConversationService(
		ChatStoragePorts{
			Transactions: passthroughTransactionRunner{}, Conversations: store,
			GatheringConversations: store, Members: store, UserStates: store,
			ConversationCommands: commands,
		},
		noopCache{}, syncNoopEventPublisher{}, nil, nil, nil, nil, syncNoopGroupAvatarScheduler{},
	)
	request := GatheringConversationProvisioningRequest{
		SourceEventID: "gathering-1:created:1", GatheringID: "gathering-1",
		OwnerPersonaID: "owner-1", Title: "贡嘎同行", MaxGroupSize: 8,
	}
	conversation, err := service.ProvisionGatheringConversation(context.Background(), request)
	if err != nil {
		t.Fatalf("ProvisionGatheringConversation: %v", err)
	}
	if conversation.GatheringId != "gathering-1" || conversation.OriginType != "gathering" ||
		conversation.CreatorId != "owner-1" || conversation.MemberCount != 1 {
		t.Fatalf("invalid Gathering conversation: %+v", conversation)
	}
	if _, err := store.FindMember(context.Background(), conversation.ID, "owner-1"); err != nil {
		t.Fatalf("owner membership missing: %v", err)
	}
	if !containsAggregateEvent(commands.events, "GatheringConversationProvisioned") {
		t.Fatalf("Gathering binding event missing: %#v", commands.eventTypes())
	}
	replayed, err := service.ProvisionGatheringConversation(context.Background(), request)
	if err != nil || replayed.ID != conversation.ID || len(store.conversations) != 1 {
		t.Fatalf("replay created another binding: replay=%+v err=%v count=%d", replayed, err, len(store.conversations))
	}
}

func containsAggregateEvent(events []AggregateOutboxEvent, eventType string) bool {
	for _, event := range events {
		if event.EventType == eventType {
			return true
		}
	}
	return false
}

type syncNoopEventPublisher struct{}

func (syncNoopEventPublisher) PublishDomainEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}

func (syncNoopEventPublisher) PublishRecordedDomainEvent(
	context.Context,
	string,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}

type syncNoopGroupAvatarScheduler struct{}

func (syncNoopGroupAvatarScheduler) EnqueueRecompute(
	context.Context,
	GroupAvatarRecomputeTask,
) error {
	return nil
}

func (syncNoopGroupAvatarScheduler) EnqueueConversationAvatarPatch(
	context.Context,
	ConversationAvatarPatchTask,
) error {
	return nil
}

type circleGroupChatSyncMemoryStore struct {
	ConversationStore
	MemberStore
	UserStateStore
	CircleGroupConversationReader
	CircleGroupMembershipProjectionStore
	CircleGroupChatBindingProjectionStore

	conversations             map[string]*model.Conversation
	members                   map[string]*model.ConversationMember
	states                    map[string]*model.ConversationUserState
	membershipProjections     map[string]CircleGroupMembershipProjectionState
	bindingProjections        map[string]CircleGroupChatBindingProjectionState
	hideNextCircleGroupLookup bool
}

func newCircleGroupChatSyncMemoryStore() *circleGroupChatSyncMemoryStore {
	return &circleGroupChatSyncMemoryStore{
		conversations:         map[string]*model.Conversation{},
		members:               map[string]*model.ConversationMember{},
		states:                map[string]*model.ConversationUserState{},
		membershipProjections: map[string]CircleGroupMembershipProjectionState{},
		bindingProjections:    map[string]CircleGroupChatBindingProjectionState{},
	}
}

func (s *circleGroupChatSyncMemoryStore) CreateConversation(_ context.Context, value *model.Conversation) error {
	if _, exists := s.conversations[value.ID]; exists {
		return errors.New("duplicate conversation")
	}
	if strings.TrimSpace(value.CircleGroupId) != "" {
		for _, existing := range s.conversations {
			if existing.CircleGroupId == value.CircleGroupId {
				return model.ErrCircleGroupConversationAlreadyBound
			}
		}
	}
	if strings.TrimSpace(value.GatheringId) != "" {
		for _, existing := range s.conversations {
			if existing.GatheringId == value.GatheringId {
				return model.ErrGatheringConversationAlreadyBound
			}
		}
	}
	copy := *value
	s.conversations[value.ID] = &copy
	return nil
}

func (s *circleGroupChatSyncMemoryStore) FindConversationByID(_ context.Context, id string) (*model.Conversation, error) {
	value := s.conversations[id]
	if value == nil {
		return nil, model.ErrConversationNotFound
	}
	copy := *value
	return &copy, nil
}

func (s *circleGroupChatSyncMemoryStore) FindConversationByCircleGroupID(_ context.Context, groupID string) (*model.Conversation, error) {
	if s.hideNextCircleGroupLookup {
		s.hideNextCircleGroupLookup = false
		return nil, model.ErrConversationNotFound
	}
	for _, value := range s.conversations {
		if value.CircleGroupId == groupID {
			copy := *value
			return &copy, nil
		}
	}
	return nil, model.ErrConversationNotFound
}

func (s *circleGroupChatSyncMemoryStore) FindConversationByGatheringID(_ context.Context, gatheringID string) (*model.Conversation, error) {
	for _, value := range s.conversations {
		if value.GatheringId == gatheringID {
			copy := *value
			return &copy, nil
		}
	}
	return nil, model.ErrConversationNotFound
}

func (s *circleGroupChatSyncMemoryStore) UpdateConversation(_ context.Context, id string, value *model.Conversation) error {
	if _, exists := s.conversations[id]; !exists {
		return model.ErrConversationNotFound
	}
	copy := *value
	s.conversations[id] = &copy
	return nil
}

func (s *circleGroupChatSyncMemoryStore) CreateMember(_ context.Context, value *model.ConversationMember) error {
	key := s.memberKey(value.ConversationId, value.UserId)
	if _, exists := s.members[key]; exists {
		return errors.New("duplicate member")
	}
	copy := *value
	s.members[key] = &copy
	return nil
}

func (s *circleGroupChatSyncMemoryStore) DeleteMember(_ context.Context, conversationID, userID string) error {
	delete(s.members, s.memberKey(conversationID, userID))
	return nil
}

func (s *circleGroupChatSyncMemoryStore) FindMember(_ context.Context, conversationID, userID string) (*model.ConversationMember, error) {
	value := s.members[s.memberKey(conversationID, userID)]
	if value == nil {
		return nil, model.ErrMemberNotFound
	}
	copy := *value
	return &copy, nil
}

func (s *circleGroupChatSyncMemoryStore) UpdateMemberRole(_ context.Context, conversationID, userID, role string) error {
	value := s.members[s.memberKey(conversationID, userID)]
	if value == nil {
		return model.ErrMemberNotFound
	}
	value.Role = role
	return nil
}

func (s *circleGroupChatSyncMemoryStore) ListMembers(_ context.Context, conversationID string, _ ListMembersQuery) ([]model.ConversationMember, error) {
	result := make([]model.ConversationMember, 0)
	for _, value := range s.members {
		if value.ConversationId == conversationID {
			result = append(result, *value)
		}
	}
	return result, nil
}

func (s *circleGroupChatSyncMemoryStore) CountMembers(_ context.Context, conversationID string) (int, error) {
	count := 0
	for _, value := range s.members {
		if value.ConversationId == conversationID {
			count++
		}
	}
	return count, nil
}

func (s *circleGroupChatSyncMemoryStore) CountUserMembers(_ context.Context, conversationID string) (int, error) {
	count := 0
	for _, value := range s.members {
		if value.ConversationId == conversationID && value.MemberType == "user" {
			count++
		}
	}
	return count, nil
}

func (s *circleGroupChatSyncMemoryStore) BumpMembersRosterRevision(_ context.Context, conversationID string, memberCount *int) error {
	value := s.conversations[conversationID]
	if value == nil {
		return model.ErrConversationNotFound
	}
	value.MembersRosterRevision++
	if memberCount != nil {
		value.MemberCount = *memberCount
	}
	return nil
}

func (s *circleGroupChatSyncMemoryStore) UpsertUserState(_ context.Context, value *model.ConversationUserState) error {
	copy := *value
	s.states[s.stateKey(value.UserId, value.ConversationId)] = &copy
	return nil
}

func (s *circleGroupChatSyncMemoryStore) DeleteUserState(_ context.Context, userID, conversationID string) error {
	delete(s.states, s.stateKey(userID, conversationID))
	return nil
}

func (s *circleGroupChatSyncMemoryStore) FindUserState(_ context.Context, userID, conversationID string) (*model.ConversationUserState, error) {
	value := s.states[s.stateKey(userID, conversationID)]
	if value == nil {
		return nil, model.ErrUserStateNotFound
	}
	copy := *value
	return &copy, nil
}

func (s *circleGroupChatSyncMemoryStore) LoadCircleGroupMembershipProjection(_ context.Context, groupID, userID string) (CircleGroupMembershipProjectionState, bool, error) {
	value, found := s.membershipProjections[groupID+":"+userID]
	return value, found, nil
}

func (s *circleGroupChatSyncMemoryStore) SaveCircleGroupMembershipProjection(_ context.Context, value CircleGroupMembershipProjectionState) error {
	s.membershipProjections[value.CircleGroupID+":"+value.UserID] = value
	return nil
}

func (s *circleGroupChatSyncMemoryStore) LoadCircleGroupChatBindingProjection(_ context.Context, groupID string) (CircleGroupChatBindingProjectionState, bool, error) {
	value, found := s.bindingProjections[groupID]
	return value, found, nil
}

func (s *circleGroupChatSyncMemoryStore) SaveCircleGroupChatBindingProjection(_ context.Context, value CircleGroupChatBindingProjectionState) error {
	s.bindingProjections[value.CircleGroupID] = value
	return nil
}

func (s *circleGroupChatSyncMemoryStore) memberKey(conversationID, userID string) string {
	return conversationID + ":" + userID
}

func (s *circleGroupChatSyncMemoryStore) stateKey(userID, conversationID string) string {
	return userID + ":" + conversationID
}
