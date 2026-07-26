package user_account

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"sync"
	"time"

	rtobs "quwoquan_service/runtime/observability"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
)

const (
	closeOutboxLease                     = 30 * time.Second
	closeOutboxPoll                      = time.Second
	closeOutboxMaxBackoff                = time.Minute
	closeOutboxInitialWait               = time.Second
	closeOutboxMaxDeliveryAttempts       = 8
	closeOutboxTerminalFailureRetention  = 30 * 24 * time.Hour
	closeOutboxTerminalFailurePruneEvery = time.Hour
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
	RecordReadiness(ready bool, terminalFailures int)
}

// UserAccountOutboxRelay 负责 UserAccount 生命周期事件的至少一次投递。
type UserAccountOutboxRelay struct {
	store     accountports.UserAccountOutboxStore
	publisher UserAccountEventPublisher
	owner     string
	now       func() time.Time
	observer  UserAccountOutboxObserver

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        accountports.UserAccountOutboxFailure
	hasLastFailure     bool
	lastTerminalPrune  time.Time
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
	if err := relay.pruneExpiredTerminalFailures(ctx, now); err != nil {
		failure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailureRetentionPrune,
			err,
		)
		relay.recordFailure(now, failure)
		return false, newUserAccountOutboxRelayError(failure)
	}
	event, found, err := relay.store.ClaimReady(
		ctx,
		relay.owner,
		now,
		closeOutboxLease,
	)
	if err != nil {
		failure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailureClaim,
			err,
		)
		relay.recordFailure(now, failure)
		return false, newUserAccountOutboxRelayError(failure)
	}
	if !found {
		relay.recordSuccessfulScan(now)
		return false, nil
	}
	var payload map[string]any
	if err := json.Unmarshal(event.PayloadJSON, &payload); err != nil {
		return relay.markTerminalFailure(
			ctx,
			event,
			now,
			userAccountOutboxFailure(
				accountports.UserAccountOutboxFailurePayloadDecode,
				err,
			),
		)
	}
	if !isSupportedUserAccountEvent(event.EventType) {
		return relay.markTerminalFailure(
			ctx,
			event,
			now,
			userAccountOutboxFailure(
				accountports.UserAccountOutboxFailureUnsupportedType,
				errors.New(event.EventType),
			),
		)
	}
	if err := relay.publisher.PublishUserAccountEvent(
		ctx,
		event,
		payload,
	); err != nil {
		return relay.handlePublishFailure(
			ctx,
			event,
			now,
			userAccountOutboxFailure(
				accountports.UserAccountOutboxFailurePublish,
				err,
			),
		)
	}
	if err := relay.store.MarkPublished(
		ctx,
		event.EventID,
		relay.owner,
		now,
	); err != nil {
		failure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailurePublishAck,
			err,
		)
		relay.recordDelivery("failed")
		relay.recordFailure(now, failure)
		return true, newUserAccountOutboxRelayError(failure)
	}
	relay.recordDelivery("published")
	relay.recordDelivered(now)
	return true, nil
}

func (relay *UserAccountOutboxRelay) Run(ctx context.Context) {
	ticker := time.NewTicker(closeOutboxPoll)
	defer ticker.Stop()
	for {
		for {
			didWork, err := relay.RelayOnce(ctx)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				failure := userAccountOutboxFailureFromError(err)
				slog.ErrorContext(
					ctx,
					"UserAccount outbox relay failed",
					slog.String("failure_code", string(failure.Code)),
					slog.String("failure_digest", failure.Digest),
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

// Healthy is a readiness check: it requires a recent completed scan, no
// unresolved relay fault, and no terminal failure that is blocking per-account
// delivery order. It never starts work or exposes raw dependency errors.
func (relay *UserAccountOutboxRelay) Healthy(
	ctx context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("UserAccount outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}

	now := relay.now().UTC()
	terminalFailures, err := relay.store.TerminalFailureCount(ctx)
	if err != nil {
		failure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailureHealthStore,
			err,
		)
		relay.recordReadiness(false, 0)
		return newUserAccountOutboxRelayError(failure)
	}

	relay.healthMu.RLock()
	lastSuccessfulScan := relay.lastSuccessfulScan
	lastFailure := relay.lastFailure
	hasLastFailure := relay.hasLastFailure
	relay.healthMu.RUnlock()

	if lastSuccessfulScan.IsZero() {
		relay.recordReadiness(false, terminalFailures)
		return errors.New("UserAccount outbox relay has not completed a scan")
	}
	if hasLastFailure {
		relay.recordReadiness(false, terminalFailures)
		return newUserAccountOutboxRelayError(lastFailure)
	}
	if now.Sub(lastSuccessfulScan) > maxStaleness {
		relay.recordReadiness(false, terminalFailures)
		return errors.New("UserAccount outbox relay heartbeat is stale")
	}
	if terminalFailures > 0 {
		relay.recordReadiness(false, terminalFailures)
		return errors.New("UserAccount outbox relay has terminal failures")
	}
	relay.recordReadiness(true, 0)
	return nil
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

func (relay *UserAccountOutboxRelay) recordReadiness(
	ready bool,
	terminalFailures int,
) {
	if relay.observer != nil {
		relay.observer.RecordReadiness(ready, terminalFailures)
	}
}

func (relay *UserAccountOutboxRelay) handlePublishFailure(
	ctx context.Context,
	event accountports.UserAccountOutboxEvent,
	now time.Time,
	failure accountports.UserAccountOutboxFailure,
) (bool, error) {
	if event.DeliveryAttempt >= closeOutboxMaxDeliveryAttempts {
		return relay.markTerminalFailure(ctx, event, now, failure)
	}
	if err := relay.store.MarkFailed(
		ctx,
		event.EventID,
		relay.owner,
		now,
		now.Add(closeOutboxBackoff(event.DeliveryAttempt)),
		failure,
	); err != nil {
		persistFailure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailureRetryRecord,
			err,
		)
		relay.recordDelivery("failed")
		relay.recordFailure(now, persistFailure)
		return true, newUserAccountOutboxRelayError(persistFailure)
	}
	relay.recordDelivery("failed")
	relay.recordFailure(now, failure)
	return true, newUserAccountOutboxRelayError(failure)
}

func (relay *UserAccountOutboxRelay) markTerminalFailure(
	ctx context.Context,
	event accountports.UserAccountOutboxEvent,
	now time.Time,
	failure accountports.UserAccountOutboxFailure,
) (bool, error) {
	if err := relay.store.MarkTerminalFailure(
		ctx,
		event.EventID,
		relay.owner,
		now,
		now.Add(closeOutboxTerminalFailureRetention),
		failure,
	); err != nil {
		persistFailure := userAccountOutboxFailure(
			accountports.UserAccountOutboxFailureTerminalRecord,
			err,
		)
		relay.recordDelivery("failed")
		relay.recordFailure(now, persistFailure)
		return true, newUserAccountOutboxRelayError(persistFailure)
	}
	relay.recordDelivery("terminal")
	relay.recordTerminal(now)
	return true, nil
}

func (relay *UserAccountOutboxRelay) pruneExpiredTerminalFailures(
	ctx context.Context,
	now time.Time,
) error {
	relay.healthMu.RLock()
	lastTerminalPrune := relay.lastTerminalPrune
	relay.healthMu.RUnlock()
	if !lastTerminalPrune.IsZero() &&
		now.Sub(lastTerminalPrune) < closeOutboxTerminalFailurePruneEvery {
		return nil
	}
	if _, err := relay.store.PruneExpiredTerminalFailures(ctx, now); err != nil {
		return err
	}
	relay.healthMu.Lock()
	if relay.lastTerminalPrune.IsZero() || now.After(relay.lastTerminalPrune) {
		relay.lastTerminalPrune = now
	}
	relay.healthMu.Unlock()
	return nil
}

func (relay *UserAccountOutboxRelay) recordSuccessfulScan(now time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	relay.healthMu.Unlock()
}

func (relay *UserAccountOutboxRelay) recordDelivered(now time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	relay.lastFailure = accountports.UserAccountOutboxFailure{}
	relay.hasLastFailure = false
	relay.healthMu.Unlock()
}

func (relay *UserAccountOutboxRelay) recordTerminal(now time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	relay.lastFailure = accountports.UserAccountOutboxFailure{}
	relay.hasLastFailure = false
	relay.healthMu.Unlock()
}

func (relay *UserAccountOutboxRelay) recordFailure(
	now time.Time,
	failure accountports.UserAccountOutboxFailure,
) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	relay.lastFailure = failure
	relay.hasLastFailure = true
	relay.healthMu.Unlock()
}

type userAccountOutboxRelayError struct {
	failure accountports.UserAccountOutboxFailure
}

func newUserAccountOutboxRelayError(
	failure accountports.UserAccountOutboxFailure,
) error {
	return &userAccountOutboxRelayError{failure: failure}
}

func (err *userAccountOutboxRelayError) Error() string {
	if err == nil {
		return ""
	}
	return "UserAccount outbox relay failure code=" + string(err.failure.Code) +
		" digest=" + err.failure.Digest
}

func userAccountOutboxFailure(
	code accountports.UserAccountOutboxFailureCode,
	cause error,
) accountports.UserAccountOutboxFailure {
	input := string(code)
	if cause != nil {
		input += "\x00" + cause.Error()
	}
	sum := sha256.Sum256([]byte(input))
	return accountports.UserAccountOutboxFailure{
		Code:   code,
		Digest: hex.EncodeToString(sum[:]),
	}
}

func userAccountOutboxFailureFromError(
	err error,
) accountports.UserAccountOutboxFailure {
	var relayErr *userAccountOutboxRelayError
	if errors.As(err, &relayErr) && relayErr != nil {
		return relayErr.failure
	}
	return userAccountOutboxFailure(
		accountports.UserAccountOutboxFailureUnexpected,
		err,
	)
}

func isSupportedUserAccountEvent(eventType string) bool {
	switch eventType {
	case UserAccountClosedEventName,
		UserSuspendedEventName,
		UserRestoredEventName,
		userevent.UserProfileTagsChanged:
		return true
	default:
		return false
	}
}
