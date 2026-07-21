package application

import (
	"fmt"

	assistantgenerated "quwoquan_service/services/assistant-service/internal/generated"
)

// AssistantStreamEventType 是 AssistantRun SSE 的唯一公开事件集合。
//
// 内部模型交互、原始推理和工具入参只进入可观测链路，绝不能借由该协议到达用户界面。
type AssistantStreamEventType = assistantgenerated.AssistantStreamEventType

const (
	AssistantStreamEventRunStarted     = assistantgenerated.AssistantStreamEventTypeRunStarted
	AssistantStreamEventProcessReplace = assistantgenerated.AssistantStreamEventTypeProcessReplace
	AssistantStreamEventProcessAppend  = assistantgenerated.AssistantStreamEventTypeProcessAppend
	AssistantStreamEventProcessCommit  = assistantgenerated.AssistantStreamEventTypeProcessCommit
	AssistantStreamEventAnswerDelta    = assistantgenerated.AssistantStreamEventTypeAnswerDelta
	AssistantStreamEventCompleted      = assistantgenerated.AssistantStreamEventTypeCompleted
	AssistantStreamEventFailed         = assistantgenerated.AssistantStreamEventTypeFailed
	AssistantStreamEventCancelled      = assistantgenerated.AssistantStreamEventTypeCancelled
)

func isAssistantStreamEventTypeValid(eventType AssistantStreamEventType) bool {
	switch eventType {
	case AssistantStreamEventRunStarted,
		AssistantStreamEventProcessReplace,
		AssistantStreamEventProcessAppend,
		AssistantStreamEventProcessCommit,
		AssistantStreamEventAnswerDelta,
		AssistantStreamEventCompleted,
		AssistantStreamEventFailed,
		AssistantStreamEventCancelled:
		return true
	default:
		return false
	}
}

func requireAssistantStreamEventType(
	eventType AssistantStreamEventType,
) error {
	if isAssistantStreamEventTypeValid(eventType) {
		return nil
	}
	return fmt.Errorf("unsupported assistant stream event type %q", eventType)
}
