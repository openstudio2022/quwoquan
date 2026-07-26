package application

import (
	"context"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type Recorder interface {
	ReportScorecards(context.Context, []assistant.Scorecard) (map[string]any, error)
}

type Ingestion struct{ recorder Recorder }

func NewIngestion(recorder Recorder) *Ingestion {
	if recorder == nil {
		panic("assistant scorecard recorder is required")
	}
	return &Ingestion{recorder: recorder}
}

func (s *Ingestion) Append(ctx context.Context, scores []assistant.Scorecard) (map[string]any, error) {
	if len(scores) == 0 {
		return nil, rterr.NewInvalidArgument(rterr.ModuleAssistant, "scorecards 不能为空", "empty scorecards")
	}
	return s.recorder.ReportScorecards(ctx, scores)
}
