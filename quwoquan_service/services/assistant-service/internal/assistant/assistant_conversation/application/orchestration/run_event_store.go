package orchestration

import (
	"context"

	"quwoquan_service/runtime/streaming"
)

// AssistantRunEventStore 持久化单个 AssistantRun 拥有的有序流事件。
// SSE 重连只按 runId + seq 读取该日志，不重新推导或合成历史事件。
type AssistantRunEventStore interface {
	AppendRunEvent(ctx context.Context, runID string, envelope streaming.Envelope) error
	ListRunEvents(
		ctx context.Context,
		runID string,
		afterSeq uint64,
		limit int,
	) ([]streaming.Envelope, error)
}

func WithAssistantRunEventStore(store AssistantRunEventStore) AssistantServiceOption {
	return func(service *AssistantService) {
		service.runEvents = store
	}
}
