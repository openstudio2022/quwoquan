package application

import (
	"context"
	"errors"

	"quwoquan_service/runtime/accountrestriction"
)

var ErrUserAccountRestrictionProjectionConflict = errors.New(
	"content user account restriction projection conflict",
)

type UserAccountRestrictionProjectionResult struct {
	Replayed bool
	Stale    bool
	Terminal bool
	Affected int64
}

// AccountRestrictionProjection is the content-owned application port for the
// reversible UserSuspended/UserRestored read model. Irreversible closure stays
// on the separate account-closure workflow.
type AccountRestrictionProjection interface {
	Apply(
		ctx context.Context,
		event accountrestriction.Event,
	) (UserAccountRestrictionProjectionResult, error)
}
