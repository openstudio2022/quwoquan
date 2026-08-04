package main

import (
	"strings"
	"testing"
)

func TestChatRealtimeEventPayloadGenerationUsesObjectLocalTypedSource(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	fields, events, err := collectChatRealtimeEventSources(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	providedEnums, err := chatOperationProvidedEnumRefs()
	if err != nil {
		t.Fatal(err)
	}
	operationImports, sharedEnumImports, err := classifyChatRealtimeImports(fields, events, providedEnums)
	if err != nil {
		t.Fatal(err)
	}
	out, err := renderChatRealtimeEventPayloadsDart(
		"chat/chat/*/events.yaml",
		fields,
		events,
		operationImports,
		sharedEnumImports,
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, required := range []string{
		"final class MessageSentEventPayload extends ChatRealtimeEventPayload",
		"final class MessageRecalledEventPayload extends ChatRealtimeEventPayload",
		"final class ConversationMemberRemovedEventPayload extends ChatRealtimeEventPayload",
		"final class ConversationMemberLeftEventPayload extends ChatRealtimeEventPayload",
		"MessageType.fromWire",
		"MessageCard.fromWire",
		"shared_realtime_event_enums.g.dart' show ConversationStatus, MemberType",
		"_chatEventRequireExactFields",
		"throw FormatException('Unsupported chat realtime event type: $eventType')",
	} {
		if !strings.Contains(out, required) {
			t.Fatalf("generated Chat event payload is missing %q", required)
		}
	}
	for _, serverOnly := range []string{"AssistantMentioned", "ConversationMemberAdded"} {
		if strings.Contains(out, serverOnly) {
			t.Fatalf("server-only %s event received an App payload owner", serverOnly)
		}
	}
	if strings.Contains(out, "UnknownPayload") || strings.Contains(out, "preserves raw") {
		t.Fatal("Chat event generator emitted a future/unknown compatibility track")
	}
}

func TestChatRealtimeEventPayloadGenerationRejectsPayloadFieldDrift(t *testing.T) {
	fields := &fieldsFile{Types: map[string]entityDef{
		"MessageSentEventPayload": {
			Fields: []fieldDef{{Name: "messageId", Type: "string", Constraints: []string{"NOT_BLANK"}}},
		},
	}}
	events := &chatRealtimeEventsYAML{Events: []chatRealtimeEventYAML{{
		Name:          "MessageSent",
		ClientWsType:  "MessageSent",
		PayloadEntity: "MessageSentEventPayload",
		PayloadFields: []string{"messageId", "legacyId"},
	}}}
	if _, err := renderChatRealtimeEventPayloadsDart(
		"chat/chat/message/events.yaml",
		fields,
		events,
		map[string]struct{}{},
		map[string]struct{}{},
	); err == nil {
		t.Fatal("payload_fields drift was accepted")
	}
}
