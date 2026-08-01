package application

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/runtime/accountrestriction"
)

var ErrUserAccountRestrictionProjectionConflict = errors.New(
	"search index account restriction projection conflict",
)

type UserAccountRestrictionProjectionResult struct {
	Replayed bool
	Stale    bool
	Terminal bool
	Affected int64
}

// UserAccountRestrictionProjection owns the reversible visibility filter used
// by SearchIndexView. It must never invoke irreversible request-log cleanup.
type UserAccountRestrictionProjection interface {
	Apply(
		context.Context,
		accountrestriction.Event,
	) (UserAccountRestrictionProjectionResult, error)
}

type SubjectClosure struct {
	EventDigest    string
	AccountID      string
	AccountVersion int64
	ClosedAt       time.Time
}

type SubjectClosureProjection interface {
	FinalizeClosure(context.Context, SubjectClosure) error
}
