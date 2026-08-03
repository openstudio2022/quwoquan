package application

import (
	"context"
	"fmt"
	"strings"
	"time"
)

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

func (p *AccountClosureProjector) Apply(ctx context.Context, event AccountClosedEvent) error {
	if strings.TrimSpace(event.AccountID) == "" || len(event.PersonaIDs) == 0 || event.ClosedAt.IsZero() {
		return fmt.Errorf("CreatorRuntimeProfile account closure identity and closedAt are required")
	}
	return p.store.TombstoneForClosedSubjects(ctx, event.PersonaIDs, event.ClosedAt.UTC())
}
