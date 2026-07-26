package application

import (
	"context"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type Recorder interface {
	ReportInteractionEvents(context.Context, []assistant.InteractionEvent) (map[string]any, error)
}

type Ingestion struct{ recorder Recorder }

func NewIngestion(recorder Recorder) *Ingestion {
	if recorder == nil {
		panic("assistant interaction event recorder is required")
	}
	return &Ingestion{recorder: recorder}
}

func (s *Ingestion) Append(ctx context.Context, events []assistant.InteractionEvent) (map[string]any, error) {
	if len(events) == 0 {
		return nil, rterr.NewInvalidArgument(rterr.ModuleAssistant, "events 不能为空", "empty interaction events")
	}
	return s.recorder.ReportInteractionEvents(ctx, events)
}
