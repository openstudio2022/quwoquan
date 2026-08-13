package application

import (
	"context"
	"errors"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/domain"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var attemptAppendOutcomes = rtobs.NewEntrypointOutcomeCounter("integration_external_interaction_attempt_append")

type Store interface {
	AppendIfAbsent(context.Context, domain.Fact) (bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, attempt domain.Fact) (created bool, err error) {
	defer func() {
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		attemptAppendOutcomes.WithLabelValues(outcome).Inc()
	}()
	if a == nil || a.store == nil {
		return false, errors.New("external interaction attempt ledger is unavailable")
	}
	canonical, err := domain.NewFact(attempt)
	if err != nil {
		return false, err
	}
	return a.store.AppendIfAbsent(ctx, canonical)
}
