package user_account

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"sync"
	"time"

	rtobs "quwoquan_service/runtime/observability"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

const (
	profileSearchOutboxLease       = 30 * time.Second
	profileSearchOutboxPoll        = time.Second
	profileSearchOutboxInitialWait = time.Second
	profileSearchOutboxMaxBackoff  = time.Minute
)

// UserProfileSearchProjectionPublisher appends the self-contained projection
// fact to the durable User stream. Returning nil means transport append has
// succeeded and the User-owned outbox checkpoint may advance; Search owns the
// provider write and its independent consumer checkpoint.
type UserProfileSearchProjectionPublisher interface {
	PublishUserProfileSearch(
		ctx context.Context,
		event userports.UserProfileSearchOutboxEvent,
	) error
}

type UserProfileSearchOutboxObserver interface {
	RecordDelivery(result string)
	RecordReadiness(ready bool, pending int)
}

// UserProfileSearchOutboxRelay retries the ordinary UserProfile search
// projection indefinitely. Unlike lifecycle streams it has no terminal-drop
// state: an unappended durable event remains a recoverable divergence.
type UserProfileSearchOutboxRelay struct {
	store     userports.UserProfileSearchOutboxStore
	publisher UserProfileSearchProjectionPublisher
	owner     string
	now       func() time.Time
	observer  UserProfileSearchOutboxObserver

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        userports.UserProfileSearchOutboxFailure
	lastFailureEventID string
	hasLastFailure     bool
}

type UserProfileSearchOutboxRelayOption func(*UserProfileSearchOutboxRelay)

func WithUserProfileSearchOutboxObserver(
	observer UserProfileSearchOutboxObserver,
) UserProfileSearchOutboxRelayOption {
	return func(relay *UserProfileSearchOutboxRelay) {
		relay.observer = observer
	}
}

func NewUserProfileSearchOutboxRelay(
	store userports.UserProfileSearchOutboxStore,
	publisher UserProfileSearchProjectionPublisher,
	owner string,
	options ...UserProfileSearchOutboxRelayOption,
) (*UserProfileSearchOutboxRelay, error) {
	if store == nil || publisher == nil || owner == "" {
		return nil, errors.New(
			"UserProfile search outbox relay requires store, publisher and owner",
		)
	}
	relay := &UserProfileSearchOutboxRelay{
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

// RelayOnce advances at most one durable checkpoint. If the process stops after
// ES success but before MarkPublished, the stable ES document ID makes retry
// safe and convergent.
func (relay *UserProfileSearchOutboxRelay) RelayOnce(
	ctx context.Context,
) (didWork bool, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.UserProfileSearchOutboxRelay",
	)
	defer func() { rtobs.EndSpan(span, err) }()

	now := relay.now().UTC()
	event, found, err := relay.store.ClaimPendingOutbox(
		ctx,
		relay.owner,
		now,
		profileSearchOutboxLease,
	)
	if err != nil {
		failure := profileSearchOutboxFailure(
			userports.UserProfileSearchOutboxFailureClaim,
			err,
		)
		relay.recordFailure(now, "", failure)
		return false, newUserProfileSearchOutboxRelayError(failure)
	}
	if !found {
		relay.recordSuccessfulScan(now)
		return false, nil
	}
	if err := relay.publisher.PublishUserProfileSearch(ctx, event); err != nil {
		return relay.handleProjectionFailure(
			ctx,
			event,
			now,
			profileSearchOutboxFailure(
				userports.UserProfileSearchOutboxFailurePublish,
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
		failure := profileSearchOutboxFailure(
			userports.UserProfileSearchOutboxFailurePublishAck,
			err,
		)
		relay.recordDelivery("failed")
		relay.recordFailure(now, event.EventID, failure)
		return true, newUserProfileSearchOutboxRelayError(failure)
	}
	relay.recordDelivery("published")
	relay.recordDelivered(now, event.EventID)
	return true, nil
}

func (relay *UserProfileSearchOutboxRelay) Run(ctx context.Context) {
	ticker := time.NewTicker(profileSearchOutboxPoll)
	defer ticker.Stop()
	for {
		for {
			didWork, err := relay.RelayOnce(ctx)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				failure := userProfileSearchOutboxFailureFromError(err)
				slog.ErrorContext(
					ctx,
					"UserProfile search outbox relay failed",
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

// Healthy requires a recent successful scan and no unresolved relay fault. A
// pending count remains observable but does not suppress readiness by itself:
// active relay backlog is normal while ES is converging.
func (relay *UserProfileSearchOutboxRelay) Healthy(
	ctx context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("UserProfile search outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	now := relay.now().UTC()
	pending, err := relay.store.PendingCount(ctx)
	if err != nil {
		failure := profileSearchOutboxFailure(
			userports.UserProfileSearchOutboxFailureHealthStore,
			err,
		)
		relay.recordReadiness(false, 0)
		return newUserProfileSearchOutboxRelayError(failure)
	}

	relay.healthMu.RLock()
	lastSuccessfulScan := relay.lastSuccessfulScan
	lastFailure := relay.lastFailure
	hasLastFailure := relay.hasLastFailure
	relay.healthMu.RUnlock()

	if lastSuccessfulScan.IsZero() {
		relay.recordReadiness(false, pending)
		return errors.New("UserProfile search outbox relay has not completed a scan")
	}
	if hasLastFailure {
		relay.recordReadiness(false, pending)
		return newUserProfileSearchOutboxRelayError(lastFailure)
	}
	if now.Sub(lastSuccessfulScan) > maxStaleness {
		relay.recordReadiness(false, pending)
		return errors.New("UserProfile search outbox relay heartbeat is stale")
	}
	relay.recordReadiness(true, pending)
	return nil
}

func (relay *UserProfileSearchOutboxRelay) handleProjectionFailure(
	ctx context.Context,
	event userports.UserProfileSearchOutboxEvent,
	now time.Time,
	failure userports.UserProfileSearchOutboxFailure,
) (bool, error) {
	if err := relay.store.MarkFailed(
		ctx,
		event.EventID,
		relay.owner,
		now,
		now.Add(profileSearchOutboxBackoff(event.DeliveryAttempt)),
		failure,
	); err != nil {
		persistFailure := profileSearchOutboxFailure(
			userports.UserProfileSearchOutboxFailureRetryRecord,
			err,
		)
		relay.recordDelivery("failed")
		relay.recordFailure(now, event.EventID, persistFailure)
		return true, newUserProfileSearchOutboxRelayError(persistFailure)
	}
	relay.recordDelivery("failed")
	relay.recordFailure(now, event.EventID, failure)
	return true, newUserProfileSearchOutboxRelayError(failure)
}

func profileSearchOutboxBackoff(attempt int) time.Duration {
	if attempt <= 1 {
		return profileSearchOutboxInitialWait
	}
	backoff := profileSearchOutboxInitialWait
	for current := 1; current < attempt; current++ {
		if backoff >= profileSearchOutboxMaxBackoff/2 {
			return profileSearchOutboxMaxBackoff
		}
		backoff *= 2
	}
	return min(backoff, profileSearchOutboxMaxBackoff)
}

func (relay *UserProfileSearchOutboxRelay) recordDelivery(result string) {
	if relay.observer != nil {
		relay.observer.RecordDelivery(result)
	}
}

func (relay *UserProfileSearchOutboxRelay) recordReadiness(ready bool, pending int) {
	if relay.observer != nil {
		relay.observer.RecordReadiness(ready, pending)
	}
}

func (relay *UserProfileSearchOutboxRelay) recordSuccessfulScan(now time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	if relay.hasLastFailure && relay.lastFailureEventID == "" {
		relay.lastFailure = userports.UserProfileSearchOutboxFailure{}
		relay.hasLastFailure = false
	}
	relay.healthMu.Unlock()
}

func (relay *UserProfileSearchOutboxRelay) recordDelivered(
	now time.Time,
	eventID string,
) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	if !relay.hasLastFailure || relay.lastFailureEventID == eventID {
		relay.lastFailure = userports.UserProfileSearchOutboxFailure{}
		relay.lastFailureEventID = ""
		relay.hasLastFailure = false
	}
	relay.healthMu.Unlock()
}

func (relay *UserProfileSearchOutboxRelay) recordFailure(
	now time.Time,
	eventID string,
	failure userports.UserProfileSearchOutboxFailure,
) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = now
	relay.lastFailure = failure
	relay.lastFailureEventID = eventID
	relay.hasLastFailure = true
	relay.healthMu.Unlock()
}

type userProfileSearchOutboxRelayError struct {
	failure userports.UserProfileSearchOutboxFailure
}

func newUserProfileSearchOutboxRelayError(
	failure userports.UserProfileSearchOutboxFailure,
) error {
	return &userProfileSearchOutboxRelayError{failure: failure}
}

func (err *userProfileSearchOutboxRelayError) Error() string {
	if err == nil {
		return ""
	}
	return "UserProfile search outbox relay failure code=" +
		string(err.failure.Code) + " digest=" + err.failure.Digest
}

func profileSearchOutboxFailure(
	code userports.UserProfileSearchOutboxFailureCode,
	cause error,
) userports.UserProfileSearchOutboxFailure {
	input := string(code)
	if cause != nil {
		input += "\x00" + cause.Error()
	}
	sum := sha256.Sum256([]byte(input))
	return userports.UserProfileSearchOutboxFailure{
		Code:   code,
		Digest: hex.EncodeToString(sum[:]),
	}
}

func userProfileSearchOutboxFailureFromError(
	err error,
) userports.UserProfileSearchOutboxFailure {
	var relayErr *userProfileSearchOutboxRelayError
	if errors.As(err, &relayErr) && relayErr != nil {
		return relayErr.failure
	}
	return profileSearchOutboxFailure(
		userports.UserProfileSearchOutboxFailureUnexpected,
		err,
	)
}
