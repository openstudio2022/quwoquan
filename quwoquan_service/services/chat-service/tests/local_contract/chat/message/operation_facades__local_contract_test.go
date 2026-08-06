// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: send-message-local
// readiness_case: list-assistant-grounding-messages-local
// readiness_case: send-assistant-delivery-message-local
// readiness_case: recall-message-local
// readiness_case: list-messages-local
// readiness_case: sync-messages-local
package local_contract

import (
	"context"
	"testing"

	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
)

func TestMessageUseCasesExecuteEveryHTTPApplicationFacet(t *testing.T) {
	backend := &messageOperationBackend{calls: map[string]int{}}
	useCases := messageapp.NewUseCases(backend)
	ctx := context.Background()

	sent, err := useCases.Send(ctx, messageapp.SendMessageRequest{
		ConversationId: "conversation-1", SenderId: "persona-1", SenderAccountID: "account-1",
		Type: "text", Content: "hello", ClientMsgId: "client-1",
	})
	if err != nil || sent.MessageId != "message-1" || sent.Seq != 7 {
		t.Fatalf("SendMessage result=%+v err=%v", sent, err)
	}
	assistant, err := useCases.SendAssistantDelivery(ctx, messageapp.AssistantDeliveryMessageRequest{
		ConversationID: "conversation-1", CreatorPersonaID: "persona-1",
		Type: "assistant_reply", Content: "answer", ClientMsgID: "assistant-client-1",
	})
	if err != nil || assistant.MessageId != "assistant-message-1" {
		t.Fatalf("SendAssistantDeliveryMessage result=%+v err=%v", assistant, err)
	}
	if err := useCases.Recall(ctx, "conversation-1", "message-1", "persona-1"); err != nil {
		t.Fatal(err)
	}
	listed, err := useCases.List(ctx, messageapp.ListMessagesRequest{
		ConversationId: "conversation-1", ViewerID: "persona-1", Limit: 20,
	})
	if err != nil || len(listed) != 1 {
		t.Fatalf("ListMessages result=%+v err=%v", listed, err)
	}
	grounding, err := useCases.ListAssistantGrounding(ctx, "conversation-1", "persona-1", 10, 20)
	if err != nil || len(grounding) != 1 {
		t.Fatalf("ListAssistantGroundingMessages result=%+v err=%v", grounding, err)
	}
	synced, err := useCases.Sync(ctx, messageapp.SyncMessagesRequest{
		ConversationId: "conversation-1", ViewerID: "persona-1", LastSeq: 6, Limit: 20,
	})
	if err != nil || !synced.HasMore || len(synced.Messages) != 1 {
		t.Fatalf("SyncMessages result=%+v err=%v", synced, err)
	}
	for _, name := range []string{
		"SendMessage", "SendAssistantDeliveryMessage", "RecallMessage", "ListMessages",
		"ListAssistantGroundingMessages", "SyncMessages",
	} {
		if backend.calls[name] != 1 {
			t.Fatalf("%s call count=%d want=1", name, backend.calls[name])
		}
	}
}

type messageOperationBackend struct {
	calls map[string]int
}

func (backend *messageOperationBackend) record(name string) { backend.calls[name]++ }

func (backend *messageOperationBackend) SendMessage(
	context.Context,
	messageapp.SendMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	backend.record("SendMessage")
	return &messageapp.SendMessageResponse{MessageId: "message-1", Seq: 7, Timestamp: "2026-08-06T00:00:00Z"}, nil
}

func (backend *messageOperationBackend) SendAssistantDeliveryMessage(
	context.Context,
	messageapp.AssistantDeliveryMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	backend.record("SendAssistantDeliveryMessage")
	return &messageapp.SendMessageResponse{MessageId: "assistant-message-1", Seq: 8, Timestamp: "2026-08-06T00:00:01Z"}, nil
}

func (backend *messageOperationBackend) RecallMessage(context.Context, string, string, string) error {
	backend.record("RecallMessage")
	return nil
}

func (backend *messageOperationBackend) ListMessages(
	context.Context,
	messageapp.ListMessagesRequest,
) ([]messageapp.MessageSlice, error) {
	backend.record("ListMessages")
	return []messageapp.MessageSlice{{}}, nil
}

func (backend *messageOperationBackend) ListAssistantGroundingMessages(
	context.Context, string, string, int64, int,
) ([]messageapp.MessageSlice, error) {
	backend.record("ListAssistantGroundingMessages")
	return []messageapp.MessageSlice{{}}, nil
}

func (backend *messageOperationBackend) SyncMessages(
	context.Context,
	messageapp.SyncMessagesRequest,
) (*messageapp.SyncMessagesResponse, error) {
	backend.record("SyncMessages")
	return &messageapp.SyncMessagesResponse{Messages: []messageapp.MessageSlice{{}}, HasMore: true}, nil
}
