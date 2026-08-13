package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtobs "quwoquan_service/runtime/observability"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var creatorProfileProjectionOutcomes = rtobs.NewEntrypointOutcomeCounter("user_creator_runtime_profile_projection")

type AccountClosedEvent struct {
	AccountID  string
	PersonaIDs []string
	ClosedAt   time.Time
}

type AccountClosureStore interface {
	TombstoneForClosedSubjects(context.Context, []string, time.Time) error
}

type AccountClosureProjector struct {
	store AccountClosureStore
}

func NewAccountClosureProjector(store AccountClosureStore) *AccountClosureProjector {
	if store == nil {
		panic("CreatorRuntimeProfile account closure store is required")
	}
	return &AccountClosureProjector{store: store}
}

func (p *AccountClosureProjector) Apply(ctx context.Context, event AccountClosedEvent) (err error) {
	defer func() {
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		creatorProfileProjectionOutcomes.WithLabelValues(outcome).Inc()
	}()
	if strings.TrimSpace(event.AccountID) == "" || len(event.PersonaIDs) == 0 || event.ClosedAt.IsZero() {
		return fmt.Errorf("CreatorRuntimeProfile account closure identity and closedAt are required")
	}
	return p.store.TombstoneForClosedSubjects(ctx, event.PersonaIDs, event.ClosedAt.UTC())
}
