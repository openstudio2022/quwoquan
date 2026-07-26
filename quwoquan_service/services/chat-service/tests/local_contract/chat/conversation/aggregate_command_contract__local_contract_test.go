package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

// memoryAggregateCommandStore 是三个非 Message 聚合命令端口的内存合同替身：
// 幂等回执、digest 冲突、no-op receipt 与事务 outbox 追加语义与 Mongo 实现一致。
type memoryAggregateCommandStore struct {
	mu       sync.Mutex
	receipts map[string]AggregateCommandReceipt
	events   []AggregateOutboxEvent
}

func newMemoryAggregateCommandStore() *memoryAggregateCommandStore {
	return &memoryAggregateCommandStore{
		receipts: map[string]AggregateCommandReceipt{},
	}
}

func (s *memoryAggregateCommandStore) FindAggregateCommandReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) ([]byte, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return nil, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return nil, false, errors.New("idempotency key was reused with a different chat command")
	}
	return receipt.ResultJSON, true, nil
}

func (s *memoryAggregateCommandStore) CommitAggregateCommand(
	_ context.Context,
	receipt AggregateCommandReceipt,
	events []AggregateOutboxEvent,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, found := s.receipts[receipt.IdempotencyKey]; found {
		if existing.CommandDigest != receipt.CommandDigest {
			return errors.New("idempotency key was reused with a different chat command")
		}
		return nil
	}
	s.receipts[receipt.IdempotencyKey] = receipt
	s.events = append(s.events, events...)
	return nil
}

func (s *memoryAggregateCommandStore) AppendAggregateOutboxEvents(
	_ context.Context,
	events []AggregateOutboxEvent,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, events...)
	return nil
}

func (s *memoryAggregateCommandStore) eventTypes() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	types := make([]string, 0, len(s.events))
	for _, event := range s.events {
		types = append(types, event.EventType)
	}
	return types
}

func commandContext(actorID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "local_contract.chat.command",
		IdempotencyKey: key,
		Actor:          operation.ActorContext{AccountID: actorID, PersonaID: actorID},
	})
}

func TestUpdateSettingsNoopPersistsReceiptWithoutEvents(t *testing.T) {
	commands := newMemoryAggregateCommandStore()
	states := &memoryUserStateStore{}
	service := newConversationSettingsService(states, commands, activeMemberStore{})
	muted := true
	// 先写入一个已满足目标状态的 state。
	states.state = &model.ConversationUserState{
		ID: "state-1", UserId: "p1", ConversationId: "conv-1", Muted: true,
	}

	if err := service.UpdateSettings(
		commandContext("p1", "settings-key-1"),
		UpdateSettingsRequest{UserId: "p1", ConversationId: "conv-1", Muted: &muted},
	); err != nil {
		t.Fatalf("noop update settings: %v", err)
	}
	if len(commands.receipts) != 1 {
		t.Fatalf("noop must persist exactly one receipt, got %d", len(commands.receipts))
	}
	if len(commands.events) != 0 {
		t.Fatalf("noop must not append outbox events, got %v", commands.eventTypes())
	}
	if states.upserts != 0 {
		t.Fatalf("noop must not rewrite aggregate state, got %d upserts", states.upserts)
	}

	// 相同 key 重放：即使状态后续变化也返回原结果且不再提交。
	states.state.Muted = false
	if err := service.UpdateSettings(
		commandContext("p1", "settings-key-1"),
		UpdateSettingsRequest{UserId: "p1", ConversationId: "conv-1", Muted: &muted},
	); err != nil {
		t.Fatalf("replay noop: %v", err)
	}
	if len(commands.receipts) != 1 || states.upserts != 0 {
		t.Fatalf(
			"replay must not create second receipt or state write: receipts=%d upserts=%d",
			len(commands.receipts), states.upserts,
		)
	}
}

func TestUpdateSettingsCommitsStateReceiptAndEventTogether(t *testing.T) {
	commands := newMemoryAggregateCommandStore()
	states := &memoryUserStateStore{}
	service := newConversationSettingsService(states, commands, activeMemberStore{})
	pinned := true
	if err := service.UpdateSettings(
		commandContext("p1", "settings-key-2"),
		UpdateSettingsRequest{UserId: "p1", ConversationId: "conv-1", Pinned: &pinned},
	); err != nil {
		t.Fatalf("update settings: %v", err)
	}
	if states.upserts != 1 {
		t.Fatalf("expected one state write, got %d", states.upserts)
	}
	if len(commands.receipts) != 1 {
		t.Fatalf("expected one receipt, got %d", len(commands.receipts))
	}
	types := commands.eventTypes()
	if len(types) != 1 || !strings.Contains(types[0], "ConversationUserSettingsChanged") {
		t.Fatalf("expected settings changed event via outbox, got %v", types)
	}
	var receipt AggregateCommandReceipt
	for _, item := range commands.receipts {
		receipt = item
	}
	if receipt.ResultJSON != nil {
		var decoded map[string]any
		if err := json.Unmarshal(receipt.ResultJSON, &decoded); err != nil {
			t.Fatalf("receipt result must be valid JSON: %v", err)
		}
	}
	if receipt.ExpiresAt.Before(time.Now()) {
		t.Fatal("receipt must carry a future expiry")
	}
}

func TestUpdateSettingsRejectsNonMemberBeforeCreatingUserState(t *testing.T) {
	states := &memoryUserStateStore{}
	service := newConversationSettingsService(
		states,
		newMemoryAggregateCommandStore(),
		deniedMemberStore{},
	)
	pinned := true

	err := service.UpdateSettings(
		commandContext("p1", "settings-non-member"),
		UpdateSettingsRequest{UserId: "p1", ConversationId: "conv-1", Pinned: &pinned},
	)
	if err == nil || !strings.Contains(err.Error(), "CHAT.USER.conversation_not_found") {
		t.Fatalf("non-member settings must be hidden as conversation_not_found, got %v", err)
	}
	if states.upserts != 0 || states.state != nil {
		t.Fatalf("non-member settings must not create user state: %+v", states)
	}
}

func newConversationSettingsService(
	states *memoryUserStateStore,
	commands AggregateCommandStore,
	members MemberStore,
) *ConversationService {
	return NewConversationService(
		ChatStoragePorts{
			Transactions:      passthroughTransactionRunner{},
			Conversations:     activeConversationStore{},
			Members:           members,
			UserStates:        states,
			UserStateCommands: commands,
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
}

type passthroughTransactionRunner struct{}

func (passthroughTransactionRunner) RunInTransaction(
	ctx context.Context,
	fn func(context.Context) error,
) error {
	return fn(ctx)
}

type noopCache struct{}

func (noopCache) InvalidateConversation(context.Context, string) error { return nil }

type memoryUserStateStore struct {
	state   *model.ConversationUserState
	upserts int
	deletes int
}

func (s *memoryUserStateStore) UpsertUserState(
	_ context.Context,
	state *model.ConversationUserState,
) error {
	s.upserts++
	s.state = state
	return nil
}

func (s *memoryUserStateStore) DeleteUserState(
	_ context.Context,
	userID string,
	conversationID string,
) error {
	if s.state != nil && s.state.UserId == userID && s.state.ConversationId == conversationID {
		s.state = nil
	}
	s.deletes++
	return nil
}

func (s *memoryUserStateStore) FindUserState(
	_ context.Context,
	userID string,
	conversationID string,
) (*model.ConversationUserState, error) {
	if s.state == nil || s.state.UserId != userID || s.state.ConversationId != conversationID {
		return nil, model.ErrUserStateNotFound
	}
	return s.state, nil
}

func (s *memoryUserStateStore) ListUserStatePage(
	context.Context,
	string,
	int,
	string,
) (model.ConversationUserStatePage, error) {
	if s.state == nil {
		return model.ConversationUserStatePage{}, nil
	}
	return model.ConversationUserStatePage{
		Items: []model.ConversationUserState{*s.state},
	}, nil
}

func (s *memoryUserStateStore) ListUserStates(
	context.Context,
	string,
	int,
	string,
) ([]model.ConversationUserState, error) {
	if s.state == nil {
		return nil, nil
	}
	return []model.ConversationUserState{*s.state}, nil
}

func (s *memoryUserStateStore) ListUserStatesByConversationID(
	context.Context,
	string,
	int,
	string,
) ([]model.ConversationUserState, error) {
	if s.state == nil {
		return nil, nil
	}
	return []model.ConversationUserState{*s.state}, nil
}

func (s *memoryUserStateStore) AdvanceInboxUnread(
	context.Context,
	string,
	string,
	int64,
	int,
	int,
	time.Time,
) error {
	return nil
}

type activeConversationStore struct{ ConversationStore }

func (activeConversationStore) FindConversationByID(
	context.Context,
	string,
) (*model.Conversation, error) {
	return &model.Conversation{
		ID:     "conv-1",
		Status: model.ConversationStatusActive,
	}, nil
}

type activeMemberStore struct{ MemberStore }

func (activeMemberStore) FindMember(
	context.Context,
	string,
	string,
) (*model.ConversationMember, error) {
	return &model.ConversationMember{ID: "member-1", UserId: "p1"}, nil
}

type deniedMemberStore struct{ MemberStore }

func (deniedMemberStore) FindMember(
	context.Context,
	string,
	string,
) (*model.ConversationMember, error) {
	return nil, errors.New("not a member")
}
