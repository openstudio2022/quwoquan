// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: get-receipts-local
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	receiptapp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/application"
	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
)

type memoryStore struct {
	committed map[string]receiptmodel.Fact
}

func (store *memoryStore) AppendIfAbsent(
	_ context.Context,
	fact receiptmodel.Fact,
) (receiptmodel.Fact, bool, error) {
	key := fact.MessageID + ":" + fact.UserID
	if committed, ok := store.committed[key]; ok {
		if !committed.SameImmutableValue(fact) {
			return receiptmodel.Fact{}, false, receiptmodel.ErrIdentityConflict
		}
		return committed, true, nil
	}
	store.committed[key] = fact
	return fact, false, nil
}

func (store *memoryStore) ListByMessage(
	_ context.Context,
	messageID string,
) ([]receiptmodel.Fact, error) {
	result := make([]receiptmodel.Fact, 0)
	for _, fact := range store.committed {
		if fact.MessageID == messageID {
			result = append(result, fact)
		}
	}
	return result, nil
}

func TestMessageReceiptFactIsImmutableAndReplaySafe(t *testing.T) {
	store := &memoryStore{committed: map[string]receiptmodel.Fact{}}
	appender := receiptapp.NewAppender(store)
	fact := receiptmodel.Fact{
		ID:             "receipt-1",
		MessageID:      "message-1",
		ConversationID: "conversation-1",
		UserID:         "persona-1",
		ReadAt:         time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC),
	}

	committed, replayed, err := appender.Append(context.Background(), fact)
	if err != nil || replayed || !committed.SameImmutableValue(fact) {
		t.Fatalf("first append committed=%+v replayed=%v err=%v", committed, replayed, err)
	}
	replayedFact, replayed, err := appender.Append(context.Background(), fact)
	if err != nil || !replayed || !replayedFact.SameImmutableValue(committed) {
		t.Fatalf("exact replay fact=%+v replayed=%v err=%v", replayedFact, replayed, err)
	}

	conflict := fact
	conflict.ID = "receipt-2"
	if _, _, err := appender.Append(context.Background(), conflict); !errors.Is(err, receiptmodel.ErrIdentityConflict) {
		t.Fatalf("identity reuse with different immutable fact must conflict, got %v", err)
	}
	if len(store.committed) != 1 {
		t.Fatalf("replay or conflict appended a second fact: %d", len(store.committed))
	}
	items, err := appender.ListByMessage(context.Background(), fact.MessageID)
	if err != nil || len(items) != 1 || !items[0].SameImmutableValue(fact) {
		t.Fatalf("GetReceipts query result=%+v err=%v", items, err)
	}
	wire, err := json.Marshal(committed)
	if err != nil {
		t.Fatal(err)
	}
	if string(wire) != `{"id":"receipt-1","messageId":"message-1","conversationId":"conversation-1","userId":"persona-1","readAt":"2026-08-02T10:00:00Z"}` {
		t.Fatalf("canonical MessageReceiptFact wire drifted: %s", wire)
	}
}

func TestMessageReceiptFactRejectsIncompleteIdentityAndTimestamp(t *testing.T) {
	appender := receiptapp.NewAppender(&memoryStore{committed: map[string]receiptmodel.Fact{}})
	if _, _, err := appender.Append(context.Background(), receiptmodel.Fact{}); !errors.Is(err, receiptmodel.ErrIdentityIncomplete) {
		t.Fatalf("incomplete identity must fail, got %v", err)
	}
	if _, _, err := appender.Append(context.Background(), receiptmodel.Fact{
		ID: "receipt", MessageID: "message", ConversationID: "conversation", UserID: "persona",
	}); !errors.Is(err, receiptmodel.ErrReadAtRequired) {
		t.Fatalf("missing readAt must fail, got %v", err)
	}
}
