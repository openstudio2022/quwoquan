package application

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

// 会话生命周期合同：ListAssistantConversations / ListConversationTurns /
// CancelAssistantRun 与 contracts/metadata/assistant/** 声明一致。
// GWT 归属：assistant-run-learning/run-stream-policy（Run 状态机与查询面）。

func newLifecycleService(t *testing.T, store ConversationRunStore) *AssistantService {
	t.Helper()
	return NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(store),
	)
}

func seedConversation(t *testing.T, store ConversationRunStore, userID, conversationID string, updatedAt time.Time) {
	t.Helper()
	_, _, err := store.InsertConversation(context.Background(), assistant.AssistantConversation{
		ConversationID: conversationID,
		UserID:         userID,
		State:          "active",
		CreatedAt:      updatedAt,
		UpdatedAt:      updatedAt,
	})
	if err != nil {
		t.Fatalf("seed conversation %s: %v", conversationID, err)
	}
}

func seedTurn(t *testing.T, store ConversationRunStore, turn assistant.AssistantTurn) {
	t.Helper()
	if _, _, err := store.InsertTurn(context.Background(), turn); err != nil {
		t.Fatalf("seed turn %s: %v", turn.TurnID, err)
	}
}

func TestListConversationsKeysetPaginationAndOwnerIsolation(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	service := newLifecycleService(t, store)

	base := time.Date(2026, 7, 20, 10, 0, 0, 0, time.UTC)
	seedConversation(t, store, "user-a", "conv-1", base.Add(1*time.Minute))
	seedConversation(t, store, "user-a", "conv-2", base.Add(2*time.Minute))
	seedConversation(t, store, "user-a", "conv-3", base.Add(3*time.Minute))
	seedConversation(t, store, "user-b", "conv-x", base.Add(4*time.Minute))

	page1, err := service.ListConversations(ctx, "user-a", 2, "")
	if err != nil {
		t.Fatalf("ListConversations page1: %v", err)
	}
	if len(page1.Items) != 2 || page1.Items[0].ConversationID != "conv-3" || page1.Items[1].ConversationID != "conv-2" {
		t.Fatalf("page1 must be updatedAt desc [conv-3 conv-2], got %#v", page1.Items)
	}
	if page1.NextCursor == "" {
		t.Fatalf("page1 must expose nextCursor")
	}
	page2, err := service.ListConversations(ctx, "user-a", 2, page1.NextCursor)
	if err != nil {
		t.Fatalf("ListConversations page2: %v", err)
	}
	if len(page2.Items) != 1 || page2.Items[0].ConversationID != "conv-1" {
		t.Fatalf("page2 must be [conv-1], got %#v", page2.Items)
	}
	if page2.NextCursor != "" {
		t.Fatalf("page2 must be terminal page, got cursor %q", page2.NextCursor)
	}
	for _, item := range append(append([]assistant.AssistantConversation{}, page1.Items...), page2.Items...) {
		if item.UserID != "user-a" {
			t.Fatalf("owner isolation violated: %#v", item)
		}
	}

	if _, err := service.ListConversations(ctx, "user-a", 2, "not-a-cursor"); err == nil {
		t.Fatalf("invalid cursor must be rejected")
	}
}

func TestListConversationTurnsTerminalOnlyDescending(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	service := newLifecycleService(t, store)

	base := time.Date(2026, 7, 20, 11, 0, 0, 0, time.UTC)
	seedConversation(t, store, "user-a", "conv-1", base)
	completedAt := base.Add(5 * time.Minute)
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-1", ConversationID: "conv-1", UserID: "user-a",
		Status: "completed", Input: assistant.AssistantTurnInput{Text: "q1"},
		AnswerText: "a1", CreatedAt: base.Add(1 * time.Minute), CompletedAt: &completedAt,
	})
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-2", ConversationID: "conv-1", UserID: "user-a",
		Status: "failed", Input: assistant.AssistantTurnInput{Text: "q2"},
		CreatedAt: base.Add(2 * time.Minute),
	})
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-3", ConversationID: "conv-1", UserID: "user-a",
		Status: "cancelled", Input: assistant.AssistantTurnInput{Text: "q3"},
		CreatedAt: base.Add(3 * time.Minute),
	})
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-4", ConversationID: "conv-1", UserID: "user-a",
		Status: "running", Input: assistant.AssistantTurnInput{Text: "q4"},
		CreatedAt: base.Add(4 * time.Minute),
	})

	view, err := service.ListConversationTurns(ctx, "user-a", "conv-1", 10, "")
	if err != nil {
		t.Fatalf("ListConversationTurns: %v", err)
	}
	if len(view.Items) != 3 {
		t.Fatalf("terminal-only list must have 3 items, got %d", len(view.Items))
	}
	gotOrder := []string{view.Items[0].TurnID, view.Items[1].TurnID, view.Items[2].TurnID}
	if gotOrder[0] != "turn-3" || gotOrder[1] != "turn-2" || gotOrder[2] != "turn-1" {
		t.Fatalf("turns must be createdAt desc [turn-3 turn-2 turn-1], got %v", gotOrder)
	}
	if view.Items[2].InputText != "q1" || view.Items[2].AnswerText != "a1" ||
		view.Items[2].CompletedAt == "" {
		t.Fatalf("summary must carry inputText/answerText/completedAt, got %#v", view.Items[2])
	}
	if view.Items[0].Status != "cancelled" || view.Items[1].Status != "failed" {
		t.Fatalf("summary status must be preserved, got %#v", view.Items)
	}

	// 分页推进
	page1, err := service.ListConversationTurns(ctx, "user-a", "conv-1", 2, "")
	if err != nil {
		t.Fatalf("turns page1: %v", err)
	}
	if len(page1.Items) != 2 || page1.NextCursor == "" {
		t.Fatalf("turns page1 must have 2 items + cursor, got %#v", page1)
	}
	page2, err := service.ListConversationTurns(ctx, "user-a", "conv-1", 2, page1.NextCursor)
	if err != nil {
		t.Fatalf("turns page2: %v", err)
	}
	if len(page2.Items) != 1 || page2.Items[0].TurnID != "turn-1" || page2.NextCursor != "" {
		t.Fatalf("turns page2 must be terminal [turn-1], got %#v", page2)
	}

	// 非 owner 防枚举
	if _, err := service.ListConversationTurns(ctx, "user-b", "conv-1", 10, ""); err == nil {
		t.Fatalf("non-owner must get conversation_not_found")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) || !strings.Contains(appErr.Code.String(), "conversation_not_found") {
			t.Fatalf("non-owner error must be conversation_not_found, got %v", err)
		}
	}
}

func TestCancelRunStateMachineAndIdempotency(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	service := newLifecycleService(t, store)

	base := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	seedConversation(t, store, "user-a", "conv-1", base)
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-running", ConversationID: "conv-1", UserID: "user-a",
		Status: "running", Input: assistant.AssistantTurnInput{Text: "q"},
		CreatedAt: base,
	})

	cancelled, err := service.CancelRun(ctx, "user-a", "turn-running")
	if err != nil {
		t.Fatalf("CancelRun: %v", err)
	}
	if cancelled.Status != "cancelled" || cancelled.CompletedAt == nil {
		t.Fatalf("cancel must transition running->cancelled with completedAt, got %#v", cancelled)
	}

	// 重复取消幂等返回 cancelled
	again, err := service.CancelRun(ctx, "user-a", "turn-running")
	if err != nil {
		t.Fatalf("CancelRun twice: %v", err)
	}
	if again.Status != "cancelled" {
		t.Fatalf("repeated cancel must stay cancelled, got %s", again.Status)
	}

	// completed 终态取消幂等返回 completed，不覆盖终态
	completedAt := base.Add(time.Minute)
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-completed", ConversationID: "conv-1", UserID: "user-a",
		Status: "completed", Input: assistant.AssistantTurnInput{Text: "q2"},
		AnswerText: "done", CreatedAt: base, CompletedAt: &completedAt,
	})
	completed, err := service.CancelRun(ctx, "user-a", "turn-completed")
	if err != nil {
		t.Fatalf("CancelRun on completed: %v", err)
	}
	if completed.Status != "completed" || completed.AnswerText != "done" {
		t.Fatalf("cancel on terminal turn must be idempotent no-op, got %#v", completed)
	}

	// 不存在 / 非 owner → run_not_found
	if _, err := service.CancelRun(ctx, "user-a", "turn-missing"); err == nil {
		t.Fatalf("cancel missing run must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) || !strings.Contains(appErr.Code.String(), "run_not_found") {
			t.Fatalf("missing run error must be run_not_found, got %v", err)
		}
	}
	if _, err := service.CancelRun(ctx, "user-b", "turn-running"); err == nil {
		t.Fatalf("non-owner cancel must fail with run_not_found")
	}
}

func TestCancelledTurnStreamReplayEmitsCancelledEvent(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	service := newLifecycleService(t, store)

	base := time.Date(2026, 7, 20, 13, 0, 0, 0, time.UTC)
	seedConversation(t, store, "user-a", "conv-1", base)
	cancelledAt := base.Add(time.Minute)
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID: "turn-c", ConversationID: "conv-1", UserID: "user-a",
		Status: "cancelled", Input: assistant.AssistantTurnInput{Text: "q"},
		CreatedAt: base, CompletedAt: &cancelledAt,
		StreamState: assistant.AssistantTurnStreamState{LastSeq: 4},
	})

	events := []streaming.Envelope{}
	if err := service.StreamTurn(ctx, "user-a", "turn-c", func(envelope streaming.Envelope) error {
		events = append(events, envelope)
		return nil
	}); err != nil {
		t.Fatalf("StreamTurn replay: %v", err)
	}
	if len(events) != 1 || events[0].EventType != string(AssistantStreamEventCancelled) {
		t.Fatalf("cancelled replay must emit cancelled, got %#v", events)
	}
}

func TestRunEventJournalResumesStrictlyAfterLastEventID(t *testing.T) {
	store := persistence.NewMemoryConversationRunStore()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(store),
		WithAgentLoop(NewAgentLoop(
			staticSkillRuntime{selection: SkillSelection{SkillID: "general_qa"}},
			ReactRuntime{Model: streamingFinalModelProvider{}},
			nil,
		)),
	)
	createdAt := time.Date(2026, 7, 20, 14, 0, 0, 0, time.UTC)
	seedConversation(t, store, "user-resume", "conv-resume", createdAt)
	seedTurn(t, store, assistant.AssistantTurn{
		TurnID:         "turn-resume",
		ConversationID: "conv-resume",
		UserID:         "user-resume",
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "请流式回答"},
		TraceID:        "trace-resume",
		CreatedAt:      createdAt,
	})
	allEvents, err := service.ExecuteTurn(t.Context(), "user-resume", "turn-resume")
	if err != nil {
		t.Fatalf("ExecuteTurn() error = %v", err)
	}
	if len(allEvents) < 4 {
		t.Fatalf("events=%d", len(allEvents))
	}
	afterSeq := allEvents[len(allEvents)/2].Seq
	resumed := []streaming.Envelope{}
	if err := service.StreamTurnAfterSeq(
		t.Context(),
		"user-resume",
		"turn-resume",
		afterSeq,
		func(envelope streaming.Envelope) error {
			resumed = append(resumed, envelope)
			return nil
		},
	); err != nil {
		t.Fatalf("StreamTurnAfterSeq() error = %v", err)
	}
	if len(resumed) == 0 {
		t.Fatal("resume must return remaining events")
	}
	for _, envelope := range resumed {
		if envelope.Seq <= afterSeq {
			t.Fatalf("resumed seq=%d afterSeq=%d", envelope.Seq, afterSeq)
		}
	}
	if resumed[len(resumed)-1].EventType != string(AssistantStreamEventCompleted) {
		t.Fatalf("last event=%s", resumed[len(resumed)-1].EventType)
	}
}

func TestConversationLifecycleQueriesFailClosedWithoutStore(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	assertStorageUnavailable := func(operation string, err error) {
		t.Helper()
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "storage_unavailable") {
			t.Fatalf("%s must fail closed with storage_unavailable, got %v", operation, err)
		}
	}
	_, err := service.ListConversations(ctx, "user-a", 10, "")
	assertStorageUnavailable("ListConversations", err)
	_, err = service.ListConversationTurns(ctx, "user-a", "conv-1", 10, "")
	assertStorageUnavailable("ListConversationTurns", err)
	_, err = service.CancelRun(ctx, "user-a", "turn-1")
	assertStorageUnavailable("CancelRun", err)
}
