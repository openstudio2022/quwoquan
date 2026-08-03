package skillcontext

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
)

const maxConversationContextMessages = 20

// ConversationContextResolver projects only the membership-filtered Chat
// grounding window frozen on the Run. Message text remains untrusted data and
// can never change the Skill, system prompt, permissions or completion gate.
type ConversationContextResolver struct {
	Runs RunReader
}

func (resolver ConversationContextResolver) Resolve(
	ctx context.Context,
	request application.ResolveRequest,
) (application.ResolvedContext, error) {
	if resolver.Runs == nil {
		return application.ResolvedContext{}, fmt.Errorf("conversation context resolver is unavailable")
	}
	run, err := resolver.Runs.Load(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	conversationID := strings.TrimSpace(run.RequestContext.SurfaceID)
	if strings.TrimSpace(run.RequestContext.SurfaceKind) != "conversation" || conversationID == "" {
		return application.ResolvedContext{}, fmt.Errorf("conversation context surface is unavailable")
	}
	raw, ok := run.ContextSnapshot["conversationContext"].(map[string]any)
	if !ok || stringMapValue(raw, "conversationId") != conversationID {
		return application.ResolvedContext{}, fmt.Errorf("conversation context identity mismatch")
	}
	messages, maxSeq, err := normalizedConversationMessages(raw["messages"])
	if err != nil {
		return application.ResolvedContext{}, err
	}
	triggerSeq, triggerSeqOK := mapInt64Value(raw, "triggerSeq")
	if !triggerSeqOK || triggerSeq <= 0 || maxSeq >= triggerSeq {
		return application.ResolvedContext{}, fmt.Errorf("conversation context sequence is invalid")
	}
	triggerMessageID := stringMapValue(raw, "triggerMessageId")
	if triggerMessageID == "" || triggerMessageID != stringMapValue(run.Trigger, "messageId") {
		return application.ResolvedContext{}, fmt.Errorf("conversation trigger identity mismatch")
	}
	value := map[string]any{
		"conversationId":   conversationID,
		"triggerMessageId": triggerMessageID,
		"triggerSeq":       triggerSeq,
		"messages":         messages,
		"trust":            "untrusted_conversation_data",
	}
	encoded, _ := json.Marshal(value)
	return application.ResolvedContext{
		Kind:        "conversation",
		SourceRef:   fmt.Sprintf("chat.Conversation:%s@seq:%d", conversationID, triggerSeq),
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityInternal,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   (len(encoded) + 3) / 4,
		Value:       value,
		ArtifactRef: "assistant.Run:" + run.RunID + ":conversationContext",
		Summary: fmt.Sprintf(
			"Conversation %s grounding window has %d messages before seq %d",
			conversationID,
			len(messages),
			triggerSeq,
		),
	}, nil
}

func normalizedConversationMessages(raw any) ([]any, int64, error) {
	items, ok := raw.([]any)
	if !ok || len(items) > maxConversationContextMessages {
		return nil, 0, fmt.Errorf("conversation context message window is invalid")
	}
	result := make([]any, 0, len(items))
	var maxSeq int64
	for _, rawItem := range items {
		item, ok := rawItem.(map[string]any)
		if !ok {
			return nil, 0, fmt.Errorf("conversation context message is invalid")
		}
		messageID := stringMapValue(item, "messageId")
		senderPersonaID := stringMapValue(item, "senderPersonaId")
		messageType := stringMapValue(item, "type")
		seq, seqOK := mapInt64Value(item, "seq")
		if messageID == "" || senderPersonaID == "" || messageType == "" || !seqOK || seq <= 0 {
			return nil, 0, fmt.Errorf("conversation context message identity is invalid")
		}
		if seq > maxSeq {
			maxSeq = seq
		}
		normalized := map[string]any{
			"messageId":       messageID,
			"seq":             seq,
			"senderPersonaId": senderPersonaID,
			"type":            messageType,
			"content":         stringMapValue(item, "content"),
			"mentions":        stringSliceValue(item, "mentions"),
		}
		if senderName := stringMapValue(item, "senderDisplayName"); senderName != "" {
			normalized["senderDisplayName"] = senderName
		}
		if objectRef, present := item["objectRef"]; present {
			normalizedRef, err := normalizedConversationObjectRef(objectRef)
			if err != nil {
				return nil, 0, err
			}
			normalized["objectRef"] = normalizedRef
		}
		result = append(result, normalized)
	}
	return result, maxSeq, nil
}

func normalizedConversationObjectRef(raw any) (map[string]any, error) {
	value, ok := raw.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("conversation context object reference is invalid")
	}
	objectTypeRef := stringMapValue(value, "objectTypeRef")
	objectID := stringMapValue(value, "objectId")
	routeID := stringMapValue(value, "routeId")
	if objectTypeRef == "" || objectID == "" || routeID == "" {
		return nil, fmt.Errorf("conversation context object reference is invalid")
	}
	return map[string]any{
		"objectTypeRef": objectTypeRef,
		"objectId":      objectID,
		"routeId":       routeID,
	}, nil
}

func mapInt64Value(values map[string]any, key string) (int64, bool) {
	switch value := values[key].(type) {
	case int64:
		return value, true
	case int:
		return int64(value), true
	case float64:
		converted := int64(value)
		return converted, value == float64(converted)
	default:
		return 0, false
	}
}

var _ application.Resolver = ConversationContextResolver{}
