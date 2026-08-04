// spec_ref: specs/feature-tree/runtime/runtime-assistant/assistant-mentioned-consumer/spec.md#gwt-001
package local_contract

import (
	"context"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type assistantSessionChatMentionServiceFakeChatGroundingClient struct {
	listMessagesCalled bool
	membershipChecked  bool
	membershipDenied   bool
	sent               []ports.ChatGroundingSendMessageRequest
}

func (f *assistantSessionChatMentionServiceFakeChatGroundingClient) ListMessages(
	_ context.Context,
	chatConversationID string,
	creatorPersonaID string,
	beforeSeq int64,
	limit int,
) ([]ports.ChatGroundingMessage, error) {
	f.listMessagesCalled = chatConversationID == "conv-1" &&
		creatorPersonaID == "user-a" &&
		beforeSeq == 12 &&
		limit == 20
	return []ports.ChatGroundingMessage{
		{MessageID: "msg-10", Seq: 10, SenderID: "user-a", SenderName: "小明", Type: "text", Content: "周末去川西怎么样？"},
		{MessageID: "msg-11", Seq: 11, SenderID: "user-b", SenderName: "小红", Type: "text", Content: "我想知道自驾路线和住宿。"},
	}, nil
}

func (f *assistantSessionChatMentionServiceFakeChatGroundingClient) ResolveAssistantDeliveryMembership(
	_ context.Context,
	chatConversationID string,
	creatorPersonaID string,
	assistantMemberID string,
) (bool, error) {
	f.membershipChecked = chatConversationID == "conv-1" &&
		creatorPersonaID == "user-a" &&
		assistantMemberID == "assistant"
	return !f.membershipDenied, nil
}

func (f *assistantSessionChatMentionServiceFakeChatGroundingClient) SendMessage(
	_ context.Context,
	req ports.ChatGroundingSendMessageRequest,
) error {
	f.sent = append(f.sent, req)
	return nil
}

func TestHandleAssistantMentionedReadsChatConversationContextAndReplies(t *testing.T) {
	chat := &assistantSessionChatMentionServiceFakeChatGroundingClient{}
	model := &contextAssemblyRecordingModel{}
	loop := runorchestration.NewAgentLoop(
		nil,
		runorchestration.ReactRuntime{
			Model: model,
			Tools: canonicalTestToolCoordinator(nil),
		},
		nil,
	)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)
	runOption, runtime := canonicalRunTestRuntime(t, loop)
	descriptors, err := skillcontextinfra.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	registry, err := skillcontextinfra.NewRuntimeRegistry(catalog, runtime, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	loop.SkillContexts = skillcontext.NewAssembler(registry)
	service := NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		WithSessionStore(persistence.NewMemorySessionStore()),
		runOption,
		WithChatGroundingClient(chat),
	)

	err = service.HandleAssistantMentioned(context.Background(), AssistantMentionedEvent{
		ChatConversationID: "conv-1",
		MessageID:          "msg-12",
		Seq:                12,
		SenderAccountID:    "account-a",
		SenderID:           "user-a",
		Content:            "@小趣 根据前文规划川西自驾行程和住宿",
		AssistantMemberID:  "assistant",
	})
	if err != nil {
		t.Fatalf("HandleAssistantMentioned returned error: %v", err)
	}
	if !chat.listMessagesCalled {
		t.Fatal("expected ListMessages to be called with trigger seq window")
	}
	if !chat.membershipChecked {
		t.Fatal("expected exact creator and assistant membership check")
	}
	if len(chat.sent) != 1 {
		t.Fatalf("expected one reply, got %d", len(chat.sent))
	}
	reply := chat.sent[0]
	if reply.ChatConversationID != "conv-1" {
		t.Fatalf("reply chatConversation=%s, want conv-1", reply.ChatConversationID)
	}
	if reply.CreatorPersonaID != "user-a" {
		t.Fatalf("reply authorization coordinates drifted: %+v", reply)
	}
	if strings.TrimSpace(reply.Content) == "" {
		t.Fatal("expected non-empty assistant reply")
	}
	if !strings.HasPrefix(reply.ClientMsgID, "assistant-") {
		t.Fatalf("reply clientMsgId=%s, want assistant-*", reply.ClientMsgID)
	}
	storedRun, err := runtime.Load(
		context.Background(),
		strings.TrimPrefix(reply.ClientMsgID, "assistant-"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := storedRun.ContextSnapshot["conversationContext"].(map[string]any); !ok {
		t.Fatalf("canonical Run lost conversation context: %#v", storedRun.ContextSnapshot)
	}
	if _, err := (skillcontextinfra.ConversationContextResolver{Runs: runtime}).Resolve(
		context.Background(),
		skillcontext.ResolveRequest{
			RunID:   storedRun.RunID,
			SkillID: "travel_companion",
		},
	); err != nil {
		t.Fatalf("canonical Run conversation context is not resolvable: %v", err)
	}
	if len(model.assemblies) == 0 || model.assemblies[0] == nil {
		t.Fatal("model did not receive the canonical Run context assembly")
	}
	snapshot := model.assemblies[0].SkillContextSnapshot
	if snapshot == nil {
		t.Fatal("skill context snapshot is missing")
	}
	var conversation *skillcontext.Segment
	for index := range snapshot.Segments {
		if snapshot.Segments[index].SlotID == "conversation_context" {
			conversation = &snapshot.Segments[index]
			break
		}
	}
	if conversation == nil ||
		conversation.Sensitivity != assistantgenerated.AssistantContextSensitivityInternal ||
		conversation.Value["trust"] != "untrusted_conversation_data" {
		t.Fatalf("conversation context was not assembled as internal untrusted data: %#v", snapshot)
	}
	messages, ok := conversation.Value["messages"].([]any)
	if !ok || len(messages) != 2 {
		t.Fatalf("conversation messages=%#v, want 2 structured messages", conversation.Value["messages"])
	}
}

func TestHandleAssistantMentionedDropsEventWhenAssistantWasRemoved(t *testing.T) {
	chat := &assistantSessionChatMentionServiceFakeChatGroundingClient{
		membershipDenied: true,
	}
	service := NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		WithSessionStore(persistence.NewMemorySessionStore()),
		WithChatGroundingClient(chat),
	)

	err := service.HandleAssistantMentioned(context.Background(), AssistantMentionedEvent{
		ChatConversationID: "conv-1",
		MessageID:          "msg-12",
		Seq:                12,
		SenderAccountID:    "account-a",
		SenderID:           "user-a",
		Content:            "@小趣 总结一下",
		AssistantMemberID:  "assistant",
	})
	if err != nil {
		t.Fatalf("removed assistant event must be ack-and-drop, got error: %v", err)
	}
	if !chat.membershipChecked {
		t.Fatal("expected membership to be checked before processing")
	}
	if chat.listMessagesCalled {
		t.Fatal("removed assistant event must not load the chat conversation window")
	}
	if len(chat.sent) != 0 {
		t.Fatalf("removed assistant event sent %d replies, want 0", len(chat.sent))
	}
}
