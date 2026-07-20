package application

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
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

func TestScopedChatIdempotencyKeyRequiresTransportKey(t *testing.T) {
	if _, err := scopedChatIdempotencyKey(context.Background(), "persona-1"); err == nil {
		t.Fatal("missing Idempotency-Key must be rejected for chat commands")
	}
	first, err := scopedChatIdempotencyKey(commandContext("persona-1", "key-1"), "persona-1")
	if err != nil {
		t.Fatalf("scoped key: %v", err)
	}
	second, err := scopedChatIdempotencyKey(commandContext("persona-2", "key-1"), "persona-2")
	if err != nil {
		t.Fatalf("scoped key: %v", err)
	}
	if first == second {
		t.Fatal("same transport key from different actors must scope to different receipts")
	}
	if !strings.HasPrefix(first, "chat:") {
		t.Fatalf("scoped key must be namespaced, got %q", first)
	}
}

func TestChatCommandDigestDistinguishesSemanticPayload(t *testing.T) {
	base, err := chatCommandDigest("UpdateConversationTitle", UpdateConversationTitleRequest{
		ConversationId: "conv-1", OperatorId: "p1", Title: "A",
	})
	if err != nil {
		t.Fatalf("digest: %v", err)
	}
	changed, err := chatCommandDigest("UpdateConversationTitle", UpdateConversationTitleRequest{
		ConversationId: "conv-1", OperatorId: "p1", Title: "B",
	})
	if err != nil {
		t.Fatalf("digest: %v", err)
	}
	if base == changed {
		t.Fatal("different command payloads must produce different digests")
	}
}

func TestReplayChatCommandReturnsFirstResultAndRejectsDigestMismatch(t *testing.T) {
	store := newMemoryAggregateCommandStore()
	scopedKey := "chat:test-replay"
	first := model.Conversation{ID: "conv-1", Title: "first"}
	receipt, err := chatCommandReceipt(scopedKey, "CreateConversation", "digest-a", first.ID, first)
	if err != nil {
		t.Fatalf("receipt: %v", err)
	}
	if err := store.CommitAggregateCommand(context.Background(), receipt, nil); err != nil {
		t.Fatalf("commit: %v", err)
	}

	var replayed model.Conversation
	found, err := replayChatCommand(
		context.Background(), store, scopedKey, "CreateConversation", "digest-a", &replayed,
	)
	if err != nil || !found {
		t.Fatalf("replay must return first result: found=%v err=%v", found, err)
	}
	if replayed.Title != "first" {
		t.Fatalf("replayed result mismatch: %+v", replayed)
	}

	if _, err := replayChatCommand(
		context.Background(), store, scopedKey, "CreateConversation", "digest-b", nil,
	); err == nil {
		t.Fatal("same key with different digest must be rejected as idempotency conflict")
	} else if !strings.Contains(err.Error(), "CHAT.USER.message_idempotency_conflict") {
		t.Fatalf("conflict must map to the structured stable error code, got %v", err)
	}
}

func TestUpdateSettingsNoopPersistsReceiptWithoutEvents(t *testing.T) {
	commands := newMemoryAggregateCommandStore()
	states := &memoryUserStateStore{}
	service := &ConversationService{
		transactions:      passthroughTransactionRunner{},
		userStates:        states,
		userStateCommands: commands,
		cache:             noopCache{},
	}
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
	service := &ConversationService{
		transactions:      passthroughTransactionRunner{},
		userStates:        states,
		userStateCommands: commands,
		cache:             noopCache{},
	}
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
}

func (s *memoryUserStateStore) UpsertUserState(
	_ context.Context,
	state *model.ConversationUserState,
) error {
	s.upserts++
	s.state = state
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
