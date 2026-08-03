package followed_subject_visit_state

import (
	"context"
	"fmt"
	"strings"
)

type AccountClosedEvent struct {
	AccountID  string
	PersonaIDs []string
}

type AccountClosureStore interface {
	DeleteForClosedSubjects(context.Context, string, []string) error
}

type AccountClosureProjector struct {
	store AccountClosureStore
}

func NewAccountClosureProjector(store AccountClosureStore) *AccountClosureProjector {
	if store == nil {
		panic("FollowedSubjectVisitState account closure store is required")
	}
	return &AccountClosureProjector{store: store}
}

func (p *AccountClosureProjector) Apply(ctx context.Context, event AccountClosedEvent) error {
	if strings.TrimSpace(event.AccountID) == "" || len(event.PersonaIDs) == 0 {
		return fmt.Errorf("FollowedSubjectVisitState account closure identity is required")
	}
	return p.store.DeleteForClosedSubjects(ctx, event.AccountID, event.PersonaIDs)
}
