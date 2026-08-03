package application

import (
	"context"
	"errors"
)

type Appender struct {
	sink Publisher
}

func NewAppender(sink Publisher) (*Appender, error) {
	if sink == nil {
		return nil, errors.New("RecommendationSignalFact sink is required")
	}
	return &Appender{sink: sink}, nil
}

func (appender *Appender) Append(ctx context.Context, fact Signal) error {
	if appender == nil || appender.sink == nil {
		return errors.New("RecommendationSignalFact appender is unavailable")
	}
	if err := fact.Validate(); err != nil {
		return err
	}
	return appender.sink.PublishSearchSignal(ctx, fact)
}
