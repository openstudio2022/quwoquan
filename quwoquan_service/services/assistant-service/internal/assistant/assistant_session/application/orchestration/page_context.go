package orchestration

import (
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

func FormatPageContextForPrompt(
	context *assistant.AssistantContextSnapshot,
) string {
	if context == nil {
		return ""
	}
	var b strings.Builder
	b.WriteString("\n当前页面结构化上下文（仅用于定位，不得据此虚构对象正文）：")
	b.WriteString("\n- pageType: ")
	b.WriteString(context.PageType)
	for _, object := range context.PageObjects {
		b.WriteString("\n- object: ")
		b.WriteString(object.ObjectTypeRef)
		b.WriteString(":")
		b.WriteString(object.ObjectID)
	}
	for _, action := range context.UserActions {
		b.WriteString("\n- userAction: ")
		b.WriteString(action.Action)
		if action.ObjectTypeRef != "" && action.ObjectID != "" {
			b.WriteString(" @ ")
			b.WriteString(action.ObjectTypeRef)
			b.WriteString(":")
			b.WriteString(action.ObjectID)
		}
	}
	return b.String()
}
