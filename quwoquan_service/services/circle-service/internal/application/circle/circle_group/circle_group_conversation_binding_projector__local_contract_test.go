package circlegroup

import (
	"context"
	"testing"
)

func TestConversationBindingProjectorUsesDurableEventIdentity(t *testing.T) {
	writer := &memoryConversationBindingWriter{}
	projector := NewConversationBindingProjector(writer)
	fact := ConversationProvisionedFact{
		EventID:  "conversation-1:CircleGroupConversationProvisioned:1",
		CircleID: "circle-1", CircleGroupID: "group-1", ConversationID: "conversation-1",
	}
	if err := projector.Apply(context.Background(), fact); err != nil {
		t.Fatalf("apply durable binding: %v", err)
	}
	if writer.eventID != fact.EventID || writer.circleID != fact.CircleID ||
		writer.groupID != fact.CircleGroupID || writer.conversationID != fact.ConversationID {
		t.Fatalf("binding projection lost source identity: %+v", writer)
	}
}

func TestConversationBindingProjectorRejectsIncompleteFact(t *testing.T) {
	projector := NewConversationBindingProjector(&memoryConversationBindingWriter{})
	if err := projector.Apply(context.Background(), ConversationProvisionedFact{
		EventID: "event-1", CircleID: "circle-1", CircleGroupID: "group-1",
	}); err == nil {
		t.Fatal("incomplete reverse binding payload must remain pending and retryable")
	}
}

type memoryConversationBindingWriter struct {
	eventID        string
	circleID       string
	groupID        string
	conversationID string
}

func (w *memoryConversationBindingWriter) BindConversation(
	_ context.Context,
	eventID string,
	circleID string,
	groupID string,
	conversationID string,
) error {
	w.eventID = eventID
	w.circleID = circleID
	w.groupID = groupID
	w.conversationID = conversationID
	return nil
}
