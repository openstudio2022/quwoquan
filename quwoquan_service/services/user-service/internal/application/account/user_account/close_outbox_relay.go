package user_account

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	rtobs "quwoquan_service/runtime/observability"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

const (
	closeOutboxLease       = 30 * time.Second
	closeOutboxPoll        = time.Second
	closeOutboxMaxBackoff  = time.Minute
	closeOutboxInitialWait = time.Second
)

// UserAccountEventPublisher 必须先写 durable stream，再返回成功。
type UserAccountEventPublisher interface {
	PublishUserAccountEvent(
		ctx context.Context,
		event accountports.UserAccountOutboxEvent,
		payload map[string]any,
	) error
}

type UserAccountOutboxObserver interface {
	RecordDelivery(result string)
}

// UserAccountOutboxRelay 负责 UserAccount 生命周期事件的至少一次投递。
type UserAccountOutboxRelay struct {
	store     accountports.UserAccountOutboxStore
	publisher UserAccountEventPublisher
	owner     string
	now       func() time.Time
	observer  UserAccountOutboxObserver
}

type UserAccountOutboxRelayOption func(*UserAccountOutboxRelay)

func WithUserAccountOutboxObserver(
	observer UserAccountOutboxObserver,
) UserAccountOutboxRelayOption {
	return func(relay *UserAccountOutboxRelay) {
		relay.observer = observer
	}
}

func NewUserAccountOutboxRelay(
	store accountports.UserAccountOutboxStore,
	publisher UserAccountEventPublisher,
	owner string,
	options ...UserAccountOutboxRelayOption,
) (*UserAccountOutboxRelay, error) {
	if store == nil || publisher == nil || owner == "" {
		return nil, errors.New(
			"UserAccount outbox relay requires store, publisher and owner",
		)
	}
	relay := &UserAccountOutboxRelay{
		store:     store,
		publisher: publisher,
		owner:     owner,
		now:       time.Now,
	}
	for _, option := range options {
		if option != nil {
			option(relay)
		}
	}
	return relay, nil
}

// RelayOnce 投递至多一条记录；返回 didWork 供测试和 drain loop 使用。
func (relay *UserAccountOutboxRelay) RelayOnce(
	ctx context.Context,
) (didWork bool, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.UserAccountOutboxRelay",
	)
	defer func() { rtobs.EndSpan(span, err) }()

	now := relay.now().UTC()
	event, found, err := relay.store.ClaimReady(
		ctx,
		relay.owner,
		now,
		closeOutboxLease,
	)
	if err != nil || !found {
		return false, err
	}
	var payload map[string]any
	if err := json.Unmarshal(event.PayloadJSON, &payload); err != nil {
		markErr := relay.store.MarkFailed(
			ctx,
			event.EventID,
			relay.owner,
			now.Add(closeOutboxBackoff(event.DeliveryAttempt)),
			"decode payload: "+err.Error(),
		)
		relay.recordDelivery("failed")
		return true, errors.Join(err, markErr)
	}
	if !isSupportedUserAccountEvent(event.EventType) {
		err := fmt.Errorf(
			"unsupported UserAccount outbox event %q",
			event.EventType,
		)
		markErr := relay.store.MarkFailed(
			ctx,
			event.EventID,
			relay.owner,
			now.Add(closeOutboxMaxBackoff),
			err.Error(),
		)
		relay.recordDelivery("failed")
		return true, errors.Join(err, markErr)
	}
	if err := relay.publisher.PublishUserAccountEvent(
		ctx,
		event,
		payload,
	); err != nil {
		markErr := relay.store.MarkFailed(
			ctx,
			event.EventID,
			relay.owner,
			now.Add(closeOutboxBackoff(event.DeliveryAttempt)),
			err.Error(),
		)
		relay.recordDelivery("failed")
		return true, errors.Join(err, markErr)
	}
	if err := relay.store.MarkPublished(
		ctx,
		event.EventID,
		relay.owner,
		now,
	); err != nil {
		relay.recordDelivery("failed")
		return true, err
	}
	relay.recordDelivery("published")
	return true, nil
}

func (relay *UserAccountOutboxRelay) Run(ctx context.Context) {
	ticker := time.NewTicker(closeOutboxPoll)
	defer ticker.Stop()
	for {
		for {
			didWork, err := relay.RelayOnce(ctx)
			if err != nil {
				slog.ErrorContext(
					ctx,
					"UserAccount outbox relay failed",
					slog.String("error", err.Error()),
				)
				break
			}
			if !didWork {
				break
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func closeOutboxBackoff(attempt int) time.Duration {
	if attempt <= 1 {
		return closeOutboxInitialWait
	}
	backoff := closeOutboxInitialWait
	for current := 1; current < attempt; current++ {
		if backoff >= closeOutboxMaxBackoff/2 {
			return closeOutboxMaxBackoff
		}
		backoff *= 2
	}
	return min(backoff, closeOutboxMaxBackoff)
}

func (relay *UserAccountOutboxRelay) recordDelivery(result string) {
	if relay.observer != nil {
		relay.observer.RecordDelivery(result)
	}
}

func isSupportedUserAccountEvent(eventType string) bool {
	switch eventType {
	case UserAccountClosedEventName, UserSuspendedEventName, UserRestoredEventName:
		return true
	default:
		return false
	}
}
