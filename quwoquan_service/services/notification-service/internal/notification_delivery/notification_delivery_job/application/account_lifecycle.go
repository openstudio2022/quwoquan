package application

import (
	"context"

	"quwoquan_service/runtime/accountrestriction"
)

type AccountClosure struct {
	EventID         string
	SubjectIDs      []string
	NotificationIDs []string
}

type AccountClosureResult struct {
	DeletedJobs             int64
	DeletedRecipientRecords int64
	AnonymizedAuditRecords  int64
}

// AccountLifecycle is NotificationDeliveryJob's object-owned privacy and
// restriction port. Notification orchestration must never open job collections.
type AccountLifecycle interface {
	ApplyRestriction(context.Context, accountrestriction.Event) (int64, error)
	CloseAccount(context.Context, AccountClosure) (AccountClosureResult, error)
}
