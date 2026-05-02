package reliabletask

import (
	"context"
	"time"
)

type NotificationFanout func(ctx context.Context, notification NotificationOutboxRecord, recipientID string) (int64, error)

type NotificationWorker struct {
	Store      Store
	EventTypes []string
	WorkerID   string
	LeaseTTL   time.Duration
	Retry      RetryPolicy
	Now        func() time.Time
}

func (w NotificationWorker) ProcessOne(ctx context.Context, fanout NotificationFanout) (bool, error) {
	if w.Store == nil {
		return false, ErrStoreRequired
	}
	if fanout == nil {
		return false, nil
	}
	now := time.Now().UTC()
	if w.Now != nil {
		now = w.Now().UTC()
	}
	leaseTTL := w.LeaseTTL
	if leaseTTL <= 0 {
		leaseTTL = 30 * time.Second
	}
	notification, err := w.Store.ClaimNotification(ctx, w.EventTypes, w.WorkerID, leaseTTL, now)
	if err != nil || notification == nil {
		return false, err
	}
	if err := w.Store.EnsureRecipientLedgers(ctx, notification.NotificationID, notification.EventType, notification.RecipientIDs); err != nil {
		return false, w.retry(ctx, *notification, err)
	}
	recipients, err := w.Store.ListPendingRecipients(ctx, notification.NotificationID)
	if err != nil {
		return false, w.retry(ctx, *notification, err)
	}
	hadFailure := false
	for _, recipient := range recipients {
		seq, err := fanout(ctx, *notification, recipient.RecipientID)
		if err != nil {
			hadFailure = true
			_ = w.Store.MarkRecipientFailed(ctx, notification.NotificationID, recipient.RecipientID, RuntimeFailure{
				Code:    "RELIABLETASK.NOTIFICATION.fanout_failed",
				Message: err.Error(),
			})
			continue
		}
		if err := w.Store.MarkRecipientDelivered(ctx, notification.NotificationID, recipient.RecipientID, seq); err != nil {
			hadFailure = true
		}
	}
	if hadFailure {
		return true, w.retry(ctx, *notification, errNotificationPartialFailure)
	}
	if err := w.Store.CompleteNotification(ctx, notification.NotificationID, notification.LeaseToken); err != nil {
		return false, err
	}
	return true, nil
}

func (w NotificationWorker) retry(ctx context.Context, notification NotificationOutboxRecord, err error) error {
	policy := w.Retry
	if policy.MaxAttempts <= 0 {
		policy = DefaultRetryPolicy()
	}
	now := time.Now().UTC()
	if w.Now != nil {
		now = w.Now().UTC()
	}
	return w.Store.RetryNotification(ctx, notification.NotificationID, notification.LeaseToken, RuntimeFailure{
		Code:    "RELIABLETASK.NOTIFICATION.retry",
		Message: err.Error(),
		Attributes: map[string]string{
			"aggregateId": notification.AggregateID,
			"eventType":   notification.EventType,
		},
	}, policy, now)
}
