package application

import (
	"context"
	"errors"

	rtobs "quwoquan_service/runtime/observability"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var signalAppendOutcomes = rtobs.NewEntrypointOutcomeCounter("search_recommendation_signal_append")

type Appender struct {
	sink Publisher
}

func NewAppender(sink Publisher) (*Appender, error) {
	if sink == nil {
		return nil, errors.New("RecommendationSignalFact sink is required")
	}
	return &Appender{sink: sink}, nil
}

func (appender *Appender) Append(ctx context.Context, fact Signal) (err error) {
	defer func() {
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		signalAppendOutcomes.WithLabelValues(outcome).Inc()
	}()
	if appender == nil || appender.sink == nil {
		return errors.New("RecommendationSignalFact appender is unavailable")
	}
	if err := fact.Validate(); err != nil {
		return err
	}
	return appender.sink.PublishSearchSignal(ctx, fact)
}
